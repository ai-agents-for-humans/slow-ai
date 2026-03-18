from pydantic import BaseModel
from typing import Any


class ProblemBrief(BaseModel):
    goal: str
    domain: str
    constraints: dict[str, Any]
    unknowns: list[str]
    success_criteria: list[str]
    milestone_flags: list[str]
    excluded_paths: list[str]
