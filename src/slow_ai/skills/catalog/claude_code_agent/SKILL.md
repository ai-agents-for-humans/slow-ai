---
name: claude_code_agent
description: Delegate complex, multi-file coding tasks to an autonomous coding agent that can iterate and self-correct. Uses Claude Code if ANTHROPIC_API_KEY is set, otherwise falls back to Gemini via generate_code + execute.
tools: [code_execution]
source: built-in
tags:
- coding
- autonomous
- iteration
- implementation
- analysis
---

## When to use
Use this skill when the research task requires:
- Writing and running non-trivial code that needs iteration to get right
- Analysing a codebase (clone a repo, understand its structure, answer questions about it)
- Generating a working implementation of something described in a paper or spec
- Running experiments where the code needs to adapt based on intermediate results
- Any coding task where a single `generate_code` + `execute` cycle would not be enough

Do NOT use for trivial one-shot scripts — `code_execution` alone is faster and sufficient.

## How to execute

### Step 1 — Check which backend is available

Always run this check first:

```python
import os, subprocess

has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
claude_available = False
if has_anthropic_key:
    r = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    claude_available = r.returncode == 0

print("backend:", "claude_code" if claude_available else "gemini_fallback")
```

Execute this with `execute()`. Then follow the matching path below.

---

### Path A — Claude Code (when `claude_available` is True)

`claude -p` runs non-interactively and exits when done.

```python
import subprocess

task = """
<describe the coding task in full detail>
Output the result as plain text or JSON.
"""

result = subprocess.run(
    ["claude", "-p", task],
    capture_output=True,
    text=True,
    timeout=300,
)
print("exit:", result.returncode)
print(result.stdout)
if result.stderr:
    print("stderr:", result.stderr[:2000])
```

If the output is incomplete, make a follow-up call with the prior output as context:

```python
result2 = subprocess.run(
    ["claude", "-p", f"Previous output:\n{result.stdout}\n\nContinue: <remaining task>"],
    capture_output=True, text=True, timeout=300,
)
print(result2.stdout)
```

---

### Path B — Gemini fallback (when `claude_available` is False)

Use `generate_code` to produce the implementation, then `execute` to run it. Iterate up to 3 times.

**Iteration pattern:**
1. Call `generate_code("full task description")` — returns working Python
2. Call `execute(code)` — run it, read stdout/stderr
3. If it fails or output is wrong: call `generate_code("fix this: <error> in this code: <code>")` and execute again
4. After 3 iterations, accept the best result and record what remains incomplete

For codebase analysis without Claude Code:
```python
import subprocess, tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    subprocess.run(["git", "clone", "--depth=1", repo_url, tmpdir], check=True, timeout=120)
    # Then use generate_code + execute to analyse the cloned repo
```

---

## Output contract
Include in `proof`:
- `backend_used`: `"claude_code"` or `"gemini_fallback"`
- `task_given`: the coding task description
- `output`: the final result (stdout or generated artefact)
- `iterations`: number of attempts made
- `exit_code` (Claude Code path): 0 = success
- `error_output` (if any): stderr or exception text

List produced files in `artefacts`.

## Quality bar
- Always run the Step 1 backend check — do not assume which is available
- Claude Code path: capture both stdout and stderr; stderr shows tool use logs
- Gemini fallback path: do not exceed 3 iterations — accept partial results and note gaps in proof
- Never pass secrets or credentials in the task string
- Set timeout ≥ 120s on all subprocess calls

## Pairs with
- `web_browse` / `browser_use` — fetch specs or docs first, then pass them to the coding agent
- `dataset_inspection` — inspect a dataset's schema, then delegate cleaning/analysis here
- `code_execution` — this skill IS the advanced form of code_execution; use plain code_execution for simple one-shot scripts
