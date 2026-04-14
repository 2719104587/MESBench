import os
import json
import asyncio
from typing import Any, Dict, List, Tuple
from tqdm import tqdm
from .llm import async_retry_llm
from .prompt import format_question_prompt, format_summary_prompt


def _build_prompt(item: Dict[str, Any], en_mode: bool) -> str:
    return format_question_prompt(item, en_mode=en_mode)


def _empty_usage() -> Dict[str, int]:
    return {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}


def _merge_usage(base: Dict[str, int], extra: Dict[str, Any]) -> Dict[str, int]:
    base["completion_tokens"] += int((extra or {}).get("completion_tokens", 0) or 0)
    base["prompt_tokens"] += int((extra or {}).get("prompt_tokens", 0) or 0)
    base["total_tokens"] += int((extra or {}).get("total_tokens", 0) or 0)
    return base


def _safe_rel(rel: str) -> str:
    rel = (rel or "").replace("\\", os.sep)
    rel = os.path.normpath(rel)
    if not rel:
        return "unknown.json"
    if os.path.isabs(rel):
        return os.path.basename(rel)
    if rel == ".." or rel.startswith(".." + os.sep):
        return os.path.basename(rel)
    return rel


async def _eval_one(
    item: Dict[str, Any],
    model_cfg: Dict[str, Any],
    en_mode: bool,
    prompt_override: str = None,
) -> Dict[str, Any]:
    prompt = prompt_override if prompt_override else _build_prompt(item, en_mode=en_mode)

    r, c, u = await async_retry_llm(
        api_key=model_cfg.get("api_key"),
        base_url=model_cfg.get("base_url"),
        prompt=prompt,
        model=model_cfg.get("model_name"),
        max_tokens=model_cfg.get("max_tokens") or 32768,
        temperature=model_cfg.get("temperature") or 0.0,
        top_p=model_cfg.get("top_p") or 0.0,
        top_k=model_cfg.get("top_k"),
        enable_thinking=bool(model_cfg.get("enable_thinking")),
        stream=bool(model_cfg.get("stream", True)),
        max_retries=model_cfg.get("max_retries") or 3,
        timeout=model_cfg.get("timeout") or 60.0,
    )
    r = r or ""
    c = c or ""
    out = dict(item)
    out["提示词"] = prompt
    out["思考过程"] = r
    out["模型回答"] = c

    usage_dict = _empty_usage()
    if u:
        usage_dict = _merge_usage(
            _empty_usage(),
            {
                "completion_tokens": u.completion_tokens,
                "prompt_tokens": u.prompt_tokens,
                "total_tokens": u.total_tokens,
            },
        )
    out["usage"] = usage_dict

    return out


