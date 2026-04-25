---
description: Download a PDF from a URL and extract its full text — ideal for research
  papers, reports, and documentation. Returns page count and extracted text.
name: pdf_extraction
source: built-in
tags:
- pdf
- research
- papers
- documents
- extraction
tools:
- url_fetch
---

## When to use
Apply when the work item requires reading the actual content of a research paper,
technical report, regulation document, methodology specification, or any content
published as a PDF. Use when web_browse returns only a landing page or abstract
and the full text is needed. Signals: "read the paper", "extract from the report",
"check the methodology", "find the exact wording in".

## How to execute
1. Confirm the URL points directly to a PDF (ends in .pdf or is a direct download
   link from a publisher/repository), not to an HTML landing page.
2. Call fetch_url(url) — the tool will download and extract the text automatically.
3. Read the returned text in full before extracting anything.
4. Identify the sections relevant to the task: abstract, methodology, results,
   appendix. Skip unrelated sections to stay within budget.
5. Extract verbatim quotes for any key definitions, thresholds, equations, or findings.
6. Note the document title, authors, year, and publisher for citation purposes.

## Output contract
Produce a citation block (title, authors, year, URL) and a structured extraction
containing: relevant section names, verbatim quotes for all critical facts, and a
plain-language summary of what the document contributes to the task.

## Quality bar
- Never paraphrase quantitative thresholds, legal definitions, or formula
  components — always quote verbatim.
- Record the full citation (not just the URL) for every document extracted.
- If extraction fails or returns garbled text, report this explicitly.
- Only extract sections relevant to the task — do not dump entire documents.

## Pairs well with
- web_search
- web_browse
- dataset_inspection
