---
layout: default
title: Workflow Ecosystem Design
nav_order: 9
---

# Slow AI — Workflow Ecosystem Design
{: .no_toc }

The evolution of Slow AI from a research orchestration system into a general-purpose distributed workflow platform powered by AI agents.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## The shift in framing

Slow AI started as a research tool. The core insight that made it work — phase-based decomposition, parallel specialist agents, evidence envelopes, skill catalog, file-based state, git as memory — has nothing to do with research specifically.

**Research is one workflow. There are thousands of others.**

A workflow is: *decompose an objective into phases, run agents in parallel within each phase, collect structured outputs, feed them forward, produce a final artifact.* Slow AI already does this. The only thing that was research-specific was the brief model, the system prompts, and the final output format.

This document defines what changes, what stays, and what the new system looks like.

---

## What stays (the invariants)

These are not changing. They are the foundation.

| Invariant | Why it stays |
|---|---|
| Two-plane architecture (UI reads, engine writes) | Subprocess isolation solves real async problems. Nothing breaks this. |
| File-based state | Any consumer reads the same files. CLI, UI, external scripts — no coupling needed. |
| Git as long-term memory | One branch per run. Milestone commits. The corpus is the training data. |
| Evidence envelopes as the atomic output unit | Every claim traceable to an agent, a confidence score, artefacts. This works for any workflow, not just research. |
| Skill catalog | Domain knowledge in SKILL.md files, not in agent prompts. Skills compose. |
| Phase-based, wave-driven execution | Phases are sequential. Work items within a phase are parallel. Orchestrator assesses between phases. |

---

## What changes

### 1. WorkflowBrief replaces ProblemBrief

`ProblemBrief` has research-specific fields: `research_questions`, `knowledge_gaps`, `success_criteria` framed around information discovery.

`WorkflowBrief` generalises this:

```python
class WorkflowBrief(BaseModel):
    workflow_id: str
    workflow_type: str          # "research" | "production" | "distribution" | "custom"
    objective: str              # what this workflow achieves
    domain: str
    context: str                # background the agents need
    constraints: list[str]      # time, cost, format, legal, etc.
    inputs: dict                # named inputs (URLs, file paths, config values)
    output_spec: OutputSpec     # what the final artifact looks like
    schedule: ScheduleSpec | None  # cron expression + trigger config
    prior_run_ids: list[str]    # for chaining workflows
    tags: list[str]             # for cataloguing and filtering
```

```python
class OutputSpec(BaseModel):
    type: str                   # "document" | "audio" | "playlist" | "dataset" | "code" | "custom"
    format: str                 # "markdown" | "mp3" | "json" | "csv" | "html" | etc.
    destination: str | None     # "local" | "google_drive" | "s3" | "rss_feed" | etc.
    filename_template: str      # e.g. "morning-show-{date}.mp3"
```

`ProblemBrief` is kept as a subtype for backwards compatibility. Existing research runs continue working.

---

### 2. Skill catalog expands beyond research

The current catalog has 5 research skills: `web_search`, `web_browse`, `pdf_extraction`, `dataset_inspection`, `code_execution`.

The expanded catalog adds three new categories:

**Production skills** — transform content into new formats:
- `text_to_speech` — convert script text to audio (Gemini TTS, ElevenLabs)
- `audio_assembly` — mix audio segments, add music beds, normalise levels (ffmpeg)
- `script_generation` — generate creative content (dialogues, narration, structured prose)
- `image_generation` — generate images or thumbnails

**Integration skills** — connect to external services:
- `spotify_api` — search tracks, curate playlists, get audio features, generate timing manifests
- `calendar_api` — read/write Google Calendar events
- `drive_upload` — upload files to Google Drive, generate shareable links
- `rss_publish` — append an item to an RSS feed, generate podcast enclosures
- `email_send` — send structured email with attachments

**Curation skills** — filter, rank, and personalise:
- `interest_filter` — score content against a personal interest profile
- `deduplication` — identify and remove near-duplicate content across sources
- `trend_detection` — identify emerging themes across a corpus

Each skill gets a full `SKILL.md` in `src/slow_ai/skills/catalog/{skill_name}/` with tools, playbook, and output contract — same pattern as today.

---

### 3. Scheduled runs (cron capability)

Today, every run starts with a human-initiated interview. Workflows need scheduled, headless runs.

A `WorkflowSchedule` stores a brief + approved graph + cron expression. At trigger time, the engine launches the run without any interview step.

