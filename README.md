# 论文规范与引用检查助手

> **路径 A（技术栈较完整的智能体应用，对标 demo_5）** ｜ 期末考查：开源 AI 技术实践（杉达学院 2026–2027 学年第一学期）

面向学生的论文 Agent 助手：上传/粘贴论文文稿，用自然语言指令驱动——检查参考文献格式、检索文献是否真实存在、识别漏引用、生成规范修改报告、导出校验表格。全程可在 Streamlit 界面看到 Agent 调用各个工具的过程。

本工具**只做格式检查与文献真实性核验，不代写、不生成论文正文**，符合学术诚信与课程选题边界。

---

## 一、解决什么问题

写课程论文/毕业论文时，学生常在参考文献上踩坑：

- 格式不统一：缺文献类型码 `[J]/[M]`、缺年份、标点混用、多作者未用"等"；
- 引用不规范：正文引用了但参考文献列表没有（漏引），或列表有但正文没引；
- 文献真假难辨：引用了不存在或拼错的文献。

本助手把"找问题 → 核验 → 出报告"这一套流程，做成一个能规划、会用工具、能产出文件的 Agent。

---

## 二、技术栈

| 层        | 选型                              | 说明                                                                                   |
| -------- | ------------------------------- | ------------------------------------------------------------------------------------ |
| 模型       | 阿里百炼 Qwen（OpenAI 兼容接口）          | 默认 `qwen-plus`（工具编排快），可切 `qwen-max`/`qwen3.7-plus`；也支持本地 Ollama Qwen                 |
| Agent 框架 | **LangChain Deep Agents**       | 课程 demo_5 主推框架，支持工具、Skill、子代理、长期记忆、流式                                                |
| 自定义工具    | 4 个（见下）                         | `parse_reference` / `check_citation_format` / `search_paper_doi` / `generate_report` |
| Skill    | `paper-check`（`SKILL.md`）       | 封装整套论文校验流程，按需加载                                                                      |
| 长期记忆     | `AGENTS.md`                     | 记住默认格式要求 GB/T 7714-2015 与学术诚信边界                                                      |
| 界面       | Streamlit                       | 流式展示工具调用过程 + 历史会话 + 产出文件预览                                                           |
| 产出物      | Markdown + Excel                | 自动写入 `workspace/` 目录                                                                 |
| 加分项      | 子代理 + 长期记忆 + 权限隔离 + 流式 + Docker | 见下文"相对 demo_5 的改动"                                                                   |

---

## 三、4 个自定义工具（答辩演示重点，调用过程肉眼可见）

| 工具                      | 作用                                 | 关键技术点                                          |
| ----------------------- | ---------------------------------- | ---------------------------------------------- |
| `parse_reference`       | 解析参考文献条目，统计"漏引用/多余引用"              | 正则切分 `[n]` 条目；扫描正文 `[1] (作者,年)` 引用标记做覆盖率比对     |
| `check_citation_format` | 对照 GB/T 7714-2015 检查单条格式           | **确定性规则**，可解释：缺序号/文献类型码/年份、多作者未用"等"、标点混用、缺 DOI |
| `search_paper_doi`      | 调 Crossref API 核验文献是否真实存在          | 联网失败/超时**优雅降级**，不崩溃                            |
| `generate_report`       | 写出《引用校验报告》md + xlsx 到 `workspace/` | 明确产出物，侧边栏可预览下载                                 |

> 工具调用全程在 Streamlit 界面"执行过程"面板实时展示——这是答辩最直观的视觉点。

---

## 四、环境要求

- Python **3.10 及以上**，推荐 **3.12**
- 一个可用的模型接口：阿里百炼 API Key（推荐），或本地 Ollama + Qwen
- 联网（仅 `search_paper_doi` 需要；离线时该工具自动降级）

---

## 五、安装与启动（Windows）

### 1. 准备环境

