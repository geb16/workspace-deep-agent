"""Unit tests for command policy and guarded backend behavior."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

from deep_agents.sandbox import CommandPolicy, GuardedLocalShellBackend


class CommandPolicyTests(unittest.TestCase):
    """Regression tests for command policy and heredoc rewriting."""

    def setUp(self) -> None:
        """Create an isolated temporary workspace for each test."""
        self.workspace = (Path(__file__).resolve().parent / ".tmp_policy_workspace").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.policy = CommandPolicy(self.workspace)

    def tearDown(self) -> None:
        """Clean up temporary workspace state."""
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_blocks_recursive_delete(self) -> None:
        """Policy should block common recursive delete patterns."""
        verdict = self.policy.validate("rm -rf ./build")
        self.assertFalse(verdict.allowed)
        self.assertIn("blocked", verdict.reason.lower())

    def test_blocks_outside_workspace_absolute_path(self) -> None:
        """Policy should reject access to absolute paths outside the workspace."""
        verdict = self.policy.validate(r'type "C:\Windows\System32\drivers\etc\hosts"')
        self.assertFalse(verdict.allowed)

    def test_allows_safe_command(self) -> None:
        """Policy should allow benign commands."""
        verdict = self.policy.validate("python --version")
        self.assertTrue(verdict.allowed)

    def test_rewrites_posix_workspace_path(self) -> None:
        """Policy should map POSIX workspace paths to local host paths."""
        rewritten = self.policy.rewrite_for_host("python /data/run.py")
        self.assertIn(str(self.workspace), rewritten)

    def test_executes_python_heredoc_on_windows(self) -> None:
        """Backend should translate heredoc snippets to temporary scripts."""
        env = dict(os.environ)
        env["PATH"] = str(Path(sys.executable).resolve().parent) + os.pathsep + env.get("PATH", "")
        backend = GuardedLocalShellBackend(
            workspace_root=self.workspace,
            timeout=30,
            max_output_bytes=20_000,
            env=env,
        )
        command = "python - <<'PY'\nprint('ok-heredoc')\nPY"
        result = backend.execute(command)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ok-heredoc", result.output)


if __name__ == "__main__":
    unittest.main()
