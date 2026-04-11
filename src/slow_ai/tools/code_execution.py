import asyncio
import sys
import tempfile
from pathlib import Path


async def code_execution(code: str, timeout: int = 30, working_dir: str | None = None) -> dict:
    """
    Execute Python code in an isolated subprocess and return the result.

    The agent passes code as a string; stdout is the primary output channel.
    Always print() results you want to capture — return values are not visible.

    Returns dict with: success (bool), stdout (str), stderr (str)
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        cwd = working_dir if working_dir else None
        if cwd:
            Path(cwd).mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
            }

        return {
            "success": proc.returncode == 0,
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)
