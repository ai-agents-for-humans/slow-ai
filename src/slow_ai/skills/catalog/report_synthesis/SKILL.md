---
name: report_synthesis
description: Produce a comprehensive, detail-preserving research report from all phase findings and agent evidence.
tools: []
source: built-in
tags:
- synthesis
- report
- final
---

## When to use
Run once as the mandatory final step of every research run, after all phases have completed.
Takes the full set of phase syntheses and every agent's evidence and produces a single
long-form document — the primary deliverable of the run, written for a practitioner who
needs to act on the research and will not go back to re-run it.

## Core principle
**Do not summarise. Preserve and organise.**
Every piece of evidence, every data point, every finding from every agent belongs in this
report. Your job is not to cut — it is to arrange all the detail into a structure that a
reader can navigate. A reader should be able to make decisions based on this report alone
without needing to dig into the raw evidence.

## How to execute

Structure the document as follows:

### 1. Title
A specific title that reflects the actual research goal, not a generic label.

### 2. Executive Overview (3–5 sentences)
The single most important finding and its confidence level. What it means for the original
goal. Anything a decision-maker must know upfront. This is the only brief section — write
it last so it accurately reflects what follows.

### 3. Research Scope
- What was investigated and why
- Key unknowns at the start
- Success criteria from the brief
- What was explicitly excluded and why

### 4. Findings — one section per phase
For each phase, write a dedicated section with its full name as the heading. Within each
phase section:
  - Open with the phase-level synthesis (the orchestrator's assessment)
  - Then a dedicated subsection for **each agent** in the phase:
    - Agent name and role as a sub-heading
    - All findings from that agent in full — do not truncate, do not paraphrase away detail
    - Specific data points: numbers, names, URLs, dates, quotes, rankings, comparisons
    - Confidence level and basis for it
    - Contradictions with other agents explicitly noted

### 5. Cross-Phase Synthesis
Patterns and conclusions that emerge across multiple phases. What phase 1 set up that
phase 2 confirmed or contradicted. How the picture evolved. This is the only place where
you synthesise across phases — the phase sections must preserve the raw findings in full.

### 6. Open Questions
Unknowns from the original brief that remain unresolved. Be direct and specific — do not
paper over gaps or pretend the research answered everything.

### 7. Limitations
What the research could not cover. Low-confidence areas and why. Data that was unavailable.
Time-bound information that may have already changed.

### 8. Recommendations
Concrete, prioritised next steps grounded in specific findings from this report. Each
recommendation cites the evidence it rests on. No generic advice — every recommendation
must be traceable to something an agent found.

### 9. Sources
List every agent with their role, phase, confidence score, and their single most important
contribution to the report.

## Writing rules
- Write in clear, readable prose with headers — not bullet dumps except where lists
  genuinely add clarity (e.g. ranked lists of items, step-by-step actions)
- Be specific everywhere: actual numbers, actual URLs, actual company names, actual quotes
- Calibrate language: "the data strongly shows…" vs "one source indicated…"
- Preserve all contradictions and tensions — do not flatten them into false consensus
- When an agent produced a ranked list or table, reproduce it in full
- Never fabricate — only report what agents actually produced
- Never cite an agent_id that was not provided
- Length follows from the material: if the research is deep, the report is long — do not
  artificially compress

## Output contract
A single markdown document. Starts with the level-1 title heading. Ends with Sources.
No preamble. No code fences. No postscript.
Every major factual claim has at least one [agent_id] citation where an agent produced it.

## Quality bar
- A reader who did not see the run can reconstruct every key finding from this document
- No agent's key findings are lost or compressed to the point of uselessness
- Contradictions between agents are surfaced, not resolved by picking one side
- Open Questions is honest about every unresolved unknown
- Recommendations each trace back to specific evidence
- Sources section lists every agent with role and contribution
