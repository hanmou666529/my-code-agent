# My-Code-Agent

> 轻量级本地化 AI 编程助手 — 零外部依赖，单进程启动，模型智能路由，安全文件编辑

一个面向个人开发者的终端 AI 编码助手。无需向量数据库、Redis 或 Docker，安装后直接运行。内置模型路由策略：简单任务自动使用轻量模型，复杂任务智能调用大模型，帮助你控制 API 成本。

## 核心功能

- **ReAct 循环** — 自动分析任务、读写文件、执行命令、自我纠错，最多 25 步自动停止
- **模型智能路由** — 根据任务复杂度自动选择模型：简单任务走本地/轻量模型，复杂任务走 Claude/Qwen
- **安全文件编辑** — 基于 search/replace 的精准修改，禁止全文重写，确保修改可控
- **代码感知上下文** — 使用 tree-sitter 解析 AST 索引代码符号，ripgrep 检索文件内容，精准注入上下文
- **多层安全防护** — 路径逃逸检测、敏感文件拦截、命令黑名单、输出截断、密钥脱敏
- **Git 自动检查点** — 每次写操作前自动 commit，随时可用 `git revert` 回滚
- **终端图形界面** — Textual TUI 支持流式渲染 Markdown、Diff 预览、Token 统计

## 系统要求

- Python 3.11+
- pip（包管理器）
- Git（可选，用于 Git 检查点功能）

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

## 配置

### 第一步：获取 API Key

前往你的 LLM 提供商后台获取 API Key，例如 Mimomo：[https://www.xiaomimimo.com](https://www.xiaomimimo.com)

### 第二步：创建 .env 文件

在你**准备写代码的项目目录**中创建 `.env` 文件。智能体会在当前目录读取它。

例如你想在 `E:\Projects\MyApp` 目录下使用智能体：

```bash
# 进入你的项目目录
cd E:\Projects\MyApp

# 创建 .env 文件
```

用你喜欢的编辑器打开 `.env`，填入以下内容：

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
| `ANTHROPIC_API_KEY` | ✅ | 你的 API 密钥 | `sk-ckstzdxo2wzgb95zsliqoe1bl1213t8wzrbx0t5nswnidzkg` |
| `API_BASE` | ✅ | LLM API 端点地址 | `https://api.xiaomimimo.com/anthropic` |
| `PRIMARY_MODEL` | ❌ | 复杂任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `SECONDARY_MODEL` | ❌ | 中等复杂度任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `LOCAL_MODEL` | ❌ | 简单任务使用的模型 | `anthropic/mimo-v2.5-pro` |
| `max_session_tokens` | ❌ | 会话 Token 上限 | `100000` |

**默认值：** 如果省略 `PRIMARY_MODEL`、`SECONDARY_MODEL`、`LOCAL_MODEL`，智能体将使用 LiteLLM 内置的默认模型。建议明确配置以匹配你的 API 提供商。

### 多模型路由示例

如果你想让简单任务和复杂任务使用不同的模型：

```ini
# 简单任务用轻量模型（节省费用）
LOCAL_MODEL=anthropic/mimo-v2.5-pro

# 复杂任务用高质量模型
PRIMARY_MODEL=anthropic/mimo-v2.5-pro
```

智能体会自动根据任务复杂度选择模型，简单格式化、创建文件等任务走轻量模型，复杂重构、架构设计等任务走高质量模型。

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
# 安装后
my-code-agent --cli

# 或从源码运行
python -m my_code_agent --cli
```

进入 CLI 后直接输入任务描述，回车即可：

```
Coding Agent CLI (Ctrl+C to quit)
Type a task, or 'quit' to exit:

> 在 utils.py 中创建一个函数，接收用户名字典，按姓氏排序后返回

```

### 智能体能做什么

| 能力 | 示例指令 |
|------|----------|
| **创建文件** | `创建一个 hello.py 文件，打印 Hello World` |
| **读写文件** | `读取 config.py 的内容` |
| **编辑文件** | `将 utils.py 中的 foo 函数重命名为 bar` |
| **搜索代码** | `搜索所有包含 TODO 的文件` |
| **执行命令** | `运行 python hello.py` |
| **Git 操作** | 每次写操作自动创建检查点，支持回滚 |

## 架构

```
┌─────────────────────────────────────────────┐
│           Terminal UI (Textual)              │
│  流式 Markdown · Diff 预览 · Token 统计       │
├─────────────────────────────────────────────┤
│           Safety & Guardrails Layer          │
│  路径校验 · 命令黑名单 · Prompt 注入防护      │
├─────────────────────────────────────────────┤
│            Lightweight ReAct Loop            │
│  自我纠错 · 模型智能路由                      │
├──────────┬──────────┬───────────┬───────────┤
│ File Ops │ Search   │ Shell     │ Git       │
│ 安全读写  │ ripgrep  │ 受限执行   │ 检查点    │
└──────────┴──────────┴───────────┴───────────┘
         ↕ LiteLLM (统一模型接口)
┌─────────────────────────────────────────────┐
│  Claude · Qwen3-Coder · Ollama Local         │
└─────────────────────────────────────────────┘
```

## 安全特性

- **路径逃逸防护** — 所有文件操作限制在 workspace 目录内，`Path.resolve().relative_to(workspace)` 校验
- **敏感文件保护** — 自动拦截 `.env`、`.key`、`credentials`、`.pem`、`id_rsa` 等文件
- **命令黑名单** — 阻止 `rm -rf`、`curl|bash`、`chmod 777`、`mkfs` 等危险命令
- **输出截断** — 命令输出超过 10 KB 自动截断，防止 Token 爆炸
- **密钥脱敏** — 发送请求前自动扫描并替换 API Key 类模式为 `[REDACTED]`
- **Git 检查点** — 每次写操作前自动 commit，支持 `git revert` 回滚

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

## 测试

```bash
pytest tests/ -v
```

## 项目结构

```
src/my_code_agent/
├── __init__.py          # 包入口
├── __main__.py          # CLI / TUI 入口
├── agent.py             # ReAct 循环 + 模型路由
├── config.py            # pydantic-settings 配置
├── context.py           # tree-sitter + ripgrep 上下文引擎
├── safety.py            # 安全防护模块
├── tools/               # 工具模块
│   ├── file_ops.py      # 安全读写 + search_replace
│   ├── search.py        # 代码搜索
│   ├── shell.py         # 受限命令执行
│   └── git_ops.py       # Git 检查点
└── tui/                 # 终端界面
    ├── app.py           # Textual 主界面
    ├── diff_view.py     # Diff 预览组件
    └── confirm.py       # 确认对话框

tests/
├── test_context.py      # 上下文引擎测试
└── test_safety.py       # 安全模块测试
```

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

## 开源参考

- [Aider](https://github.com/Aider-AI/aider) — Repomap 设计、Edit Format、Git 集成
- [Smolagents](https://github.com/huggingface/smolagents) — 极简 Agent 循环、Tool 定义规范
- [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) — TUI 交互、安全确认流程
- [SWE-agent](https://github.com/princeton-nlp/SWE-agent) — ACI 设计、Eval 体系
