"""
run_reader — read-only tools for the post-run conversation agent.

All functions read from a fixed run directory (closed over at agent construction time).
Nothing is written. Nothing is executed. The agent uses these to answer questions
about what the swarm found without spawning any new research agents.
"""

import json
import re
from pathlib import Path


def make_run_reader_tools(run_path: Path):
    """
    Return a dict of tool functions closed over run_path.
    Register these with the conversation agent.
    """

    def list_phases() -> str:
        """
        List all phases that ran, with their name, confidence score,
        and covered/partial/uncovered work item counts.
        Call this first to get an overview of what happened.
        """
        path = run_path / "live" / "phase_summaries.json"
        if not path.exists():
            return json.dumps({"error": "No phase summaries found for this run."})
        summaries = json.loads(path.read_text(encoding="utf-8"))
        result = []
        for s in summaries:
            result.append(
                {
                    "phase_id": s["phase_id"],
                    "phase_name": s["phase_name"],
                    "mean_confidence": round(s.get("mean_confidence", 0.0), 3),
                    "covered_items": s.get("covered_item_ids", []),
                    "partial_items": s.get("partial_item_ids", []),
                    "uncovered_items": s.get("uncovered_item_ids", []),
                    "total_tokens": s.get("total_tokens", 0),
                }
            )
        return json.dumps(result, indent=2)

    def read_phase(phase_id: str) -> str:
        """
        Read the full synthesis narrative and envelope summaries for a specific phase.
        Use phase_id values from list_phases() (e.g. 'phase-1', 'phase-2').
        """
        path = run_path / "syntheses" / f"{phase_id}.json"
        if not path.exists():
            # Fall back to live summary
            live = run_path / "live" / "phase_summaries.json"
            if live.exists():
                for s in json.loads(live.read_text(encoding="utf-8")):
                    if s["phase_id"] == phase_id:
                        return json.dumps(
                            {
                                "phase_id": phase_id,
                                "phase_name": s["phase_name"],
                                "synthesis": s.get("synthesis", ""),
                                "mean_confidence": s.get("mean_confidence", 0),
                                "covered_items": s.get("covered_item_ids", []),
                                "partial_items": s.get("partial_item_ids", []),
                                "uncovered_items": s.get("uncovered_item_ids", []),
                            },
                            indent=2,
                        )
            return json.dumps({"error": f"Phase '{phase_id}' not found."})

        data = json.loads(path.read_text(encoding="utf-8"))
        # Return synthesis + per-envelope summaries (not full proof — agent must call
        # read_envelope explicitly to get the raw evidence)
        envelope_summaries = []
        for env in data.get("envelopes", []):
            envelope_summaries.append(
                {
                    "agent_id": env.get("agent_id"),
                    "role": env.get("role"),
                    "status": env.get("status"),
                    "confidence": env.get("confidence"),
                    "verdict": env.get("verdict"),
                    "artefacts": env.get("artefacts", []),
                }
            )
        return json.dumps(
            {
                "phase_id": data.get("phase_id"),
                "phase_name": data.get("phase_name"),
                "synthesis": data.get("synthesis", ""),
                "mean_confidence": data.get("mean_confidence", 0),
                "covered_items": data.get("covered_item_ids", []),
                "partial_items": data.get("partial_item_ids", []),
                "uncovered_items": data.get("uncovered_item_ids", []),
                "envelope_summaries": envelope_summaries,
            },
            indent=2,
        )

    def read_envelope(agent_id: str) -> str:
        """
        Read the full evidence envelope for a specific agent — including its proof dict,
        confidence reasoning, and verdict. Use agent_id values from read_phase().
        """
        # Envelopes are stored as envelopes/{phase_id}/{agent_id}.json
        matches = list(run_path.glob(f"envelopes/**/{agent_id}.json"))
        if not matches:
            return json.dumps({"error": f"No envelope found for agent_id '{agent_id}'."})
        data = json.loads(matches[0].read_text(encoding="utf-8"))
        return json.dumps(data, indent=2)

    def read_report() -> str:
        """
        Read the final synthesised report for this run — includes datasets found,
        summary narrative, and paths not taken.
        """
        path = run_path / "report.json"
        if not path.exists():
            return json.dumps({"error": "No report found — run may not have completed."})
        return path.read_text(encoding="utf-8")

    def search_evidence(keyword: str) -> str:
        """
        Search for a keyword across all phase syntheses and evidence envelopes.
        Returns a list of matches with their source and a surrounding snippet.
        Use this to find where specific topics, datasets, or findings are mentioned.
        """
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        matches = []

        # Search phase syntheses
        for synth_path in (
            sorted((run_path / "syntheses").glob("*.json"))
            if (run_path / "syntheses").exists()
            else []
        ):
            try:
                data = json.loads(synth_path.read_text(encoding="utf-8"))
                text = data.get("synthesis", "")
                for m in pattern.finditer(text):
                    start = max(0, m.start() - 100)
                    end = min(len(text), m.end() + 100)
                    matches.append(
                        {
                            "source": f"synthesis:{data.get('phase_id', synth_path.stem)}",
                            "snippet": "…" + text[start:end] + "…",
                        }
                    )
            except Exception:
                pass

        # Search envelopes
        for env_path in sorted(run_path.glob("envelopes/**/*.json")):
            try:
                data = json.loads(env_path.read_text(encoding="utf-8"))
                proof_text = json.dumps(data.get("proof", {}))
                for m in pattern.finditer(proof_text):
                    start = max(0, m.start() - 100)
                    end = min(len(proof_text), m.end() + 100)
                    matches.append(
                        {
                            "source": f"envelope:{data.get('agent_id', env_path.stem)}:{data.get('role', '')}",
                            "snippet": "…" + proof_text[start:end] + "…",
                        }
                    )
                    if len(matches) >= 20:
                        break
            except Exception:
                pass
            if len(matches) >= 20:
                break

        if not matches:
            return json.dumps({"matches": [], "note": f"No results found for '{keyword}'."})
        return json.dumps({"keyword": keyword, "matches": matches[:20]}, indent=2)

    def read_artefact(relative_path: str) -> str:
        """
        Read a specific artefact file produced during the run — e.g. a downloaded dataset
        sample, a generated Python script, or a parsed document.
        Use paths like 'artefacts/phase-1/agent-abc123/data.csv'.
        List available artefacts by checking envelope.artefacts from read_envelope().
        """
        # Sanitise path — no directory traversal
        safe = Path(relative_path).parts
        if ".." in safe or relative_path.startswith("/"):
            return json.dumps({"error": "Invalid path."})

        path = run_path / relative_path
        if not path.exists():
            return json.dumps({"error": f"Artefact not found: {relative_path}"})
        if path.stat().st_size > 500_000:
            return json.dumps(
                {
                    "error": "Artefact too large to read directly. Use search_evidence() to find specific content."
                }
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            # If JSON, parse and pretty-print
            try:
                return json.dumps(json.loads(content), indent=2)[:8000]
            except json.JSONDecodeError:
                return content[:8000]
        except Exception as e:
            return json.dumps({"error": str(e)})

    return {
        "list_phases": list_phases,
        "read_phase": read_phase,
        "read_envelope": read_envelope,
        "read_report": read_report,
        "search_evidence": search_evidence,
        "read_artefact": read_artefact,
    }


def search_across_runs(run_paths: list[Path], keyword: str) -> str:
    """
    Search across multiple prior runs for a keyword.
    Returns combined matches with their run_id prefixed to the source.
    """
    all_matches = []
    for run_path in run_paths:
        if not run_path.exists():
            continue
        tools = make_run_reader_tools(run_path)
        try:
            result = json.loads(tools["search_evidence"](keyword))
        except Exception:
            continue
        for match in result.get("matches", []):
            match["run_id"] = run_path.name
            all_matches.append(match)
        if len(all_matches) >= 30:
            break

    if not all_matches:
        return json.dumps(
            {
                "matches": [],
                "note": f"No results found for '{keyword}' across {len(run_paths)} prior run(s).",
            }
        )
    return json.dumps(
        {
            "keyword": keyword,
            "runs_searched": len(run_paths),
            "matches": all_matches[:30],
        },
        indent=2,
    )
