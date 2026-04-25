---
description: Download a dataset from a URL and inspect its actual contents — schema,
  column types, shape, sample rows, and null counts. Supports CSV, Parquet, Excel,
  JSON, and JSONL. Use this to look inside a dataset, not just its landing page.
name: dataset_inspection
source: built-in
tags:
- data
- datasets
- inspection
- schema
- tabular
tools:
- url_fetch
---

## When to use
Apply when the work item requires assessing whether a specific dataset is fit for
purpose — what columns it has, what values are present, how complete it is, and
whether its coverage matches the task requirements. Use after web_search or
web_browse has identified a candidate dataset URL. Do not speculate about a
dataset's contents — inspect the actual file.

## How to execute
1. Obtain the direct download URL for the dataset file (not the landing page).
   If only a landing page URL is available, browse it first to find the download link.
2. Call fetch_url(url) — the tool returns schema, column types, shape, sample rows,
   and null counts automatically.
3. Assess fitness for purpose: does the geographic coverage match? Does the time
   range match? Are the key columns present and populated?
4. Note the file format, size, number of rows, and any missing-value patterns.
5. Record the dataset name, source organisation, licence, and direct download URL.
6. Flag any quality concerns: columns with high null rates, suspicious value ranges,
   unclear units, or mismatched geography.

## Output contract
Produce a dataset assessment card in the proof field containing: dataset name,
source URL, licence, format, dimensions (rows × columns), key columns and their
types, coverage (geography, time range, resolution), fitness verdict (suitable /
partially suitable / not suitable) with rationale, and quality concerns if any.

## Quality bar
- Always use the direct file URL — do not report on a landing page as if it were
  the dataset itself.
- State coverage (geography, time, resolution) explicitly — never assume.
- If the dataset is unsuitable, explain why and suggest what to look for instead.
- Record the licence — datasets without open licences must be flagged.

## Pairs well with
- web_search
- code_execution
- web_browse
