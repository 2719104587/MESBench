# Norma-MESBench 1.0

<p align="center">
  <img src="assets/logo.png" alt="Logo" width="1000" />
  <br>
  <a href="https://github.com/2719104587/MESBench">
    <img src="https://img.shields.io/badge/GitHub-MESBench-black?logo=github" alt="GitHub">
  </a>
  <a href="https://www.modelscope.cn/datasets/DongZekai/Norma_MESBench_1.0">
    <img src="https://img.shields.io/badge/ModelScope-Norma_MESBench_1.0-blue" alt="ModelScope">
  </a>
</p>

## Table of Contents
- [Introduction](#introduction)
- [Overall Framework](#overall-framework)
- [Dataset Construction Method](#dataset-construction-method)
- [Question Examples](#question-examples)
- [Scoring Mechanism](#scoring-mechanism)
- [Model Evaluation Result Analysis](#model-evaluation-result-analysis)
- [Directory Structure](#directory-structure)
- [Installation and Usage](#installation-and-usage)
- [Configuration](#configuration)
- [Evaluation Process](#evaluation-process)
- [Notes](#notes)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Introduction
Norma-MESBench 1.0 is the first 10,000-level multi-task LLM evaluation benchmark tailored for China's construction supervision industry. Focusing on housing construction, it contains 10,144 questions across Professional Technology, General Comprehensive, and Special Scenes, including single-choice, multiple-choice, true/false, and Q&A formats. By employing a "multi-level hybrid scoring mechanism," it comprehensively measures LLMs' professional capabilities. This project aims to help practitioners assess the accuracy and reliability of model outputs, addressing the lack of evaluation benchmarks in the supervision domain.

<p align="center">
  <img src="assets/leaderboard_large.png" alt="Large-Parameter Model Leaderboard" width="48%" height="360px" />
  <img src="assets/leaderboard_medium.png" alt="Medium-Parameter Model Leaderboard" width="48%" height="360px" />
</p>

## Overall Framework
To comprehensively evaluate the professional capabilities of Large Language Models in the field of engineering supervision, MESBench has constructed a multi-dimensional evaluation structure containing 3 major sections and multiple levels, and further refined the granularity of evaluation based on the depth and breadth of supervision work.

![Overall Framework](assets/overall_framework.png)

## Dataset Construction Method
The project adopts a hybrid mode of "Manual Questioning + LLM-assisted Questioning" to construct the evaluation set.

### 1. Manual Questioning
Authored by senior supervision professionals, providing "scenario questions", "correct answers", "references", and "specific options"/"scoring points".

### 2. LLM-assisted Questioning
- **RAG-based Generation**: Utilizing OCR and Embedding technologies to convert standards, management manuals, and other technical documents into a vector database. Questions are generated via Retrieval Augmented Generation (RAG) based on accurate references and verified manually.
- **Scenario Rewriting**: For questions from the National Certified Supervision Engineer Examination subjects, methods like shuffling options and scenario rewriting are used to reduce "memorization" and test actual problem-solving abilities.

### 3. Quality Control
- **Format Unification**: Scripts convert all questions into a unified JSON format.
- **Deduplication**: Based on semantic matching and vector similarity calculation.
- **Distribution Check**: Ensuring sufficient questions for each evaluation unit. The dataset totals 10,144 questions, including 4,669 single-choice, 3,709 multiple-choice, 1,271 true/false, and 495 Q&A questions.
- **Quality Inspection**: Focusing on common errors across mainstream models to replace defective questions.

## Question Examples
![Question Examples](assets/question_example.png)

### Question Format Example
```json
    {
        "id": "45",
        "领域": "质量",
        "分部工程": "地基与基础",
        "子分部工程": "地下水控制",
        "分项工程": "降水与排水",
        "题型": "单选题",
        "问题": "分层、分块开挖的土质基坑，开挖前潜水水位应控制在土层开挖面以下多少范围\nA. 1.5m～2.0m\nB. 1.0m～1.5m\nC. 0.5m～1.0m\nD. 0.3m～0.5m\n",
        "答案": "C"
    },
```

## Scoring Mechanism
![Scoring Mechanism](assets/scoring_mechanism.png)

### 1. Overall Calculation Logic
To scientifically evaluate the professional level of models in various supervision sub-fields, this project proposes a "Multi-level Multi-type Hybrid Scoring Mechanism".

#### Total Score Calculation
The total score is a weighted sum of three major sections:

![Total Score Formula](assets/total_score_formula.png)

#### Section 1: Professional Technology (Weight 0.45)
Composed of "Safety Management" and "Quality Control", each accounting for 50%.
- **Safety Management**: Calculated hierarchically from "Safety Specials" and "Safety Types".
- **Quality Control**: Calculated hierarchically from "Sub-item Projects", "Sub-division Projects", and "Division Projects".

#### Section 2: General Comprehensive (Weight 0.35)
Includes "Basic Theory", "Contract Management", "Investment Control", and "Schedule Control", each accounting for 25%.

#### Section 3: Special Scenes (Weight 0.2)
Composed of "Medical Architecture" and "Airport Traffic Architecture", each accounting for 50%, to deeply evaluate the knowledge reserve of high-barrier knowledge points in the two characteristic project types of medical architecture and airport traffic architecture, which are distinct from traditional housing construction supervision projects.

### 2. Standardized Answering Mode
Adopts Zero-shot and generative evaluation. No problem-solving templates are provided; only output formats are constrained.

### 3. Scoring Mechanism for Each Question Type
- **Objective Questions** (Single/Multi-choice, True/False): Scored by comparing with standard answers to calculate Accuracy.
- **Subjective Questions** (Q&A): Adopts a "Split Scoring Points + LLM Judge Group" mechanism. A judge group consisting of kimi-k2-thinking, deepseek-r1, and qwen3-235b-a22b-thinking-2507 scores independently based on scoring points, and the average is taken.

## Model Evaluation Result Analysis

### 1. Mainstream LLM Selection
14 mainstream LLMs were selected for evaluation (including models with/without deep thinking enabled), with parameters ranging from 20B to over 100B, covering both open-source and closed-source models.
| Model Name | Deep Thinking | Parameters | Open Source |
| :--- | :--- | :--- | :--- |
| qwen3-30b-a3b-thinking-2507 | Yes | 30B (Total), 3B (Active) | Yes |
| qwen3-30b-a3b-instruct-2507 | No | 30B (Total), 3B (Active) | Yes |
| qwen3-32b | Yes | 32B | Yes |
| qwen3-32b | No | 32B | Yes |
| qwen3-235b-a22b-thinking-2507 | Yes | 235B (Total), 22B (Active) | Yes |
| qwen3-max | No | 1T (Total), 220B (Active) | No |
| deepseek-r1-distill-qwen-32b | Yes | 32B | Yes |
| glm-4.7 | Yes | 358B (Total), 32B (Active) | Yes |
| glm-4.7 | No | 358B (Total), 32B (Active) | Yes |
| kimi-k2 | Yes | 1T (Total), 32B (Active) | Yes |
| doubao-seed-1.6 | Yes | 230B (Total), 23B (Active) | No |
| deepseek-v3.2 | Yes | 671B (Total), 37B (Active) | Yes |
| deepseek-v3.2 | No | 671B (Total), 37B (Active) | Yes |
| deepseek-r1 | Yes | 671B (Total), 37B (Active) | Yes |
| gpt-oss-20b | Yes | 20B | Yes |
| gpt-oss-120b | Yes | 120B | Yes |
| nvidia-nemotron-3-30b-a3b | Yes | 30B (Total), 3B (Active) | Yes |

### 2. Large Parameter Model Leaderboard
Comparing models with over 100 billion parameters. Except for Qwen3-Max and doubao-seed-1.6, all are open-source.
- **Intense Competition in First Tier**: Kimi-k2 (Deep Thinking) wins narrowly with 73.52, followed closely by DeepSeek-v3.2 (Deep Thinking) and Qwen3-Max (Non-Deep Thinking). The top six are very close.
- **Falling Behind**: GPT-OSS-120B, as a foreign model, shows a significant gap compared to other large-parameter models, while DeepSeek-R1, being an older model from December 2024, performs poorly compared to other latest versions of domestic large-parameter models.

<p align="center">
  <img src="assets/super_large_model_comparison.png" alt="Comparison of Total Scores for Super Large Parameter Models" width="800" />
</p>
<p align="center">
  <img src="assets/super_large_model_results.png" alt="Evaluation Results for Models with Over 100 Billion Parameters" width="800" />
</p>

### 3. Small and Medium Parameter Model Leaderboard
Comparing open-source models with 20B-32B parameters, suitable for local deployment with limited resources.
- **Leapfrog Performance**: Qwen3-32B (Deep Thinking) scored 65.63, surpassing all small and medium parameter models and some large models, offering high cost-effectiveness.
- **Acclimatization Issues**: nvidia-nemotron-3-30b-a3b and gpt-oss-20b perform poorly in Chinese supervision.

<p align="center">
  <img src="assets/leaderboard_small.png" alt="Small Parameter Model Leaderboard" width="800" />
</p>
<p align="center">
  <img src="assets/small_model_results.png" alt="Small Parameter Model Evaluation Results" width="800" />
</p>

### 4. Thinking vs. Non-Thinking Mode
Scores of all models increase significantly after enabling "Deep Thinking (CoT)".
- **Significant Improvement**: DeepSeek-v3.2 improved most (+7.5 points), proving CoT is essential in supervision.
- **Cost of "Slow Thinking"**: CoT slows down response speed, requiring trade-offs based on scenarios.

<p align="center">
  <img src="assets/deep_thinking_effect_comparison.png" alt="Comparison of Deep Thinking Effects" width="800" />
</p>
<p align="center">
  <img src="assets/thinking_vs_non_thinking.png" alt="Thinking vs Non-Thinking Comparison" width="800" />
</p>

### 5. Score Comparison in Different Sub-fields (Taking Kimi-k2 as Example)
- **Professional Technology**: "Quality" (~71.5) is better than "Safety" (~67.1).
- **General Comprehensive**: Avg ~79.4, the strongest sector, benefiting from text understanding capabilities and potential public training data.

<p align="center">
  <img src="assets/kimi_k2_detailed_analysis.png" alt="Detailed Analysis of Kimi-K2 Scores in All Dimensions" width="800" />
</p>

### 6. Domestic vs. Foreign Models
Comparing Qwen3-32B with foreign models of similar size (Nemotron-30B, GPT-OSS-20B).
- **Complete Domination**: Qwen3-32B wins in all dimensions.
- **Professional Barrier**: Foreign models fail in "Professional Technology", proving the barriers of foreign models in this vertical domain.

<p align="center">
  <img src="assets/domestic_vs_foreign_comparison.png" alt="Comparison of Models with Similar Parameters from Domestic and Foreign Sources" width="800" />
</p>
<p align="center">
  <img src="assets/domestic_vs_foreign_detailed_comparison.png" alt="Detailed Comparison of Domestic and Foreign Models" width="800" />
</p>

## Directory Structure
- `assets/`: Project assets (images, documents, etc.).
- `data/`: Evaluation datasets (Professional Technology, General Comprehensive, Special Scenes, etc.).
- `frame/`: Knowledge framework definitions.
- `config/`: Configuration files.
- `pipeline/`: Core processing logic.

## Installation and Usage

### 1. Install Dependencies
Ensure you have a Python environment set up, then install the required packages:
```bash
pip install -r requirements.txt
```

### 2. Run Evaluation
Run the evaluation using the default configuration (`config/test.yaml`):
```bash
python main.py
```
Or specify a custom configuration file:
```bash
python main.py --config_yaml_path config/your_config.yaml
```

### 3. Dataset Validation
Before running the evaluation, you can validate the integrity of the dataset (e.g., check if necessary question types exist for each category):
```bash
python main.py --validate_dataset
```

## Configuration
The configuration file (e.g., `config/test.yaml`) includes:
- **candidate_model**: Parameters for the model to be evaluated (api_key, base_url, model_name, etc.).
- **judges**: List of judge models (used for scoring QA questions).
- **datasets_config_path**: Path to the dataset selection file (.txt) defining the scope of questions.
- **result_output_path**: Directory for output results.
- **weights**: Scoring weights for different question types.

## Evaluation Process
1. **Initialization**: Validate the availability of candidate and judge models.
2. **Data Loading**: Load the specified questions based on the configuration.
3. **Model Inference**: Concurrently call the candidate model to generate answers.
4. **Scoring**:
   - Objective questions (Single/Multi-choice, True/False): Automatically scored against standard answers.
   - Subjective questions (QA): Scored by judge models.
5. **Report Generation**: Output `scores.csv` (detailed scores) and `report.md` (analysis report).

## Notes
- `data/` and `frame/` directories contain source data and usually do not need modification.
- Results are saved in the `results/` directory (or the path specified in the config).
- If no valid judge model is configured, QA questions will not be included in the final score.

## Future Plans
This project is the first open-source evaluation benchmark attempt for the supervision industry. Please bear with any shortcomings. The SRIBS Consulting Group has plans for more evaluation sets and other AI projects in the future. For further inquiries, please contact the team at: wuhao@jkec.com.cn

## License
This project is licensed under the [CC BY-NC License](https://creativecommons.org/licenses/by-nc/4.0/). It is intended for non-commercial research use only.

## Acknowledgements
This project is released by the SRIBS Consulting Group. We hereby express our gratitude to SRIBS Consulting Group Co., Ltd., SRIBS Engineering Consulting Co., Ltd., and all colleagues who participated in the project construction.
