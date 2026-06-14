# Coding Agent 全栈架构升级技术方案 v3.5 (Final + 2026 H1 Tech Refresh)

> **版本**: v3.5  
> **更新日期**: 2026-06-13  
> **定位**: 具备自进化能力的结构感知型 Coding Agent  
> **核心差异化**: Executable Skills + Auto-Distill Pipeline + Structure-Aware Context + Eval-Gated Quality + Multi-Modal Perception  
> **技术栈刷新**: MCP SDK v1.29+ / LiteLLM 最新 / Anthropic Claude API 最新 / 2026 CLI 最佳实践

---

## 1. 战略定位与差异化壁垒

### 1.1 为什么不是又一个 "Cursor/Claude Code Clone"

当前开源 Agent 普遍采用"静态 Skill MD + 扁平文件索引 + 通用 Prompt"范式，存在三个根本缺陷：
1.  **Skill 是死文本**: 无法自验证、无法绑定工具链、无法保证执行一致性
2.  **不理解项目结构**: 把 Monorepo 当单文件处理，跨模块任务频繁幻觉
3.  **不会自我学习**: 每次失败都归零，无法从历史经验中沉淀新能力

### 1.2 我们的差异化价值主张

> **核心理念**: Skill 不是写给 LLM 读的散文，而是**带类型签名、带测试、带结构感知的可执行程序单元**。Agent 不是被动执行指令的工具，而是能从自身运行轨迹中**自动提炼、验证、发布新技能的自进化系统**。

### 1.3 量化目标

| 指标 | 行业基线 | v3.5 目标 | 差异化来源 |
| :--- | :--- | :--- | :--- |
| 复杂任务成功率 | ~65% | ≥88% | Executable Skill + 结构感知 |
| 跨模块重构准确率 | ~45% | ≥82% | 语义目录树 + 依赖图谱 |
| 新 Skill 产出周期 | 人工 2-3天 | 自动提炼 + 审核 <4h | Auto-Distill Pipeline |
| Skill 执行一致性 | ~70% | ≥95% | Eval-Gated + 代码块验证 |
| Token 效率 | 100% | ≤55% | Structure-Aware Injection |
| 多模态理解 | N/A | ≥80% | 图像/图表/日志感知 |

---

## 2. 总体架构

### 2.1 八层架构模型 (v3.5 新增感知层)

