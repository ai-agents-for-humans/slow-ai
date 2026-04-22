---
layout: home
title: Slow AI
nav_order: 1
---

# Systems that learn.<br>Agents that work.<br>Humans who stay in control.
{: .fs-9 }

An open-source agent orchestration system for knowledge workers who want to understand what their agents are doing — and build a system that gets sharper every time it runs.
{: .fs-5 .fw-300 }

[How it works](how-it-works){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/ai-agents-for-humans/slow-ai){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## The gap nobody is talking about

Every elite performer has a practice loop. They do the work. They review what happened. They find the gaps. They get better.

That loop — deliberate, recorded, improving — is how expertise compounds. Not through speed. Through honest review of what happened and why.

AI agents, as most teams use them today, have no such loop.

You run a workflow. You get an output. You cannot see what the agent searched, what it concluded, where it hesitated, what it chose to ignore. When it goes wrong, you cannot tell why. When you run it again, it starts from zero.

> *"We handed people the keys to an excavator and told them to trust the bucket."*

This is not a technology problem. It is a design problem. The tools we have were built for speed. They were not built for understanding. And a system that cannot be understood cannot be improved.

---

## The learning argument

Slow AI is built around one conviction: **a system that cannot learn from what it does is not a system — it is a very expensive one-shot.**

Every run Slow AI produces is a complete, structured record. What was found. How confident each agent was. What gaps it hit. What evidence it produced. All of it committed to git, inspectable, and available to every run that follows.

The skills the system couldn't execute become a backlog. The next run builds on what the last run found. The brief gets sharper because the interview taught you something. The context graph improves because you've run this class of problem before.

Over time the system doesn't just run your investigations. **It gets better at running them.**

{: .highlight }
> **Runs chain** — prior evidence flows forward. Agents don't repeat covered ground. Each investigation starts smarter than the last.
>
> **Gaps compound into capability** — every skill the system couldn't find is recorded. The backlog grows across runs. You always know what to build next.
>
> **Context is yours** — every run lives in a git repository on your own infrastructure. Not a platform's training data. Yours.

---

## No more drawing boxes

Every other workflow tool asks you to design the workflow first.

Draw the DAG. Connect the nodes. Map the failure paths. Find someone technical enough to maintain it when something changes.

n8n. Zapier. LangGraph. Every enterprise agentic framework. They are all asking the same question: *Can you describe your process as a flowchart?*

Most knowledge workers cannot. And they shouldn't have to.

**Slow AI starts with the problem, not the pipeline.**

Describe what you need to understand in plain language. The interview clarifies it. The system designs the workflow. A context graph emerges — phases, parallel investigations, the shape of the problem made visible.

Then your team runs it. This week, next quarter, across every client, every market, every dataset. The workflow is reusable because it is problem-shaped, not tool-shaped.

> *"The knowledge worker who knows the domain should be the one who runs the investigation. Not the engineer who built the pipeline."*

---

## A real investigation

My knee has been injured for years. A cartilage problem that needs surgery I haven't been able to have.

So I did what any person does: I searched. I read. I got overwhelmed by medical papers, clinic websites, forum posts, conflicting advice. I couldn't tell efficacy from marketing.

Then I used Slow AI to investigate it properly.

First: an interview. Not a search box — a conversation. The system asked me questions I hadn't thought to ask myself. It pushed back on vague assumptions. By the end I understood my own problem more clearly than when I started.

Then it built a context graph. A structured breakdown of the research question — non-invasive procedures available locally, clinical efficacy data, patient outcome studies, cost and accessibility. The shape of the problem, made visible.

Then the agents went to work.

Some searched medical databases. Some downloaded and parsed clinical papers. Some wrote code to cross-reference datasets. Some called APIs to check what was available in my city. Each agent did the kind of work that kind of question actually requires.

And I could see all of it.

Every phase. Every finding. Every confidence score. Every place an agent got stuck and said *I couldn't find enough evidence*.

At the end I had something no search engine had given me: not just information, but *understanding*. I knew what had been looked at, what hadn't, what the agents were confident about, and what remained genuinely uncertain.

That uncertainty — honestly reported — was itself valuable. It told me what questions to bring to a doctor.

> *"At the end I didn't just have an answer. I had a collaborator. And I knew exactly how we got there."*

---

## Three things we believe

### Bring your own models

You should not have to trust a platform's model choices. Slow AI routes each task type to whichever model you configure — Google, Anthropic, OpenAI, or a local model running on your own hardware.

One JSON file. No code. No rebuilds.

Different task types use different model slots. Complex reasoning goes to a capable frontier model. Fast synthesis goes to a flash model. Code generation goes to a code-specialist. When a better model appears on the leaderboard, you update one entry and every agent that uses that slot benefits immediately.

### Sovereignty over your workflows

When you run an investigation with Slow AI, the context graph, the agent plans, the evidence, and the final report all live on your disk. In a git repository. Committed with full history.

You are not uploading your business processes to a platform. You are not training someone else's model on your proprietary questions. You own the system of record.

### Knowledge workers are not replaceable

The agent swarm does not replace the expert. It works for the expert.

The analyst who knows their domain brings the questions. The system brings the scale to investigate them properly.

What you get at the end is not AI output you have to take on faith. It is evidence you can interrogate, reasoning you can follow, and gaps you can decide to close — or accept.

That is augmentation. The other thing has a different name.

---

## This is for you if...

You are an expert in something. You have hard questions. You want to understand how the answers were found.

| Who | What Slow AI gives them |
|---|---|
| **Researcher** | A structured map of a field of evidence — solid parts and thin parts, clearly labelled |
| **Consultant** | A repeatable, inspectable investigation class — run across every client, not rebuilt each time |
| **Analyst** | A team to work with — agents that do the multi-modal work the question actually requires |
| **Engineer** | A system they can see inside — every decision, every artefact, every agent action visible |
| **Strategist** | A workflow that connects search, computation, documents, and APIs — without a DAG |
| **Knowledge worker** | A way to adopt AI that compounds rather than creates dependency |

You do not need to be technical to use Slow AI. You need to be willing to think carefully about your problem. The interview will help with the rest.

---

## An open project

Slow AI exists because of a frustration with how the industry is moving — fast, opaque, platform-dependent, human-optional.

It is an attempt to show there is another way to operate with agents. One where the human stays skilled. One where the organisation keeps its knowledge. One where the system can be interrogated, improved, and owned.

One where we do not throw away everything we know about how to build reliable systems just because the models are fast.

It is not finished. It is not a product with a pricing page. It is a working system with a point of view.

If this resonates — if you have felt the same gap, or if you have a hard problem you want to investigate — the code is on GitHub. Run it. Break it. Tell me what you found.

[View on GitHub](https://github.com/ai-agents-for-humans/slow-ai){: .btn .btn-primary }
[Read the architecture](architecture){: .btn }

---

*No hype. No waitlist. No magic. Just agents, transparency, and a system that compounds.*
