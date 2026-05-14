"""Optional tool registration for the Deep Agents runtime.

The module currently exposes Slack delivery tooling when token and channel
configuration are available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.tools import tool
from slack_sdk import WebClient

from deep_agents.config import AppSettings


def build_optional_tools(settings: AppSettings, backend: Any) -> list[Any]:
    """Build optional runtime tools based on available configuration.

    Args:
        settings: Validated application settings.
        backend: Deep Agents backend used for workspace file downloads.

    Returns:
        List of callable tool objects to register with the agent.
    """
    tools: list[Any] = []
    if settings.slack_user_token and settings.slack_channel_id:
        tools.append(_build_slack_send_message_tool(settings, backend))
    return tools


def _build_slack_send_message_tool(settings: AppSettings, backend: Any) -> Any:
    """Create a Slack tool that sends messages and optional file attachments.

    Args:
        settings: Validated application settings with Slack credentials.
        backend: Backend object used to fetch workspace files.

    Returns:
        LangChain tool callable for Slack message delivery.
    """
    slack_client = WebClient(token=settings.slack_user_token)
    slack_channel = settings.slack_channel_id or ""

    @tool(parse_docstring=True)
    def slack_send_message(text: str, file_path: str | None = None) -> str:
        """Send a Slack message and optionally attach one workspace file.

        Args:
            text: Message body to publish.
            file_path: Optional workspace-relative file path to upload.

        Returns:
            Confirmation text including uploaded file ID when available.

        Raises:
            ValueError: If the attachment path is invalid or unreadable.
        """
        if not file_path:
            slack_client.chat_postMessage(channel=slack_channel, text=text)
            return "Message sent."

        target = file_path.strip()
        downloads = backend.download_files([target])
        if not downloads:
            raise ValueError(f"Unable to fetch attachment: {target}")

        item = downloads[0]
        if item.error:
            raise ValueError(f"Unable to fetch attachment '{target}': {item.error}")

        file_bytes = item.content
        if file_bytes is None:
            local_path = Path(target)
            if not local_path.is_absolute():
                local_path = (Path.cwd() / local_path).resolve()
            if local_path.exists() and local_path.is_file():
                file_bytes = local_path.read_bytes()
            else:
                raise ValueError(f"Attachment has no content and was not found locally: {target}")

        filename = Path(target).name or "attachment.bin"
        response = slack_client.files_upload_v2(
            channel=slack_channel,
            file=file_bytes,
            filename=filename,
            initial_comment=text,
        )
        uploaded = response.get("file") or (response.get("files") or [None])[0]
        if uploaded and uploaded.get("id"):
            return f"Message sent. file_id={uploaded['id']}"
        return "Message sent."

    return slack_send_message
