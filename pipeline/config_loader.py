import os
from typing import Any, Dict, List
import yaml


def _get(d: Dict[str, Any], key: str, default: Any) -> Any:
    return d[key] if key in d and d[key] is not None else default


def load_config(path: str) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                cfg = yaml.safe_load(text) or {}

    candidate_raw = cfg.get("candidate_model", {}) or {}
    judges_raw = cfg.get("judges", []) or []

    candidate_model = {
        "api_key": _get(candidate_raw, "api_key", None),
        "base_url": _get(candidate_raw, "base_url", None),
        "model_name": _get(candidate_raw, "model_name", None),
        "max_tokens": _get(candidate_raw, "max_tokens", 32768),
        "temperature": _get(candidate_raw, "temperature", None),
        "top_p": _get(candidate_raw, "top_p", None),
        "enable_thinking": _get(candidate_raw, "enable_thinking", False),
        "max_retries": _get(candidate_raw, "max_retries", 3),
        "concurrency": _get(candidate_raw, "concurrency", 4),
    }

    judges: List[Dict[str, Any]] = []
    for j in judges_raw:
        j = j or {}
        judges.append(
            {
                "api_key": _get(j, "api_key", None),
                "base_url": _get(j, "base_url", None),
                "model_name": _get(j, "model_name", None),
                "max_tokens": _get(j, "max_tokens", 32768),
                "temperature": _get(j, "temperature", None),
                "top_p": _get(j, "top_p", None),
                "enable_thinking": _get(j, "enable_thinking", False),
                "max_retries": _get(j, "max_retries", 3),
                "concurrency": _get(j, "concurrency", 2),
            }
        )

    datasets_config_path = _get(cfg, "datasets_config_path", None)
    module_1_path = _get(cfg, "module_1_path", os.path.join(".", "data", "1专业技术"))
    module_2_path = _get(cfg, "module_2_path", os.path.join(".", "data", "2通用综合"))
    module_3_path = _get(cfg, "module_3_path", os.path.join(".", "data", "3特色场景"))
    en_mode = bool(_get(cfg, "en_mode", False))
    result_output_path = _get(cfg, "result_output_path", os.path.join("results"))

    weights_raw = cfg.get("weights", {}) or {}
    weights = {
        "专业技术": {
            "单选": int(_get(weights_raw.get("专业技术", {}) or {}, "单选", 40)),
            "多选": int(_get(weights_raw.get("专业技术", {}) or {}, "多选", 40)),
            "判断": int(_get(weights_raw.get("专业技术", {}) or {}, "判断", 20)),
            "问答": int(_get(weights_raw.get("专业技术", {}) or {}, "问答", 30)),
        },
        "通用综合": {
            "单选": int(_get(weights_raw.get("通用综合", {}) or {}, "单选", 40)),
            "多选": int(_get(weights_raw.get("通用综合", {}) or {}, "多选", 40)),
            "问答": int(_get(weights_raw.get("通用综合", {}) or {}, "问答", 20)),
        },
        "特色场景": {
            "单选": int(_get(weights_raw.get("特色场景", {}) or {}, "单选", 40)),
            "多选": int(_get(weights_raw.get("特色场景", {}) or {}, "多选", 40)),
            "判断": int(_get(weights_raw.get("特色场景", {}) or {}, "判断", 20)),
            "问答": int(_get(weights_raw.get("特色场景", {}) or {}, "问答", 30)),
        },
        "安全权重": int(_get(weights_raw, "安全权重", 50)),
        "质量权重": int(_get(weights_raw, "质量权重", 50)),
        "基础理论权重": int(_get(weights_raw, "基础理论权重", 25)),
        "合同管理权重": int(_get(weights_raw, "合同管理权重", 25)),
        "投资控制权重": int(_get(weights_raw, "投资控制权重", 25)),
        "进度控制权重": int(_get(weights_raw, "进度控制权重", 25)),
        "医疗权重": int(_get(weights_raw, "医疗权重", 50)),
        "机场权重": int(_get(weights_raw, "机场权重", 50)),
        "专业技术权重": int(_get(weights_raw, "专业技术权重", 40)),
        "通用综合权重": int(_get(weights_raw, "通用综合权重", 40)),
        "特色场景权重": int(_get(weights_raw, "特色场景权重", 20)),
    }

    return {
        "candidate_model": candidate_model,
        "judges": judges,
        "datasets_config_path": datasets_config_path,
        "module_1_path": module_1_path,
        "module_2_path": module_2_path,
        "module_3_path": module_3_path,
        "en_mode": en_mode,
        "result_output_path": result_output_path,
        "weights": weights,
    }
