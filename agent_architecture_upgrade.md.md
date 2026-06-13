# Coding Agent 全栈架构升级技术方案

> **版本**: v2.0  
> **状态**: 草案  
> **核心驱动**: Skills 抽象层 + MCP 协议标准化 + 全链路工程化  

## 1. 升级背景与战略目标

### 1.1 当前架构瓶颈
-   **能力耦合**: 工具定义、Prompt、业务逻辑混杂在单体代码中，迭代牵一发而动全身。
-   **上下文低效**: 全量注入 System Prompt，缺乏动态检索与按需加载机制，Token 浪费严重。
-   **执行不可靠**: 缺乏沙箱隔离与确定性校验，代码执行存在安全风险且结果不稳定。
-   **观测黑盒**: 缺少结构化 Trace，故障排查依赖日志翻找，无法量化评估 Agent 表现。
-   **生态封闭**: 无法复用社区标准化工具，每个新能力都需从头开发适配层。

### 1.2 升级战略目标
| 维度 | 现状 | 目标状态 | 关键指标 |
| :--- | :--- | :--- | :--- |
| 能力接入 | 硬编码，2天/工具 | MCP 即插即用，2小时/工具 | 工具扩展效率 ↑10x |
| 上下文管理 | 全量静态注入 | 动态 Resources + 向量检索 | Token 消耗 ↓30% |
| 任务成功率 | ~65% (复杂任务) | ≥85% (L2+ Skills 覆盖) | 成功率 ↑20pp |
| 执行安全 | 本地直接执行 | 沙箱隔离 + 权限白名单 | 安全事故 → 0 |
| 可观测性 | 非结构化日志 | OpenTelemetry Trace + 仪表盘 | MTTR ↓50% |
| 多模型支持 | 单一 Provider | 模型无关抽象层 | 切换成本 <1h |

---

## 2. 总体架构设计

### 2.1 五层架构模型

```text
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                     │
│         IDE Plugin / Web UI / CLI / API Gateway           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  Orchestration Layer                      │
│  ┌────────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐ │
│  │Skill Router│ │ Planner  │ │Memory   │ │ Safety    │ │
│  │& Matcher   │ │& Decomposer│ │Manager │ │ Guardrail │ │
│  └─────┬──────┘ └────┬─────┘ └────┬────┘ └─────┬─────┘ │
│        └─────────────┼────────────┼─────────────┘       │
│               ┌──────▼────────────▼──────┐               │
│               │    LLM Abstraction Layer  │               │
│               │ (Multi-provider/Fallback) │               │
│               └──────────────┬───────────┘               │
└──────────────────────────────┼──────────────────────────┘
                               │ MCP Protocol (stdio/SSE/HTTP)
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │  Codebase    │ │   Skills     │ │  External    │
     │  MCP Server  │ │  MCP Server  │ │  MCP Servers │
     │(Tools+Res)   │ │ (Prompts)    │ │(DB/Web/API)  │
     └──────────────┘ └──────────────┘ └──────────────┘
              │                │                │
     ┌────────▼────────────────▼────────────────▼──────┐
     │              Execution Sandbox                    │
     │   (Docker/E2B/Wasm · Network Isolation · ACL)    │
     └─────────────────────────────────────────────────┘
```

### 2.2 核心设计原则
- **Protocol First**: 所有能力交互必须经过 MCP，禁止绕过协议的直接调用。
- **Capability as a Service**: 每个 Skill/Tool 是独立可部署、可测试、可版本化的服务单元。
- **Context on Demand**: 上下文永远不预加载，由 Skill/Planner 显式声明并按需拉取。
- **Defense in Depth**: 安全校验贯穿 LLM 输出解析、Tool 调用前、执行中、结果返回后全流程。
- **Observable by Default**: 每次调用自动生成 Trace Span，无需额外埋点。

## 3. 六大核心升级模块

### 3.1 Skills 技能体系（能力分层）

#### 技能分级

| Level | 名称 | 定义 | 示例 | 触发方式 |
| :--- | :--- | :--- | :--- | :--- |
| L0 | Atomic Tool | 单步原子操作 | read_file, grep, exec | LLM 自主决策 |
| L1 | Micro Skill | 单目标多步封装 | format-code, lint-fix | 关键词/意图匹配 |
| L2 | Task Skill | 完整子任务编排 | refactor-function, gen-tests | Planner 分解调用 |
| L3 | Workflow Skill | 端到端业务流程 | full-pr-review, migration | 用户显式/CI 触发 |

#### Skill 注册规范 (MCP Prompt)

