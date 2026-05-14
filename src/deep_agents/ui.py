"""Streamlit UI helpers for rendering AgentBox interactions.

This module contains presentational helpers and event-to-view transformation
logic so the top-level application file can stay focused on interaction flow.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st

from deep_agents.agent_service import AgentEvent


def apply_app_style() -> None:
    """Apply global page configuration and custom CSS theme."""
    st.set_page_config(
        page_title="AgentBox",
        page_icon="🧭",
        layout="wide",
    )
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap');

:root {
  --bg-0: #090a0c;
  --bg-1: #101216;
  --bg-2: #171a21;
  --panel: #12151c;
  --panel-soft: #191d27;
  --line: #2a2f3a;
  --ink-0: #f6f8fb;
  --ink-1: #c9d0db;
  --ink-2: #96a1af;
  --accent: #ff385c;
  --accent-soft: #ff5f7d;
  --ok: #34d399;
  --warn: #f59e0b;
  --error: #f87171;
}

html, body, [class*="css"]  {
  font-family: "Space Grotesk", "Trebuchet MS", sans-serif;
  color: var(--ink-0);
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 520px at 10% -5%, rgba(255, 56, 92, 0.20), transparent 68%),
    radial-gradient(1000px 500px at 96% -8%, rgba(38, 74, 132, 0.22), transparent 65%),
    linear-gradient(180deg, var(--bg-0) 0%, #08090b 100%);
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0e1015 0%, #0b0d11 100%);
  border-right: 1px solid var(--line);
}

[data-testid="stSidebar"] * {
  color: var(--ink-1);
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: var(--ink-0);
}

[data-testid="stHeader"] {
  background: transparent;
}

h1, h2, h3, h4, strong, label {
  color: var(--ink-0) !important;
}

p, span, li, small, div, [data-testid="stCaptionContainer"] {
  color: var(--ink-1);
}

[data-testid="stChatMessage"] {
  background: linear-gradient(180deg, var(--panel) 0%, #10131a 100%);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.4rem 0.65rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

[data-testid="stChatInput"] {
  background: rgba(9, 11, 14, 0.88);
  border-top: 1px solid var(--line);
}

[data-testid="stChatInput"] textarea {
  background: var(--panel) !important;
  color: var(--ink-0) !important;
  border: 1px solid var(--line) !important;
  border-radius: 12px !important;
}

.stButton > button {
  background: linear-gradient(180deg, #1a1f29 0%, #131720 100%);
  color: var(--ink-0);
  border: 1px solid var(--line);
  border-radius: 10px;
}

.stButton > button:hover {
  border-color: var(--accent-soft);
  color: #fff;
}

.stStatus {
  background: var(--panel) !important;
  border: 1px solid var(--line);
  border-radius: 12px;
}

.agentbox-title {
  color: var(--ink-0);
  font-size: 2rem;
  line-height: 1.1;
  margin: 0;
  letter-spacing: -0.02em;
}

.agentbox-subtitle {
  color: var(--ink-2);
  margin-top: 0.25rem;
  margin-bottom: 1rem;
}

[data-testid="stExpander"] {
  background: var(--panel-soft);
  border: 1px solid var(--line);
  border-radius: 10px;
}

[data-testid="stExpander"] summary {
  color: var(--ink-0) !important;
  font-weight: 600;
}

[data-testid="stCodeBlock"] {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #0c0f14;
}

code, pre {
  font-family: "IBM Plex Mono", Consolas, monospace !important;
}

hr {
  border-color: var(--line);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_header(workspace_root: Path, model_name: str) -> None:
    """Render the page title and runtime context header.

    Args:
        workspace_root: Active workspace root path.
        model_name: Configured model identifier.
    """
    st.markdown('<h1 class="agentbox-title">AgentBox Workspace Runner</h1>', unsafe_allow_html=True)
    st.markdown(
        (
            f'<div class="agentbox-subtitle">Model: <code>{model_name}</code> '
            f"· Workspace: <code>{workspace_root}</code></div>"
        ),
        unsafe_allow_html=True,
    )


@dataclass
class TraceStep:
    """One renderable execution step in the right-side trace panel.

    Attributes:
        title: Display title for the step.
        kind: Logical step category.
        node: Source graph node.
        state: Step state (for example ``running`` or ``complete``).
        command: Shell command text when applicable.
        output: Captured tool/command output.
        details: Free-form markdown details.
        todos: Checklist lines for todo updates.
    """

    title: str
    kind: str
    node: str
    state: str = "complete"
    command: str = ""
    output: str = ""
    details: str = ""
    todos: list[str] = field(default_factory=list)


def render_event_list(
    events: Iterable[AgentEvent],
    max_events: int = 12,
    *,
    running: bool = False,
    key_prefix: str = "trace",
) -> None:
    """Render a compact event timeline.

    Args:
        events: Stream of normalized runtime events.
        max_events: Maximum number of recent events to render.
        running: Whether the run is currently active.
        key_prefix: Prefix reserved for keyed UI components.
    """
    _ = key_prefix
    recent = list(events)[-max_events:]
    if not recent:
        st.caption("No execution steps yet.")
        return

    steps = _build_trace_steps(recent)
    if not steps:
        st.caption("No execution steps yet.")
        return

    for index, step in enumerate(steps, start=1):
        badge = {"complete": "✅", "running": "⏳", "error": "❌"}.get(step.state, "•")
        st.markdown(f"**{index}. {step.title}** {badge}")
        st.caption(f"node: {step.node}")

        if step.kind == "todos":
            if step.todos:
                for todo in step.todos:
                    st.markdown(f"- {todo}")
            elif step.details:
                st.markdown(step.details)
            continue

        if step.kind == "command":
            if step.command:
                st.caption("I run this command:")
                st.code(step.command, language="bash")
            if step.output:
                output_expanded = running and index == len(steps)
                with st.expander("Terminal Output", expanded=output_expanded):
                    st.code(step.output, language=None, wrap_lines=False, height=260)
            elif running:
                st.caption("Waiting for command output...")
            continue

        if step.details:
            st.markdown(step.details)

        if step.output:
            with st.expander("Tool Output", expanded=False):
                st.code(step.output, language=None, wrap_lines=False, height=220)


def _build_trace_steps(events: list[AgentEvent]) -> list[TraceStep]:
    """Transform normalized events into UI timeline steps.

    Args:
        events: Ordered agent events for one run.

    Returns:
        Renderable timeline steps with start/result reconciliation.
    """
    steps: list[TraceStep] = []
    pending_by_tool: dict[str, list[int]] = {}

    for event in events:
        if event.kind == "tool_call":
            tool_name = _tool_name(event)
            args = _tool_args(event)

            if tool_name == "write_todos":
                todos = _format_todos(args)
                steps.append(
                    TraceStep(
                        title="Todos",
                        kind="todos",
                        node=event.node,
                        state="complete",
                        todos=todos,
                        details=event.body,
                    )
                )
                continue

            if tool_name == "execute":
                command = args.get("command", "") if isinstance(args, dict) else ""
                steps.append(
                    TraceStep(
                        title="Run Command",
                        kind="command",
                        node=event.node,
                        state="running",
                        command=str(command).strip(),
                    )
                )
                pending_by_tool.setdefault(tool_name, []).append(len(steps) - 1)
                continue

            steps.append(
                TraceStep(
                    title=f"Use Tool: {tool_name}",
                    kind="tool",
                    node=event.node,
                    state="running",
                    details=_pretty_args(args, fallback=event.body),
                )
            )
            pending_by_tool.setdefault(tool_name, []).append(len(steps) - 1)
            continue

        if event.kind == "tool_result":
            tool_name = _tool_name(event)
            pending = pending_by_tool.get(tool_name, [])
            if pending:
                step = steps[pending.pop(0)]
                step.output = event.body.strip()
                step.state = "error" if _looks_error(step.output) else "complete"
            else:
                steps.append(
                    TraceStep(
                        title=f"Tool Result: {tool_name}",
                        kind="result",
                        node=event.node,
                        state="error" if _looks_error(event.body) else "complete",
                        output=event.body.strip(),
                    )
                )
            continue

        if event.kind == "assistant":
            text = event.body.strip()
            if text:
                steps.append(
                    TraceStep(
                        title="Assistant",
                        kind="assistant",
                        node=event.node,
                        state="complete",
                        details=text,
                    )
                )
            continue

        if event.kind == "error":
            steps.append(
                TraceStep(
                    title="Runtime Error",
                    kind="error",
                    node=event.node,
                    state="error",
                    output=event.body.strip(),
                )
            )

    return steps


def _tool_name(event: AgentEvent) -> str:
    """Extract the tool name from event metadata or title text.

    Args:
        event: Event instance emitted by :class:`AgentService`.

    Returns:
        Inferred tool name.
    """
    if isinstance(event.meta, dict) and event.meta.get("tool_name"):
        return str(event.meta["tool_name"])

    match = re.match(r"^(?:Tool Call|Tool Result):\s*(.+)$", event.title)
    if match:
        return match.group(1).strip()
    return "tool"


def _tool_args(event: AgentEvent) -> dict[str, Any]:
    """Extract structured tool arguments from event metadata or body.

    Args:
        event: Event instance emitted by :class:`AgentService`.

    Returns:
        Parsed dictionary of tool arguments.
    """
    if isinstance(event.meta, dict):
        args = event.meta.get("args")
        if isinstance(args, dict):
            return args

    try:
        parsed = json.loads(event.body)
    except Exception:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _pretty_args(args: dict[str, Any], *, fallback: str) -> str:
    """Format tool arguments for markdown display.

    Args:
        args: Structured tool argument dictionary.
        fallback: Raw fallback text when args are unavailable.

    Returns:
        Markdown-formatted code block string.
    """
    if args:
        return f"```json\n{json.dumps(args, indent=2, ensure_ascii=False)}\n```"

    text = fallback.strip()
    if not text:
        return ""
    return f"```text\n{text}\n```"


def _format_todos(args: dict[str, Any]) -> list[str]:
    """Convert ``write_todos`` payload into checklist lines.

    Args:
        args: Tool call arguments for ``write_todos``.

    Returns:
        Markdown checklist entries.
    """
    items = args.get("todos")
    if not isinstance(items, list):
        return []

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        status = str(item.get("status", "")).strip().lower()
        if not content:
            continue
        marker = "x" if status == "completed" else " "
        lines.append(f"[{marker}] {content}")
    return lines


def _looks_error(output: str) -> bool:
    """Heuristically determine whether tool output indicates failure.

    Args:
        output: Tool or command output text.

    Returns:
        ``True`` when output looks like an error.
    """
    low = output.lower()
    return (
        "sandbox policy blocked command" in low
        or "error:" in low
        or "command failed with exit code" in low
        or "exit code: 1" in low
        or "exit code: 12" in low
    )
