from typing import Any, Dict, List, Optional, Tuple
import asyncio
from tqdm import tqdm
from .llm import retry_llm
from .prompt import format_qa_judge_prompt


def _parse_int(s: str) -> Optional[int]:
    try:
        s = s.strip()
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None
        v = int(digits)
        if v < 0:
            v = 0
        if v > 100:
            v = 100
        return v
    except Exception:
        return None


async def judge_one(
    item: Dict[str, Any], judge_cfg: Dict[str, Any], en_mode: bool
) -> Tuple[Optional[int], Dict[str, Any], Dict[str, int]]:
    q = str(item.get("问题") or "")
    rubric = str(item.get("得分比例") or "")
    ans = str(item.get("模型回答") or "")
    prompt = format_qa_judge_prompt(q, rubric, ans, en_mode=en_mode)

    def run():
        r, c, u = retry_llm(
            api_key=judge_cfg.get("api_key"),
            base_url=judge_cfg.get("base_url"),
            prompt=prompt,
            model=judge_cfg.get("model_name"),
            max_tokens=judge_cfg.get("max_tokens") or 1024,
            temperature=judge_cfg.get("temperature") or 0.0,
            top_p=judge_cfg.get("top_p") or 0.0,
            enable_thinking=bool(judge_cfg.get("enable_thinking")),
            max_retries=judge_cfg.get("max_retries") or 3,
            timeout=judge_cfg.get("timeout") or 60.0,
        )
        return r or "", c or "", u

    r, c, u = await asyncio.to_thread(run)
    usage_dict = {}
    if u:
        usage_dict = {
            "completion_tokens": u.completion_tokens,
            "prompt_tokens": u.prompt_tokens,
            "total_tokens": u.total_tokens,
        }
    score = _parse_int(c)
    detail = {
        "提示词": prompt,
        "思考过程": r,
        "模型回答": c,
        "模型回答_int": score,
    }
    return score, detail, usage_dict


async def judge_items(
    items: List[Dict[str, Any]], judges: List[Dict[str, Any]], en_mode: bool = False
) -> Tuple[List[Optional[float]], Dict[str, Dict[str, int]]]:
    if not judges:
        return [None for _ in items], {}
    sem = asyncio.Semaphore(int(judges[0].get("concurrency") or 2))

    total_tasks = len(items) * len(judges)
    pbar = tqdm(total=total_tasks, desc="Judging QA", unit="task")

    judge_usages = {
        j["model_name"]: {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
        for j in judges
    }

    async def score_item(it: Dict[str, Any]) -> Optional[float]:
        scores: List[int] = []

        async def run_one_judge(j: Dict[str, Any]):
            async with sem:
                s, _detail, u = await judge_one(it, j, en_mode=en_mode)
                pbar.update(1)
                return s, u, j["model_name"]

        j_tasks = [run_one_judge(j) for j in judges]
        results = await asyncio.gather(*j_tasks)

        for s, u, model_name in results:
            if s is not None:
                scores.append(s)
            if u:
                judge_usages[model_name]["completion_tokens"] += u.get(
                    "completion_tokens", 0
                )
                judge_usages[model_name]["prompt_tokens"] += u.get("prompt_tokens", 0)
                judge_usages[model_name]["total_tokens"] += u.get("total_tokens", 0)

        if not scores:
            return None
        return sum(scores) / len(scores)

    tasks = [score_item(it) for it in items]
    res = await asyncio.gather(*tasks)
    pbar.close()
    return res, judge_usages
