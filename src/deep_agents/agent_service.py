"""Agent orchestration service for streaming Deep Agents events to the UI.

This module composes the LLM, backend, and optional tools into a single
runtime service that emits normalized event objects for frontend rendering.
"""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from deepagents import create_deep_agent
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from deep_agents.config import AppSettings
from deep_agents.sandbox import GuardedLocalShellBackend
from deep_agents.tools import build_optional_tools

# Suppress one known non-fatal startup warning emitted by langgraph serializer
# defaults at import-time. Keep all other warnings intact.
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version\..*",
    category=LangChainPendingDeprecationWarning,
)


APP_SYSTEM_PROMPT = """You are the execution engine inside a developer workspace.

Behavior:
- Work step-by-step and keep outputs precise.
- Prefer filesystem tools (`ls`, `read_file`, `glob`, `grep`) for discovery.
- For execution, use `execute` with clear, minimal commands.
- Shell environment is Windows (`cmd` semantics), not bash.
- Do NOT use bash/heredoc syntax like `python - <<'PY' ... PY`.
- Prefer either:
  - `python -c "..."` for short snippets
  - write a `.py` file then run `python path\\to\\script.py`
- Always write generated artifacts inside the workspace.
- When finishing, provide a concise final answer and include artifact file paths.
"""


@dataclass(frozen=True)
class AgentEvent:
    """Normalized event emitted by :class:`AgentService`.

    Attributes:
        kind: Event category (for example ``tool_call`` or ``assistant``).
        title: Human-readable event title for UI display.
        body: Event payload text.
        node: Graph node that emitted the event.
        meta: Optional structured metadata for advanced rendering.
    """

    kind: str
    title: str
    body: str
    node: str
    meta: dict[str, Any] = field(default_factory=dict)


class AgentService:
    """Coordinate agent runtime and stream normalized execution events."""

    def __init__(self, settings: AppSettings) -> None:
        """Initialize the service and construct a Deep Agent instance.

        Args:
            settings: Validated application settings.
        """
        self.settings = settings
        self.thread_id = str(uuid4())

        python_dir = str(Path(os.sys.executable).resolve().parent)
        backend_env = dict(os.environ)
        backend_env["PATH"] = python_dir + os.pathsep + backend_env.get("PATH", "")

        self.backend = GuardedLocalShellBackend(
            workspace_root=settings.workspace_root,
            timeout=settings.shell_timeout_s,
            max_output_bytes=settings.shell_max_output_bytes,
            env=backend_env,
        )
        tools = build_optional_tools(settings, self.backend)

        model = ChatOpenAI(
            model=settings.model_name,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        self.agent = create_deep_agent(
            model=model,
            tools=tools,
            backend=self.backend,
            checkpointer=InMemorySaver(),
            system_prompt=APP_SYSTEM_PROMPT,
        )

    def new_thread(self) -> str:
        """Start a fresh conversation thread.

        Returns:
            Newly generated thread ID.
        """
        self.thread_id = str(uuid4())
        return self.thread_id

    def stream_turn(self, prompt: str) -> Iterator[AgentEvent]:
        """Execute one user turn and stream normalized events.

        Args:
            prompt: User instruction to pass to the agent.

        Yields:
            :class:`AgentEvent` objects in UI-friendly order.
        """
        seen_message_ids: set[str] = set()
        input_message = {"role": "user", "content": prompt}
        config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": self.settings.max_agent_turns,
        }

        for step in self.agent.stream({"messages": [input_message]}, config, stream_mode="updates"):
            if not isinstance(step, dict):
                continue

            for node_name, update in step.items():
                if not isinstance(update, dict):
                    continue

                messages = update.get("messages")
                if not isinstance(messages, list):
                    continue

                for message in messages:
                    message_id = self._message_id(message, node_name)
                    if message_id in seen_message_ids:
                        continue

                    seen_message_ids.add(message_id)
                    yield from self._to_events(message, node_name)

    def _to_events(self, message: Any, node_name: str) -> list[AgentEvent]:
        """Convert one backend message into zero or more :class:`AgentEvent`s.

        Args:
            message: Raw LangGraph/LangChain message object.
            node_name: Source graph node name.

        Returns:
            List of normalized events extracted from the message.
        """
        events: list[AgentEvent] = []
        message_type = getattr(message, "type", message.__class__.__name__).lower()

        if message_type == "ai":
            tool_calls = getattr(message, "tool_calls", []) or []
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    tool_name = str(tool_call.get("name", "tool"))
                    args = tool_call.get("args", {})
                    call_id = str(tool_call.get("id", "")) if tool_call.get("id") else ""
                else:
                    tool_name = str(getattr(tool_call, "name", "tool"))
                    args = getattr(tool_call, "args", {})
                    call_id = (
                        str(getattr(tool_call, "id", "")) if getattr(tool_call, "id", None) else ""
                    )

                args_text = self._safe_json(args)
                events.append(
                    AgentEvent(
                        kind="tool_call",
                        title=f"Tool Call: {tool_name}",
                        body=args_text,
                        node=node_name,
                        meta={"tool_name": tool_name, "args": args, "call_id": call_id},
                    )
                )

            text = self._flatten_content(getattr(message, "content", ""))
            if text.strip():
                events.append(
                    AgentEvent(
                        kind="assistant",
                        title="Assistant",
                        body=text,
                        node=node_name,
                        meta={"message_type": "assistant"},
                    )
                )
            return events

        if message_type == "tool":
            tool_name = getattr(message, "name", "tool")
            content = self._flatten_content(getattr(message, "content", ""))
            events.append(
                AgentEvent(
                    kind="tool_result",
                    title=f"Tool Result: {tool_name}",
                    body=content,
                    node=node_name,
                    meta={"tool_name": str(tool_name)},
                )
            )
            return events

        text = self._flatten_content(getattr(message, "content", ""))
        if text.strip():
            events.append(
                AgentEvent(
                    kind="message",
                    title=message_type.upper(),
                    body=text,
                    node=node_name,
                    meta={"message_type": message_type},
                )
            )
        return events

    @staticmethod
    def _message_id(message: Any, node_name: str) -> str:
        """Build a stable event de-duplication key.

        Args:
            message: Raw message object from stream updates.
            node_name: Source graph node name.

        Returns:
            Stable identifier for one message instance.
        """
        message_id = getattr(message, "id", None)
        if message_id:
            return f"{node_name}:{message_id}"
        return f"{node_name}:{hash(repr(message))}"

    @staticmethod
    def _safe_json(value: Any) -> str:
        """Serialize arbitrary values to readable JSON when possible.

        Args:
            value: Any serializable or non-serializable Python value.

        Returns:
            Pretty JSON string, or ``str(value)`` as a fallback.
        """
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except TypeError:
            return str(value)

    @staticmethod
    def _flatten_content(content: Any) -> str:
        """Normalize mixed content payloads into plain text.

        Args:
            content: Message content from LangChain message objects.

        Returns:
            Readable plain-text representation of ``content``.
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue

                if isinstance(item, dict):
                    if "text" in item and isinstance(item["text"], str):
                        chunks.append(item["text"])
                        continue

                    chunk_type = str(item.get("type", "content"))
                    chunks.append(f"[{chunk_type} block]")
                    continue

                chunks.append(str(item))
            return "\n".join(chunks)

        return str(content)
