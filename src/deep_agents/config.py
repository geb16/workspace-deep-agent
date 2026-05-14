"""Runtime configuration loading for the Deep Agents workspace app.

This module centralizes environment variable parsing and validation so the
application can fail fast with actionable error messages when configuration is
missing or malformed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

CHANNEL_ID_RE = re.compile(r"^[CGDZ][A-Z0-9]{8,}$")


def _as_int(name: str, default: int) -> int:
    """Parse an integer environment variable.

    Args:
        name: Environment variable name.
        default: Fallback value used when the variable is missing or empty.

    Returns:
        Parsed integer value or ``default`` when not set.

    Raises:
        ValueError: If the variable is set but cannot be parsed as an integer.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {raw!r}") from exc

    return value


@dataclass(frozen=True)
class AppSettings:
    """Immutable runtime configuration for the application.

    Attributes:
        project_root: Absolute project root directory.
        workspace_root: Workspace directory exposed to the agent.
        model_name: OpenAI model identifier used for chat completions.
        openai_api_key: OpenAI API key for authenticated model access.
        shell_timeout_s: Maximum shell execution timeout in seconds.
        shell_max_output_bytes: Upper bound for captured shell output bytes.
        max_agent_turns: Maximum recursion limit for a single agent turn.
        slack_user_token: Optional Slack user token for message/file delivery.
        slack_channel_id: Optional Slack conversation ID for message delivery.
    """

    project_root: Path
    workspace_root: Path
    model_name: str
    openai_api_key: str
    shell_timeout_s: int
    shell_max_output_bytes: int
    max_agent_turns: int
    slack_user_token: str | None
    slack_channel_id: str | None


def load_settings(project_root: Path) -> AppSettings:
    """Load and validate application settings from environment variables.

    The function loads ``.env`` from ``project_root`` when present, validates
    required fields, and applies conservative lower bounds for runtime limits.

    Args:
        project_root: Root directory containing project assets and ``.env``.

    Returns:
        A validated :class:`AppSettings` instance.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required in .env")

    workspace_root_raw = os.getenv("AGENT_WORKSPACE_ROOT", "").strip()
    workspace_root = Path(workspace_root_raw) if workspace_root_raw else project_root
    workspace_root = workspace_root.expanduser().resolve()
    if not workspace_root.exists():
        raise ValueError(f"AGENT_WORKSPACE_ROOT does not exist: {workspace_root}")

    slack_user_token = os.getenv("SLACK_USER_TOKEN", "").strip() or None
    slack_channel_id = os.getenv("SLACK_CHANNEL_ID", "").strip() or None
    if slack_channel_id and not CHANNEL_ID_RE.fullmatch(slack_channel_id):
        raise ValueError("SLACK_CHANNEL_ID must be a conversation ID like C012AB3CD or G012AB3CD.")

    return AppSettings(
        project_root=project_root,
        workspace_root=workspace_root,
        model_name=os.getenv("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4",
        openai_api_key=openai_api_key,
        shell_timeout_s=max(10, _as_int("AGENT_SHELL_TIMEOUT_S", 180)),
        shell_max_output_bytes=max(10_000, _as_int("AGENT_SHELL_MAX_OUTPUT_BYTES", 150_000)),
        max_agent_turns=max(8, _as_int("AGENT_MAX_TURNS", 300)),
        slack_user_token=slack_user_token,
        slack_channel_id=slack_channel_id,
    )
