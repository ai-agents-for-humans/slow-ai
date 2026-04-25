---
description: Search the web for information using natural language queries. Returns
  summaries and sources from live web results.
name: web_search
source: built-in
tags:
- search
- realtime
- general
tools:
- perplexity_search
---

## When to use
Apply when the work item requires discovering current facts, statistics, regulations,
market data, or any information that needs to come from live web sources. Signals
include: "find", "research", "what is the current", "identify", "discover", "look
up". Use early in a task to establish baselines before browsing specific URLs or
inspecting datasets.

## How to execute
1. Decompose the work item into 2–4 specific, narrow questions — avoid vague queries.
2. Write each query precisely: include domain, timeframe, and geography where relevant
   (e.g. "EU AI Act compliance requirements 2024" not "AI regulations").
3. Run each search and read the returned answer and citations carefully.
4. If the answer cites authoritative URLs (government, academic, primary source),
   follow them with web_browse to extract the full content.
5. Cross-check key facts with a second query phrased differently.
6. Record all citations — URL, title, and the specific claim each one supports.

## Output contract
Produce a structured findings block in the proof field containing: the specific
questions asked and answers found, all citations (URL + title + claim supported),
confidence in each finding (high / medium / low) with rationale, and any
contradictions found between sources.

## Quality bar
- Every factual claim must have at least one citation.
- Do not rely on a single source for high-stakes facts — verify with a second query.
- If results are sparse or contradictory, state that explicitly rather than guessing.
- Queries must be specific enough to return useful results — no single-word queries.
- Check timeframe — flag information older than 2 years as potentially stale.

## Pairs well with
- web_browse
- pdf_extraction
- dataset_inspection
