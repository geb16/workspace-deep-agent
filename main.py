"""Console wrapper for local execution from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def main() -> None:
    """Run the package CLI after local ``src`` path bootstrap."""
    from deep_agents.cli import main as run_cli

    run_cli()


if __name__ == "__main__":
    main()
