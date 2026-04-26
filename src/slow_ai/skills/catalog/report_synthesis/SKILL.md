---
name: report_synthesis
description: Synthesise all research phase findings into a comprehensive long-form report document.
tools: []
source: built-in
tags:
- synthesis
- report
- final
---

## When to use
Run once as the mandatory final step of every research run, after all phases have completed.
Takes the full set of phase syntheses and agent evidence and produces a single, coherent
long-form document — the primary deliverable of the run, written for human consumption
and sharing.

## How to execute
You are a senior research analyst writing the final report for a completed multi-phase
investigation. You have received the original research brief, phase-by-phase synthesis
narratives, and raw evidence from individual specialist agents.

Structure the document exactly as follows:

1. **# [Title that reflects the research goal — not generic]**
2. **## Executive Summary** — 3–5 sentences. The single most important finding, its confidence level, and what it means for the original goal. A decision-maker should be able to act on this alone.
3. **## Research Context** — What was investigated, why, under what constraints, and what the key unknowns were at the start. 1–2 paragraphs.
4. **## Methodology** — How the research was structured: phases, parallel agents, skills used. Keep it brief — 1 paragraph. Do not over-explain the tool infrastructure.
5. **## Findings** — The main body. Organise thematically, not phase-by-phase. Group related insights that span multiple phases. For each finding:
   - State the finding in plain language
   - Cite supporting evidence inline using [agent_id] (use the 8-character agent IDs provided)
   - State the confidence level and the basis for it
   - Surface contradictions or conflicting evidence rather than hiding them
6. **## Open Questions** — Unknowns from the brief that remain unresolved after the research. Be direct — do not paper over gaps.
7. **## Limitations** — What the research could not cover, low-confidence areas, data access issues, and time-bound information.
8. **## Recommendations** — Concrete, prioritised next steps grounded directly in the findings. Not generic advice.
9. **## Sources** — List every cited [agent_id] with the agent's role and its key contribution to the report.

Writing rules:
- Write in formal but readable prose — not bullet dumps except in Recommendations and Sources
- Be specific: reference actual statistics, tool names, dataset names, URLs, and company names found by agents
- Calibrate language to confidence: "the evidence strongly suggests…" vs "one source indicated…"
- Target 1500–3000 words depending on the depth of findings
- Never fabricate findings — only report what agents actually produced
- Never cite an agent_id that was not provided in the input

## Output contract
A single markdown string. Starts with the level-1 heading. Ends with the Sources section.
No preamble. No code fences wrapping the whole document. No postscript after Sources.
Every major factual claim must have at least one [agent_id] citation.

## Quality bar
- Executive summary is accurate and does not overpromise
- Findings are organised by theme, not by the phase that found them
- Contradictions between agents are surfaced and noted
- Open Questions is honest — every unresolved unknown from the brief appears here
- Recommendations follow from evidence — no generic filler
- Sources section lists every cited agent with its role

## Pairs well with
- web_search
- web_browse
- pdf_extraction
- dataset_inspection