```json
{
  "name": "refactor-function",
  "description": "安全重构指定函数，保持测试通过",
  "arguments": [
    {"name": "file_path", "type": "string", "required": true},
    {"name": "function_name", "type": "string", "required": true},
    {"name": "goal", "type": "string", "required": true}
  ],
  "recommended_tools": ["read_file", "write_file", "run_tests", "search_symbol"],
  "context_resources": ["file://{file_path}/ast", "tests://{function_name}"],
  "safety_constraints": ["no-delete-public-api", "preserve-signature"],
  "evaluation_criteria": ["tests-pass", "lint-clean", "diff-minimal"]
}
```

### 3.2 MCP 协议集成（连接标准化）

- **传输层**: 本地 Server 使用 stdio；远程 Server 使用 SSE/HTTP + OAuth2
- **发现机制**: 启动时扫描 .mcp/config.json + 环境变量，动态注册可用 Server
- **版本协商**: Client/Server 握手时协商 MCP 版本，不兼容时优雅降级
- **错误处理**: 统一 MCP Error Codes，Client 侧实现重试/熔断/降级策略
- **社区生态**: 预置 GitHub、Postgres、Slack、Browser 等官方 MCP Server 配置模板

### 3.3 上下文引擎（智能记忆）

#### 三层上下文架构

- **Working Memory (热)**: 当前对话轮次的 Messages + 活跃 Skill 状态 → 直接进 Prompt
- **Episodic Memory (温)**: 近期会话摘要 + 成功/失败经验 → RAG 检索后注入
- **Semantic Memory (冷)**: 代码库索引 + 文档知识库 + 历史 Trace → 向量/全文混合检索

#### 动态加载策略

- Skill 声明 context_resources → Orchestrator 在执行前批量拉取
- Resource URI 支持分页: `file://src/main.py/ast?page=1&chunk=functions`
- LLM 可申请展开: 先读摘要，需要时调用 expand_resource 获取详情
- 自动压缩: Working Memory 超阈值时，LLM 摘要旧消息并归档到 Episodic

### 3.4 执行沙箱与安全（确定性保障）

#### 沙箱方案

- **首选**: E2B / Modal 云沙箱（秒级启动，完全隔离）
- **备选**: Docker + gVisor（自建部署，网络白名单）
- **轻量**: Wasm (WASI) 用于纯计算型 Tool，零容器开销

#### 安全护栏

| 检查点 | 机制 | 动作 |
| :--- | :--- | :--- |
| LLM 输出解析 | Structured Output + JSON Schema 校验 | 解析失败则重试/拒绝 |
| Tool 调用前 | 参数白名单 + 路径遍历检测 + 敏感操作确认 | 拦截/请求用户授权 |
| 执行中 | 超时熔断 + 资源配额 + 网络隔离 | 强制终止 |
| 结果返回后 | 输出过滤(PII/Secret) + 格式校验 | 脱敏/截断 |
| 全局 | 操作审计日志 + 异常行为告警 | 记录/通知 |

### 3.5 可观测性与评估（质量闭环）

#### Tracing (OpenTelemetry)

- 每个用户请求 → Trace
- 每次 Planner/Skill/Tool 调用 → Span
- 每次 LLM 调用 → Span (含 input/output tokens, latency, model)
- 自动关联: Trace ID 贯穿 MCP 协议头，跨 Server 可追踪

#### 评估体系

- **离线评测**: Golden Dataset + 自动化断言（准确率/步骤数/Token）
- **在线监控**: 成功率/延迟/Token 消耗/用户反馈 实时仪表盘
- **回归检测**: 每次 Skill/Model 变更自动跑评测，不达标阻断发布
- **A/B 实验**: 支持按用户/任务类型分流，对比不同 Skill/Prompt 版本

### 3.6 LLM 抽象与路由（模型无关）

- **统一接口**: Chat Completion / Embedding / Structured Output 抽象层
- **Provider 适配**: OpenAI / Anthropic / Google / Local (Ollama/vLLM)
- **智能路由**: 根据任务类型/Skill 要求自动选择最优模型
  - 简单 Tool 调用 → 小模型 (GPT-4o-mini / Haiku)
  - 复杂规划/重构 → 大模型 (Opus / o1)
- **Fallback 链**: 主模型超时/报错 → 自动切换备用模型
- **缓存**: Semantic Cache 对相似查询复用响应，降低成本

## 4. 技术选型建议

