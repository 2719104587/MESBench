# “盈科·绳墨” 监理行业大模型测评集1.0

<p align="center">
  <img src="assets/logo.png" alt="Logo" width="1000" />
</p>

## 项目简介
本项目旨在构建一个针对建设监理领域的专业知识评测框架，通过自动化评测大模型在安全、质量、通用综合及特色场景（如医疗、机场）等方面的表现，输出详细的分数统计与分析报告。

## 总体框架
![总体框架](assets/总体框架.png)

## 题目示例
![题目示例](assets/题目示例.png)

## 评分机制
![评分机制](assets/评分机制.png)

## 目录结构
- `data/`: 评测数据集（包含专业技术、通用综合、特色场景等）
- `frame/`: 知识体系框架定义
- `config/`: 配置文件
- `pipeline/`: 核心处理逻辑
- `results/`: 评测结果输出目录

## 安装与运行

### 1. 安装依赖
请确保已安装 Python 环境，并执行以下命令安装所需依赖：
```bash
pip install -r requirements.txt
```

### 2. 运行评测
默认使用 `config/test.yaml` 配置文件进行评测：
```bash
python main.py
```
或者指定配置文件路径：
```bash
python main.py --config_yaml_path config/your_config.yaml
```

### 3. 数据集校验
在运行评测前，可以对数据集的完整性进行校验（例如检查各分类下是否包含必要的单选、多选、判断及问答题）：
```bash
python main.py --validate_dataset
```

## 配置说明
配置文件（如 `config/test.yaml`）包含以下主要部分：
- **candidate_model**: 待评测模型参数（api_key, base_url, model_name 等）。
- **judges**: 裁判模型参数列表（用于对问答题进行评分）。
- **datasets_config_path**: 评测集选择文件路径（.txt），指定需要评测的题目范围。
- **result_output_path**: 结果输出目录。
- **weights**: 各类题型的分值权重设置。

## 评测流程
1. **初始化**: 验证待评测模型与裁判模型的可用性。
2. **加载数据**: 根据配置加载指定的评测题目。
3. **模型作答**: 并发调用待评测模型，生成答案。
4. **评分统计**:
   - 客观题（单选/多选/判断）：根据标准答案自动评分。
   - 主观题（问答）：使用裁判模型（如 GPT-4）进行打分。
5. **报告生成**: 输出 `scores.csv`（详细分数）与 `report.md`（分析报告）。

## 注意事项
- `data/` 与 `frame/` 目录为数据源，通常不需要修改。
- 评测结果会保存在 `results/` 目录下（或配置文件指定的路径）。
- 如果未配置有效的裁判模型，问答题将不计入最终分数。
