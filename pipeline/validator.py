
import os
import json
from collections import defaultdict, Counter
from typing import Dict, Any, List
from loguru import logger
from pipeline.dataset_loader import _list_json_files, _load_json

def validate_model(model_config: Dict[str, Any]):
    """
    Validates the model configuration.
    """
    if not model_config:
        return False, "Model config is empty"
    if not model_config.get("model_name"):
        return False, "model_name is missing"
    return True, ""

def validate_dataset(data_root: str, frame_root: str):
    logger.info("Starting dataset validation...")
    
    # 1. Load all data into memory for efficient querying
    all_items = []
    files = _list_json_files(data_root)
    for fp in files:
        try:
            items = _load_json(fp)
            for item in items:
                all_items.append(item)
        except Exception as e:
            logger.error(f"Failed to load file {fp}: {e}")

    logger.info(f"Loaded {len(all_items)} items for validation.")

    # Helper to filter items
    def filter_items(**kwargs):
        subset = []
        for item in all_items:
            match = True
            for k, v in kwargs.items():
                # Handle keys that might have different names in data vs query
                item_val = str(item.get(k) or "")
                # Special handling for domain which can be "领域" or "工程类别"
                if k == "domain":
                    item_val = str(item.get("领域") or item.get("工程类别") or "")
                
                if item_val != v:
                    match = False
                    break
            if match:
                subset.append(item)
        return subset

    # Helper to count types
    def count_types(items):
        counts = Counter()
        for item in items:
            q_type = str(item.get("题型", "未知"))
            counts[q_type] += 1
        return counts

    # --- Rule 1: 1-1 Safety ---
    frame_path = os.path.join(frame_root, "1专业技术", "1-1安全框架.json")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'r', encoding='utf-8') as f:
                frame_data = json.load(f)
            
            # Structure: {"安全": { "SafetyType": { "SafetySpecial": [...] } }}
            security_root = frame_data.get("安全", {})
            for s_type_key, s_type_val in security_root.items():
                # Strip suffix like (安全类型)
                s_type = s_type_key.split("(")[0]
                
                # Check Essay/QA for Safety Type
                type_items = filter_items(domain="安全", 安全类型=s_type)
                type_counts = count_types(type_items)
                if type_counts.get("问答题", 0) < 1:
                    logger.error(f"[Rule 1] 1-1安全: 安全类型 '{s_type}' 下缺少问答题 (当前: {type_counts.get('问答题', 0)})")

                if isinstance(s_type_val, dict):
                    for s_special_key in s_type_val.keys():
                         # Strip suffix like (安全专项)
                        s_special = s_special_key.split("(")[0]
                        
                        # Check Single/Multi/Judge for Safety Special
                        special_items = filter_items(domain="安全", 安全类型=s_type, 安全专项=s_special)
                        special_counts = count_types(special_items)
                        
                        if special_counts.get("单选题", 0) < 1:
                            logger.error(f"[Rule 1] 1-1安全: 安全类型 '{s_type}' - 安全专项 '{s_special}' 下缺少单选题")
                        if special_counts.get("多选题", 0) < 1:
                            logger.error(f"[Rule 1] 1-1安全: 安全类型 '{s_type}' - 安全专项 '{s_special}' 下缺少多选题")
                        if special_counts.get("判断题", 0) < 1:
                            logger.error(f"[Rule 1] 1-1安全: 安全类型 '{s_type}' - 安全专项 '{s_special}' 下缺少判断题")
        except Exception as e:
            logger.error(f"Error processing Rule 1: {e}")
    else:
        logger.warning(f"Frame file not found: {frame_path}")

    # --- Rule 2: 1-2 Quality ---
    frame_path = os.path.join(frame_root, "1专业技术", "1-2质量框架.json")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'r', encoding='utf-8') as f:
                frame_data = json.load(f)
            
            # Structure: {"质量": { "Division": { "SubDivision": { "SubItem": [...] } } }}
            quality_root = frame_data.get("质量", {})
            for div_key, div_val in quality_root.items():
                division = div_key.split("(")[0]
                
                if isinstance(div_val, dict):
                    for sub_div_key, sub_div_val in div_val.items():
                        sub_division = sub_div_key.split("(")[0]
                        
                        # Check Essay/QA for SubDivision
                        sub_div_items = filter_items(domain="质量", 分部工程=division, 子分部工程=sub_division)
                        sub_div_counts = count_types(sub_div_items)
                        if sub_div_counts.get("问答题", 0) < 1:
                            logger.error(f"[Rule 2] 1-2质量: 分部 '{division}' - 子分部 '{sub_division}' 下缺少问答题")

                        if isinstance(sub_div_val, dict):
                            for sub_item_key in sub_div_val.keys():
                                sub_item = sub_item_key.split("(")[0]
                                
                                # Check Single/Multi/Judge for SubItem
                                # Note: sub_item might be "/" in data? Need to check if data uses "/" or empty string
                                # Assuming data matches frame name.
                                sub_item_items = filter_items(domain="质量", 分部工程=division, 子分部工程=sub_division, 分项工程=sub_item)
                                sub_item_counts = count_types(sub_item_items)
                                
                                if sub_item_counts.get("单选题", 0) < 1:
                                    logger.error(f"[Rule 2] 1-2质量: 子分部 '{sub_division}' - 分项 '{sub_item}' 下缺少单选题")
                                if sub_item_counts.get("多选题", 0) < 1:
                                    logger.error(f"[Rule 2] 1-2质量: 子分部 '{sub_division}' - 分项 '{sub_item}' 下缺少多选题")
                                if sub_item_counts.get("判断题", 0) < 1:
                                    logger.error(f"[Rule 2] 1-2质量: 子分部 '{sub_division}' - 分项 '{sub_item}' 下缺少判断题")
        except Exception as e:
            logger.error(f"Error processing Rule 2: {e}")
    else:
        logger.warning(f"Frame file not found: {frame_path}")

    # --- Rule 3: 2-1 General ---
    frame_path = os.path.join(frame_root, "2通用综合", "2-1通用部分框架.json")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'r', encoding='utf-8') as f:
                frame_data = json.load(f)
            
            # Structure: {"房屋建筑工程(工程类别)": { "BlockType": [...] }}
            # Iterate root keys (usually one)
            for root_key, root_val in frame_data.items():
                domain = root_key.split("(")[0] # e.g. "房屋建筑工程"
                
                if isinstance(root_val, dict):
                    for block_key in root_val.keys():
                        block_type = block_key.split("(")[0]
                        
                        # Check Total >= 1
                        block_items = filter_items(domain=domain, 板块类型=block_type)
                        if len(block_items) < 1:
                            logger.error(f"[Rule 3] 2-1通用: 板块类型 '{block_type}' 下缺少题目")
        except Exception as e:
            logger.error(f"Error processing Rule 3: {e}")
    else:
        logger.warning(f"Frame file not found: {frame_path}")

    # --- Rule 4: 3-1 Medical ---
    frame_path = os.path.join(frame_root, "3特色场景", "3-1医疗.json")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'r', encoding='utf-8') as f:
                frame_data = json.load(f)
            
            # Structure: {"医疗": { "SpecialtyCat": { "SpecialtySpecial": { "SubSpecialtySpecial": [...] } } }}
            medical_root = frame_data.get("医疗", {})
            
            # We need to traverse deep to find SubSpecialtySpecial
            # 医疗 -> 专业类别 -> 专业专项 -> 子专业专项
            for cat_key, cat_val in medical_root.items(): # 专业类别
                if isinstance(cat_val, dict):
                    for spec_key, spec_val in cat_val.items(): # 专业专项
                         if isinstance(spec_val, dict):
                            for sub_spec_key in spec_val.keys(): # 子专业专项
                                sub_spec = sub_spec_key.split("(")[0]
                                
                                # Check Total >= 1
                                # Note: Data only has "子专业专项" field? Or do we need to match path?
                                # dataset_loader uses: item.get("子专业专项")
                                sub_spec_items = filter_items(domain="医疗", 子专业专项=sub_spec)
                                if len(sub_spec_items) < 1:
                                    logger.error(f"[Rule 4] 3-1医疗: 子专业专项 '{sub_spec}' 下缺少题目")

        except Exception as e:
            logger.error(f"Error processing Rule 4: {e}")
    else:
        logger.warning(f"Frame file not found: {frame_path}")

    # --- Rule 5: 3-2 Airport ---
    frame_path = os.path.join(frame_root, "3特色场景", "3-2机场.json")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'r', encoding='utf-8') as f:
                frame_data = json.load(f)
            
            # Structure: {"机场": [ "Special", ... ]}
            airport_root = frame_data.get("机场", [])
            if isinstance(airport_root, list):
                for special in airport_root:
                    # Check Total >= 1
                    special_items = filter_items(domain="机场", 专项=special)
                    if len(special_items) < 1:
                        logger.error(f"[Rule 5] 3-2机场: 专项 '{special}' 下缺少题目")
            elif isinstance(airport_root, dict):
                 # Handle if it's a dict like others (though sample showed list earlier)
                 pass

        except Exception as e:
            logger.error(f"Error processing Rule 5: {e}")
    else:
        logger.warning(f"Frame file not found: {frame_path}")

    logger.info("Dataset validation completed.")
