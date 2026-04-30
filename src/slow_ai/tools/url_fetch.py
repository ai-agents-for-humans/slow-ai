"""
url_fetch — download a file from a URL and extract meaningful content based on type.

Handles:
  - PDF      → full text extraction (pdfplumber)
  - CSV      → schema, dtypes, shape, sample rows, null counts
  - JSON/JSONL → structure, key inventory, sample records
  - Excel    → same as CSV (openpyxl / xlrd if installed)
  - Parquet  → same as CSV (pyarrow if installed)
  - HTML     → falls back to readable text extraction (like web_browse)
  - Plain text → returned as-is
"""

import io
import json

import httpx
from pydantic import BaseModel

_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB hard cap
_MAX_CHARS = 6000
_MAX_ROWS = 50


class FetchResult(BaseModel):
    url: str
    content_type: str  # "pdf" | "csv" | "json" | "excel" | "parquet" | "html" | "text" | "unknown"
    summary: str  # human-readable description of what was found
    data: dict  # structured payload (schema, sample, etc.)
    success: bool = True
    error: str | None = None


async def url_fetch(url: str) -> FetchResult:
    """
    Download a file from a URL and return its contents in a structured, agent-readable form.

    Use this to inspect actual datasets (CSV, Parquet, Excel, JSON) and research papers (PDF),
    not just their landing pages. Returns schema, sample rows, and summaries.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SlowAI-Research/1.0)"},
        ) as client:
            # Stream the response so we can cap download size
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                raw_content_type = response.headers.get("content-type", "").lower()
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_DOWNLOAD_BYTES:
                        break
                raw = b"".join(chunks)

    except Exception as e:
        return FetchResult(
            url=url,
            content_type="unknown",
            summary="",
            data={},
            success=False,
            error=str(e),
        )

    # Detect type from Content-Type header first, then URL extension
    detected = _detect_type(raw_content_type, url)

    try:
        if detected == "pdf":
            return _handle_pdf(url, raw)
        elif detected == "csv":
            return _handle_tabular(url, raw, "csv")
        elif detected in ("excel", "xlsx", "xls"):
            return _handle_tabular(url, raw, "excel")
        elif detected == "parquet":
            return _handle_tabular(url, raw, "parquet")
        elif detected == "json":
            return _handle_json(url, raw)
        elif detected == "jsonl":
            return _handle_jsonl(url, raw)
        elif detected == "html":
            return _handle_html(url, raw)
        else:
            # Try to decode as text
            text = raw.decode("utf-8", errors="replace")[:_MAX_CHARS]
            return FetchResult(
                url=url,
                content_type="text",
                summary=f"Plain text — {len(raw):,} bytes.",
                data={"text": text},
            )
    except Exception as e:
        return FetchResult(
            url=url,
            content_type=detected,
            summary="",
            data={},
            success=False,
            error=f"Extraction failed: {e}",
        )


# ── Type detection ────────────────────────────────────────────────────────────


def _detect_type(content_type: str, url: str) -> str:
    ct = content_type.split(";")[0].strip()
    mime_map = {
        "application/pdf": "pdf",
        "text/csv": "csv",
        "application/csv": "csv",
        "application/json": "json",
        "application/x-ndjson": "jsonl",
        "application/vnd.ms-excel": "excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
        "application/octet-stream": "binary",
        "text/html": "html",
        "text/plain": "text",
    }
    if ct in mime_map and mime_map[ct] != "binary":
        return mime_map[ct]

    # Fall back to URL extension
    path = url.split("?")[0].lower()
    ext_map = {
        ".pdf": "pdf",
        ".csv": "csv",
        ".tsv": "csv",
        ".json": "json",
        ".jsonl": "jsonl",
        ".ndjson": "jsonl",
        ".xlsx": "excel",
        ".xls": "excel",
        ".parquet": "parquet",
        ".pq": "parquet",
        ".html": "html",
        ".htm": "html",
        ".txt": "text",
        ".md": "text",
    }
    for ext, kind in ext_map.items():
        if path.endswith(ext):
            return kind

    # Peek at first bytes for PDF magic bytes
    return "unknown"


# ── Handlers ──────────────────────────────────────────────────────────────────


def _handle_pdf(url: str, raw: bytes) -> FetchResult:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages[:30]:  # cap at 30 pages
            t = page.extract_text()
            if t:
                text_parts.append(t)

    full_text = "\n\n".join(text_parts)
    preview = full_text[:_MAX_CHARS]
    truncated = len(full_text) > _MAX_CHARS

    return FetchResult(
        url=url,
        content_type="pdf",
        summary=f"PDF — {n_pages} page(s), {len(full_text):,} chars extracted.",
        data={
            "pages": n_pages,
            "text": preview + ("\n\n[truncated]" if truncated else ""),
            "truncated": truncated,
        },
    )


def _handle_tabular(url: str, raw: bytes, fmt: str) -> FetchResult:
    import pandas as pd

    if fmt == "csv":
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    elif fmt == "excel":
        df = pd.read_excel(io.BytesIO(raw))
    elif fmt == "parquet":
        df = pd.read_parquet(io.BytesIO(raw))
    else:
        raise ValueError(f"Unknown tabular format: {fmt}")

    rows, cols = df.shape
    dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
    null_counts = {col: int(df[col].isna().sum()) for col in df.columns}
    sample = df.head(_MAX_ROWS).to_dict(orient="records")

    # Numeric summary for numeric columns
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    describe = {}
    if numeric_cols:
        desc = df[numeric_cols].describe().round(3)
        describe = desc.to_dict()

    col_list = ", ".join(df.columns[:20]) + ("…" if len(df.columns) > 20 else "")
    summary = f"{fmt.upper()} — {rows:,} rows × {cols} columns. Columns: {col_list}."

    return FetchResult(
        url=url,
        content_type=fmt,
        summary=summary,
        data={
            "shape": [rows, cols],
            "columns": list(df.columns),
            "dtypes": dtypes,
            "null_counts": null_counts,
            "sample_rows": sample,
            "numeric_summary": describe,
        },
    )


def _handle_json(url: str, raw: bytes) -> FetchResult:
    text = raw.decode("utf-8", errors="replace")
    parsed = json.loads(text)

    if isinstance(parsed, list):
        n = len(parsed)
        sample = parsed[:10]
        keys = (
            sorted(set().union(*[d.keys() for d in sample if isinstance(d, dict)]))
            if sample
            else []
        )
        summary = f"JSON array — {n:,} records. Keys: {', '.join(str(k) for k in keys[:20])}."
        return FetchResult(
            url=url,
            content_type="json",
            summary=summary,
            data={"type": "array", "length": n, "keys": keys, "sample": sample},
        )
    elif isinstance(parsed, dict):
        keys = list(parsed.keys())
        summary = (
            f"JSON object — {len(keys)} top-level keys: {', '.join(str(k) for k in keys[:20])}."
        )
        return FetchResult(
            url=url,
            content_type="json",
            summary=summary,
            data={"type": "object", "keys": keys, "preview": str(parsed)[:_MAX_CHARS]},
        )
    else:
        return FetchResult(
            url=url,
            content_type="json",
            summary="JSON scalar value.",
            data={"value": parsed},
        )


def _handle_jsonl(url: str, raw: bytes) -> FetchResult:
    lines = raw.decode("utf-8", errors="replace").splitlines()
    records = []
    for line in lines[:10]:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    keys = (
        sorted(set().union(*[d.keys() for d in records if isinstance(d, dict)])) if records else []
    )
    summary = f"JSONL — {len(lines):,} lines. Keys: {', '.join(str(k) for k in keys[:20])}."
    return FetchResult(
        url=url,
        content_type="jsonl",
        summary=summary,
        data={"line_count": len(lines), "keys": keys, "sample": records},
    )


def _handle_html(url: str, raw: bytes) -> FetchResult:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.find("body")
    text = " ".join(main.get_text(separator=" ").split()) if main else ""
    text = text[:_MAX_CHARS]
    return FetchResult(
        url=url,
        content_type="html",
        summary=f"HTML page — title: {title!r}. {len(text):,} chars of readable text.",
        data={"title": title, "text": text},
    )