```text
┌──────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                              │
│         CLI (Rich/Textual) / Web UI / IDE Plugin / CI Hook        │
│         ┌────────────────────────────────────────────────────┐    │
│         │  Welcome Screen (ASCII Art + Status Dashboard)     │    │
│         │  Streaming Response (SSE/Ink/Textual)              │    │
│         │  Interactive Prompt (Clack/Textual.Input)          │    │
│         └────────────────────────────────────────────────────┘    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                   Orchestration Layer                              │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐      │
│  │ Skill Router │ │ Planner  │ │ Memory   │ │ Safety     │      │
│  │ + Matcher    │ │ + Decomp │ │ Manager  │ │ Guardrail  │      │
│  └──────┬───────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘      │
│         └──────────────┼────────────┼──────────────┘               │
│              ┌─────────▼────────────▼──────────┐                   │
│              │   LLM Abstraction Layer v2       │                   │
│              │ (Multi-provider/Router/Cache)    │                   │
│              │ + Multi-Modal Support (Vision)   │                   │
│              └──────────────────┬──────────────┘                   │
└────────────────────────────────┼──────────────────────────────────┘
                                 │ MCP Protocol (v1.29+)
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
 ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
 │  Codebase MCP   │  │   Skills MCP    │  │  External MCP   │
 │  Server         │  │   Server        │  │  Servers        │
 │ (Tools+Res+Dir) │  │ (Exec+Eval+Dist)│  │ (DB/Web/API)    │
 └────────┬────────┘  └────────┬────────┘  └─────────────────┘
          │                    │
┌─────────▼────────────────────▼────────────────────────────────┐
│           Workspace Intelligence Layer v2                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │ Semantic Dir │ │ Dependency   │ │ Convention Pattern   │   │
│  │ Tree (3-Lay) │ │ Graph Engine │ │ Learner v2           │   │
│  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘   │
│         └────────────────┼────────────────────┘                │
│              Semantic Cache + RAG Index                        │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│           Execution Sandbox v2                                  │
│    (E2B/Docker/Wasm · Network Isolation · ACL · Tracing)       │
│    + gVisor 容器级隔离 + AST 白名单 + 超时熔断                  │
└────────────────────────────────────────────────────────────────┘
                           ▲
┌─────────────────────────┴─────────────────────────────────────┐
│           Self-Evolution Engine v2                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │ Trace Miner  │ │ Skill Draft  │ │ Eval Gate + Human    │   │
│  │ + Clusterer  │ │ Generator    │ │ Approval Workflow    │   │
│  └──────────────┘ └──────────────┘ └──────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
                           ▲
┌─────────────────────────┴─────────────────────────────────────┐
│         Multi-Modal Perception Layer 🆕 NEW                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │ Vision       │ │ Log Parser   │ │ Audio/Video          │   │
│  │ (Error Screenshot) │ │ (CI/CD Logs) │ │ (Demo Review)    │   │
│  └──────────────┘ └──────────────┘ └──────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 关键变化 (v3.0 → v3.5)

| 变化 | 说明 | 价值 |
| :--- | :--- | :--- |
| **感知层** | 新增 Multi-Modal Perception 层 | 支持截图诊断、日志分析、视频回放 |
| **LLM 抽象层 v2** | 增加 Vision 支持 + Semantic Cache v2 | 多模态输入 + 语义去重减少重复调用 |
| **Convention Learner v2** | 基于 LLM 的隐式模式提取 | 自动推断项目约定，减少手动配置 |
| **RAG Index** | 向量索引 + BM25 混合检索 | 比纯向量检索更精确的代码搜索 |

---

## 3. 核心创新模块详解

### 3.1 Executable Skill 规范 (保持不变，核心差异化)

> *(内容同 v3.0，见原文档第 3.1 节)*

### 3.2 Auto-Distill Pipeline (v2 增强)

#### 从 Trace 到 Skill 的全自动流水线

```text
User Session Traces
        │
        ▼
┌─────────────────┐
│  Trace Miner    │ ← 聚类相似成功轨迹，提取共性步骤
│  + Clusterer    │ ← 识别重复出现的 Tool 调用序列
└────────┬────────┘
         │ Candidate Patterns
         ▼
┌─────────────────┐
│  Skill Draft    │ ← LLM 将模式转化为 Executable Skill MD
│  Generator      │ ← 自动生成 eval cases + structure requirements
└────────┬────────┘
         │ Draft Skill
         ▼
┌─────────────────┐
│  Eval Gate      │ ← 沙箱内自动运行 eval cases
│  (Automated)    │ ← 通过率 ≥95% 才进入下一步
└────────┬────────┘
         │ Passed Skill
         ▼
┌─────────────────┐
│  Human Review   │ ← PR 形式，开发者审核/微调
│  + Approval     │ ← 合并后自动注册到 Skills Registry
└────────┬────────┘
         │ Published Skill
         ▼
   Skills MCP Server (Hot Reload)
```

#### v2 新增：反馈闭环增强

- **失败 Trace → Improvement Suggestion**: Skill 执行失败时，自动生成修复建议并关联到对应 Skill Issue
- **Usage Analytics → Auto-Deprecation**: 连续 30 天未被调用的 Skill 自动标记为候选废弃
- **Version Diff → Regression Test**: Skill 更新时自动对比新旧版本的 eval 结果
- **Multi-Modal Feedback**: 截图/日志作为额外上下文辅助 Skill 调试
- **Cross-Project Generalization**: 跨项目识别通用模式，生成可复用的 Global Skills

### 3.3 Structure-Aware Skill Injection (保持不变)

> *(内容同 v3.0，见原文档第 3.3 节)*

### 3.4 语义化目录树 (v2 增强)

**Layer 1: 语义标注型**
- `.agent/workspace-structure.yaml` 配置 + 自动推断
- `workspace://structure` Resource 输出带角色标签的紧凑树
- 过滤 generated/node_modules/dist 等噪音目录

