"""Configuration management for the coding agent.

Uses pydantic-settings with .env file support. All config fields have
sensible defaults so the agent works out-of-the-box with zero config.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """All configuration for the coding agent. <10 top-level fields."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- Model routing (3 tiers) ---
    # All tiers route through the same provider, configurable via api_base
    primary_model: str = Field(
        default="anthropic/mimo-v2.5-pro",
        description="Primary LLM for complex reasoning tasks",
    )
    secondary_model: str = Field(
        default="anthropic/mimo-v2.5-pro",
        description="Secondary LLM for moderate complexity tasks",
    )
    local_model: str = Field(
        default="anthropic/mimo-v2.5-pro",
        description="Local model endpoint for simple tasks",
    )

    # --- API base URL ---
    api_base: str = Field(
        default="https://api.xiaomimimo.com/anthropic",
        description="Base URL for the LLM API provider",
    )

    # --- API Key ---
    anthropic_api_key: str = Field(
        default="",
        description="API key for the LLM provider",
    )

    # --- Token budget ---
    max_session_tokens: int = Field(
        default=100_000,
        ge=10_000,
        description="Maximum tokens per session before pause",
    )

    # --- Safety ---
    workspace_root: str = Field(
        default=".",
        description="Workspace root directory for path validation",
    )
    max_command_output_bytes: int = Field(
        default=10_240,  # 10 KB
        description="Max command output bytes before truncation",
    )
    blocked_commands: List[str] = Field(
        default=[
            "rm -rf", "curl|bash", "wget|bash", "chmod 777",
            "mkfs", "> /dev/sda", ":(){:|:&}:",
        ],
        description="Command substrings that are always blocked",
    )

    # --- Git ---
    auto_git_checkpoint: bool = Field(
        default=True,
        description="Automatically create git checkpoint before file writes",
    )
    git_commit_message_prefix: str = Field(
        default="[agent]",
        description="Prefix for auto-generated git commit messages",
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")

    # --- Semantic Directory Tree ---
    workspace_structure_config: str = Field(
        default=".agent/workspace-structure.yaml",
        description="Path to workspace structure YAML config relative to workspace root",
    )

    # --- MCP ---
    mcp_enabled: bool = Field(
        default=False,
        description="Enable MCP (Model Context Protocol) mode",
    )
    mcp_skills_path: str = Field(
        default=".mcp/skills.json",
        description="Path to the legacy skills definition JSON file",
    )
    skills_dir: str = Field(
        default=".agent/skills",
        description="Directory for Executable Skill .skill.md files",
    )

    # --- Auto-Distill Pipeline ---
    trace_dir: str = Field(
        default=".agent/traces",
        description="Directory for session trace storage (JSONL)",
    )
    distill_enabled: bool = Field(
        default=False,
        description="Enable the auto-distill pipeline (trace collection)",
    )
    distill_interval_hours: int = Field(
        default=6,
        description="Interval between distillation cycles when running as daemon",
    )
    distill_min_cluster_size: int = Field(
        default=3,
        description="Minimum traces per cluster to generate a draft",
    )

    # --- Semantic Cache ---
    semantic_cache_enabled: bool = Field(
        default=True,
        description="Enable semantic cache to reduce repeated LLM calls",
    )
    semantic_cache_ttl_seconds: int = Field(
        default=3600,
        description="TTL for cached responses in seconds",
    )
    semantic_cache_max_entries: int = Field(
        default=5000,
        description="Maximum number of entries in the semantic cache",
    )

    # --- Multi-Modal Perception ---
    vision_enabled: bool = Field(
        default=False,
        description="Enable vision-based screenshot diagnostics",
    )
    log_parser_enabled: bool = Field(
        default=True,
        description="Enable log parser for CI/CD log analysis",
    )

    # --- Execution Sandbox v2 ---
    sandbox_enabled: bool = Field(
        default=True,
        description="Enable sandbox v2 for hardened command execution",
    )
    sandbox_default_timeout: float = Field(
        default=30.0,
        description="Default command execution timeout in seconds",
    )
    sandbox_max_output_bytes: int = Field(
        default=102_400,
        description="Maximum sandbox command output in bytes",
    )

    # --- OpenTelemetry Tracing ---
    tracing_enabled: bool = Field(
        default=True,
        description="Enable OpenTelemetry-style tracing",
    )
    trace_dir_spans: str = Field(
        default=".agent/traces",
        description="Directory for span trace exports (JSON)",
    )

    # --- State Machine Orchestration ---
    state_machine_enabled: bool = Field(
        default=False,
        description="Use LangGraph-style state machine instead of simple ReAct",
    )
    state_machine_max_steps: int = Field(
        default=25,
        description="Max steps in the state machine",
    )

    # --- Multi-Agent Collaboration ---
    multi_agent_enabled: bool = Field(
        default=False,
        description="Enable multi-agent team collaboration mode",
    )
    multi_agent_max_rounds: int = Field(
        default=5,
        description="Max collaboration rounds for the agent team",
    )

    @property
    def workspace_path(self) -> Path:
        """Resolved absolute workspace path."""
        return Path(self.workspace_root).resolve()
