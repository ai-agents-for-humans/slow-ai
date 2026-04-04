import asyncio, json
from slow_ai.models import ProblemBrief
from slow_ai.agents.orchestrator import run_orchestrator

def test_specialists():
    brief = ProblemBrief(
        goal='Find Sentinel-2 datasets for crop monitoring in Kenya 2020-2023',
        domain='earth observation',
        constraints={'region': 'Kenya', 'time_range': '2020-2023',
    'resolution': '10m'},
        unknowns=['cloud cover availability'],
        success_criteria=['at least 2 datasets found'],
        milestone_flags=['source_discovery'],
        excluded_paths=[],
    )
    plan = asyncio.run(run_orchestrator(brief, run_id='test-001'))
    print('Specialists:', [s.role for s in plan.specialists])
    print('Milestones:', plan.milestone_flags)


import asyncio, json
from slow_ai.models import AgentContext, AgentTask, AgentMemory
from slow_ai.agents.specialist import run_specialist


def test_specialist():
  ctx = AgentContext(
      agent_id='copernicus-test-001',
      role='Copernicus Data Specialist',
      expertise=['Sentinel-2', 'ESA Open Access Hub'],
      task=AgentTask(
          task_id='task-001',
          agent_type='copernicus_specialist',
          goal='Find Sentinel-2 datasets for crop monitoring in Kenya 2020-2023',
          context_budget=6000,
      ),
  memory=AgentMemory(agent_id='copernicus-test-001',
                     agent_type='copernicus_specialist', context_budget=6000), 
                     constraints={'region': 'Kenya', 'time_range': '2020-2023'},
                     evidence_required={'datasets_found': 'list of datasets',
  'download_url': 'direct URL'},)

  envelope, updated_ctx = asyncio.run(run_specialist(ctx))
  print('Status:', envelope.status)
  print('Verdict:', envelope.verdict)
  print('Confidence:', envelope.confidence)
  print('Memory entries:', len(updated_ctx.memory.entries))
  print('Tokens used:', updated_ctx.memory.total_tokens)

if __name__=="__main__":
    #test_specialists()
    test_specialist()
