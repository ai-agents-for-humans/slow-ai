---
name: browser_use
description: Drive a real browser with an LLM agent to interact with JavaScript-rendered pages, login flows, multi-step forms, and dynamic content that static HTTP fetching cannot reach.
tools: [browser_use]
source: built-in
tags:
- web
- browser
- interactive
- javascript
- scraping
---

## When to use
Use `browser_use` when:
- The target page is a JavaScript SPA that returns no useful content to a plain HTTP GET
- The task requires interaction: clicking, form submission, pagination, infinite scroll
- The content is behind authentication (describe the login steps in the task)
- Static `web_browse` returned empty or placeholder content

Do NOT use `browser_use` for simple pages that `web_browse` can already read — it is slower and consumes more resources.

## How to execute

### 1. Write a precise task description
The browser agent is driven by a natural-language task. Be specific:
- State the starting URL
- Describe each step (search for X, click Y, extract Z)
- State exactly what to return ("return the full text of the article", "return all prices in a table as JSON")

Good task: `"Go to https://arxiv.org/search/, search for 'diffusion models', and return the titles, authors, and abstracts of the first 5 results."`

Bad task: `"Find papers on diffusion models."`

### 2. Call the tool
```
browse_interactive(task="<precise task description>")
```
The agent will navigate, interact, and return the extracted content as a string.

### 3. Handle the result
- On success: `result` contains the extracted content. Parse it for your proof.
- On failure: `error` explains why. Common causes:
  - Page requires human CAPTCHA — cannot be automated, note in verdict
  - Login credentials not provided — restate task with credentials if available
  - Max steps reached — the page may require more interaction than expected

### 4. Combine with web_browse
Use `browser_use` to get past the JS gate, then `web_browse` on specific URLs the browser agent discovered if you need raw text parsing on child pages.

## Output contract
Return your findings in the `proof` dict under descriptive keys:
- `extracted_content`: the raw result from the browser agent
- `source_url`: the URL(s) visited
- `interaction_notes`: any notable observations about the page behaviour

## Quality bar
- Never use browser_use on a URL that web_browse already handled successfully
- If the task requires credentials you don't have, mark verdict=escalate and explain in proof
- If the page is geo-blocked or rate-limited, note it in proof and set confidence accordingly
- Always include the source URL in artefacts

## Pairs with
- `web_browse` — use for static pages; use browser_use only when interactivity is required
- `pdf_extraction` — browser_use can trigger a PDF download; url_fetch can then parse it
