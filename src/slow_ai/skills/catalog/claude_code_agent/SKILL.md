---
name: claude_code_agent
description: Delegate complex, multi-file coding tasks to a Claude Code subprocess that can iterate, self-correct, and produce working implementations — far beyond single-shot code generation.
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
- Any coding task where `generate_code` + `execute` would need more than 2 cycles to converge

Do NOT use for trivial one-shot scripts — `code_execution` is faster and sufficient.

## How to execute

### 1. Check Claude Code is available
```python
import subprocess
result = subprocess.run(["claude", "--version"], capture_output=True, text=True)
print(result.stdout)
```
If the command fails, note in proof and fall back to `code_execution`.

### 2. Invoke Claude Code in print mode
`claude -p` runs non-interactively and exits when done. This is the correct mode for agent use.

```python
import subprocess, json

task = """
<describe the coding task in full detail here>
Output the result as plain text or JSON.
"""

result = subprocess.run(
    ["claude", "-p", task],
    capture_output=True,
    text=True,
    timeout=300,
)

print("stdout:", result.stdout)
print("stderr:", result.stderr)
print("exit:", result.returncode)
```

Wrap this in an `execute()` call.

### 3. Iterating on the result
If the first output is incomplete, make a follow-up call with more context:
```python
result2 = subprocess.run(
    ["claude", "-p", f"Previous attempt:\n{result.stdout}\n\nNow fix the following issue: <issue>"],
    capture_output=True, text=True, timeout=300,
)
```

### 4. Codebase analysis
To analyse a remote repository:
```python
import subprocess, os, tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    subprocess.run(["git", "clone", "--depth=1", repo_url, tmpdir], check=True, timeout=120)
    result = subprocess.run(
        ["claude", "-p", f"Analyse the codebase at {tmpdir} and answer: <question>"],
        capture_output=True, text=True, timeout=300, cwd=tmpdir,
    )
    print(result.stdout)
```

## Output contract
- `claude_output`: full stdout from Claude Code
- `task_given`: the task description passed to Claude Code
- `exit_code`: 0 = success, non-zero = error
- `iterations`: number of claude invocations made
- If code was produced and saved, list the file paths in `artefacts`

## Quality bar
- Always capture both stdout and stderr — stderr contains tool use logs that explain what Claude did
- Set timeout ≥ 120s; complex tasks can take 2–3 minutes
- If exit code is non-zero, include stderr in proof under `error_output`
- Do not pass secrets or credentials in the task string — they will appear in logs

## Pairs with
- `code_execution` — use for simple one-shot scripts; use claude_code_agent for iterative work
- `web_browse` / `browser_use` — fetch specs or docs first, then pass them to Claude Code for implementation
- `dataset_inspection` — inspect a dataset's schema, then delegate cleaning/analysis to Claude Code
