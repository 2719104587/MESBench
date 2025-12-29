import os
from typing import Any, Dict, List


def _pick(rows: List[Dict[str, Any]], part: str, level: str) -> List[Dict[str, Any]]:
    return [r for r in rows if r.get("部分") == part and r.get("层级") == level]


def _top_bottom(
    rows: List[Dict[str, Any]], k: int = 3
) -> (List[Dict[str, Any]], List[Dict[str, Any]]):
    s = sorted(rows, key=lambda x: float(x.get("分数") or 0.0))
    return s[-k:] if len(s) >= k else s, s[:k]


def build_report(
    rows: List[Dict[str, Any]],
    totals: Dict[str, float],
    eval_usage: Dict[str, int],
    judge_usage: Dict[str, Dict[str, int]],
    eval_model_name: str,
) -> str:
    lines: List[str] = []
    lines.append("# 模型测评分析报告")
    lines.append("")
    lines.append("## 总览")
    for k in ["总分", "专业技术", "安全", "质量", "通用综合", "特色场景"]:
        v = totals.get(k)
        lines.append(f"- {k}：{round(v, 2) if v is not None else 0.0}")

    lines.append("")
    lines.append("## Token 消耗统计")
    lines.append(f"### 待评测模型 ({eval_model_name})")
    lines.append(f"- Completion Tokens: {eval_usage.get('completion_tokens', 0)}")
    lines.append(f"- Prompt Tokens: {eval_usage.get('prompt_tokens', 0)}")
    lines.append(f"- Total Tokens: {eval_usage.get('total_tokens', 0)}")

    lines.append("")
    lines.append("### 裁判模型")
    for model_name, usage in judge_usage.items():
        lines.append(f"#### {model_name}")
        lines.append(f"- Completion Tokens: {usage.get('completion_tokens', 0)}")
        lines.append(f"- Prompt Tokens: {usage.get('prompt_tokens', 0)}")
        lines.append(f"- Total Tokens: {usage.get('total_tokens', 0)}")

    lines.append("")
    lines.append("## 强项与弱项")

    sec_types = _pick(rows, "1-1安全", "安全类型")
    if sec_types:
        top, bottom = _top_bottom(sec_types)
        lines.append("### 安全类型")
        lines.append(
            "- 强项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in reversed(top)])
        )
        lines.append(
            "- 弱项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in bottom])
        )

    qual_subs = _pick(rows, "1-2质量", "子分部工程")
    if qual_subs:
        top, bottom = _top_bottom(qual_subs)
        lines.append("### 质量子分部工程")
        lines.append(
            "- 强项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in reversed(top)])
        )
        lines.append(
            "- 弱项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in bottom])
        )

    gen_blks = _pick(rows, "2通用综合", "板块类型")
    if gen_blks:
        top, bottom = _top_bottom(gen_blks)
        lines.append("### 通用综合板块类型")
        lines.append(
            "- 强项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in reversed(top)])
        )
        lines.append(
            "- 弱项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in bottom])
        )

    spec_cats = _pick(rows, "3特色场景", "专业类别")
    if spec_cats:
        top, bottom = _top_bottom(spec_cats)
        lines.append("### 特色场景专业类别")
        lines.append(
            "- 强项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in reversed(top)])
        )
        lines.append(
            "- 弱项：" + ", ".join([f"{r['名称']}({r['分数']})" for r in bottom])
        )

    return "\n".join(lines)


def write_report(text: str, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path
