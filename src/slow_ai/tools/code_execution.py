"""
code_execution — run Python code in a sandboxed run-scoped virtual environment.

Before executing anything, bandit scans the code for security issues:
  HIGH severity   → hard block, code is not executed
  MEDIUM severity → warning logged in output, execution proceeds
  LOW severity    → silent, execution proceeds

The run venv is created with uv the first time code is executed in a run,
then reused for all subsequent executions in the same run.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Packages seeded into every new run venv.
# Agents can install more via pip install inside execute(), but these are guaranteed present.
_SEED_PACKAGES = [
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "seaborn",
    "plotly",
    "requests",
    "httpx",
    "beautifulsoup4",
    "lxml",
    "pdfplumber",
    "openpyxl",
    "pyarrow",
    "networkx",
    "scikit-learn",
    "bandit",
]


def _venv_python(venv_path: Path) -> Path:
    """Return path to the Python executable inside a venv (cross-platform)."""
    unix = venv_path / "bin" / "python"
    if unix.exists():
        return unix
    return venv_path / "Scripts" / "python.exe"


def setup_run_venv(run_id: str, base_path: Path = Path("runs")) -> Path:
    """
    Create a uv virtual environment for this run and pre-install common packages.
    Idempotent — safe to call multiple times; returns immediately if venv exists.
    Returns the absolute venv directory path.
    """
    venv_path = (base_path / run_id / ".venv").resolve()
    if venv_path.exists():
        return venv_path

    subprocess.run(
        ["uv", "venv", str(venv_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["uv", "pip", "install", "--python", str(_venv_python(venv_path))] + _SEED_PACKAGES,
        check=True,
        capture_output=True,
    )
    return venv_path


def security_scan(code: str) -> dict:
    """
    Run bandit on a code string and return categorised findings.

    Returns:
      {
        "high":    [...],   # HIGH severity issues — block execution
        "medium":  [...],   # MEDIUM severity — warn but allow
        "low":     [...],   # LOW severity — ignore
        "blocked": bool,    # True when any HIGH issues found
      }
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = Path(f.name)

    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return {"high": [], "medium": [], "low": [], "blocked": False}

        findings: dict = {"high": [], "medium": [], "low": []}
        for issue in data.get("results", []):
            severity = issue.get("issue_severity", "LOW").upper()
            entry = {
                "test_id": issue.get("test_id"),
                "description": issue.get("issue_text"),
                "line": issue.get("line_number"),
                "confidence": issue.get("issue_confidence"),
            }
            findings.setdefault(severity.lower(), []).append(entry)

        findings["blocked"] = bool(findings.get("high"))
        return findings
    finally:
        tmp_path.unlink(missing_ok=True)


async def code_execution(
    code: str,
    timeout: int = 60,
    working_dir: str | None = None,
    venv_path: str | None = None,
) -> dict:
    """
    Execute Python code in a sandboxed subprocess.

    Steps:
      1. Bandit security scan — blocks on HIGH severity findings
      2. Execute in the run venv (or the main interpreter if no venv provided)
      3. Return stdout, stderr, success flag, and scan results

    Always print() results you want to capture — return values are not visible.
    """
    # ── Security scan ─────────────────────────────────────────────────────────
    scan = security_scan(code)

    if scan["blocked"]:
        issues_text = "\n".join(
            f"  [{f['test_id']}] line {f['line']}: {f['description']} "
            f"(confidence: {f['confidence']})"
            for f in scan["high"]
        )
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                "BLOCKED — bandit found HIGH severity security issues. "
                "Fix the code before it can be executed:\n" + issues_text
            ),
            "security_scan": scan,
        }

    medium_warning = ""
    if scan.get("medium"):
        medium_warning = (
            "Security warnings (MEDIUM severity — execution allowed):\n"
            + "\n".join(
                f"  [{f['test_id']}] line {f['line']}: {f['description']}" for f in scan["medium"]
            )
            + "\n\n"
        )

    # ── Choose interpreter ────────────────────────────────────────────────────
    # Resolve to absolute path: asyncio.create_subprocess_exec resolves a
    # relative executable path relative to cwd (the artefacts dir), not the
    # process working directory, which causes FileNotFoundError.
    if venv_path and Path(venv_path).exists():
        python = str(_venv_python(Path(venv_path).resolve()))
    else:
        python = sys.executable

    # ── Execute ───────────────────────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        cwd = working_dir or None
        if cwd:
            Path(cwd).mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            python,
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "security_scan": scan,
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        return {
            "success": proc.returncode == 0,
            "stdout": medium_warning + stdout,
            "stderr": stderr,
            "security_scan": scan,
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)
