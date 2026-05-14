"""Console entrypoint helpers for the Deep Agents project."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    """Print a concise startup message and launch guidance."""
    project_root = Path(__file__).resolve().parents[2]
    print("Deep Agents workspace runner is ready.")
    print(f"Project root: {project_root}")
    print("Run the UI with: uv run streamlit run streamlit_app.py")


if __name__ == "__main__":
    main()
