---
description: Execute arbitrary Python code in an isolated subprocess. Use for data
  transformation, statistical analysis, geospatial processing, knowledge graph modeling,
  ontology engineering, RDF serialization, data visualization, document parsing, and
  any computation task. Always print() results to capture them.
name: code_execution
source: built-in
tags:
- compute
- python
- analysis
- transformation
- modeling
tools:
- code_execution
---

## When to use
Apply when the work item requires any computation that cannot be done by reading web
pages — numerical analysis, data transformation, statistical modelling, geospatial
processing, graph construction, document parsing, or producing structured output from
raw data. If the task says "calculate", "model", "analyse data", "build", "generate",
"process", or "compute", this skill is needed.

## How to execute
1. Use generate_python_code(task_description) first — describe what the code must do,
   what inputs it will use, and what it must print as output. Let the code specialist
   write well-structured code rather than writing ad-hoc snippets.
2. Review the generated code before executing — check that it prints results, handles
   edge cases, and does not rely on external files that aren't present.
3. Run the code with execute(code) and capture stdout/stderr.
4. If execution fails, read the error, adjust the code, and retry — do not give up
   after one failure.
5. Save meaningful code as a named .py artefact (include agent_id in the filename).
6. Interpret the output in plain language — what do the numbers mean for the task?

## Output contract
Produce: one .py artefact with the complete, runnable code; printed output captured
in the proof field; and a plain-language interpretation of the results. Code must
be self-contained — another person should be able to run it and get the same output.

## Quality bar
- Always call generate_python_code first — do not write raw code strings manually.
- Every result the task needs must be printed — nothing that stays in a variable.
- Code must run without external credentials or proprietary data not available.
- On failure, report the exact error and what was tried to fix it.
- Interpret numerical results — do not just dump raw numbers.

## Pairs well with
- dataset_inspection
- web_search
- pdf_extraction
