import asyncio
from slow_ai.models import ProblemBrief
from slow_ai.research.runner import run_research

brief = ProblemBrief(
    goal='Find Sentinel-2 datasets for crop monitoring in Kenya 2020-2023',
    domain='earth observation',
    constraints={'region': 'Kenya', 'time_range': '2020-2023', 'resolution':
 '10m'},
    unknowns=['cloud cover availability'],
    success_criteria=['at least 2 datasets found'],
    milestone_flags=['source_discovery'],
    excluded_paths=[],
)
report = asyncio.run(run_research(brief, on_progress=print))
print('Datasets found:', len(report.datasets))
for ds in report.datasets[:3]:
    print(f'  {ds.name} — quality: {ds.quality_score:.2f}')