**Layer 2: 按需展开型**
- `expand_directory(path, depth, filter)` Tool
- `search_by_structure(pattern, role)` Tool
- `get_module_boundary(file_path)` Tool

**Layer 3: 图谱投影型 (Phase 4)**
- 物理视图 / 模块视图 / 依赖视图 / 变更视图
- 基于 Tree-sitter + madge 构建真实 DAG
- 支持 `workspace://tree?view=dependency&focus=auth` URI

**Layer 2.5: 隐式 Convention Learner 🆕 NEW**
- 自动分析项目文件分布、命名模式、导入关系
- 推断 `feature_dirs`、`test_pattern`、`source_prefix` 等约定
- 输出 `.agent/inferred-conventions.yaml`
- 用户可通过 CLI 命令 `agent convention review` 审核/修正

### 3.5 新增：Multi-Modal Perception Layer

| 能力 | 技术实现 | 使用场景 |
| :--- | :--- | :--- |
| **Vision** | Claude Vision / GPT-4V | 截图诊断 UI Bug、错误堆栈截图 |
| **Log Parser** | Regex + LLM 摘要 | CI/CD 日志分析、调试日志解读 |
| **Audio/Video** | Whisper + LLM | 语音指令输入、Demo 视频分析 |

```python
# Vision 能力示例
async def diagnose_screenshot(image_path: Path) -> str:
    """通过视觉分析诊断 UI 问题"""
    response = await anthropic.messages.create(
        model="claude-sonnet-4-5-20260522",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "分析这个截图中的 UI 问题"},
                {
                    "type": "image_url",
                    "image_url": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image_path.read_bytes()).decode(),
                    },
                },
            ],
        }],
    )
    return response.content[0].text
```

### 3.6 LLM Abstraction Layer v2

| 组件 | 推荐方案 | 理由 |
| :--- | :--- | :--- |
| 网关 | **LiteLLM** (latest) | 100+ Provider，内置缓存/限流/路由 |
| 路由策略 | **Complexity-based + Cost-aware** | 简单任务走本地模型，复杂任务走云端 |
| Fallback | **Exponential Backoff + Tier Swap** | 三级模型降级链 |
| Semantic Cache | **LiteLLM Proxy Cache + 自定义 TTL** | 语义相似请求去重 |
| Multi-Modal | **Native Vision Support** | 支持图片/图表输入 |

---

## 4. 技术选型 (2026 H1 刷新)

| 组件 | 推荐方案 | 版本 | 理由 |
| :--- | :--- | :--- | :--- |
| Skill 规范 | 自研 Executable Skill Spec (YAML+MD+Python) | — | 业界无等价物，核心差异化 |
| Auto-Distill | LangGraph Pipeline + GPT-4o-mini | — | 低成本高频提炼 |
| 目录树构建 | Tree-sitter + chokidar + madge | ts>=0.23 | 增量解析 + 真实依赖 |
| MCP SDK | `@modelcontextprotocol/sdk` | v1.29+ | 协议兼容性最佳，支持 SSE/stdio |
| 沙箱 | E2B | — | 秒级启动，原生支持 Tracing |
| 向量库 | Qdrant | — | 高性能过滤，Rust 内核 |
| Tracing | Arize Phoenix (Self-hosted) | — | 开源免费，Agent 专用可视化 |
| LLM 网关 | LiteLLM | latest | 100+ Provider，内置缓存/限流 |
| 编排 | LangGraph | — | 状态机可控，适合复杂 Pipeline |
| Eval 框架 | Braintrust / 自研 | — | 支持自定义断言 + CI 集成 |
| CLI 框架 | **Rich + Textual** | rich>=13.9 / textual>=1.0 | 生产级 TUI，Flexbox 布局 |
| ASCII Art | **rich.text.Text** + 内嵌字体 | — | 零外部依赖，跨平台 |
| 终端样式 | **Rich Console** | — | 内置颜色/表格/面板/Markdown |
| OAuth | **keyring** + `webbrowser` | — | 平台原生安全存储 |