| 组件 | 推荐方案 | 备选方案 | 理由 |
| :--- | :--- | :--- | :--- |
| MCP SDK | mcp (Python/TS 官方) | 自研轻量客户端 | 官方维护，协议兼容性最好 |
| 沙箱 | E2B | Docker + gVisor | 秒级启动，免运维，API 友好 |
| 向量数据库 | Qdrant | Chroma / pgvector | 高性能，支持过滤，Rust 内核 |
| Tracing | LangSmith / Arize Phoenix | Self-hosted Jaeger | Agent 专用，可视化好 |
| LLM 网关 | LiteLLM | OpenRouter | 100+ Provider 统一接口，缓存 |
| 编排框架 | LangGraph / 自研 | CrewAI / AutoGen | 状态机可控性强，适合生产 |
| 配置管理 | Pydantic Settings + YAML | Env vars only | 类型安全，支持嵌套/验证 |

## 5. 分阶段实施路线图

### Phase 1: 基础协议层 (Week 1-3)
- 集成 MCP SDK，实现 Client/Server 通信
- 构建 Codebase MCP Server (基础 Tools + AST Resources)
- LLM 抽象层 + LiteLLM 网关部署
- 现有工具迁移至 MCP，验证功能不退化
- **里程碑**: Agent 可通过 MCP 完成原有全部功能

### Phase 2: Skills + 上下文 (Week 4-7)
- Skills MCP Server + 注册/发现机制
- Top 5 高频任务封装为 L2 Skills
- 动态上下文加载器 + Working Memory 压缩
- 执行沙箱 (E2B) 集成 + 基础安全护栏
- **里程碑**: 复杂任务成功率 ≥80%，Token ↓25%

### Phase 3: 观测 + 评估 + 生态 (Week 8-12)
- OpenTelemetry Tracing 全链路接入
- 离线评测 Pipeline + 在线仪表盘
- 接入 3+ 社区 MCP Servers
- Skill 自动学习原型 (从成功 Trace 提取)
- 多模型路由 + Semantic Cache
- **里程碑**: 具备持续改进闭环，新工具接入 <2h

### Phase 4: 高级特性 (持续迭代)
- Multi-Agent 协作 (共享 MCP Server)
- 长期记忆 + 个性化 Skill 推荐
- 用户反馈驱动的 Skill 自动优化
- 企业级权限/审计/合规

## 6. 风险矩阵与应对

| 风险 | 概率 | 影响 | 缓解措施 |
| :--- | :--- | :--- | :--- |
| MCP 协议延迟过高 | 中 | 高 | 本地 stdio 优先；结果缓存；异步流式返回 |
| Skill 匹配错误导致误操作 | 中 | 高 | 置信度阈值+用户确认；Safety Guardrail；回滚机制 |
| 沙箱冷启动慢 | 低 | 中 | 预热池；Wasm 轻量替代；预测性启动 |
| 社区 MCP Server 不安全 | 高 | 高 | 白名单审核；沙箱内运行；网络隔离；定期审计 |
| LLM Provider API 变更 | 中 | 中 | LiteLLM 抽象隔离；多 Provider Fallback；契约测试 |
| 团队 MCP/Skills 学习曲线 | 高 | 中 | 内部文档+模板；Pair Programming；渐进式迁移 |

## 7. 成功度量 (KPIs)

| 指标 | 基线 | Phase 1 目标 | Phase 3 目标 |
| :--- | :--- | :--- | :--- |
| 复杂任务成功率 | ~65% | ≥75% | ≥85% |
| 平均 Token/任务 | 100% | ≤80% | ≤65% |
| 新工具接入时间 | 2 天 | 4 小时 | 2 小时 |
| P95 响应延迟 | 30s | ≤25s | ≤20s |
| 安全事件数 | N/A | 0 | 0 |
| 评测覆盖率 | 0% | ≥60% | ≥90% |

## Appendix A: MCP Config 示例

```json
{
  "mcpServers": {
    "codebase": {
      "command": "python",
      "args": ["-m", "agent.mcp.codebase_server"],
      "env": {"REPO_ROOT": "."}
    },
    "skills": {
      "command": "python",
      "args": ["-m", "agent.mcp.skills_server"]
    },
    "github": {
      "url": "https://mcp.github.com/sse",
      "headers": {"Authorization": "Bearer ${GITHUB_TOKEN}"}
    }
  }
}
```

## Appendix B: Skill 开发 Checklist

- [ ] 遵循 MCP Prompt 规范定义
- [ ] 声明 recommended_tools 和 context_resources
- [ ] 包含 safety_constraints
- [ ] 提供 ≥2 个 Few-shot 示例
- [ ] 通过离线评测 (准确率 ≥90%)
- [ ] 文档化输入/输出/限制条件
- [ ] 注册到 Skills Registry
