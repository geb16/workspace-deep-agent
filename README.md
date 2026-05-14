# Deep Agents Workspace Runner

Production-grade Deep Agents workspace app with a guarded local shell backend, Streamlit UI, and GitHub-ready quality gates.

## 1) Purpose

This repository gives you a safe-by-default execution harness for Deep Agents:

- Chat-first Streamlit interface.
- Step-by-step tool and command trace.
- Command policy guardrails for local shell usage.
- Standardized lint/format/test/fix workflow.
- GitHub CI pipeline ready out of the box.

## 2) Architecture

```text
.
├─ src/deep_agents/
│  ├─ __init__.py
│  ├─ agent_service.py      # Agent composition + event streaming
│  ├─ app.py                # Streamlit app orchestration
│  ├─ cli.py                # Console entrypoint
│  ├─ config.py             # Environment loading and validation
│  ├─ sandbox.py            # Command policy + guarded shell backend
│  ├─ tools.py              # Optional Slack tool wiring
│  └─ ui.py                 # Streamlit styling + trace rendering
├─ tests/
│  └─ test_sandbox_policy.py
├─ dev_task.py              # Unified developer command runner
├─ streamlit_app.py         # Root wrapper entrypoint
├─ pyproject.toml
└─ .pre-commit-config.yaml
```

## 3) Prerequisites

- Python `3.11+`
- `uv` installed
- OpenAI API key

## 4) Local Setup (E2E)

1. Clone and enter the repo.

```powershell
git clone <your-repo-url>
cd deep_agents
```

2. Install runtime + dev dependencies.

```powershell
uv sync --all-groups
```

3. Create local environment config.

```powershell
copy .env.example .env
```

4. Edit `.env` and set required value:

```env
OPENAI_API_KEY=your_openai_api_key
```

Optional values:

- `OPENAI_MODEL` (default `gpt-5.4`)
- `AGENT_WORKSPACE_ROOT`
- `AGENT_SHELL_TIMEOUT_S`
- `AGENT_SHELL_MAX_OUTPUT_BYTES`
- `AGENT_MAX_TURNS`
- `SLACK_USER_TOKEN`
- `SLACK_CHANNEL_ID`

## 5) Quality Gates (Local)

Use the unified task runner:

```powershell
uv run python dev_task.py lint
uv run python dev_task.py lint-fix
uv run python dev_task.py format-check
uv run python dev_task.py format-write
uv run python dev_task.py test
uv run python dev_task.py fix
uv run python dev_task.py check
uv run python dev_task.py clean
```

Recommended before every push:

```powershell
uv run python dev_task.py check
```

## 6) Run the Application

```powershell
uv run streamlit run streamlit_app.py
```

The app loads settings from `.env` and starts the agent workspace UI.

## 7) Git Hooks

Install hooks once:

```powershell
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg
```

What runs automatically:

- `pre-commit`: repository checks + Ruff checks + format + cache cleanup.
- `pre-push`: full quality gate (`format-check`, `lint`, `test`).
- `commit-msg`: conventional commit validation.

## 8) GitHub CI (Already Included)

This repo includes:

- `.github/workflows/ci.yml`

Pipeline behavior:

- Triggers on pushes and pull requests to `main`.
- Installs Python and `uv`.
- Syncs dependencies with `uv sync --all-groups`.
- Runs `uv run python dev_task.py check`.

## 9) Deploy from GitHub (Streamlit Community Cloud)

1. Push your repo to GitHub.
2. In Streamlit Community Cloud, create a new app.
3. Select:
- Repository: your repo
- Branch: `main`
- App file: `streamlit_app.py`
4. Add secrets in Streamlit app settings:
- `OPENAI_API_KEY`
- Optional runtime and Slack vars as needed
5. Deploy and verify startup logs.

## 10) Security and Repo Hygiene

- Do not commit `.env`.
- Keep secrets only in local `.env` or platform secret managers.
- Cache hygiene is enforced:
- `pytest` cache provider disabled.
- Ruff runs with `--no-cache`.
- `dev_task.py` cleanup removes `.pytest_cache`, `.ruff_cache`, and `__pycache__`.

## 11) Production Readiness Checklist

Before release:

1. `uv run python dev_task.py check` passes locally.
2. CI workflow is green on GitHub.
3. Required secrets are configured in deployment target.
4. Branch protection requires CI pass on pull requests.
5. Runtime logs show no secret leakage and no policy bypasses.

## 12) Troubleshooting

- `OPENAI_API_KEY is required in .env`:
Set `OPENAI_API_KEY` in `.env` or deployment secrets.

- Slack tool not appearing:
Set both `SLACK_USER_TOKEN` and valid `SLACK_CHANNEL_ID`.

- Command blocked by policy:
Review the guardrails in `src/deep_agents/sandbox.py` and adjust only with explicit risk review.

## 13) Acknowledgment

This project is built on top of the LangChain Deep Agents ecosystem. Credit to the LangChain team and contributors for the Deep Agents SDK, patterns, and documentation that informed this implementation.

## 14) Reference

- LangChain Deep Agents Overview: https://docs.langchain.com/oss/python/deepagents/overview
- LangChain Deep Agents Quickstart: https://docs.langchain.com/oss/python/deepagents/quickstart
- LangChain Deep Agents API Reference (Python): https://reference.langchain.com/python/deepagents/
- Deep Agents GitHub Repository: https://github.com/langchain-ai/deepagents
