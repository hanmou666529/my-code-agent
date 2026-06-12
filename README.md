# my-code-agent

轻量级本地化 AI 编程助手。零外部依赖，单进程启动，支持模型路由（Claude > Qwen > Ollama）。

## 安装

### 方法一：pip 安装（推荐）

```bash
pip install .
# 或直接安装后运行
my-code-agent --cli
```

### 方法二：从源码运行

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 安装开发依赖
pip install -e ".[dev]"
```

## 配置

将 `.env.example` 复制为 `.env` 并填入你的 API Key：

```bash
cp .env.example .env
```

### 环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `ANTHROPIC_API_KEY` | 你的 API Key | `sk-ant-...` |
| `API_BASE` | API 端点地址 | `https://api.xiaomimimo.com/anthropic` |
| `PRIMARY_MODEL` | 主模型名称 | `anthropic/mimo-v2.5-pro` |
| `SECONDARY_MODEL` | 次模型名称 | `anthropic/mimo-v2.5-pro` |
| `LOCAL_MODEL` | 本地模型名称 | `anthropic/mimo-v2.5-pro` |

### .env 文件放置

智能体运行时从 **当前工作目录（cwd）** 读取 `.env` 文件。你可以在任意想写代码的目录创建 `.env`：

```bash
# 进入你的项目目录
cd E:\Users\MyProject

# 创建 .env 文件并填入配置
# 然后启动智能体
my-code-agent --cli

# 智能体会在此目录（E:\Users\MyProject）读写文件、创建 Git 检查点等
```

## 使用

### TUI 模式（推荐）

```bash
# 源码运行
python -m my_code_agent

# 安装后
my-code-agent
```

### CLI 模式（命令行交互）

```bash
# 源码运行
python -m my_code_agent --cli

# 安装后
my-code-agent --cli
```

CLI 模式下输入任务描述，Agent 会自动分析意图、读写文件、执行命令并返回结果。

## 架构

```
┌─────────────────────────────────────────────┐
│           Terminal UI (Textual)              │
│  流式 Markdown · Diff 预览 · Token 统计       │
├─────────────────────────────────────────────┤
│           Safety & Guardrails Layer          │
│  路径校验 · 命令黑名单 · Prompt 注入防护      │
├─────────────────────────────────────────────┤
│            Lightweight ReAct Loop             │
│  自我纠错 · 模型智能路由                      │
├──────────┬──────────┬───────────┬───────────┤
│ File Ops │ Search   │ Shell     │ Git       │
│ 安全读写  │ ripgrep  │ 受限执行   │ 检查点    │
└──────────┴──────────┴───────────┴───────────┘
         ↕ LiteLLM (统一模型接口)
┌─────────────────────────────────────────────┐
│  Claude Sonnet · Qwen3-Coder · Ollama Local  │
└─────────────────────────────────────────────┘
```

## 安全特性

- **路径逃逸防护** — 所有文件操作限制在 workspace 目录内
- **敏感文件保护** — 自动拦截 `.env`、`.key`、`credentials` 等文件
- **命令黑名单** — 阻止 `rm -rf`、`curl|bash`、`chmod 777` 等危险命令
- **输出截断** — 命令输出超过 10 KB 自动截断
- **密钥脱敏** — 发送前自动替换 API Key 模式为 `[REDACTED]`
- **Git 检查点** — 每次写操作前自动 commit，支持 `git revert` 回滚

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
