# Python 终端编程智能体 (Coding Agent) 开发指南
> **定位**：面向个人开发者的轻量级、本地化、低成本 AI 编程助手  
> **技术栈**：Python + Textual/Rich + Tree-sitter + LiteLLM  
> **版本**：v1.0 (2026-06)

---

## 1. 核心设计理念

面向个人开发者的 Coding Agent 与企业级产品有本质区别，必须遵循以下原则：

-   **零外部依赖**：无需向量数据库、Redis、Docker，单进程启动
-   **成本可控**：内置模型路由，简单任务自动降级到小模型/本地模型
-   **安全优先**：轻量级沙箱 + Git 检查点 + 交互式确认，防止误操作
-   **精准上下文**：用 AST + ripgrep 替代 RAG，代码修改准确率 >95%
-   **开箱即用**：`pip install` 一键安装，配置项 <10 个

---

## 2. 系统架构

```text
┌─────────────────────────────────────────────┐
│              Terminal UI (Textual/Rich)       │
│  流式Markdown · Diff预览 · 权限确认 · Token统计 │
├─────────────────────────────────────────────┤
│           Safety & Guardrails Layer          │
│  路径校验 · 命令黑名单 · Prompt注入防护 · 预算控制 │
├─────────────────────────────────────────────┤
│            Lightweight ReAct Loop            │
│  Extended Thinking · 自我纠错 · 模型智能路由    │
├──────────┬──────────┬───────────┬───────────┤
│ File Ops │ Search   │ Shell     │ Context   │
│ edit/read│ ripgrep  │ restricted│ AST+Git   │
└──────────┴──────────┴───────────┴───────────┘
         ↕ LiteLLM (统一模型接口)
┌─────────────────────────────────────────────┐
│  Claude Sonnet · Qwen3-Coder · Ollama Local  │
└─────────────────────────────────────────────┘

```
## 3. 技术选型详解
| 模块 | 推荐方案 | 备选方案 | 选择理由 |
| :--- | :--- | :--- | :--- |
| Agent 循环 | 自研 ReAct (200行) | smolagents | 个人项目无需 LangGraph 复杂度 |
| 终端 UI | Textual | Rich + Prompt Toolkit | TUI 天花板，支持异步渲染 |
| 代码索引 | tree-sitter-python + ripgrep | jedi / ast 标准库 | 语法感知精准检索，零配置 |
| LLM 接入 | litellm | openai SDK | 统一接口，一键切换 100+ 模型 |
| 安全防护 | 路径校验 + Git 检查点 | RestrictedPython | 轻量够用，无性能损耗 |
| 配置管理 | pydantic-settings | tomllib | 类型安全，支持环境变量覆盖 |
| 打包分发 | uv / hatch | setuptools | 现代 Python 工具链，秒级安装 |

## 4. 核心模块实现
4.1 代码上下文引擎 (Context Engine)
核心思想：不将整个仓库塞入 Prompt，而是按需构建精准上下文。
4.2 安全文件编辑工具
核心原则：禁止全文重写，强制搜索替换 + 唯一匹配校验。
4.3 轻量级 ReAct 循环
4.4 模型路由策略


## 5. 安全防护清单

| 层级 | 措施 | 实现方式 |
| :--- | :--- | :--- |
| 文件安全 | 路径遍历防护 | `Path.resolve().is_relative_to(workspace)` |
| 文件安全 | 敏感文件只读 | 正则匹配 `.env`, `.key`, `credentials`, `/etc/` |
| 命令安全 | 危险命令拦截 | 黑名单: `rm -rf`, `curl\|bash`, `chmod 777`, `mkfs` |
| 命令安全 | 输出截断 | 命令输出 >10KB 自动截断，防止 Token 爆炸 |
| Prompt 安全 | 内容隔离 | 文件内容用 `<file_content>` XML 标签包裹 |
| 成本控制 | Token 预算 | 单次会话上限，超限暂停并提示用户确认续期 |
| 可恢复性 | Git 检查点 | 每次写操作前自动 commit，支持 `git revert` |
| API 安全 | 密钥脱敏 | 发送前正则扫描并替换为 `[REDACTED]` |

## 6. 项目结构模板
my-code-agent/
├── pyproject.toml          # uv/hatch 项目配置
├── src/
│   └── my_code_agent/
│       ├── __init__.py
│       ├── __main__.py     # CLI 入口: python -m my_code_agent
│       ├── agent.py        # ReAct 循环 + 模型路由
│       ├── config.py       # pydantic-settings 配置
│       ├── context.py      # Tree-sitter + ripgrep 上下文引擎
│       ├── safety.py       # 安全防护模块
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── file_ops.py
│       │   ├── search.py
│       │   ├── shell.py
│       │   └── git_ops.py
│       └── tui/
│           ├── __init__.py
│           ├── app.py      # Textual App 主界面
│           ├── diff_view.py
│           └── confirm.py
├── tests/
│   ├── test_context.py
│   ├── test_safety.py
│   └── evals/              # 自建评测集
│       ├── fixtures/
│       └── test_tasks.py
└── README.md

## 7. 四周 MVP 开发路线
| 周次 | 里程碑 | 验收标准 |
| :--- | :--- | :--- |
| Week 1 | 核心循环跑通 | 终端对话 → 读写文件 → 执行命令，能完成一个简单重构任务 |
| Week 2 | 代码感知 + 安全 | Tree-sitter 索引生效；编辑有 Diff 预览和确认；路径逃逸被拦截 |
| Week 3 | TUI + 体验 | Rich/Textual 流式渲染；模型路由生效；Token 统计显示；错误自动重试 |
| Week 4 | 测试 + 发布 | 20 个评测任务通过率 >80%；`pip install` 可用；README 含演示 GIF |

## 8. 开源参考项目

| 项目 | 学习重点 | 链接 |
| :--- | :--- | :--- |
| Aider | Repomap 设计、Edit Format、Git 集成 | github.com/Aider-AI/aider |
| Smolagents | 极简 Agent 循环、Tool 定义规范 | github.com/huggingface/smolagents |
| Open Interpreter | TUI 交互、安全确认流程、多模态支持 | github.com/OpenInterpreter/open-interpreter |
| SWE-agent | ACI 设计、Eval 体系、Agent-环境接口 | github.com/princeton-nlp/SWE-agent |
| Claude Code Docs | Tool 定义最佳实践、MCP 集成、安全模型 | docs.anthropic.com/claude-code |

## 9. 常见陷阱与避坑指南
❌ 过早引入 Multi-Agent：单 Agent + 好工具足以应对 90% 个人编程场景。Multi-Agent 增加调试难度和 Token 成本。
❌ 过度追求代码感知：代码是结构化数据，语法相关性 ≠ 语义相似度。Tree-sitter 生效率 <90%。
❌ 用向量 RAG 做代码检索：代码是结构化数据，语义相似度 ≠ 语法相关性。Tree-sitter + ripgrep 永远优先。
❌ 让 LLM 自由写 Shell 命令：必须白名单/黑名单 + 输出截断。一条 find / -name "*.log" -delete 就能毁掉一天。
❌ 忽略 Token 监控：个人开发者没有企业预算。从第一天就加 Token 计数和费用估算显示。
❌ 追求完美再开源：Week 2 就可以发 Alpha 版。社区反馈比闭门造车快 10 倍。
✅ 拥抱 MCP 协议：即使现在只用内置工具，也按 MCP 规范定义接口。未来接入外部生态零改造。