### 4.1 CLI 技术选型详解

**为什么选择 Rich + Textual：**

| 对比项 | Rich + Textual | Ink (React CLI) | Clack |
| :--- | :--- | :--- | :--- |
| 语言 | Python (原生) | Node.js (JSX) | Python |
| 依赖数 | 2 个核心包 | 5+ 包 (Ink + UI + Router) | 1 个 |
| 交互深度 | ★★★★★ | ★★★★★ | ★★★ |
| 学习曲线 | 低 | 中 (需懂 React) | 低 |
| 跨平台 | 完美 | 部分限制 | 完美 |
| 与现有代码复用 | 100% | 需桥接 | 100% |

**结论**: 本项目已有 Rich + Textual 依赖，继续深化使用是最优路径。

---

## 5. 实施路线图

### Phase 1: 基础协议 + 目录树 Layer 1 (Week 1-4)
- MCP SDK 集成 + Codebase Server 基础 Tools
- LLM 抽象层 v2 + LiteLLM 部署
- 语义标注型目录树 + `workspace://structure` Resource
- 现有工具迁移至 MCP
- **交付物**: Agent 可通过 MCP 完成原有功能 + 理解项目架构

### Phase 2: Executable Skills + 目录树 Layer 2 (Week 5-9)
- Executable Skill 规范定义 + Parser + Validator
- Skills MCP Server + 注册/发现/热更新
- Top 5 高频任务封装为 Executable L2 Skills
- 按需展开 Tools (`expand_directory`, `search_by_structure`)
- 执行沙箱 + 基础安全护栏
- **交付物**: 复杂任务成功率 ≥80%，Skill 执行一致性 ≥90%

### Phase 3: Auto-Distill + Eval Gate + 观测 (Week 10-15)
- Trace Miner + Clustering Pipeline
- Skill Draft Generator + Automated Eval Gate
- Human Review Workflow (PR-based)
- OpenTelemetry 全链路 + 仪表盘
- Structure-Aware Skill Injection 引擎
- **交付物**: 首个自动提炼 Skill 上线，Token ↓40%

### Phase 4: 图谱投影 + 自进化闭环 (Week 16+)
- 依赖图引擎 + 多维视图 (Layer 3)
- 失败 Trace → Improvement Suggestion 闭环
- Usage Analytics + Auto-Deprecation
- Multi-Agent 协作
- **交付物**: 跨模块重构准确率 ≥82%，Skill 自进化周期 <4h

### Phase 5: Multi-Modal + CLI 体验增强 (Week 20+) 🆕
- Vision 诊断能力集成
- Log Parser 自动分析 CI/CD 日志
- CLI Welcome Screen 动态 Dashboard
- 语音指令支持
- **交付物**: 完整的 Multi-Modal 体验 + 专业级 CLI

---

## 6. 风险与应对

| 风险 | 概率 | 影响 | 缓解措施 |
| :--- | :--- | :--- | :--- |
| Executable Block 沙箱逃逸 | 低 | 极高 | gVisor 隔离 + AST 白名单校验 + 超时熔断 |
| Auto-Distill 生成低质 Skill | 高 | 中 | Eval Gate ≥95% + Human Review 双重门禁 |
| 目录推断错误导致 Skill 误用 | 中 | 高 | Structure Requirements 显式声明 + 运行时校验 |
| Skill 数量膨胀导致匹配变慢 | 中 | 中 | 语义向量检索 + 使用频率衰减权重 + 自动废弃 |
| MCP 协议延迟 | 中 | 高 | 本地 stdio 优先 + 结果缓存 + 流式返回 |
| 团队对新规范接受度低 | 高 | 中 | 提供 CLI 脚手架 + VSCode 插件 + 渐进式迁移 |
| Multi-Modal 成本过高 | 中 | 中 | Vision 调用按需触发 + 本地预处理过滤 |

