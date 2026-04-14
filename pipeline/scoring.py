import os
import json
import csv
import asyncio
from typing import Any, Dict, List, Tuple, Optional
from tqdm import tqdm
from .judger import judge_one


def _read_all_json(root: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = os.path.join(root, "raw")
    for r, _d, files in os.walk(base):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            fp = os.path.join(r, fn)
            rel = os.path.normpath(os.path.relpath(fp, base))
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for it in data:
                        if isinstance(it, dict):
                            x = dict(it)
                            x["__source_relpath"] = rel
                            out.append(x)
            except Exception:
                continue
    return out


def _letters(s: str) -> List[str]:
    s = (s or "").upper()
    return [ch for ch in s if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]


def _is_correct_single(item: Dict[str, Any]) -> Optional[bool]:
    gt = str(item.get("答案") or "").strip().upper()
    pred = str(item.get("模型回答") or "").strip().upper()
    if not gt or not pred:
        return None
    return gt == pred


def _is_correct_multi(item: Dict[str, Any]) -> Optional[bool]:
    gt = set(_letters(str(item.get("答案") or "")))
    pred = set(_letters(str(item.get("模型回答") or "")))
    if not gt or not pred:
        return None
    return gt == pred


def _is_correct_judge(item: Dict[str, Any]) -> Optional[bool]:
    gt = str(item.get("答案") or "").strip()
    pred = str(item.get("模型回答") or "").strip()
    if not gt or not pred:
        return None

    def norm(x: str) -> str:
        x = x.strip()
        if x in ["正确", "对", "是", "true", "True"]:
            return "正确"
        if x in ["错误", "错", "否", "false", "False"]:
            return "错误"
        return x

    return norm(gt) == norm(pred)


def _acc(vals: List[Optional[bool]]) -> float:
    xs = [1.0 if v else 0.0 for v in vals if v is not None]
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


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


def _empty_usage() -> Dict[str, int]:
    return {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}


def _norm_usage(u: Any) -> Dict[str, int]:
    if not isinstance(u, dict):
        return {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
    return {
        "completion_tokens": int((u or {}).get("completion_tokens", 0) or 0),
        "prompt_tokens": int((u or {}).get("prompt_tokens", 0) or 0),
        "total_tokens": int((u or {}).get("total_tokens", 0) or 0),
    }


def _merge_usage(base: Dict[str, int], extra: Any) -> Dict[str, int]:
    x = _norm_usage(extra)
    base["completion_tokens"] += x["completion_tokens"]
    base["prompt_tokens"] += x["prompt_tokens"]
    base["total_tokens"] += x["total_tokens"]
    return base


async def _judge_items_cached(
    items: List[Dict[str, Any]],
    judges: List[Dict[str, Any]],
    result_root: str,
    en_mode: bool,
) -> Tuple[List[Optional[float]], Dict[str, Dict[str, int]]]:
    """
    对一批题目 items 进行“带磁盘缓存”的评审打分，并返回每题的聚合分数与 token 用量统计。

    缓存设计：
    - items 来自多个 raw json 文件，函数使用每条样本的 "__source_relpath" 将评审结果按来源文件分片保存；
    - 每个来源文件对应一个缓存文件：{result_root}/judge/{__source_relpath}；
    - 缓存文件内容是一个 list[dict]，每个 dict 对应一个题目（用 id 索引），并包含各个 judge 模型的评审详情。

    并发设计：
    - 对每个 judge 模型单独设置信号量（Semaphore），限制该模型的并发请求数（默认 2，可由 judges[i]["concurrency"] 覆盖）；
    - 只对“缓存缺失”的 (item, model) 创建异步任务，已完成的直接复用缓存并跳过调用。

    返回：
    - scores：与 items 等长的列表；每条为多个 judge 给出的 "模型回答_int" 的平均值（若缺失则为 None）
    - judge_usages：按 model_name 汇总的 token 用量（prompt/completion/total）
    """
    if not judges:
        return [None for _ in items], {}

    # 按模型统计 token 用量。每次调用 judge_one 返回的 usage 会累计到对应模型。
    judge_usages = {
        j["model_name"]: {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
        for j in judges
    }

    # 每个模型独立限流：避免某一个模型在大批量任务中被打爆或触发限速。
    sem_by_model = {
        j["model_name"]: asyncio.Semaphore(max(1, int(j.get("concurrency") or 2)))
        for j in judges
    }

    # 进程内的文件级缓存：避免同一个 judge_fp 反复读写磁盘。
    # 结构：{judge_fp: {"data": list[dict], "by_id": {id: entry}, "dirty": bool}}
    file_cache: Dict[str, Dict[str, Any]] = {}

    def load_file_cache(judge_fp: str) -> Dict[str, Any]:
        # 读取并解析某个缓存文件；同一进程内重复请求直接命中内存缓存。
        if judge_fp in file_cache:
            return file_cache[judge_fp]
        data: List[Dict[str, Any]] = []
        if os.path.exists(judge_fp) and os.path.getsize(judge_fp) > 0:
            try:
                with open(judge_fp, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    data = [x for x in loaded if isinstance(x, dict)]
            except Exception:
                data = []
        # 使用字符串化的 id 建索引，便于从 items 的 id 直接定位缓存条目。
        by_id = {str(x.get("id")): x for x in data if x.get("id") is not None}
        file_cache[judge_fp] = {"data": data, "by_id": by_id, "dirty": False}
        return file_cache[judge_fp]

    async def run_one_missing(
        it: Dict[str, Any], j: Dict[str, Any], entry: Dict[str, Any]
    ):
        # 对缓存缺失的一次评审调用：更新 entry 中该模型的 detail 与 usage，并累加全局用量。
        async with sem_by_model[j["model_name"]]:
            s, detail, u = await judge_one(it, j, en_mode=en_mode)
            normalized_usage = _norm_usage(u)
            entry[j["model_name"]] = detail
            # usage_details：按模型保存 usage 的细分信息，便于后续回溯与增量合并。
            usage_details = entry.get("usage_details")
            if not isinstance(usage_details, dict):
                usage_details = {}
            usage_details[j["model_name"]] = normalized_usage
            entry["usage_details"] = usage_details

            # usage：将 usage_details 中所有模型的 usage 汇总成一个总用量。
            total_usage = _empty_usage()
            for model_usage in usage_details.values():
                _merge_usage(total_usage, model_usage)
            entry["usage"] = total_usage

            _merge_usage(judge_usages[j["model_name"]], normalized_usage)
            return s

    # missing_tasks：仅为缺失的 (item, model) 创建任务；避免重复评审。
    missing_tasks: List[asyncio.Task] = []
    # missing_by_rel / total_by_rel：按来源文件统计缺失数与总数，用于提示哪些文件已评完可跳过。
    missing_by_rel: Dict[str, int] = {}
    total_by_rel: Dict[str, int] = {}

    for it in items:
        # "__source_relpath" 来自 _read_all_json；这里会做安全化，防止生成越界路径。
        rel = _safe_rel(str(it.get("__source_relpath") or ""))
        total_by_rel[rel] = total_by_rel.get(rel, 0) + 1
        judge_fp = os.path.join(result_root, "judge", rel)
        cache = load_file_cache(judge_fp)
        qid = str(it.get("id"))
        entry = cache["by_id"].get(qid)
        if entry is None:
            # 缓存文件里没有该题：创建一个基础 entry。
            # 排除一些运行期字段，避免把中间态/冗余字段写入缓存导致体积膨胀。
            entry = {
                k: v
                for k, v in it.items()
                if k
                not in (
                    "__source_relpath",
                    "usage",
                    "usage_details",
                    "candidate_usage",
                    "summary_usage",
                    "heavy_think_content",
                )
            }
            cache["data"].append(entry)
            cache["by_id"][qid] = entry
            cache["dirty"] = True

        # 兼容历史缓存结构：将 entry 中旧字段规范化为 usage_details，并确保只保留本次 judges 列表中的模型。
        usage_details = entry.get("usage_details")
        if not isinstance(usage_details, dict):
            usage_details = {}
        valid_models = {j["model_name"] for j in judges}
        usage_details = {
            k: _norm_usage(v)
            for k, v in usage_details.items()
            if k in valid_models and isinstance(v, dict)
        }
        changed = False
        for j in judges:
            model_name = j["model_name"]
            if model_name in usage_details and isinstance(usage_details[model_name], dict):
                usage_details[model_name] = _norm_usage(usage_details[model_name])
                continue
            # 部分旧缓存会把 usage 放在 entry[model_name]["usage"]；这里迁移/同步到 usage_details。
            model_detail = entry.get(model_name)
            if isinstance(model_detail, dict) and isinstance(model_detail.get("usage"), dict):
                usage_details[model_name] = _norm_usage(model_detail.get("usage"))
                changed = True
        if changed or "usage_details" not in entry:
            entry["usage_details"] = usage_details
            cache["dirty"] = True

        # 重新计算总用量 entry["usage"]，保证与 usage_details 一致（用于展示或后续汇总）。
        total_usage = _empty_usage()
        for model_usage in usage_details.values():
            _merge_usage(total_usage, model_usage)
        if entry.get("usage") != total_usage:
            entry["usage"] = total_usage
            cache["dirty"] = True

        for j in judges:
            model_name = j["model_name"]
            cached = entry.get(model_name)
            cached_score = None
            if isinstance(cached, dict):
                # 评审结果的核心字段：judge_one 产出的 detail 里应包含 "模型回答_int"（整数分/档位）。
                cached_score = cached.get("模型回答_int")
            if isinstance(cached_score, int):
                continue
            # 缓存缺失：创建异步任务补齐该 (item, model) 的评审详情。
            cache["dirty"] = True
            missing_by_rel[rel] = missing_by_rel.get(rel, 0) + 1
            missing_tasks.append(asyncio.create_task(run_one_missing(it, j, entry)))

    for rel, n in total_by_rel.items():
        if missing_by_rel.get(rel, 0) == 0:
            print(f"Skipping judge {rel}, already done ({n} items).")

    if missing_tasks:
        pbar = tqdm(total=len(missing_tasks), desc="Judging QA (cached)", unit="task")

        async def track(t: asyncio.Task):
            try:
                return await t
            finally:
                pbar.update(1)

        # 所有缺失任务并发执行（每个模型仍受 sem_by_model 限流），并用 track 更新进度条。
        await asyncio.gather(*[track(t) for t in missing_tasks])
        pbar.close()

    # 将发生变更的缓存文件写回磁盘：只写 dirty 的，减少 IO。
    for judge_fp, cache in file_cache.items():
        if not cache.get("dirty"):
            continue
        os.makedirs(os.path.dirname(judge_fp), exist_ok=True)
        with open(judge_fp, "w", encoding="utf-8") as f:
            json.dump(cache["data"], f, ensure_ascii=False, indent=2)

    # 生成最终 scores：每题取所有 judges 的 "模型回答_int" 做均值。
    # 注意：这里不会触发评审调用，只读取缓存（本次已补齐缺失并写回）。
    scores: List[Optional[float]] = []
    for it in items:
        rel = _safe_rel(str(it.get("__source_relpath") or ""))
        judge_fp = os.path.join(result_root, "judge", rel)
        cache = load_file_cache(judge_fp)
        qid = str(it.get("id"))
        entry = cache["by_id"].get(qid) or {}
        xs: List[int] = []
        for j in judges:
            d = entry.get(j["model_name"])
            if isinstance(d, dict) and isinstance(d.get("模型回答_int"), int):
                xs.append(int(d.get("模型回答_int")))
        if xs:
            scores.append(sum(xs) / len(xs))
        else:
            scores.append(None)

    return scores, judge_usages


async def compute_scores(
    result_root: str,
    judges: List[Dict[str, Any]],
    weights: Dict[str, Any],
    en_mode: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, Any]]:
    items = _read_all_json(result_root)
    security: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    quality: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    general: Dict[str, List[Dict[str, Any]]] = {}
    special: Dict[str, Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]]] = {}

    # Initialize usage stats
    total_judge_usage = {}
    for j in judges:
        total_judge_usage[j["model_name"]] = {
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "total_tokens": 0,
        }

    def merge_usage(usage_map: Dict[str, Dict[str, int]]):
        for model, usage in usage_map.items():
            if model not in total_judge_usage:
                total_judge_usage[model] = {
                    "completion_tokens": 0,
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                }
            total_judge_usage[model]["completion_tokens"] += usage.get(
                "completion_tokens", 0
            )
            total_judge_usage[model]["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_judge_usage[model]["total_tokens"] += usage.get("total_tokens", 0)

    for it in items:
        t = str(it.get("题型"))
        domain = str(it.get("领域") or "")
        if domain == "安全":
            atype = str(it.get("安全类型") or "")
            aspec = str(it.get("安全专项") or "")
            security.setdefault(atype, {}).setdefault(aspec, []).append(it)
        elif domain == "质量":
            dep = str(it.get("分部工程") or "")
            sub = str(it.get("子分部工程") or "")
            itemx = str(it.get("分项工程") or "")
            quality.setdefault(dep, {}).setdefault(sub, {}).setdefault(
                itemx, []
            ).append(it)
        elif domain in ["医疗", "机场"]:
            if domain == "机场":
                # For Airport, map "专项" to "专业类别", others empty
                val = it.get("专项")
                if val is None:
                    print(
                        f"DEBUG: Missing '专项' for item id={it.get('id')}, keys={it.keys()}"
                    )
                cat = str(val or "")
                spec = ""
                sub_spec = ""
                detail = ""
            else:
                cat = str(it.get("专业类别") or "")
                spec = str(it.get("专业专项") or "")
                sub_spec = str(it.get("子专业专项") or "")
                detail = str(it.get("细分子专业") or "")

            special.setdefault(domain, {}).setdefault(cat, {}).setdefault(
                spec, {}
            ).setdefault(sub_spec, {}).setdefault(detail, []).append(it)
        else:
            blk = str(it.get("板块类型") or "")
            if blk:
                general.setdefault(blk, []).append(it)

    qa_score_by_key: Dict[Tuple[str, str], Optional[float]] = {}
    if judges:
        qa_all = [
            x
            for x in items
            if str(x.get("题型")) == "问答题" and x.get("id") is not None
        ]
        if qa_all:
            qs, usages = await _judge_items_cached(
                qa_all, judges, result_root=result_root, en_mode=en_mode
            )
            merge_usage(usages)
            for it, s in zip(qa_all, qs):
                rel = _safe_rel(str(it.get("__source_relpath") or ""))
                qa_score_by_key[(rel, str(it.get("id")))] = s

    def qa_score(it: Dict[str, Any]) -> Optional[float]:
        qid = it.get("id")
        if qid is None:
            return None
        rel = _safe_rel(str(it.get("__source_relpath") or ""))
        return qa_score_by_key.get((rel, str(qid)))

    w_pro = weights["专业技术"]
    w_gen = weights["通用综合"]
    w_spec = weights["特色场景"]

    rows: List[Dict[str, Any]] = []

    sec_type_scores: List[float] = []
    for atype, spec_map in security.items():
        spec_scores: List[float] = []
        qa_type_items: List[Dict[str, Any]] = []
        for aspec, items_s in spec_map.items():
            if aspec != "/":
                sc = _acc(
                    [
                        _is_correct_single(x)
                        for x in items_s
                        if str(x.get("题型")) == "单选题"
                    ]
                )
                mc = _acc(
                    [
                        _is_correct_multi(x)
                        for x in items_s
                        if str(x.get("题型")) == "多选题"
                    ]
                )
                jc = _acc(
                    [
                        _is_correct_judge(x)
                        for x in items_s
                        if str(x.get("题型")) == "判断题"
                    ]
                )
                score = w_pro["单选"] * sc + w_pro["多选"] * mc + w_pro["判断"] * jc
                spec_scores.append(score)
                rows.append(
                    {
                        "部分": "1-1安全",
                        "层级": "安全专项",
                        "名称": f"{atype}-{aspec}",
                        "分数": round(score, 2),
                    }
                )
            else:
                qa_type_items.extend(
                    [x for x in items_s if str(x.get("题型")) == "问答题"]
                )
        qa_scores = []
        if qa_type_items and qa_score_by_key:
            qa_scores = [
                x for x in [qa_score(it) for it in qa_type_items] if x is not None
            ]
        spec_mean = _mean(spec_scores)
        qa_mean = _mean(qa_scores)
        type_score = spec_mean * ((100 - w_pro["问答"]) / 100.0) + qa_mean * (
            w_pro["问答"] / 100.0
        )
        sec_type_scores.append(type_score)
        rows.append(
            {
                "部分": "1-1安全",
                "层级": "安全类型",
                "名称": atype,
                "分数": round(type_score, 2),
            }
        )

    sec_score = _mean(sec_type_scores)
    if sec_type_scores:
        rows.append(
            {
                "部分": "1-1安全",
                "层级": "整体",
                "名称": "安全",
                "分数": round(sec_score, 2),
            }
        )

    qual_dep_scores: List[float] = []
    for dep, sub_map in quality.items():
        sub_scores: List[float] = []
        for sub, item_map in sub_map.items():
            item_scores: List[float] = []
            qa_sub_items: List[Dict[str, Any]] = []
            for itemx, items_q in item_map.items():
                if itemx != "/":
                    sc = _acc(
                        [
                            _is_correct_single(x)
                            for x in items_q
                            if str(x.get("题型")) == "单选题"
                        ]
                    )
                    mc = _acc(
                        [
                            _is_correct_multi(x)
                            for x in items_q
                            if str(x.get("题型")) == "多选题"
                        ]
                    )
                    jc = _acc(
                        [
                            _is_correct_judge(x)
                            for x in items_q
                            if str(x.get("题型")) == "判断题"
                        ]
                    )
                    score = w_pro["单选"] * sc + w_pro["多选"] * mc + w_pro["判断"] * jc
                    item_scores.append(score)
                    rows.append(
                        {
                            "部分": "1-2质量",
                            "层级": "分项工程",
                            "名称": f"{dep}-{sub}-{itemx}",
                            "分数": round(score, 2),
                        }
                    )
                else:
                    qa_sub_items.extend(
                        [x for x in items_q if str(x.get("题型")) == "问答题"]
                    )
            qa_scores = []
            if qa_sub_items and qa_score_by_key:
                qa_scores = [
                    x for x in [qa_score(it) for it in qa_sub_items] if x is not None
                ]
            item_mean = _mean(item_scores)
            qa_mean = _mean(qa_scores)
            sub_score = item_mean * ((100 - w_pro["问答"]) / 100.0) + qa_mean * (
                w_pro["问答"] / 100.0
            )
            sub_scores.append(sub_score)
            rows.append(
                {
                    "部分": "1-2质量",
                    "层级": "子分部工程",
                    "名称": f"{dep}-{sub}",
                    "分数": round(sub_score, 2),
                }
            )
        dep_score = _mean(sub_scores)
        qual_dep_scores.append(dep_score)
        rows.append(
            {
                "部分": "1-2质量",
                "层级": "分部工程",
                "名称": dep,
                "分数": round(dep_score, 2),
            }
        )

    qual_score = _mean(qual_dep_scores)
    if qual_dep_scores:
        rows.append(
            {
                "部分": "1-2质量",
                "层级": "整体",
                "名称": "质量",
                "分数": round(qual_score, 2),
            }
        )

    gen_blk_scores_weighted = 0.0
    for blk, items_g in general.items():
        sc = _acc(
            [_is_correct_single(x) for x in items_g if str(x.get("题型")) == "单选题"]
        )
        mc = _acc(
            [_is_correct_multi(x) for x in items_g if str(x.get("题型")) == "多选题"]
        )
        qa_items = [x for x in items_g if str(x.get("题型")) == "问答题"]
        qa_scores = []
        if qa_items and qa_score_by_key:
            qa_scores = [x for x in [qa_score(it) for it in qa_items] if x is not None]
        qa_mean = _mean(qa_scores)
        blk_score = (
            w_gen["单选"] * sc + w_gen["多选"] * mc + w_gen["问答"] / 100.0 * qa_mean
        )

        blk_weight_key = f"{blk}权重"
        blk_w = weights.get(blk_weight_key, 0.0)
        gen_blk_scores_weighted += blk_score * blk_w

        rows.append(
            {
                "部分": "2通用综合",
                "层级": "板块类型",
                "名称": blk,
                "分数": round(blk_score, 2),
            }
        )

    gen_score = gen_blk_scores_weighted / 100.0
    if general:
        rows.append(
            {
                "部分": "2通用综合",
                "层级": "整体",
                "名称": "通用综合",
                "分数": round(gen_score, 2),
            }
        )

    spec_domain_scores_weighted = 0.0
    for domain, cat_map in special.items():
        cat_scores: List[float] = []
        for cat, spec_map in cat_map.items():
            spec_scores: List[float] = []
            for spec, sub_spec_map in spec_map.items():
                sub_spec_scores: List[float] = []
                for sub_spec, detail_map in sub_spec_map.items():
                    detail_scores: List[float] = []
                    for detail, items_d in detail_map.items():
                        # Calculate score
                        if domain == "机场":
                            # Special case: Airport items are grouped by "专项"
                            pass

                        sc = _acc(
                            [
                                _is_correct_single(x)
                                for x in items_d
                                if str(x.get("题型")) == "单选题"
                            ]
                        )
                        mc = _acc(
                            [
                                _is_correct_multi(x)
                                for x in items_d
                                if str(x.get("题型")) == "多选题"
                            ]
                        )
                        jc = _acc(
                            [
                                _is_correct_judge(x)
                                for x in items_d
                                if str(x.get("题型")) == "判断题"
                            ]
                        )
                        score = (
                            w_spec["单选"] * sc
                            + w_spec["多选"] * mc
                            + w_spec["判断"] * jc
                        )

                        detail_scores.append(score)
                        if detail != "":
                            rows.append(
                                {
                                    "部分": "3特色场景",
                                    "层级": "细分子专业",
                                    "名称": f"{domain}-{cat}-{spec}-{sub_spec}-{detail}",
                                    "分数": round(score, 2),
                                }
                            )

                    sub_spec_score = _mean(detail_scores)
                    sub_spec_scores.append(sub_spec_score)
                    if sub_spec != "":
                        rows.append(
                            {
                                "部分": "3特色场景",
                                "层级": "子专业专项",
                                "名称": f"{domain}-{cat}-{spec}-{sub_spec}",
                                "分数": round(sub_spec_score, 2),
                            }
                        )

                spec_score = _mean(sub_spec_scores)
                spec_scores.append(spec_score)
                if spec != "":
                    rows.append(
                        {
                            "部分": "3特色场景",
                            "层级": "专业专项",
                            "名称": f"{domain}-{cat}-{spec}",
                            "分数": round(spec_score, 2),
                        }
                    )

            cat_score = _mean(spec_scores)
            cat_scores.append(cat_score)
            rows.append(
                {
                    "部分": "3特色场景",
                    "层级": "专业类别",
                    "名称": f"{domain}-{cat}"
                    if domain != "机场"
                    else f"{domain}-{cat}",
                    "分数": round(cat_score, 2),
                }
            )

        domain_score = _mean(cat_scores)
        w_domain = weights.get(f"{domain}权重", 0.0)
        spec_domain_scores_weighted += domain_score * w_domain

        rows.append(
            {
                "部分": "3特色场景",
                "层级": "领域",
                "名称": domain,
                "分数": round(domain_score, 2),
            }
        )

    spec_total_score = spec_domain_scores_weighted / 100.0
    if special:
        rows.append(
            {
                "部分": "3特色场景",
                "层级": "整体",
                "名称": "特色场景",
                "分数": round(spec_total_score, 2),
            }
        )

    pro_total = 0.0
    if sec_type_scores or qual_dep_scores:
        pro_total = sec_score * (
            (100 - int(weights["安全权重"])) / 100.0
        ) + qual_score * ((100 - int(weights["质量权重"])) / 100.0)
        rows.append(
            {
                "部分": "1专业技术",
                "层级": "整体",
                "名称": "专业技术",
                "分数": round(pro_total, 2),
            }
        )

    total_score = (
        pro_total * weights["专业技术权重"] / 100.0
        + gen_score * weights["通用综合权重"] / 100.0
        + spec_total_score * weights["特色场景权重"] / 100.0
    )

    rows.append(
        {
            "部分": "整体",
            "层级": "总分",
            "名称": "总分",
            "分数": round(total_score, 2),
        }
    )

    totals: Dict[str, float] = {
        "安全": sec_score,
        "质量": qual_score,
        "专业技术": pro_total,
        "通用综合": gen_score,
        "特色场景": spec_total_score,
        "总分": total_score,
    }

    return rows, totals, total_judge_usage


def write_csv(rows: List[Dict[str, Any]], out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    headers = ["部分", "层级", "名称", "分数"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out_path
