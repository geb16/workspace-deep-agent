"""Developer task runner for local quality workflows.

The commands exposed here are intentionally simple and script-friendly so they
can be used consistently in local development, CI pipelines, and pre-commit
hooks.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LINT_TARGETS = ["src", "tests", "main.py", "streamlit_app.py", "dev_task.py"]


def _run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    """Run one subprocess command and return its exit code.

    Args:
        command: Command and arguments to execute.
        env: Optional environment variable overrides.

    Returns:
        Process return code.
    """
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)

    process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        env=merged_env,
    )
    return process.returncode


def _remove_path(path: Path) -> None:
    """Delete a file or directory if it exists.

    Args:
        path: Path to remove.
    """
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def clean() -> int:
    """Remove transient caches and Python build artifacts.

    Returns:
        Exit code (always ``0``).
    """
    top_level_targets = [
        PROJECT_ROOT / ".pytest_cache",
        PROJECT_ROOT / ".ruff_cache",
        PROJECT_ROOT / ".mypy_cache",
        PROJECT_ROOT / ".coverage",
        PROJECT_ROOT / ".agentbox_tmp",
    ]
    for target in top_level_targets:
        _remove_path(target)

    for path in PROJECT_ROOT.rglob("__pycache__"):
        _remove_path(path)

    for pattern in ("*.pyc", "*.pyo"):
        for path in PROJECT_ROOT.rglob(pattern):
            _remove_path(path)

    return 0


def lint() -> int:
    """Run Ruff lint checks without using cache.

    Returns:
        Ruff exit code.
    """
    return _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format=concise",
            *LINT_TARGETS,
        ]
    )


def lint_fix() -> int:
    """Apply Ruff auto-fixes without using cache.

    Returns:
        Ruff exit code.
    """
    return _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--fix",
            "--exit-non-zero-on-fix",
            "--output-format=concise",
            *LINT_TARGETS,
        ]
    )


def format_check() -> int:
    """Verify Ruff formatting without writing changes.

    Returns:
        Ruff formatter exit code.
    """
    return _run([sys.executable, "-m", "ruff", "format", "--no-cache", "--check", *LINT_TARGETS])


def format_write() -> int:
    """Apply Ruff formatting in-place.

    Returns:
        Ruff formatter exit code.
    """
    return _run([sys.executable, "-m", "ruff", "format", "--no-cache", *LINT_TARGETS])


def test() -> int:
    """Run test suite without creating bytecode cache files.

    Returns:
        Pytest exit code.
    """
    return _run([sys.executable, "-m", "pytest"], env={"PYTHONDONTWRITEBYTECODE": "1"})


def _run_sequence(commands: Iterable[Callable[[], int]]) -> int:
    """Execute commands sequentially and stop on first failure.

    Args:
        commands: Callables returning shell-style exit codes.

    Returns:
        ``0`` when all commands succeed, otherwise the first non-zero code.
    """
    for command in commands:
        code = command()
        if code != 0:
            return code
    return 0


def fix() -> int:
    """Run the full automatic code-fix workflow.

    Returns:
        Exit code from the first failing command, if any.
    """
    return _run_sequence([lint_fix, format_write])


def check() -> int:
    """Run full quality gate checks.

    Returns:
        Exit code from the first failing command, if any.
    """
    return _run_sequence([format_check, lint, test])


def precommit_lint() -> int:
    """Run lint checks in pre-commit compatible mode.

    Returns:
        Ruff lint exit code.
    """
    return lint()


def precommit_format() -> int:
    """Run formatting checks in pre-commit compatible mode.

    Returns:
        Ruff format check exit code.
    """
    return format_check()


def precommit_check() -> int:
    """Run repository quality gate used by pre-push.

    Returns:
        Exit code from the first failing check.
    """
    return check()


COMMANDS: dict[str, Callable[[], int]] = {
    "clean": clean,
    "lint": lint,
    "lint-fix": lint_fix,
    "format-check": format_check,
    "format-write": format_write,
    "test": test,
    "fix": fix,
    "check": check,
    "precommit-lint": precommit_lint,
    "precommit-format": precommit_format,
    "precommit-check": precommit_check,
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(description="Run repository development tasks.")
    parser.add_argument("command", choices=sorted(COMMANDS.keys()))
    return parser.parse_args()


def main() -> int:
    """Program entrypoint.

    Returns:
        Process exit code.
    """
    args = parse_args()
    command = COMMANDS[args.command]

    try:
        code = command()
    finally:
        if args.command != "clean":
            clean()

    return code


if __name__ == "__main__":
    raise SystemExit(main())
