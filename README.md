# My-Code-Agent

> 🤖 具备自进化能力的结构感知型 Coding Agent — v1.0.0

```
 ██████╗██╗  ██╗███████╗    ██████╗ ███████╗    ██████╗  ██████╗ ███╗   ██╗
██╔════╝██║  ██║██╔════╝    ██╔══██╗██╔════╝    ██╔═══██╗██╔═══██╗████╗  ██║
██║     ███████║█████╗      ██████╔╝███████╗    ██║   ██║██║   ██║██╔██╗ ██║
██║     ██╔══██║██╔══╝      ██╔══██╗██╔════╝    ██║   ██║██║   ██║██║╚██╗██║
╚██████╗██║  ██║███████╗    ██║  ██║███████╗    ╚██████╔╝╚██████╔╝██║ ╚████║
 ╚═════╝╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝╚══════╝     ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝
```

一个面向个人开发者的终端 AI 编码助手。无需向量数据库、Redis 或 Docker，安装后直接运行。

**核心差异化**：Skill 不是死文本，而是**带类型签名、带测试、带结构感知的可执行程序单元**。Agent 不是被动执行指令的工具，而是能从自身运行轨迹中**自动提炼、验证、发布新技能的自进化系统**。

---

## 核心功能

### 🧠 智能核心

- **ReAct 循环** — 自动分析任务、读写文件、执行命令、自我纠错，最多 25 步自动停止
- **LangGraph 风格状态机** — 可配置的 Plan→Act→Observe→Reflect 状态图，替代简单 ReAct 循环
- **多 Agent 协作** — 4 角色团队（Planner/Coder/Reviewer/Executor），消息总线通信 + 共识投票机制
- **模型智能路由** — 根据任务复杂度自动选择模型：简单任务走轻量模型，复杂任务走大模型

### 🔧 可执行 Skill 系统

- **Executable Skill 规范** — YAML frontmatter + Python code_block + 类型签名 + 结构约束 + Eval 用例
- **四阶段验证** — 类型签名校验 → 结构路径校验 → 安全约束校验 → AST 语法 & 危险操作检测
- **沙箱执行** — 受限全局变量（仅安全 builtins）、输入类型校验、Eval 通过率门禁
- **热更新注册** — 基于 mtime 的文件监听，Skill 文件增删改自动重载
- **Auto-Distill Pipeline** — 从成功会话轨迹自动提炼新 Skill：Trace 收集 → Jaccard 聚类 → LLM 生成 Draft → 自动 Eval Gate → 人工审核

### 📂 结构感知

- **语义目录树** — 三层语义标注（配置覆盖 / 命名启发 / 内容分析），角色标签目录分类
- **依赖图引擎** — 基于 tree-sitter 的真实 DAG 构建，支持物理 / 模块 / 依赖 / 变更四视图
- **Convention Learner v2** — 自动推断项目约定（feature_dirs、test_pattern、source_prefix），LLM 辅助隐式模式提取
- **按需展开工具** — `expand_directory` / `search_by_structure` / `get_module_boundary` 三个结构化查询工具

### 🛡️ 安全与沙箱

- **路径逃逸防护** — 所有文件操作限制在 workspace 目录内
- **敏感文件保护** — 自动拦截 `.env`、`.key`、`credentials`、`.pem`、`id_rsa` 等
- **命令黑名单** — 阻止 `rm -rf`、`curl|bash`、`chmod 777`、管道到 shell 等危险命令
- **AST 白名单** — 代码执行前通过 AST 节点类型白名单校验，拒绝危险操作
- **超时熔断** — 命令执行超时自动终止，可配置超时阈值
- **资源预算** — 最大输出字节数、最大文件操作数、最大子进程数限制
- **密钥脱敏** — 发送请求前自动扫描并替换 API Key 类模式为 `[REDACTED]`

### 📊 可观测性

- **OpenTelemetry 兼容追踪** — 轻量级 Span 系统，Phoenix 兼容 JSON 导出，内存缓冲实时看板
- **Semantic Cache** — 双层去重：SHA-256 精确匹配 + BM25 模糊语义匹配，减少重复 LLM 调用
- **依赖分析** — FailureTracker（改进建议）、UsageAnalytics（热点/慢速/未使用）、AutoDeprecation

### 👁️ 多模态感知

