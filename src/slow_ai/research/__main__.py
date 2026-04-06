"""
Subprocess entry point for a research run.

Usage:
    python -m slow_ai.research <run_id>

The run directory (runs/<run_id>/) must already exist and contain
input_brief.json written by the caller before launching this process.
"""

import asyncio
import sys
from pathlib import Path

from slow_ai.models import ProblemBrief
from slow_ai.research.runner import run_research


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m slow_ai.research <run_id>", file=sys.stderr)
        sys.exit(1)

    run_id = sys.argv[1]
    brief_path = Path("runs") / run_id / "input_brief.json"

    if not brief_path.exists():
        print(f"input_brief.json not found at {brief_path}", file=sys.stderr)
        sys.exit(1)

    brief = ProblemBrief.model_validate_json(brief_path.read_text(encoding="utf-8"))
    asyncio.run(run_research(brief, run_id))


if __name__ == "__main__":
    main()