---

## 7. 成功度量

| 指标 | 基线 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 复杂任务成功率 | ~65% | ≥80% | ≥85% | ≥88% | ≥90% |
| 跨模块重构准确率 | ~45% | ≥70% | ≥78% | ≥82% | ≥85% |
| Token/任务 | 100% | ≤75% | ≤60% | ≤55% | ≤50% |
| 新 Skill 产出周期 | 2-3天 | 1天 | 8h | <4h | <2h |
| Skill 执行一致性 | ~70% | ≥90% | ≥93% | ≥95% | ≥97% |
| 安全事件 | N/A | 0 | 0 | 0 | 0 |
| 自动提炼 Skill 采纳率 | 0% | - | ≥60% | ≥75% | ≥85% |
| Multi-Modal 覆盖率 | 0% | - | - | - | ≥80% |

---

## Appendix A: Executable Skill 完整示例

> *(内容同 v3.0，见原文档 Appendix A)*

## Appendix B: Auto-Distill Eval Case 模板

> *(内容同 v3.0，见原文档 Appendix B)*

## Appendix C: MCP Config

```json
{
  "mcpServers": {
    "codebase": {
      "command": "python", "args": ["-m", "agent.mcp.codebase_server"],
      "env": {"REPO_ROOT": ".", "STRUCTURE_CONFIG": ".agent/workspace-structure.yaml"}
    },
    "skills": {
      "command": "python", "args": ["-m", "agent.mcp.skills_server"],
      "env": {"SKILLS_DIR": ".agent/skills/", "EVAL_STRICT": "true"}
    },
    "evolution": {
      "command": "python", "args": ["-m", "agent.evolution.server"],
      "env": {"TRACE_STORE": "./traces/", "DRAFT_OUTPUT": ".agent/skills/drafts/"}
    }
  }
}
```

## Appendix D: CLI Welcome Screen 设计规范

### D.1 设计原则

1. **零依赖**: ASCII Art 使用内嵌文本，不依赖外部字体文件
2. **自适应宽度**: 检测终端宽度，超长自动截断或换行
3. **尊重 NO_COLOR**: 检测到 `NO_COLOR=1` 时输出纯文本
4. **快速启动**: Welcome Screen 渲染时间 <50ms

### D.2 视觉层次

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│    ████████╗███████╗██████╗ ███╗   ███╗ ███████╗    │
│    ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██╔════╝    │
│       ██║   ███████╗██████╔╝██╔████╔██║█████╗      │
│       ██║   ╚════██║██╔═══╝ ██║╚██╔╝██║██╔══╝      │
│       ██║   ███████║██║     ██║ ╚═╝ ██║███████╗    │
│       ╚═╝   ╚══════╝╚═╝     ╚═╝     ╚═╝╚══════╝    │
│                                                     │
│       🤖 Autonomous Coding Agent v1.0.0              │
│                                                     │
│    ┌─────────────────────────────────────────────┐  │
│    │  Quick Start                                │  │
│    │  ─────────────────────────────────────────  │  │
│    │  $ agent "Refactor auth module"              │  │
│    │  $ agent --skill refactor-function           │  │
│    │  $ agent --status                            │  │
│    └─────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### D.3 技术实现要点

- **Rich Text**: 使用 `rich.text.Text` 构建 ASCII Art，支持 ANSI 颜色
- **终端宽度检测**: `rich.console.Console.size.width` 自适应
- **动态信息**: 启动时显示当前模型状态、Token 预算、Skill 数量
- **Theme 支持**: 支持 Light/Dark 终端主题自动适配
