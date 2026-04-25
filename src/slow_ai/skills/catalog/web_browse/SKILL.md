---
description: Navigate to and extract content from specific web URLs. Good for reading
  data portals, documentation, and landing pages.
name: web_browse
source: built-in
tags:
- browse
- web
- scraping
tools:
- web_browse
---

## When to use
Apply when you have a specific URL that you need to read in full — a data portal,
regulation document, methodology page, research paper landing page, or any page
returned by a web_search that warrants deeper reading. Use after web_search has
identified promising sources. Do not use to discover URLs (use web_search for that).

## How to execute
1. Confirm the URL is the primary/authoritative source, not a secondary summary page.
2. Browse the URL and read the returned text in full before extracting anything.
3. Identify the key sections relevant to your task — ignore navigation, footers, ads.
4. Extract verbatim quotes for any critical facts, figures, or definitions.
5. If the page links to downloadable documents (PDFs, datasets), note the direct URLs
   for follow-up with pdf_extraction or dataset_inspection.
6. Note the page title, last-updated date if visible, and the organisation responsible.

## Output contract
Produce a structured note in the proof field with: source URL, page title, publishing
organisation, date retrieved, extracted key facts with verbatim quotes, and any
follow-up URLs identified for further inspection.

## Quality bar
- Extract verbatim text for any figures, thresholds, or legal/regulatory language —
  do not paraphrase critical quantitative claims.
- Record the exact URL browsed, not just the domain.
- If the page fails to load or returns an error, report this explicitly.
- Do not infer meaning not present in the page text.

## Pairs well with
- web_search
- pdf_extraction
- dataset_inspection