```bash
cd paper-check-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2. 配置密钥

```bash
copy .env.example .env        # Linux/macOS: cp .env.example .env
```

打开 `.env`，把 `DASHSCOPE_API_KEY` 改成你的阿里百炼 API Key。其余一般不用改。

> 密钥只能写在 `.env` 里，已被 `.gitignore` 忽略，**不要**写进代码或 README。

### 3. 运行网页版（推荐，答辩用这个）

```bash
streamlit run web.py
# 未激活虚拟环境时：.venv\Scripts\python.exe -m streamlit run web.py
```

浏览器自动打开 <http://localhost:8501> 。也可命令行版：

```bash
python app.py
```

---

## 六、推荐演示话术（3–5 条）

1. "我上传了一篇课程论文，请检查它的参考文献格式。" → 观察 `parse_reference` + 多次 `check_citation_format` 被调用。
2. "帮我核验前 3 篇文献是不是真实存在的。" → 观察 `search_paper_doi` 调 Crossref。
3. "有没有漏引用？生成一份校验报告。" → 观察 `generate_report` 写出 `.md` / `.xlsx`。
4. "把参考文献格式问题整理成一份修改清单。" → 展示 Agent 汇总能力。
5. （若断网）"现在能联网核验吗？" → 展示 `search_paper_doi` 的优雅降级提示。

演示样例论文见 `examples/sample_paper.md`（虚构数据，含故意错误，便于现场展示发现问题）。

---

## 七、相对课堂 demo_5 的改动说明（可指出的增量）

> 课程要求：仅把 demo_5 改名/换皮肤按未完成处理。本项目的增量如下，均可现场指认代码：

| 维度    | demo_5 原样                          | 本项目改动（自己写的增量）                                    |
| ----- | ---------------------------------- | ------------------------------------------------ |
| 场景    | 课程助教                               | **论文规范与引用检查**新场景                                 |
| 工具    | `get_current_time` / `calculator`  | **全新 4 个领域工具** `tools.py`                        |
| Skill | `report-writer` / `code-explainer` | **新增 `skills/paper-check/SKILL.md`**             |
| 记忆    | 课程信息                               | **改写 `AGENTS.md`**（GB/T 7714-2015 格式要求 + 学术诚信边界） |
| 子代理   | researcher/critic（通用）              | 描述改为**文献调研 / 报告审稿**领域                            |
| 界面    | 通用聊天                               | 新增**论文上传入口**，示例问题改为论文场景                          |
| 产出物   | 写报告到 workspace                     | **结构化引用校验报告 md + Excel**（含漏引用分析）                 |

复用且未改动内核的部分（说明来源，避免抄袭嫌疑）：Deep Agents 组装方式、流式事件 `stream_events`、SQLite 历史持久化 `history.py`、权限隔离写法——这些直接来自课堂 demo_5，已在代码中保留原注释并注明来源。

---

## 八、目录结构

```
paper-check-agent/
├── web.py               # 网页界面（Streamlit），答辩主用
├── app.py               # 命令行界面
├── agent.py             # 组装 Deep Agent（系统提示词/工具/Skill/记忆/子代理/权限）
├── tools.py             # 4 个自定义工具（论文检查核心）
├── history.py           # 会话历史存储（SQLite），网页/命令行共用
├── AGENTS.md            # 长期记忆（GB/T 7714-2015 格式要求）
├── skills/
│   └── paper-check/
│       └── SKILL.md     # 论文校验技能（Agent Skills 规范）
├── workspace/           # Agent 唯一可写目录，报告写在这里（已被 .gitignore 忽略）
├── examples/
│   └── sample_paper.md  # 演示样例论文（虚构数据）
├── data/                # 运行后自动生成：checkpoints.db / sessions.db
├── requirements.txt
├── .env.example         # 环境变量模板（可提交）
├── .env                 # 真实密钥（勿提交）
├── Dockerfile           # 可选：Docker 一键启动
├── docker-compose.yml
└── README.md
```

---

## 九、Docker 一键启动（可选）

```bash
docker compose up --build
# 然后浏览器打开 http://localhost:8501
```

注意：需先把 `.env` 准备好（含 `DASHSCOPE_API_KEY`），`docker-compose.yml` 会把它注入容器。

---

## 十、参考来源

- 课程仓库 demo_5（LangChain Deep Agents）：Deep Agents 组装、流式 `stream_events`、SQLite 历史、权限隔离写法直接参考并复用。
- Deep Agents 文档：<https://docs.langchain.com/oss/python/deepagents/overview>
- Agent Skills 规范：<https://agentskills.io>
- 阿里百炼 OpenAI 兼容接口：<https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>
- 文献核验：Crossref REST API（<https://api.crossref.org）>
- 格式依据：GB/T 7714-2015《信息与文献 参考文献著录规则》
