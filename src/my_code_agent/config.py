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

    # --- MCP ---
    mcp_enabled: bool = Field(
        default=False,
        description="Enable MCP (Model Context Protocol) mode",
    )
    mcp_skills_path: str = Field(
        default=".mcp/skills.json",
        description="Path to the skills definition JSON file",
    )

    @property
    def workspace_path(self) -> Path:
        """Resolved absolute workspace path."""
        return Path(self.workspace_root).resolve()
