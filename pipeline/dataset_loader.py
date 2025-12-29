import os
import json
from typing import Any, Dict, List, Optional
from collections import Counter
from loguru import logger


Root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DataRoot = os.path.join(Root, "data")


def _read_lines(path: Optional[str]) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f.readlines() if x.strip()]


def _list_json_files(base: str) -> List[str]:
    out: List[str] = []
    for r, _d, files in os.walk(base):
        for fn in files:
            if fn.endswith(".json"):
                out.append(os.path.join(r, fn))
    return out


def _load_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_security(item: Dict[str, Any], parts: List[str]) -> bool:
    if len(parts) == 1:
        return True
    if len(parts) >= 2 and parts[1] != "安全":
        return False
    if len(parts) >= 3 and str(item.get("安全类型")) != parts[2]:
        return False
    if len(parts) >= 4 and str(item.get("安全专项")) != parts[3]:
        return False
    return True


def _match_quality(item: Dict[str, Any], parts: List[str]) -> bool:
    if len(parts) == 1:
        return True
    if len(parts) >= 2 and parts[1] != "质量":
        return False
    if len(parts) >= 3 and str(item.get("分部工程")) != parts[2]:
        return False
    if len(parts) >= 4 and str(item.get("子分部工程")) != parts[3]:
        return False
    if len(parts) >= 5 and str(item.get("分项工程")) != parts[4]:
        return False
    return True


def _match_general(item: Dict[str, Any], parts: List[str]) -> bool:
    if len(parts) == 1:
        return True
    if len(parts) >= 2 and str(item.get("板块类型")) != parts[1]:
        return False
    return True


def _match_special(item: Dict[str, Any], parts: List[str]) -> bool:
    if len(parts) == 1:
        return True
    
    domain = str(item.get("领域"))
    if len(parts) >= 2 and domain != parts[1]:
        return False
        
    if domain == "机场":
        if len(parts) >= 3 and str(item.get("专项")) != parts[2]:
            return False
        return True
        
    if len(parts) >= 3 and str(item.get("专业类别")) != parts[2]:
        return False
    if len(parts) >= 4 and str(item.get("专业专项")) != parts[3]:
        return False
    if len(parts) >= 5 and str(item.get("子专业专项")) != parts[4]:
        return False
    if len(parts) >= 6 and str(item.get("细分子专业")) != parts[5]:
        return False
    return True


def parse_selection_file(path: Optional[str]) -> List[Dict[str, Any]]:
    lines = _read_lines(path)
    if not lines:
        return [{"root": "全部"}]
    sels: List[Dict[str, Any]] = []
    for line in lines:
        parts = [p.strip() for p in line.split("-") if p.strip()]
        if not parts:
            continue
        sels.append({"parts": parts})
    return sels


def load_questions(selections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    files = _list_json_files(DataRoot)
    out: List[Dict[str, Any]] = []

    # Initialize counters for logging
    selection_stats = {id(s): Counter() for s in selections}

    if not selections or (len(selections) == 1 and selections[0].get("root") == "全部"):
        total_stats = Counter()
        for fp in files:
            try:
                items = _load_json(fp)
            except Exception:
                continue
            for it in items:
                out.append({"src": fp, "item": it})
                total_stats[str(it.get("题型", "未知"))] += 1

        final_stats = dict(total_stats)
        final_stats["总题数"] = sum(total_stats.values())
        logger.info(f"Subtask: 全部 | Stats: {final_stats}")
        return out

    for fp in files:
        try:
            items = _load_json(fp)
        except Exception:
            continue
        for it in items:
            for s in selections:
                parts = s.get("parts", [])
                if not parts:
                    continue
                p0 = parts[0]
                domain = str(it.get("领域") or it.get("工程类别") or "")

                matched = False
                if "专业技术" in p0:
                    if domain == "安全" and _match_security(it, parts):
                        matched = True
                    elif domain == "质量" and _match_quality(it, parts):
                        matched = True
                elif "通用综合" in p0:
                    if _match_general(it, parts):
                        matched = True
                elif "特色场景" in p0:
                    if _match_special(it, parts):
                        matched = True

                if matched:
                    out.append({"src": fp, "item": it})
                    selection_stats[id(s)][str(it.get("题型", "未知"))] += 1
                    break

    for s in selections:
        parts_str = "-".join(s.get("parts", []))
        stats = selection_stats.get(id(s))
        if stats:
            final_stats = dict(stats)
            final_stats["总题数"] = sum(stats.values())
            logger.info(f"Subtask: {parts_str} | Stats: {final_stats}")
        else:
            logger.warning(f"Subtask: {parts_str} | No matching questions found.")

    return out
