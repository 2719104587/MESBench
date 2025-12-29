import sys
import os
import asyncio
import argparse
from typing import List, Dict
from pipeline.config_loader import load_config
from pipeline.validator import validate_model
from pipeline.dataset_loader import parse_selection_file, load_questions
from pipeline.evaluator import evaluate
from pipeline.scoring import compute_scores, write_csv
from pipeline.report import build_report, write_report


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate a candidate model against a set of questions."
    )
    parser.add_argument(
        "--config_yaml_path", type=str, default="./config/test.yaml", help="Path to the configuration YAML file."
    )
    parser.add_argument(
        "--validate_dataset", action="store_true", help="Enable dataset quantity validation."
    )
    args = parser.parse_args()

    # --- Dataset Validation ---
    if args.validate_dataset:
        from pipeline.validator import validate_dataset
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
        data_root = os.path.join(project_root, "data")
        frame_root = os.path.join(project_root, "frame")
        validate_dataset(data_root, frame_root)
    # --------------------------

    cfg_path = args.config_yaml_path
    cfg = load_config(cfg_path)

    cand = cfg["candidate_model"]
    ok, msg = validate_model(cand)
    if not ok:
        print("candidate model unavailable:", msg)
        sys.exit(1)

    judges: List[Dict] = []
    for j in cfg["judges"]:
        j_ok, _ = validate_model(j)
        if j_ok:
            judges.append(j)
    if not judges:
        print("no valid judge models, QA will be ignored in scoring")

    sels = parse_selection_file(cfg.get("datasets_config_path"))
    questions = load_questions(sels)

    print(f"\n一共加载了 {len(questions)} 道题目。")
    confirm = input("是否继续执行测评？(y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("用户取消执行。")
        sys.exit(0)

    result_root = cfg.get("result_output_path") or "results"

    async def run():
        paths, eval_usage = await evaluate(questions, cand, result_root)
        # Reload completed files if necessary for scoring
        rows, totals, judge_usage = await compute_scores(result_root, judges, cfg["weights"])
        csv_path = os.path.join(result_root, "scores.csv")
        write_csv(rows, csv_path)
        report_text = build_report(rows, totals, eval_usage, judge_usage, cand.get("model_name"))
        write_report(report_text, os.path.join(result_root, "report.md"))
        print("outputs:")
        print(csv_path)
        print(os.path.join(result_root, "report.md"))

    asyncio.run(run())


if __name__ == "__main__":
    main()
