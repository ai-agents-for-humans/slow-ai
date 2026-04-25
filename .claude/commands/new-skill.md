Create a new skill in the Slow AI skill catalog for: $ARGUMENTS

A skill is a named, reusable capability that specialist agents can be assigned at runtime. It lives in `src/slow_ai/skills/catalog/{skill_name}/SKILL.md`. The catalog is discovered from the filesystem automatically — no registry file to update.

## Steps

1. **Determine the skill name** — snake_case, descriptive of the capability not the tool (e.g. `regulatory_document_analysis`, not `pdf_reader`). Check existing skills first: `web_search`, `web_browse`, `pdf_extraction`, `dataset_inspection`, `code_execution`. Do not create a skill that duplicates one that already exists.

2. **Identify which existing tools it uses** — available tools: `perplexity_search`, `web_browse`, `url_fetch`, `code_execution`, `code_generation`, `read_prior_evidence`. Prefer composing existing tools. Only flag a new tool requirement if the capability genuinely cannot be built from what exists.

3. **Create the directory and write SKILL.md** at `src/slow_ai/skills/catalog/{skill_name}/SKILL.md`:

```markdown
---
name: {skill_name}
description: {one sentence — what capability this gives an agent}
source: built-in
tags:
- {tag1}
- {tag2}
tools:
- {tool_name}
---

## When to use
{One paragraph. What signals in a work item description should trigger this skill? Name the specific verbs, topics, or question types that indicate this skill is needed.}

## How to execute
1. {Step 1 — specific and actionable}
2. {Step 2}
...

## Output contract
{What must appear in the agent's proof dict? What artefacts must be written (filename, format)? Be explicit — the specialist agent will follow this exactly.}

## Quality bar
- {Pass/fail criterion — concrete, not vague}
- {Another criterion}
...

## Pairs well with
- {skill_name}
```

4. **Verify** — read back the file and confirm:
   - Frontmatter is valid YAML
   - `tools` lists only tool names that exist in `src/slow_ai/tools/`
   - The playbook is specific enough that an agent could follow it without ambiguity
   - The output contract says exactly what goes in `proof` and what artefacts are written