```python
class WorkflowSchedule(BaseModel):
    schedule_id: str
    name: str
    cron: str                   # standard cron expression, e.g. "0 2 * * *"
    workflow_brief: WorkflowBrief
    approved_graph: ContextGraph
    enabled: bool
    last_run_id: str | None
    last_run_at: datetime | None
    created_at: datetime
```

Schedules are stored in `schedules/{schedule_id}.json`. A lightweight scheduler process (or the existing FastAPI app via `apscheduler`) reads these files and fires runs at the right time.

New API routes:
- `POST /api/schedules` — create a schedule from an approved brief+graph
- `GET /api/schedules` — list all schedules
- `PUT /api/schedules/{schedule_id}` — enable/disable, update cron
- `DELETE /api/schedules/{schedule_id}` — remove

---

### 4. Generalized final output

Today the final step always calls `generate_final_report()` and writes `final_report.md`.

With `OutputSpec` on the brief, the runner dispatches to the right output handler:

```python
OUTPUT_HANDLERS = {
    "document": generate_final_report,      # existing
    "audio":    assemble_audio_output,      # new
    "playlist": generate_playlist_output,   # new
    "dataset":  compile_dataset_output,     # new
}
```

Each handler receives `(brief, phase_summaries, all_envelopes)` and returns a `WorkflowOutput`:

```python
class WorkflowOutput(BaseModel):
    artifact_path: str          # path under runs/{run_id}/output/
    artifact_type: str
    metadata: dict
    summary: str                # one-paragraph human-readable summary
```

The git store commits the output as a milestone. The UI shows it under a generic "Output" tab that renders based on type — markdown renders as before, audio gets an inline player, datasets get a table preview.

---

### 5. Personal interest profile

For curation workflows, agents need to know what the person cares about. This is stored as a profile in `profiles/default.json` (multiple profiles supported for different workflow types).

```json
{
  "profile_id": "default",
  "name": "Nischal",
  "interests": [
    "AI agents and multi-agent systems",
    "LLM infrastructure and serving",
    "developer tools and CLI",
    "machine learning research (especially RL)",
    "startups building in AI"
  ],
  "avoid": [
    "AI hype without substance",
    "cryptocurrency",
    "social media drama"
  ],
  "preferred_depth": "technical but accessible",
  "preferred_tone": "direct, curious, some humor"
}
```

The `interest_filter` skill reads this profile to score and rank content. Agents reference it in their system prompt when the workflow brief specifies `profile_id`.

---

## The morning show workflow — first non-research workflow

This is the concrete use case that drives the design above. It runs nightly and produces a dated audio file.

### Workflow brief (what gets stored in the schedule)

```
objective: Generate a personalized AI morning radio show for {date}
workflow_type: production
output_spec:
  type: audio
  format: mp3 + timing_manifest.md
  destination: google_drive
  filename_template: "morning-show-{date}"
```

### Phases

```
Phase 1 — News ingestion (parallel)
  Agents: one per RSS/news source cluster
  Skills: web_browse, web_search
  Output: raw article corpus (title, summary, URL, published_at)

Phase 2 — Curation (parallel)
  Agents: interest_filter agent, deduplication agent, trend_detection agent
  Skills: interest_filter, deduplication, trend_detection
  Input: Phase 1 corpus
  Output: ranked shortlist of 5-8 stories with relevance scores + angle notes

Phase 3 — Script generation (parallel)
  Agents: host_alice (personality A), host_bob (personality B), music_curator
  Skills: script_generation, spotify_api
  Input: curated story shortlist + interest profile
  Output:
    - host_alice: her lines + reactions
    - host_bob: his lines + reactions
    - music_curator: Spotify playlist + track timing cues
  
Phase 4 — Script assembly (single agent)
  Agent: script_assembler
  Skills: script_generation
  Input: host lines + music cues
  Output: interleaved dialogue script with timing markers

Phase 5 — Audio production (parallel)
  Agents: voice_renderer_alice, voice_renderer_bob
  Skills: text_to_speech
  Input: script segments by speaker
  Output: per-segment audio files (wav)

Phase 6 — Final mix (single agent)
  Agent: audio_mixer
  Skills: audio_assembly
  Input: voice segments + music timing manifest
  Output: final mixed mp3 + timing_manifest.md

Phase 7 — Distribution
  Agent: publisher
  Skills: drive_upload, rss_publish
  Input: final mp3 + manifest
  Output: Google Drive link + RSS enclosure URL
```

### The timing manifest format