async def evaluate(
    questions: List[Dict[str, Any]],
    model_cfg: Dict[str, Any],
    result_root: str,
    en_mode: bool = False,
) -> Tuple[List[str], Dict[str, Any]]:
    os.makedirs(result_root, exist_ok=True)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for rec in questions:
        rel = (
            _safe_rel(rec.get("rel") or "")
            if rec.get("rel")
            else _safe_rel(os.path.basename(rec.get("src") or "unknown.json"))
        )
        groups.setdefault(rel, []).append(rec["item"])

    is_heavy = bool(model_cfg.get("heavy_think", False))
    h_think_times = max(1, int(model_cfg.get("h_think_times") or 1))
    summary_cfg = model_cfg.get("summary_model")
    if is_heavy and not summary_cfg:
        summary_cfg = model_cfg

    if not is_heavy:
        sem = asyncio.Semaphore(int(model_cfg.get("concurrency") or 4))
        total_items = len(questions)
        pbar = tqdm(total=total_items, desc="Evaluating", unit="q")
        total_usage = _empty_usage()

        async def run_group(rel: str, items: List[Dict[str, Any]]):
            out_path = os.path.join(result_root, "raw", rel)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                try:
                    with open(out_path, "r", encoding="utf-8") as f:
                        existing_results = json.load(f)
                    if isinstance(existing_results, list) and len(existing_results) > 0:
                        print(
                            f"Skipping {rel}, already done ({len(existing_results)} items)."
                        )
                        pbar.update(len(items))
                        for x in existing_results:
                            if isinstance(x, dict):
                                _merge_usage(total_usage, x.get("usage", {}))
                        return out_path
                except Exception:
                    pass

            async def run_item(it: Dict[str, Any]):
                async with sem:
                    res = await _eval_one(it, model_cfg, en_mode=en_mode)
                pbar.update(1)
                return res

            tasks = [run_item(it) for it in items]
            results = await asyncio.gather(*tasks)

            for res in results:
                _merge_usage(total_usage, res.get("usage", {}))

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            return out_path

        tasks = [run_group(rel, items) for rel, items in groups.items()]
        paths = await asyncio.gather(*tasks)
        pbar.close()
        return list(paths), total_usage

    def is_valid_heavy_record(x: Any, it: Dict[str, Any]) -> bool:
        if not isinstance(x, dict):
            return False
        heavy_think_content = x.get("heavy_think_content")
        if not isinstance(heavy_think_content, list) or len(heavy_think_content) != h_think_times:
            return False
        if not isinstance(x.get("usage"), dict):
            return False
        usage_details = x.get("usage_details")
        if not isinstance(usage_details, dict):
            return False
        candidate_details = usage_details.get("candidate_model")
        summary_detail = usage_details.get("summary_model")
        if not isinstance(candidate_details, list) or len(candidate_details) != h_think_times:
            return False
        if not isinstance(summary_detail, dict) or summary_detail.get("role") != "summary_model":
            return False
        candidate_answers = []
        for c in heavy_think_content:
            if not isinstance(c, dict):
                continue
            think = str((c or {}).get("思考过程", "") or "").strip()
            ans = str((c or {}).get("模型回答", "") or "").strip()
            candidate_answers.append((think + "\n" + ans).strip())
        expected_prompt = format_summary_prompt(it, candidate_answers, en_mode=en_mode)
        if x.get("提示词") != expected_prompt:
            return False
        return True

    def is_valid_heavy_file(data: Any, items: List[Dict[str, Any]]) -> bool:
        if not isinstance(data, list) or len(data) != len(items):
            return False
        return all(is_valid_heavy_record(rec, it) for rec, it in zip(data, items))

    total_usage: Dict[str, Any] = _empty_usage()
    total_usage["candidate_usage"] = _empty_usage()
    total_usage["summary_usage"] = _empty_usage()

    to_run: List[Dict[str, Any]] = []
    results_by_rel: Dict[str, List[Any]] = {}
    paths: List[str] = []

    for rel, items in groups.items():
        out_path = os.path.join(result_root, "raw", rel)
        paths.append(out_path)
        results_by_rel[rel] = [None for _ in items]
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if is_valid_heavy_file(existing, items):
                    for idx, rec in enumerate(existing):
                        results_by_rel[rel][idx] = rec
                        _merge_usage(total_usage, rec.get("usage", {}))
                        _merge_usage(total_usage["candidate_usage"], rec.get("candidate_usage", {}))
                        _merge_usage(total_usage["summary_usage"], rec.get("summary_usage", {}))
                    continue
            except Exception:
                pass

        for idx, it in enumerate(items):
            to_run.append({"rel": rel, "idx": idx, "item": it})

    if not to_run:
        return paths, total_usage

    cand_sem = asyncio.Semaphore(int(model_cfg.get("concurrency") or 4))
    pbar1 = tqdm(
        total=len(to_run) * h_think_times,
        desc="Evaluating Round-1 Candidate",
        unit="call",
    )

    stage1_map: Dict[Tuple[str, int], List[Any]] = {}
    for e in to_run:
        stage1_map[(e["rel"], e["idx"])] = [None for _ in range(h_think_times)]

    async def run_candidate(rel: str, idx: int, it: Dict[str, Any], k: int):
        async with cand_sem:
            res = await _eval_one(it, model_cfg, en_mode=en_mode)
        pbar1.update(1)
        return rel, idx, k, res

    cand_tasks = [
        asyncio.create_task(run_candidate(e["rel"], e["idx"], e["item"], k))
        for e in to_run
        for k in range(h_think_times)
    ]
    cand_results = await asyncio.gather(*cand_tasks)
    for rel, idx, k, res in cand_results:
        stage1_map[(rel, idx)][k] = res

    pbar1.close()

    summary_sem = asyncio.Semaphore(
        int((summary_cfg or {}).get("concurrency") or model_cfg.get("concurrency") or 4)
    )
    pbar2 = tqdm(total=len(to_run), desc="Evaluating Round-2 Summary", unit="call")

    async def run_summary(rel: str, idx: int, it: Dict[str, Any]):
        stage1_results = stage1_map[(rel, idx)]
        candidate_answers = []
        for r in stage1_results:
            if not isinstance(r, dict):
                continue
            think = str((r or {}).get("思考过程", "") or "").strip()
            ans = str((r or {}).get("模型回答", "") or "").strip()
            candidate_answers.append((think + "\n" + ans).strip())
        summary_prompt = format_summary_prompt(it, candidate_answers, en_mode=en_mode)
        async with summary_sem:
            res = await _eval_one(it, summary_cfg, en_mode=en_mode, prompt_override=summary_prompt)
        pbar2.update(1)
        return rel, idx, res

    sum_tasks = [
        asyncio.create_task(run_summary(e["rel"], e["idx"], e["item"])) for e in to_run
    ]
    sum_results = await asyncio.gather(*sum_tasks)
    pbar2.close()

    for rel, idx, summary_res in sum_results:
        stage1_results = stage1_map[(rel, idx)]

        candidate_total_usage = _empty_usage()
        candidate_usage_details: List[Dict[str, Any]] = []
        heavy_think_content: List[Dict[str, Any]] = []
        for j, stage_res in enumerate(stage1_results, start=1):
            call_usage = _merge_usage(_empty_usage(), (stage_res or {}).get("usage", {}))
            _merge_usage(candidate_total_usage, call_usage)
            candidate_usage_details.append(
                {
                    "role": "candidate_model",
                    "index": j,
                    "completion_tokens": call_usage["completion_tokens"],
                    "prompt_tokens": call_usage["prompt_tokens"],
                    "total_tokens": call_usage["total_tokens"],
                }
            )
            heavy_think_content.append(
                {
                    "提示词": (stage_res or {}).get("提示词", ""),
                    "思考过程": (stage_res or {}).get("思考过程", ""),
                    "模型回答": (stage_res or {}).get("模型回答", ""),
                }
            )

        summary_usage = _merge_usage(_empty_usage(), (summary_res or {}).get("usage", {}))
        total_call_usage = _merge_usage(
            _merge_usage(_empty_usage(), candidate_total_usage),
            summary_usage,
        )

        out = dict(summary_res)
        out["heavy_think_content"] = heavy_think_content
        out["usage"] = total_call_usage
        out["usage_details"] = {
            "candidate_model": candidate_usage_details,
            "summary_model": {
                "role": "summary_model",
                "index": 1,
                "completion_tokens": summary_usage["completion_tokens"],
                "prompt_tokens": summary_usage["prompt_tokens"],
                "total_tokens": summary_usage["total_tokens"],
            },
        }
        out["candidate_usage"] = candidate_total_usage
        out["summary_usage"] = summary_usage

        results_by_rel[rel][idx] = out
        _merge_usage(total_usage, out.get("usage", {}))
        _merge_usage(total_usage["candidate_usage"], out.get("candidate_usage", {}))
        _merge_usage(total_usage["summary_usage"], out.get("summary_usage", {}))

    for rel, results in results_by_rel.items():
        if any(x is None for x in results):
            continue
        out_path = os.path.join(result_root, "raw", rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    return paths, total_usage