- **Vision 诊断** — 截图 UI 问题分析，通过 Claude Vision API 识别布局问题、Bug、UX 异常
- **Log Parser** — CI/CD 日志结构化解析，CI 失败模式检测，严重度分级，LLM 深度分析

### 💻 交互界面

- **Textual TUI** — 流式 Markdown 渲染、Diff 预览、实时 Token/成本统计
- **CLI 模式** — 标准输入/输出交互，适合管道和脚本集成
- **Welcome Screen** — ASCII Art 动态启动画面，自适应终端宽度，暗/亮主题自动适配

---

## 系统要求

- Python 3.11+
- pip（包管理器）
- Git（可选，用于 Git 检查点功能）

---

## 安装

### 方法一：pip 一键安装（推荐）

```bash
pip install my-code-agent
```

安装完成后，在任意目录运行 `my-code-agent` 即可。

### 方法二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/hanmou666529/my-code-agent.git
cd my-code-agent

# 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 安装
pip install -e ".[dev]"
```

---

## 配置

### 第一步：获取 API Key

前往你的 LLM 提供商后台获取 API Key，例如 Mimomo：[https://www.xiaomimimo.com](https://www.xiaomimimo.com)

### 第二步：创建 .env 文件

在你**准备写代码的项目目录**中创建 `.env` 文件。智能体会在当前目录读取它。

```ini
# API Key — 必填
ANTHROPIC_API_KEY=sk-你的密钥

# API 端点地址 — 必填
API_BASE=https://api.xiaomimimo.com/anthropic

# 模型配置 — 默认三个级别都用同一个模型
PRIMARY_MODEL=anthropic/mimo-v2.5-pro
SECONDARY_MODEL=anthropic/mimo-v2.5-pro
LOCAL_MODEL=anthropic/mimo-v2.5-pro
```

### 环境变量说明

| 变量 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | 你的 API 密钥 | `sk-xxx` |
| `API_BASE` | ✅ | LLM API 端点地址 | `https://api.xiaomimimo.com/anthropic` |
| `PRIMARY_MODEL` | ❌ | 复杂任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `SECONDARY_MODEL` | ❌ | 中等复杂度任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `LOCAL_MODEL` | ❌ | 简单任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `max_session_tokens` | ❌ | 会话 Token 上限 | `100000` |
| `semantic_cache_enabled` | ❌ | 启用语义缓存（减少重复 LLM 调用） | `true` |
| `semantic_cache_ttl_seconds` | ❌ | 缓存过期时间（秒） | `3600` |
| `sandbox_enabled` | ❌ | 启用沙箱执行（AST 白名单 + 超时熔断） | `true` |
| `sandbox_default_timeout` | ❌ | 默认命令超时（秒） | `30` |
| `tracing_enabled` | ❌ | 启用 OpenTelemetry 兼容追踪 | `true` |
| `state_machine_enabled` | ❌ | 启用状态机编排（替代简单 ReAct） | `false` |
| `multi_agent_enabled` | ❌ | 启用多 Agent 团队协作 | `false` |
| `distill_enabled` | ❌ | 启用 Auto-Distill 轨迹提炼 | `false` |
| `vision_enabled` | ❌ | 启用截图诊断 | `false` |

---

## 使用

### TUI 模式（推荐）

终端图形界面，支持流式输出、Diff 预览、实时 Token 统计：

```bash
# 安装后任意目录运行
my-code-agent

# 或从源码运行
python -m my_code_agent
```

### CLI 模式

命令行交互模式，适合管道和脚本集成：

```bash
my-code-agent --cli
```

### 其他模式

```bash
# 显示欢迎画面和目录树
my-code-agent --welcome

# 自动推断项目约定
my-code-agent --learn-conventions

# 应用推断的约定
my-code-agent --apply-conventions

# 一次 Auto-Distill 运行
my-code-agent --distill

# Auto-Distill 守护进程
my-code-agent --distill-daemon

# 解析 CI/CD 日志
my-code-agent --parse-logs <logfile>

# 截图诊断
my-code-agent --diagnose <screenshot.png>

# 查看缓存统计
my-code-agent --cache-stats

# 导出追踪数据
my-code-agent --export-traces
```

---

## 智能体能做什么

