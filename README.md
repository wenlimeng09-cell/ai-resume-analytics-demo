# AI 简历优化助手 MVP 设计与效果评估

在线访问地址：[https://ai-resume-ai-pm-demo.streamlit.app/](https://ai-resume-ai-pm-demo.streamlit.app/)

## 项目背景

这是一个 **AI 简历优化助手 Demo + AI 产品 MVP 设计与效果评估项目**。项目围绕求职用户“不知道如何根据目标岗位修改简历”的问题，设计从 JD 解析、简历差距识别、结构化建议生成，到采纳反馈、优化报告导出和产品效果评估的完整闭环。

项目定位为本地 / 在线可交互的 MVP，用于展示 AI 产品设计、生成策略、质量评估、数据分析和产品迭代思路。建议生成采用“规则引擎 + 可选 DeepSeek V4 Flash”的双引擎设计：公开访问默认使用规则引擎，输入演示访问码后可体验真实模型，调用失败时自动回退到规则引擎。分析数据为演示样本数据，不作为真实上线产品，也不宣称真实提升面试率。

## 核心功能

- 简历文本输入，或 PDF / DOCX / TXT / MD 文件上传与文本提取
- 目标岗位 JD 粘贴与关键词解析
- 基于规则引擎或 DeepSeek V4 Flash 生成结构化简历优化建议
- 真实模型通过访问码解锁，并提供调用次数限制、失败重试和规则兜底
- 展示“问题定位 + 修改建议 + 示例改写 + 前后对比 + 匹配 JD 关键词”
- 对每条建议执行“采纳 / 拒绝 / 暂不处理”，并收集拒绝原因
- 当前 session 行为记录与任务状态更新
- 优化报告导出
- 基于固定演示样本数据的产品效果评估
- 项目总览、AI 能力设计、生成策略、产品效果评估和迭代路线图

## 作品集页面结构

- **项目总览**：从用户痛点、产品功能、AI 能力和评估指标说明产品设计逻辑。
- **产品体验**：体验简历/JD 输入、结构化建议生成、建议处理和优化报告导出。
- **AI 能力设计**：展示 JD 关键词识别、覆盖判断、缺口分析、质量评分和安全边界。
- **生成策略**：对比通用建议型与 JD 匹配型两类生成策略，并展示评估方法。
- **产品效果评估**：分析任务漏斗、建议采纳驱动因素、用户分群和导出转化。
- **迭代路线图**：按 P0/P1/P2 展示功能方案、优先级依据、验收指标和风险控制。

## 用户路径

访问产品 -> 上传简历 -> 上传 JD -> 生成建议 -> 采纳 / 不采纳建议 -> 导出优化报告

公开展示模式下，数据分析看板默认读取固定模拟数据，用户无需操作即可看到完整图表。体验简历优化功能产生的数据仅保存在当前 session，不会破坏默认作品集样例数据。

## 数据表设计

### users

用户基础信息表。

| 字段 | 含义 |
|---|---|
| user_id | 模拟用户 ID |
| register_date | 注册日期 |
| user_type | 应届生 / 实习生 / 转行用户 |
| target_role | 目标岗位 |
| experience_years | 工作年限 |

### resume_tasks

简历优化任务表，用于区分同一用户针对多个 JD 的多次优化。

| 字段 | 含义 |
|---|---|
| task_id | 简历优化任务 ID |
| user_id | 模拟用户 ID |
| jd_id | JD ID |
| prompt_group | A / B |
| original_match_score | 优化前匹配分 |
| current_match_score | 当前匹配分 |
| suggestion_count | 建议数 |
| adopted_count | 已采纳建议数 |
| rejected_count | 已拒绝建议数 |
| pending_count | 待处理建议数 |
| exported | 是否导出报告 |
| created_time | 创建时间 |

### events

行为日志表。

| 字段 | 含义 |
|---|---|
| event_id | 事件 ID |
| user_id | 模拟用户 ID |
| task_id | 任务 ID |
| session_id | 会话 ID |
| event_time | 事件时间 |
| event_name | 事件名称 |
| suggestion_id | 建议 ID，可为空 |
| prompt_group | Prompt 组别 |

### suggestions

优化建议明细表。

| 字段 | 含义 |
|---|---|
| suggestion_id | 建议 ID |
| task_id | 任务 ID |
| user_id | 模拟用户 ID |
| prompt_group | A / B |
| suggestion_type | 建议类型 |
| resume_section | 简历模块 |
| matched_keyword | 匹配 JD 关键词 |
| original_expression | 原表达 |
| revised_expression | 优化后表达 |
| specificity_score | 具体性评分 |
| jd_match_score | JD 匹配度评分 |
| actionability_score | 可执行性评分 |
| adopted | 是否采纳 |
| status | pending / adopted / rejected |

### feedback

小样本体验反馈表，可选。

| 字段 | 含义 |
|---|---|
| feedback_id | 反馈 ID |
| user_id | 模拟用户 ID |
| task_id | 任务 ID |
| usefulness_score | 有用性评分 |
| trust_score | 信任度评分 |
| ease_of_use_score | 易用性评分 |
| comment | 体验反馈 |

## 核心指标体系

北极星指标：

**有效优化任务完成率 = 完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数**

一级指标：

- 简历优化任务数
- 建议生成率
- 建议采纳率
- 报告导出率
- 有效优化任务完成率

二级拆解维度：

- 用户维度：用户类型、目标岗位、经验年限
- JD 维度：JD 关键词数量、JD 难度、岗位类型
- 建议维度：建议类型、质量评分、关键词匹配数
- Prompt 维度：A 组 / B 组
- 行为维度：建议查看数、采纳数、拒绝数、导出行为

## 分析方法

- 漏斗分析：定位“访问 -> 上传简历 -> 上传 JD -> 生成建议 -> 采纳建议 -> 导出报告”的主要流失环节
- Prompt A/B 实验：对比通用建议型 Prompt 与 JD 匹配型 Prompt 的采纳率、导出率和平均质量评分
- 用户分群：比较应届生、实习生、转行用户的建议采纳率、导出率和人均任务数
- 建议质量评分：从具体性、JD 匹配度、可执行性三个维度分析采纳驱动因素
- 导出转化影响因素分析：以是否导出报告为目标变量，分析已采纳建议数、待处理建议数、匹配分提升、Prompt 组别、用户类型和平均建议质量分

## 主要分析结论

以下结论均基于模拟产品日志，用于展示分析框架和产品效果评估思路：

- 主要流失点集中在“采纳建议 -> 导出报告”环节，说明用户采纳建议后仍需要明确的下一步引导。
- B 组 JD 匹配型 Prompt 的建议采纳率高于 A 组通用建议型 Prompt，说明绑定 JD 关键词和提供改写示例有助于提升采纳意愿。
- JD 匹配度越高，用户越容易采纳建议，说明用户更关注建议是否真正对应目标岗位要求。
- 转行用户的经历与目标 JD 能力映射难度更高，需要更强的可迁移能力识别和岗位差距分析。
- 低采纳建议类型应优先补充前后对比、量化结果示例和 JD 关键词解释。

## 产品优化建议

- 导出按钮前置，降低“采纳建议 -> 导出报告”环节流失
- 用户采纳建议后增加下一步引导
- 在每条建议旁展示 JD 关键词绑定解释，提升可信度
- 针对转行用户增加可迁移能力识别和岗位差距分析
- 增加“有用 / 无用”反馈按钮，持续优化建议生成逻辑
- 建立模型评测集，持续比较规则引擎与真实模型的生成质量、稳定性和单任务成本

## 技术栈

- 前端展示：Streamlit
- 数据处理：Python / pandas / NumPy
- 可视化：Plotly / Streamlit 图表
- 数据存储：CSV / SQLite
- 建议生成：规则引擎 / DeepSeek V4 Flash，使用统一 Provider 接口和 JSON 输出校验
- 模型调用：OpenAI Python SDK 连接 DeepSeek OpenAI 兼容接口
- 文件解析：python-docx 提取 Word 正文与表格，pypdf 提取文字型 PDF
- 分析方法：漏斗分析、分群分析、Prompt A/B 实验、建议质量评分、导出转化影响因素分析

## 本地运行方式

```bash
pip install -r requirements.txt
streamlit run app_ai_pm.py
```

如果需要重新生成模拟数据：

```bash
python data/generate_mock_data.py
```

### 可选：本地启用 DeepSeek

在本地创建 `.streamlit/secrets.toml`，该文件已被 `.gitignore` 屏蔽：

```toml
DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
DEMO_ACCESS_CODE = "你设置的演示访问码"
DEEPSEEK_MODEL = "deepseek-v4-flash"
MAX_LLM_CALLS_PER_SESSION = 3
```

未配置 Secrets 时应用仍可正常启动，规则引擎和固定演示样本看板不受影响。

## Streamlit Community Cloud 部署

1. 将项目上传到 GitHub。
2. 登录 Streamlit Community Cloud。
3. 点击 New app / Create app。
4. 选择 GitHub 仓库、branch 和入口文件 `app_ai_pm.py`。
5. 在 App settings / Secrets 中填写 `DEEPSEEK_API_KEY`、`DEMO_ACCESS_CODE`、`DEEPSEEK_MODEL` 和 `MAX_LLM_CALLS_PER_SESSION`。
6. 点击 Deploy；修改 Secrets 后需要保存并重启应用。
7. 部署完成后复制公开访问链接，补充到 README 的“在线访问地址”，并放入简历或作品集。

## 项目边界说明

- 当前项目为作品集 MVP Demo，主要验证产品流程和数据分析方法。
- 当前建议生成默认使用规则引擎；DeepSeek 仅作为访问码解锁的可选体验能力，并设置规则兜底。
- 大模型生成结果仍可能存在偏差，用户需要依据真实经历决定是否采纳。
- 用户行为数据为演示样本数据，少量体验反馈仅用于辅助展示。
- 项目不作为真实上线产品，不追踪真实投递结果和真实面试反馈。
- 本项目不宣称真实提升面试率或求职成功率。

## 隐私说明

- 示例简历和示例 JD 均为虚构数据。
- 上传支持 `.pdf`、`.docx`、`.txt` 和 `.md`；PDF 需要包含可复制的文字层，扫描件暂不支持 OCR，旧版 `.doc` 需要另存为 `.docx`。
- 上传文件只在当前浏览器会话中解析，文件原文和文件名不会写入 CSV、模拟日志或服务器文件。
- 使用 DeepSeek 模式时，当前简历和 JD 会发送至 DeepSeek API；公开体验只应使用虚构或已脱敏内容。
- 简历、JD、访问码和 API Key 不写入 CSV、模拟日志或服务器文件；导出的报告仅包含结构化建议，不包含原始简历或完整 JD。
- 模拟数据中的 `user_id`、`task_id`、`event_id` 均为随机生成标识，不对应真实用户身份。
- 项目不包含真实手机号、邮箱、地址、身份证号、真实简历或真实投递记录。
- GitHub 仓库不包含 API Key、访问码、`.env` 文件或 Streamlit secrets。
- `.gitignore` 已屏蔽 `.env`、`secrets.toml`、`.streamlit/secrets.toml`、`__pycache__`、本地日志和临时文件。
