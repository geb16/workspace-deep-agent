"""Streamlit application entrypoint for the Deep Agents workspace runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from deep_agents import AgentService, load_settings
from deep_agents.agent_service import AgentEvent
from deep_agents.ui import apply_app_style, render_event_list, render_header

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ensure_state() -> tuple[AgentService, Any]:
    """Initialize required Streamlit session state.

    Returns:
        Tuple of the active :class:`AgentService` and loaded settings object.
    """
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings(PROJECT_ROOT)
    if "service" not in st.session_state:
        st.session_state.service = AgentService(st.session_state.settings)
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "live_events" not in st.session_state:
        st.session_state.live_events = []
    return st.session_state.service, st.session_state.settings


def _sidebar(service: AgentService, settings: Any) -> None:
    """Render the sidebar controls and runtime metadata.

    Args:
        service: Active agent service instance.
        settings: Application settings object.
    """
    with st.sidebar:
        st.header("Control")
        st.caption(f"Thread ID: `{service.thread_id}`")

        if st.button("New Thread", use_container_width=True):
            service.new_thread()
            st.session_state.chat_history = []
            st.session_state.live_events = []
            st.rerun()

        if st.button("Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.live_events = []
            st.rerun()

        st.divider()
        st.subheader("Runtime")
        st.write(f"Model: `{settings.model_name}`")
        st.write(f"Workspace: `{settings.workspace_root}`")
        st.write(f"Shell timeout: `{settings.shell_timeout_s}s`")
        if settings.slack_user_token and settings.slack_channel_id:
            st.success(f"Slack tool enabled for `{settings.slack_channel_id}`")
        else:
            st.info("Slack tool disabled (set SLACK_USER_TOKEN + SLACK_CHANNEL_ID)")

        st.divider()
        st.caption(
            "Tip: Ask the agent to inspect files, run scripts, generate charts, or refactor code."
        )


def _render_history(chat_col: Any) -> None:
    """Render persisted chat history.

    Args:
        chat_col: Streamlit column object that hosts the chat panel.
    """
    with chat_col:
        for index, msg in enumerate(st.session_state.chat_history):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("events"):
                    render_event_list(
                        msg["events"],
                        max_events=80,
                        running=False,
                        key_prefix=f"history_{index}",
                    )


def _run_turn(
    service: AgentService,
    prompt: str,
    trace_placeholder: Any,
) -> tuple[str, list[AgentEvent]]:
    """Execute one prompt against the service and stream UI updates.

    Args:
        service: Agent service used to execute the prompt.
        prompt: User prompt text.
        trace_placeholder: Placeholder container for trace updates.

    Returns:
        Assistant final text and event list captured during execution.
    """
    assistant_text = ""
    events: list[AgentEvent] = []

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        with st.status("Agent running...", expanded=True) as status:
            try:
                for event in service.stream_turn(prompt):
                    events.append(event)
                    st.session_state.live_events = events

                    with trace_placeholder.container():
                        render_event_list(
                            events,
                            max_events=120,
                            running=True,
                            key_prefix="live",
                        )

                    if event.kind == "assistant":
                        assistant_text = event.body.strip() or assistant_text
                        if assistant_text:
                            answer_placeholder.markdown(assistant_text)
                    else:
                        status.write(event.title)

                status.update(label="Run complete", state="complete", expanded=False)
            except Exception as exc:
                status.update(label="Run failed", state="error", expanded=True)
                status.write(str(exc))
                if not assistant_text:
                    assistant_text = f"Execution failed: {exc}"

                events.append(
                    AgentEvent(
                        kind="error",
                        title="Runtime Error",
                        body=str(exc),
                        node="app",
                    )
                )
                with trace_placeholder.container():
                    render_event_list(
                        events,
                        max_events=120,
                        running=False,
                        key_prefix="live_error",
                    )

        if not assistant_text:
            assistant_text = "Task completed with no assistant summary returned."
        answer_placeholder.markdown(assistant_text)

    return assistant_text, events


def main() -> None:
    """Run the Streamlit app."""
    apply_app_style()
    service, settings = _ensure_state()
    _sidebar(service, settings)
    render_header(settings.workspace_root, settings.model_name)

    chat_col, trace_col = st.columns([1.7, 1.0], gap="large")
    _render_history(chat_col)

    with trace_col:
        st.subheader("Step-by-Step Execution")
        trace_placeholder = st.empty()
        with trace_placeholder.container():
            render_event_list(
                st.session_state.live_events,
                max_events=120,
                running=False,
                key_prefix="side_trace",
            )

    prompt = st.chat_input("Ask the agent to work inside the workspace...")
    if not prompt:
        return

    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with chat_col:
        with st.chat_message("user"):
            st.markdown(prompt)

    with trace_col:
        answer_text, events = _run_turn(service, prompt, trace_placeholder)

    st.session_state.chat_history.append(
        {"role": "assistant", "content": answer_text, "events": events}
    )
    st.session_state.live_events = events
    st.rerun()


if __name__ == "__main__":
    main()