| 能力 | 示例指令 |
|------|----------|
| **创建文件** | `创建一个 hello.py 文件，打印 Hello World` |
| **读写文件** | `读取 config.py 的内容` |
| **编辑文件** | `将 utils.py 中的 foo 函数重命名为 bar` |
| **搜索代码** | `搜索所有包含 TODO 的文件` |
| **执行命令** | `运行 python hello.py` |
| **Git 操作** | 每次写操作自动创建检查点，支持回滚 |
| **分析日志** | `分析这段 CI 日志：...` |
| **执行 Skill** | 自动匹配并执行注册的 Executable Skill |
| **状态机编排** | 复杂任务自动分解为 Plan→Act→Observe→Reflect 循环 |
| **多 Agent 协作** | 复杂任务自动组建 Planner/Coder/Reviewer/Executor 团队 |

---

## 八层架构设计

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                                                                            │
│  CLI (Rich) / TUI (Textual) / Welcome Screen / ASCII Art / Terminal Dashboard                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │  Welcome Screen (ASCII Art + Status Dashboard)                                                            │    │
│  │  Streaming Response (Textual background thread)                                                           │    │
│  │  Interactive Prompt (Textual.Input / stdin)                                                               │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────────────────────┘    │
│  __main__.py · welcome.py · tui/app.py · tui/diff_view.py · tui/confirm.py                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────────────────────────────────────────┐
│                   Orchestration Layer                                                                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐                              │
│  │ Skill Router │ │ Complexity   │ │ Conversation │ │ SafetyGuard  │ │ Token    │                              │
│  │ + Matcher    │ │ Planner      │ │ Memory       │ │ (Path/Cmd/   │ │ Budget   │                              │
│  │              │ │ (Simple/     │ │ Manager      │ │ Secret/      │ │ Tracker  │                              │
│  │              │ │  Moderate/   │ │              │ │ Output       │ │          │                              │
│  │              │ │  Complex)    │ │              │ │ Truncation)  │ │          │                              │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬─────┘                              │
│         └────────────────┼────────────────┼────────────────┼────────────────┼──────────────────┘               │
│              ┌───────────▼────────────────▼────────────────▼─────────────────┐                                 │
│              │   LLM Abstraction Layer v2                                     │                                 │
│              │  LiteLLM Gateway · Multi-provider · Tier Router · Fallback    │                                 │
│              │  Semantic Cache (SHA-256 + BM25)  ·  Multi-Modal (Vision)     │                                 │
│              └───────────────────────────┬────────────────────────────────────┘                                 │
│  agent.py · safety.py · config.py · semantic_cache.py · perception.py                                          │
└──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┘
                                           │ MCP Protocol (FastMCP / stdio / SSE)
                  ┌────────────────────────┼────────────────────────┐
                  ▼                        ▼                        ▼
   ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
   │  Codebase MCP Server     │  │   Skills MCP Server      │  │  External MCP Servers    │
   │  (Tools + Resources)     │  │  (Exec + Eval + Distill) │  │  (DB / Web / API)        │
   │                          │  │                          │  │                          │
   │  read_file               │  │  list_skills             │  │  (user-provided)         │
   │  write_file              │  │  execute_skill           │  │                          │
   │  search_replace          │  │  validate_skill          │  │                          │
   │  search_symbols          │  │  run_evals               │  │                          │
   │  rg_search               │  │  (hot reload via mtime)  │  │                          │
   │  execute_command         │  └──────────┬───────────────┘  └──────────────────────────┘
   │  git_checkpoint          │             │
   │  expand_directory        │             │
   │  search_by_structure     │             │
   │  get_module_boundary     │             │
   │  graph_query             │             │
   │  graph_analytics         │             │
   │  failure_report          │             │
   │                          │             │
   │  Resources:              │             │
   │  symbol:// · context://  │             │
   │  workspace:// · search://│             │
   │  tree:// · analytics://  │             │
   │  failures://             │             │
   └──────────┬───────────────┘             │
              │                              │
   ┌──────────▼──────────────────────────────▼───────────────────────────────────────────────────────┐
   │           Workspace Intelligence Layer v2                                                        │
   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────┐           │
   │  │ Semantic Dir │ │ Dependency   │ │ Convention   │ │ Semantic Cache + RAG Index   │           │
   │  │ Tree (3-Lay) │ │ Graph Engine │ │ Learner v2   │ │ (SHA-256 exact + BM25 fuzzy) │           │
   │  │ · config     │ │ · tree-sitter│ │ · auto infer │ │                              │           │
   │  │ · naming     │ │ · madge DAG  │ │ · confidence │ │                              │           │
   │  │ · content    │ │ · 4 views    │ │ · save YAML  │ │                              │           │
   │  │              │ │ · cycle det. │ │              │ │                              │           │
   │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────────────┬───────────────┘           │
   │         └────────────────┼────────────────┼────────────────────────┼──────────────────────────┘   │
   │              dep_engine.py: FailureTracker · UsageAnalytics · AutoDeprecation                      │
   │  semantic_tree.py · graph_projection.py · convention_learner.py · dep_engine.py · semantic_cache.py│
   └──────────────────────────┼───────────────────────────────────────────────────────────────────────┘
                              │
   ┌──────────────────────────▼───────────────────────────────────────────────────────────────────────┐
   │           Execution Sandbox v2                                                                     │
   │  ┌──────────────────────────────┐  ┌──────────────────────────────┐  ┌──────────────────────┐  │
   │  │  Process Isolation           │  │  AST Whitelist               │  │  Timeout Circuit     │  │
   │  │  · workspace root chroot     │  │  · 100+ node types allowed   │  │  Breaker             │  │
   │  │  · path validation           │  │  · dangerous op regex block  │  │  · subprocess.run()  │  │
   │  │  · no parent escape          │  │  · os/sys/subprocess blocked │  │  · configurable TTL  │  │
   │  │  · blocked command patterns  │  │  · SyntaxError detection     │  │  · hard kill on TO   │  │
   │  └──────────────┬───────────────┘  └──────────────┬───────────────┘  └──────────┬───────────┘  │
   │                 └───────────────┬──────────────────┼─────────────────────────────┘             │
   │  ┌──────────────────────────────▼──────────────────▼──────────────────────────────┐           │
   │  │  Resource Budget · Span Tracing · Safe Read/Write                              │           │
   │  │  · max_output_bytes (100KB)  · span hooks for OTel   · path.resolve() guard   │           │
   │  │  · max_file_ops (50)         · Phoenix JSON export   · restricted globals     │           │
   │  │  · max_subprocesses (5)      · InMemoryBuffer        · env sanitization       │           │
   │  └──────────────────────────────────────────────────────────────────────────────┘           │
   │  sandbox.py · safety.py                                                                      │
   └──────────────────────────────────────────────────────────────────────────────────────────────┘
                              │
   ┌──────────────────────────▼───────────────────────────────────────────────────────────────────────┐
   │           Self-Evolution Engine v2 (Auto-Distill Pipeline)                                       │
   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐             │
   │  │ Trace Miner  │ │ Skill Draft  │ │ Eval Gate    │ │ Human Review + Approval    │             │
   │  │ + Clusterer  │ │ Generator    │ │ (≥95% pass)  │ │ Workflow                   │             │
   │  │              │ │              │ │              │ │                            │             │
   │  │ · Jaccard    │ │ · LLM gen    │ │ · parse .sk  │ │ · drafts/  → pending/      │             │
   │  │   similarity │ │   .skill.md  │ │ · exec code  │ │ · approved/  → published/  │             │
   │  │ · median     │ │ · eval cases │ │ · 95% thresh │ │ · rejected/                │             │
   │  │   trajectory │ │ · fallback   │ │ · safety     │ │ · generate review diff     │             │
   │  │ · 3+ traces  │ │ · JSONL save │ │   check      │ │                            │             │
   │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────────────────────┘             │
   │  distill/models.py · distill/collector.py · distill/miner.py · distill/draft_generator.py       │
   │  distill/eval_gate.py · distill/human_review.py · distill/pipeline.py                          │
   └────────────────────────────────────────────────────────────────────────────────────────────────┘
                              ▲
   ┌──────────────────────────┴─────────────────────────────────────────────────────────────────────┐
   │         Multi-Modal Perception Layer                                                           │
   │  ┌──────────────┐ ┌──────────────────────────┐ ┌──────────────────────────────┐               │
   │  │ Vision       │ │ Log Parser               │ │ Audio/Video (planned)        │               │
   │  │              │ │                          │ │                              │               │
   │  │ · screenshot │ │ · structured log parse   │ │ · Whisper integration        │               │
   │  │   analysis   │ │ · CI failure patterns    │ │ · demo review                │               │
   │  │ · bug detect │ │ · severity breakdown     │ │                              │               │
   │  │ · UX issues  │ │ · top error modules      │ │                              │               │
   │  │ · fix sugge. │ │ · LLM deep analysis      │ │                              │               │
   │  └──────────────┘ └──────────────────────────┘ └──────────────────────────────┘               │
   │  perception.py                                                                                 │
   └────────────────────────────────────────────────────────────────────────────────────────────────┘
                              │
   ┌──────────────────────────▼───────────────────────────────────────────────────────────────────────┐
   │           Advanced Orchestration (P3 — LangGraph + Multi-Agent + Tracing)                        │
   │  ┌──────────────────────────────┐  ┌──────────────────────────────┐  ┌──────────────────────┐  │
   │  │  State Machine               │  │  Multi-Agent Collaboration   │  │  OpenTelemetry       │  │
   │  │  (Plan·Act·Observe·Reflect)  │  │                              │  │  Tracing             │  │
   │  │                              │  │  · 4 Roles:                  │  │                      │  │
   │  │  · AgentState typed schema   │  │    Planner → Coder →         │  │  · Span context mgr  │  │
   │  │  · NodeFunc / EdgeRouter     │  │    Reviewer → Executor       │  │  · Phoenix JSON exp. │  │
   │  │  · Conditional edges         │  │  · MessageBus (pub/sub)      │  │  · InMemoryBuffer    │  │
   │  │  · Infinite loop detection   │  │  · Consensus voting          │  │  · React step hooks  │  │
   │  │  · LLM-powered act/reflect   │  │  · TeamResult + report       │  │  · graceful fallback │  │
   │  └──────────────────────────────┘  └──────────────────────────────┘  └──────────────────────┘  │
   │  state_machine.py · multi_agent.py · tracing.py                                                │
   └────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
