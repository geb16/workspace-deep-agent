"""Guarded shell backend and command policy enforcement.

The classes in this module provide a best-effort policy layer on top of the
``deepagents`` local shell backend. They are designed to reduce accidental host
risk, not to replace real OS-level sandboxing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse


@dataclass(frozen=True)
class CommandPolicyResult:
    """Validation result for a shell command.

    Attributes:
        allowed: Whether command execution is permitted.
        reason: Human-readable denial reason when ``allowed`` is ``False``.
    """

    allowed: bool
    reason: str = ""


class CommandPolicy:
    """Validate and rewrite shell commands against workspace safety rules.

    The policy blocks common destructive command patterns and rejects absolute
    paths outside the configured workspace. It also offers path rewriting and
    output redaction helpers.
    """

    _DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(?i)\brm\s+-rf\b"), "Recursive force-delete is blocked."),
        (
            re.compile(r"(?i)\bremove-item\b.*\b-recurse\b"),
            "Recursive delete is blocked.",
        ),
        (re.compile(r"(?i)\bdel\b\s+/[sq]"), "Dangerous delete flags are blocked."),
        (re.compile(r"(?i)\bformat\b"), "Disk formatting commands are blocked."),
        (re.compile(r"(?i)\bmkfs\b"), "Filesystem formatting commands are blocked."),
        (
            re.compile(r"(?i)\bshutdown\b|\breboot\b"),
            "Host power control commands are blocked.",
        ),
        (
            re.compile(r"(?i)\bsc\s+stop\b|\bnet\s+stop\b"),
            "Service stop commands are blocked.",
        ),
        (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "Hard reset commands are blocked."),
        (re.compile(r"(?i)\bgit\s+clean\b.*\b-f\b"), "Destructive git clean is blocked."),
    )
    _PATH_TOKEN_RE = re.compile(r'(?:"([^"]+)"|\'([^\']+)\'|(\S+))') # Matches quoted or unquoted tokens that may contain paths.
    _ABS_WIN_PATH_RE = re.compile(r"(?i)^[A-Z]:[\\/]") # Matches absolute Windows paths like C:\ or D:/
    _SLASH_OPTION_RE = re.compile(r"^/[A-Za-z0-9][A-Za-z0-9_-]*$") # Matches tokens that look like /option which should not be treated as paths.
    _ENV_REF_RE = re.compile(r"(?i)\$(?:OPENAI|SLACK|AZURE|AWS)_[A-Z0-9_]+") # Matches environment variable references that may contain secrets.
    _PARENT_TRAVERSAL_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)") # Matches parent directory traversal patterns like ../ or ..\

    def __init__(self, workspace_root: Path) -> None:
        """Initialize a policy scoped to a workspace root.

        Args:
            workspace_root: Root path that commands are allowed to access.
        """
        self.workspace_root = workspace_root.resolve()

    def validate(self, command: str) -> CommandPolicyResult:
        """Validate a command against deny-list and path constraints.

        Args:
            command: Raw shell command string from the agent.

        Returns:
            :class:`CommandPolicyResult` with allow/deny decision.
        """
        cmd = command.strip()
        if not cmd:
            return CommandPolicyResult(False, "Empty commands are not allowed.")
        if len(cmd) > 4000:
            return CommandPolicyResult(False, "Command exceeds policy max length.")
        if self._PARENT_TRAVERSAL_RE.search(cmd):
            return CommandPolicyResult(False, "Parent-directory traversal is blocked.")

        for pattern, reason in self._DENY_PATTERNS:
            if pattern.search(cmd):
                return CommandPolicyResult(False, reason)

        for token in self._candidate_tokens(cmd):
            if self._ABS_WIN_PATH_RE.match(token):
                abs_path = Path(token).resolve()
                if not self._is_under_workspace(abs_path):
                    return CommandPolicyResult(
                        False,
                        f"Path outside workspace is blocked: {token}",
                    )
            elif token.startswith("/") and not token.startswith("//"):
                mapped = self._map_posix_path_to_workspace(token)
                if mapped is None:
                    continue
                if not self._is_under_workspace(mapped):
                    return CommandPolicyResult(
                        False,
                        f"Path outside workspace is blocked: {token}",
                    )

        return CommandPolicyResult(True, "")

    def rewrite_for_host(self, command: str) -> str:
        """Rewrite POSIX-style absolute workspace paths to host-native paths.

        Args:
            command: Raw command potentially containing POSIX paths.

        Returns:
            Command with mappable path tokens rewritten for the host shell.
        """
        pieces: list[str] = []
        cursor = 0
        for match in self._PATH_TOKEN_RE.finditer(command):
            start, end = match.span()
            pieces.append(command[cursor:start])
            raw = match.group(0)
            token = match.group(1) or match.group(2) or match.group(3) or ""
            quote = '"' if match.group(1) is not None else "'" if match.group(2) is not None else ""
            mapped = self._map_posix_path_to_workspace(token)
            if mapped is None:
                pieces.append(raw)
            else:
                mapped_text = str(mapped)
                if quote:
                    pieces.append(f"{quote}{mapped_text}{quote}")
                elif " " in mapped_text:
                    pieces.append(f'"{mapped_text}"')
                else:
                    pieces.append(mapped_text)
            cursor = end

        pieces.append(command[cursor:])
        return "".join(pieces)

    def redact(self, text: str) -> str:
        """Redact secret-like values from command output text.

        Args:
            text: Command output captured from shell execution.

        Returns:
            Redacted output safe to display in UI logs.
        """
        redacted = text
        for key, value in os.environ.items():
            if not value:
                continue
            if key.endswith("_KEY") or key.endswith("_TOKEN") or "SECRET" in key:
                redacted = redacted.replace(value, f"<redacted:{key}>")
        redacted = self._ENV_REF_RE.sub("<redacted:ENV>", redacted)
        return redacted

    def _candidate_tokens(self, command: str) -> list[str]:
        """Extract command tokens that may contain filesystem paths.

        Args:
            command: Shell command text.

        Returns:
            List of path-like tokens.
        """
        tokens: list[str] = []
        for match in self._PATH_TOKEN_RE.finditer(command):
            token = match.group(1) or match.group(2) or match.group(3) or ""
            if token and ("\\" in token or "/" in token):
                tokens.append(token)
        return tokens

    def _map_posix_path_to_workspace(self, token: str) -> Path | None:
        """Map a POSIX-style absolute path to a path under the workspace root.

        Args:
            token: Token that may represent a POSIX absolute path.

        Returns:
            Mapped absolute path under the workspace when applicable, otherwise
            ``None``.
        """
        if not token.startswith("/") or token.startswith("//"):
            return None
        if self._SLASH_OPTION_RE.fullmatch(token):
            return None
        # Keep host-absolute paths that already point inside the workspace.
        # This avoids remapping internal temp scripts on POSIX platforms.
        host_path = Path(token)
        if host_path.is_absolute():
            resolved_host_path = host_path.resolve()
            if self._is_under_workspace(resolved_host_path):
                return resolved_host_path

        rel = token.lstrip("/")
        if not rel:
            return self.workspace_root

        return (self.workspace_root / rel).resolve()

    def _is_under_workspace(self, path: Path) -> bool:
        """Check whether ``path`` is contained by the workspace root.

        Args:
            path: Candidate absolute path.

        Returns:
            ``True`` when ``path`` is inside ``workspace_root``.
        """
        try:
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False


class GuardedLocalShellBackend(LocalShellBackend):
    """Local shell backend that enforces :class:`CommandPolicy`.

    The backend additionally rewrites heredoc-based Python snippets into
    temporary scripts to support Windows command execution semantics.
    """

    _PY_HEREDOC_RE = re.compile(
        r"(?is)^\s*(?P<python>python(?:3(?:\.\d+)?)?)\s*-\s*<<\s*['\"]?(?P<tag>[A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\n(?P<body>.*)\n(?P=tag)\s*$"
    )
    _PY_POSIX_LITERAL_RE = re.compile(r"(?P<q>['\"])(?P<path>/(?!/)[^'\"]*)(?P=q)")
    _PATH_PREFIXES_TO_MAP = frozenset(
        {
            "data",
            "tmp",
            "workspace",
            "output",
            "outputs",
            "plot",
            "plots",
            "result",
            "results",
            "artifact",
            "artifacts",
        }
    )

    def __init__(
        self,
        workspace_root: Path,
        *,
        timeout: int,
        max_output_bytes: int,
        env: dict[str, str],
    ) -> None:
        """Create a guarded shell backend rooted to the workspace directory.

        Args:
            workspace_root: Workspace directory exposed to the shell backend.
            timeout: Maximum command timeout in seconds.
            max_output_bytes: Maximum bytes retained from command output.
            env: Environment variables to pass to the backend process.
        """
        self._policy = CommandPolicy(workspace_root=workspace_root)
        self._max_timeout = timeout
        self._tmp_dir = workspace_root / ".agentbox_tmp"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        super().__init__(
            root_dir=workspace_root,
            virtual_mode=True,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
            env=env,
            inherit_env=False,
        )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Run a shell command after policy enforcement and output redaction.

        Args:
            command: Raw command string from the agent.
            timeout: Optional per-call timeout override in seconds.

        Returns:
            Structured execution response from the shell backend.
        """
        rewritten_command = self._rewrite_python_heredoc(command)
        rewritten_command = self._policy.rewrite_for_host(rewritten_command)

        verdict = self._policy.validate(rewritten_command)
        if not verdict.allowed:
            return ExecuteResponse(
                output=f"Sandbox policy blocked command: {verdict.reason}",
                exit_code=126,
                truncated=False,
            )

        effective_timeout = (
            self._max_timeout if timeout is None else min(timeout, self._max_timeout)
        )
        response = super().execute(rewritten_command, timeout=effective_timeout)
        return ExecuteResponse(
            output=self._policy.redact(response.output),
            exit_code=response.exit_code,
            truncated=response.truncated,
        )

    def _rewrite_python_heredoc(self, command: str) -> str:
        """Translate ``python - <<TAG`` heredoc commands into script execution.

        Args:
            command: Candidate shell command.

        Returns:
            Original command when no heredoc is detected, otherwise a command
            executing a temporary script file.
        """
        match = self._PY_HEREDOC_RE.match(command)
        if not match:
            return command

        python_cmd = match.group("python")
        body = match.group("body")
        body = self._rewrite_python_posix_literals(body)
        script_path = self._tmp_dir / f"heredoc_{uuid4().hex}.py"
        script_path.write_text(body, encoding="utf-8")
        return f'{python_cmd} "{script_path}"'

    def _rewrite_python_posix_literals(self, source: str) -> str:
        """Rewrite selected POSIX string literals in Python heredoc source.

        Args:
            source: Python source code extracted from heredoc body.

        Returns:
            Source code with workspace-relative literals normalized for host
            execution.
        """

        def replace(match: re.Match[str]) -> str:
            quote = match.group("q")
            posix_path = match.group("path")
            mapped = self._map_posix_literal_to_workspace(posix_path)
            if mapped is None:
                return match.group(0)
            return f"{quote}{mapped.as_posix()}{quote}"

        return self._PY_POSIX_LITERAL_RE.sub(replace, source)

    def _map_posix_literal_to_workspace(self, posix_path: str) -> Path | None:
        """Map safe path literals in generated Python code to workspace paths.

        Args:
            posix_path: POSIX-style literal path discovered in source code.

        Returns:
            Resolved path under current backend working directory when allowed,
            otherwise ``None``.
        """
        if posix_path == "/":
            return self.cwd.resolve()

        parts = [part for part in posix_path.split("/") if part]
        if not parts:
            return self.cwd.resolve()

        if parts[0].lower() not in self._PATH_PREFIXES_TO_MAP:
            return None

        return (self.cwd / "/".join(parts)).resolve()