```markdown
# Morning Show — 2026-04-27

## Segments

00:00 — [MUSIC] Spotify: spotify:track:abc123 — fade in 3s, play 30s, fade out 3s
00:33 — [HOST_ALICE] "Good morning! I'm Alice..."
01:15 — [HOST_BOB] "And I'm Bob. So today in AI..."
02:45 — [MUSIC] Spotify: spotify:track:def456 — bridge, 15s
03:00 — [ALICE] "The big story today..."
...

## Spotify Playlist
spotify:playlist:xyz789

## Total duration: 22:34
```

The personal audio player (a separate app, not part of Slow AI) reads this manifest and coordinates: plays the mp3 for voice segments, triggers Spotify SDK for music segments at the right timestamps.

---

## What the personal audio player needs to do

This is a separate small application — a lightweight web app or Electron app — that:

1. Reads a `timing_manifest.md`
2. Plays the voice audio (mp3 segments or the mixed mp3) via standard HTML5 audio
3. At music cue timestamps, triggers `Spotify Web Playback SDK` to play the specified track
4. Handles fade in/out transitions
5. Shows current segment title as a "now playing" display

It does not need to be part of Slow AI. It is a consumer of Slow AI's output artifacts.

---

## Implementation order

This is the sequence that minimises rework and validates assumptions early.

### Phase A — Foundation (model + scheduler)
1. Add `WorkflowBrief`, `OutputSpec`, `WorkflowSchedule`, `WorkflowOutput` to `models.py`
2. Keep `ProblemBrief` as a `WorkflowBrief` alias/subtype for backwards compatibility
3. Add `schedules/` directory handling to `GitStore`
4. Add `WorkflowSchedule` CRUD to the API
5. Add a simple scheduler (APScheduler) that reads `schedules/*.json` and fires runs

### Phase B — New skills
6. `interest_filter` skill + tool (scores content list against a profile)
7. `script_generation` skill (creative dialogue, not research synthesis)
8. `spotify_api` skill + tool (Spotify Web API: search, playlist create)
9. `text_to_speech` skill + tool (Gemini TTS or ElevenLabs)
10. `audio_assembly` skill + tool (ffmpeg wrapper: concat, mix, normalise)
11. `drive_upload` skill + tool (Google Drive API: upload + share link)

### Phase C — Output generalisation
12. Generalise runner's final step to dispatch via `OutputSpec.type`
13. Add `audio` output handler
14. Update UI to render audio output (inline player + manifest viewer)

### Phase D — Morning show workflow
15. Define the morning show `WorkflowBrief` + `ContextGraph` as static JSON files
16. Register as a schedule (`0 2 * * *` — runs at 2am)
17. Run end-to-end manually first, fix gaps
18. Enable cron

### Phase E — Audio player app
19. Small standalone web app (vanilla JS + HTML)
20. Reads timing manifest, plays mp3, triggers Spotify Web Playback SDK at cue points
21. Serve it as a static page from Slow AI's FastAPI app or as a separate app

---

## README changes required

The README needs to change at the top level. The current headline — "research orchestration" — undersells what this is.

**New positioning:** Slow AI is a distributed workflow platform where AI agents do the work. Research workflows, production workflows, data workflows, any workflow. The morning show is the flagship non-research example.

Sections to update:
- **What you get back** — generalise from "your research data" to "your workflow outputs"
- **How it runs** — add the workflow type concept, mention scheduling
- **Your first run** — add a second example (the morning show) alongside the research example
- **The nerdy bit** — update to reflect the expanded skill catalog and output types

---

## Open questions before implementation

1. **Profile storage** — single `profiles/default.json` or per-workflow profiles referenced by ID? Per-workflow is more flexible but adds UI complexity.

2. **Cron scheduler process** — embed APScheduler inside the FastAPI app (simpler, single process) or run as a separate `slow-ai-scheduler` process (cleaner separation but more ops)? Given the two-plane architecture principle, a separate process aligns better.

3. **Audio player** — build it as a route inside Slow AI's FastAPI app (`/player/{run_id}`) or as a fully separate repo? Having it in the same app makes sharing links easy; separate repo keeps concerns clean.

4. **TTS provider** — Gemini's TTS is the path of least resistance (already integrated). ElevenLabs gives significantly better voice quality and two distinct voices. Worth the extra key?

5. **Backwards compatibility** — workflows created before this change used `ProblemBrief`. The migration path (alias + adapter in the runner) is straightforward but needs a decision on whether to auto-migrate existing run directories.