src/my_code_agent/
├── __init__.py                    # 包入口
├── __main__.py                    # CLI/TUI 入口，模式路由（--cli/--welcome/--distill 等）
├── agent.py                       # 核心 CodingAgent — ReAct 循环 + 状态机 + 多 Agent + 语义缓存
├── config.py                      # pydantic-settings 配置（模型路由/沙箱/缓存/追踪/多模态等）
├── safety.py                      # 安全防护 — 路径校验/命令黑名单/密钥脱敏/输出截断
├── context.py                     # 上下文引擎 — tree-sitter AST 符号索引 + ripgrep 全文检索
├── semantic_tree.py               # 语义目录树 — 三层标注（配置/命名/内容），角色分类
├── semantic_tree_tools.py         # 目录树 MCP 工具 — expand_directory / search_by_structure / get_module_boundary
├── graph_projection.py            # 代码图谱投影 — 物理/模块/依赖/变更四视图，tree-sitter 依赖解析
├── dep_engine.py                  # 依赖分析引擎 — FailureTracker / UsageAnalytics / AutoDeprecation
├── convention_learner.py          # 约定学习者 — 自动推断 feature_dirs / test_pattern / source_prefix
├── semantic_cache.py              # 语义缓存 — SHA-256 精确匹配 + BM25 模糊语义索引
├── perception.py                  # 多模态感知 — Vision 截图诊断 + Log Parser CI/CD 日志分析
├── sandbox.py                     # 执行沙箱 v2 — AST 白名单 + 超时熔断 + 资源预算 + 安全读写
├── tracing.py                     # OpenTelemetry 追踪 — Span 系统 + Phoenix JSON 导出 + 内存缓冲
├── state_machine.py               # LangGraph 风格状态机 — Plan/Act/Observe/Reflect 节点 + 条件边
├── multi_agent.py                 # 多 Agent 协作 — 4 角色（Planner/Coder/Reviewer/Executor）+ 消息总线
├── tools/                         # 工具模块（被 ReAct 循环和 MCP 共用）
│   ├── __init__.py                # 工具注册表 — 名称到可调用的映射
│   ├── file_ops.py                # 文件操作 — 安全读/写/search_replace
│   ├── search.py                  # 代码搜索 — 符号搜索 + ripgrep 全文检索
│   ├── shell.py                   # 命令执行 — 受限 shell 执行 + 输出截断
│   └── git_ops.py                 # Git 操作 — 自动检查点 commit
├── tui/                           # 终端图形界面（Textual TUI）
│   ├── __init__.py
│   ├── app.py                     # TUI 主应用 — 聊天气泡/流式响应/Token 统计
│   ├── diff_view.py               # Diff 预览组件
│   └── confirm.py                 # 确认对话框
├── welcome.py                     # 欢迎画面 — ASCII Art + 快速开始 + 状态栏
├── skills/                        # Executable Skill 系统
│   ├── __init__.py                # 包入口
│   ├── models.py                  # Skill 数据模型 — SkillDefinition / TypeSignature / EvalCase
│   ├── parser.py                  # Skill 解析器 — .skill.md (YAML+代码块) + 旧版 skills.json
│   ├── validator.py               # 四阶段验证 — 类型/结构/安全/AST 语法
│   ├── executor.py                # 沙箱执行器 — 受限 globals + 输入校验 + Eval 通过率
│   └── registry.py                # 注册表 — 目录发现 + mtime 热更新 + 守护线程
├── mcp/                           # MCP (Model Context Protocol) 层
│   ├── __init__.py                # 包入口，统一导出
│   ├── wrappers.py                # MCP 工具包装器 — 将 agent 工具转为 MCP 服务
│   ├── skills_server.py           # Skills MCP 服务器 — list/execute/validate/run_evals
│   ├── bridge.py                  # MCP Bridge — 进程内桥接 ReAct 循环与工具注册表
│   ├── resources.py               # MCP 资源注册 — symbol:// / context:// / workspace:// / tree:// 等 URI
│   ├── skill_matcher.py           # Skill 匹配器 — 关键词匹配 + 置信度评分
│   ├── skill_executor.py          # Skill 执行器 — 步骤序列执行
│   └── prompts.py                 # MCP 提示词模板
└── distill/                       # Auto-Distill Pipeline — 从轨迹到 Skill 的自进化流水线
    ├── __init__.py                # 包入口，统一导出
    ├── models.py                  # 数据模型 — TraceStep / SessionTrace / TraceCluster / SkillDraft
    ├── collector.py               # Trace 收集器 — ReAct 步骤 JSONL 持久化
    ├── miner.py                   # Trace 挖掘器 — Jaccard 相似度聚类 + 中位轨迹提取
    ├── draft_generator.py         # Draft 生成器 — LiteLLM 生成 .skill.md + fallback
    ├── eval_gate.py               # Eval 门禁 — 自动运行 Eval 用例，95% 通过率门槛
    ├── human_review.py            # 人工审核 — 目录式 PR 风格审核工作流
    └── pipeline.py                # 管道编排器 — 五阶段串联 + one-shot/daemon 双模式

