import os
import json
import asyncio
from typing import Any, Dict, List, Tuple
from tqdm import tqdm
from .llm import retry_llm
from .prompt import single_choice_prompt, multi_choice_prompt, judge_prompt, qa_prompt
from .dataset_loader import DataRoot


def _build_prompt(item: Dict[str, Any]) -> str:
    t = str(item.get("题型"))
    q = str(item.get("问题"))
    if t == "单选题":
        return single_choice_prompt.format(q)
    if t == "多选题":
        return multi_choice_prompt.format(q)
    if t == "判断题":
        return judge_prompt.format(q)
    return qa_prompt.format(q)


def _rel_from_data(src: str) -> str:
    try:
        return os.path.relpath(src, DataRoot)
    except Exception:
        return os.path.basename(src)


async def _eval_one(item: Dict[str, Any], model_cfg: Dict[str, Any]) -> Dict[str, Any]:
    prompt = _build_prompt(item)

    def run() -> Tuple[str, str, Any]:
        r, c, u = retry_llm(
            api_key=model_cfg.get("api_key"),
            base_url=model_cfg.get("base_url"),
            prompt=prompt,
            model=model_cfg.get("model_name"),
            max_tokens=model_cfg.get("max_tokens") or 32768,
            temperature=model_cfg.get("temperature") or 0.0,
            top_p=model_cfg.get("top_p") or 0.0,
            enable_thinking=bool(model_cfg.get("enable_thinking")),
            max_retries=model_cfg.get("max_retries") or 3,
            timeout=model_cfg.get("timeout") or 60.0,
        )
        return r or "", c or "", u

    r, c, u = await asyncio.to_thread(run)
    out = dict(item)
    out["提示词"] = prompt
    out["思考过程"] = r
    out["模型回答"] = c

    usage_dict = {}
    if u:
        usage_dict = {
            "completion_tokens": u.completion_tokens,
            "prompt_tokens": u.prompt_tokens,
            "total_tokens": u.total_tokens,
        }
    out["usage"] = usage_dict

    return out


async def evaluate(
    questions: List[Dict[str, Any]], model_cfg: Dict[str, Any], result_root: str
) -> Tuple[List[str], Dict[str, int]]:
    os.makedirs(result_root, exist_ok=True)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for rec in questions:
        rel = _rel_from_data(rec["src"]) if rec.get("src") else "unknown.json"
        groups.setdefault(rel, []).append(rec["item"])

    sem = asyncio.Semaphore(int(model_cfg.get("concurrency") or 4))

    total_items = len(questions)
    pbar = tqdm(total=total_items, desc="Evaluating", unit="q")

    total_usage = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}

    async def run_group(rel: str, items: List[Dict[str, Any]]):
        out_path = os.path.join(result_root, "raw", rel)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            # If file exists and is not empty, check if it's valid JSON
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    existing_results = json.load(f)
                if isinstance(existing_results, list) and len(existing_results) > 0:
                    # Check if the existing results cover all items in this group
                    # For simplicity, we assume if the count matches or is close, it's done.
                    # A more robust check would verify IDs or questions.
                    # Here we just trust the file if it exists and has content.
                    print(
                        f"Skipping {rel}, already done ({len(existing_results)} items)."
                    )
                    pbar.update(
                        len(items)
                    )  # Update progress bar even for skipped items
                    return out_path
            except Exception:
                pass  # If invalid, re-run

        async def run_item(it: Dict[str, Any]):
            async with sem:
                res = await _eval_one(it, model_cfg)
                pbar.update(1)
                return res

        tasks = [run_item(it) for it in items]
        results = await asyncio.gather(*tasks)

        for res in results:
            u = res.get("usage", {})
            total_usage["completion_tokens"] += u.get("completion_tokens", 0)
            total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            total_usage["total_tokens"] += u.get("total_tokens", 0)

        # out_path is already defined above
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return out_path

    tasks = [run_group(rel, items) for rel, items in groups.items()]
    paths = await asyncio.gather(*tasks)
    pbar.close()
    return list(paths), total_usage
