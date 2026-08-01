# Deep-research prompt — stage 13: EU AI Act evidence requirements

Copy everything in the fenced block below into ChatGPT deep-research mode as a single prompt. The block is self-contained. When results come back, save them as `xai/research/13-regulatory-evidence-requirements.md` with inline citations preserved.

```
You are doing deep research to support a specific open-source engineering decision, not a general literature review, and NOT legal advice. Read the context, then do the task; make clear throughout that the output is engineering research to inform templates, not legal or compliance certification.

CONTEXT — the project. `xai` (github.com/EthicalML/xai) is an open-source library from The Institute for Ethical AI & ML, first released in 2017 for tabular ML fairness/explainability, being revitalized in 2026 for agentic LLM systems. It is a provider-neutral analysis layer over agent traces (OpenTelemetry GenAI / OpenInference) that produces decision attributions and a portable, per-decision "explanation packet" (evidence timeline, decisive observable factors, tested counterfactuals, limitations, review/appeal metadata) exportable as Markdown/JSON/HTML. Firm non-goals: it will NOT be an EU AI Act "certification" product, will not expose or depend on private chain-of-thought, and will provide only a thin, clearly-caveated regulatory mapping as templates. We need to know what evidence the regulation actually requires so the explanation packet and decision ledger carry the right fields.

TASK. For the EU AI Act as of mid-2026 (post-"AI Omnibus" timeline; note the agreed dates: GPAI enforcement powers from 2 August 2026, Annex III high-risk from 2 December 2027, Annex I high-risk from 2 August 2028), produce a concrete engineering specification of what EVIDENCE a high-risk agentic AI deployment must be able to produce. For each of the following, translate the legal text into specific data fields/records, granularity, and retention expectations:
1. Article 12 (logging / traceability) — what events and record types must be automatically logged over the system's lifetime, at what granularity, for an agentic (multi-step, tool-using) system.
2. Articles 13–14 (transparency to deployers; effective human oversight) — what information must be available to a deployer, and which human-oversight events (escalation triggers, information shown to the reviewer, intervention/override/stop authority, response time, final disposition) must be captured.
3. Article 86 (right to explanation of individual decisions) — what a "clear and meaningful explanation" of the AI system's role and the main elements of an individual consequential decision must contain, expressed as a data schema/template for an affected person.
4. Relevant GPAI provider duties and how they interact with the above.
5. GDPR interaction — data minimisation and retention vs the temptation to capture full prompts/context; what a redaction-aware evidence record should and should not retain.

Also assess the draft AAS-1 agent auditability standard (v0.1) and the "Auditable Agents" framing (action recoverability, lifecycle coverage, policy checkability, responsibility attribution, evidence integrity) as concrete inputs to the schema.

OUTPUT. Structured markdown with inline citations to official Commission / EUR-Lex sources and the standards above at each claim. Express requirements as field lists / JSON-schema sketches / record templates, not prose summaries. State clearly that this is engineering research, not legal advice. End with a proposed minimal "decision ledger + explanation packet" field set that would satisfy the traceability, oversight, and explanation obligations for a high-risk agentic deployment, plus the open questions a legal review would need to close.
```