tests/
├── __init__.py
├── evals/                         # 评估用例目录
├── test_context.py                # 上下文引擎测试
├── test_convention_learner.py     # 约定学习者测试
├── test_dep_engine.py             # 依赖分析引擎测试
├── test_graph_projection.py       # 图谱投影测试
├── test_safety.py                 # 安全模块测试
├── test_semantic_tree.py          # 语义目录树测试
├── test_semantic_cache.py         # 语义缓存测试（BM25/精确匹配/持久化）
├── test_perception.py             # 多模态感知测试（LogParser/Vision）
├── test_sandbox.py                # 执行沙箱测试（AST 白名单/命令拦截/资源限制）
├── test_tracing.py                # 追踪系统测试（Span/JSON 导出/内存缓冲）
├── test_state_machine.py          # 状态机测试（节点/条件边/环检测）
├── test_multi_agent.py            # 多 Agent 测试（消息总线/共识投票/团队编排）
├── test_skill_models.py           # Skill 数据模型测试
├── test_skill_parser.py           # Skill 解析器测试
├── test_skill_validator.py        # Skill 验证器测试
├── test_skill_executor.py         # Skill 执行器测试
├── test_skill_registry.py         # Skill 注册表测试
├── test_skills_server.py          # Skills MCP 服务器测试
└── test_distill/                  # Auto-Distill Pipeline 测试
    ├── __init__.py
    ├── test_models.py             # 数据模型测试
    ├── test_collector.py          # Trace 收集器测试
    ├── test_miner.py              # Trace 挖掘器测试
    ├── test_draft_generator.py    # Draft 生成器测试
    ├── test_eval_gate.py          # Eval 门禁测试
    ├── test_human_review.py       # 人工审核测试
    └── test_pipeline.py           # 管道编排器测试
```

---

## 安全特性

- **路径逃逸防护** — 所有文件操作限制在 workspace 目录内，`Path.resolve().relative_to(workspace)` 校验
- **敏感文件保护** — 自动拦截 `.env`、`.key`、`credentials`、`.pem`、`id_rsa` 等文件
- **命令黑名单** — 阻止 `rm -rf`、`curl|bash`、`chmod 777`、`mkfs`、管道到 shell 等危险命令
- **AST 白名单** — 代码执行前通过 AST 节点类型白名单校验，拒绝 `os`/`sys`/`subprocess`/`exec` 等危险操作
- **超时熔断** — 命令执行超时自动终止，可配置超时阈值
- **资源预算** — 最大输出字节数、最大文件操作数、最大子进程数限制
- **密钥脱敏** — 发送请求前自动扫描并替换 API Key 类模式为 `[REDACTED]`
- **Git 检查点** — 每次写操作前自动 commit，支持 `git revert` 回滚

---

## 常见问题

### Q: `.env` 文件应该放在哪里？

放在你**当前要写代码的项目目录**。智能体会从当前工作目录读取 `.env`。每个项目可以有不同的 API Key 和模型配置。

### Q: 可以同时使用多个 LLM 提供商吗？

可以。将 `PRIMARY_MODEL`、`SECONDARY_MODEL`、`LOCAL_MODEL` 分别指向不同的 API 地址即可。LiteLLM 支持 100+ 模型提供商。

### Q: Token 用完了怎么办？

智能体会在 Token 用量超过 `max_session_tokens`（默认 100,000）时暂停并提示你确认是否继续。你可以修改 `.env` 中的 `max_session_tokens` 调整限制。

### Q: 智能体写错了文件怎么办？

不用担心。智能体每次写操作前会自动创建 Git 检查点（commit），你可以随时用 `git revert` 回滚：

```bash
git revert HEAD
```

### Q: 什么是 Executable Skill？

Executable Skill 是一种结构化的技能定义格式（`.skill.md`），包含 YAML frontmatter（类型签名、结构约束、安全规则、Eval 用例）和 Python code_block（可执行代码）。它不是给 LLM 读的散文，而是**带类型、带测试、可验证的可执行程序单元**。

### Q: Auto-Distill 是什么？

Auto-Distill 是从成功用户会话轨迹自动提炼新 Skill 的流水线：
1. **Trace 收集** — ReAct 循环自动记录每一步
2. **聚类挖掘** — Jaccard 相似度将相似轨迹分组
3. **Draft 生成** — LLM 将聚类模式转化为 `.skill.md`
4. **Eval 门禁** — 自动运行 Eval 用例，通过率 ≥95% 才通过
5. **人工审核** — PR 风格审核，通过后注册到 Skill 注册表

### Q: 如何查看语义缓存命中情况？

运行 `my-code-agent --cache-stats` 可查看缓存条目数、BM25 文档数、总命中次数。

### Q: 如何分析 CI/CD 日志？

运行 `my-code-agent --parse-logs <logfile>` 即可结构化解析日志，查看失败模式和严重度分布。

---

## 测试

```bash
pytest tests/ -v
```

**391 tests pass, 1 skipped** — 覆盖所有 P1/P2/P3 模块。

---

## 开发

```bash
# 克隆仓库
git clone https://github.com/hanmou666529/my-code-agent.git
cd my-code-agent

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码格式化
ruff check .
ruff format .
```

---

## 开源参考

- [Aider](https://github.com/Aider-AI/aider) — Repomap 设计、Edit Format、Git 集成
- [Smolagents](https://github.com/huggingface/smolagents) — 极简 Agent 循环、Tool 定义规范
- [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) — TUI 交互、安全确认流程
- [SWE-agent](https://github.com/princeton-nlp/SWE-agent) — ACI 设计、Eval 体系
- [LangGraph](https://github.com/langchain-ai/langgraph) — 状态机编排思想
- [Arize Phoenix](https://github.com/Arize-ai/phoenix) — Agent 追踪可视化
