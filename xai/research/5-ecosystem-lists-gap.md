# Stage 5 — Ecosystem gap review: the EthicalML awesome lists

> Migrated from the exploration-phase research (`ethical/xai/tmp/LISTS_GAPS.md`). Part of the [research plan](./0-research-plan.md); component **C7 — Positioning & ecosystem**. Reads alongside the [direction synthesis](./6-direction-synthesis.md); refreshed periodically by planned [stage 14](./0-research-plan.md). Cross-check of `awesome-production-agentic-systems` and `awesome-agentic-engineering-resources` against the four landscape reports ([stage 1](./1-landscape-observability.md)–[stage 4](./4-landscape-agentic.md)), dated 2026-07-31.

## Gaps in `awesome-production-agentic-systems` (tools list)

| Category | Gap |
|---|---|
| 🔭 Observability | Lists AgentLab, AgentOps, IntellAgent, Judgeval, Manifest — but misses the category leaders: Langfuse, Arize Phoenix, W&B Weave, Helicone, OpenLLMetry, and the standards (OTel GenAI semantic conventions, OpenInference) |
| Evaluation | No dedicated category. Inspect AI, DeepEval, Ragas have no home (promptfoo is filed under Security, which undersells it) |
| Failure analysis / debugging | Missing entirely — AgentDebug, AgentRx (Microsoft), AgentDiagnose, MAST tooling |
| Behavioral auditing / red-teaming | Security covers scanners (mcp-scan, DeepTeam) but not behavioral audit tooling: Petri, Bloom, AgentHarm, SHADE-Arena |
| Fairness / governance / compliance | Missing entirely — LangFair, audit-trail tooling, EU AI Act-driven evidence tooling |
| Explainability / attribution | Missing entirely — no category, no tools |

## Gaps in `awesome-agentic-engineering-resources` (resources list)

The list's own coverage matrix already admits the pattern: fairness/bias "light", interpretability "fewer applied tutorials", audit trails "emerging". Specific missing entries surfaced by the research:

- **Agent failure research**: MAST ("Why Do Multi-Agent LLM Systems Fail?", NeurIPS 2025), Who&When failure attribution (ICML 2025), τ-bench / τ²-bench and the `pass^k` reliability metric
- **CoT faithfulness/monitorability**: Anthropic's "reasoning models don't say what they think", OpenAI's CoT monitoring and monitorability papers — foundational for anyone trusting agent rationales
- **Attribution research**: AgentSHAP, Causal Agent Replay, AgenTracer, context-attribution methods
- **Governance engineering**: EU AI Act Art. 12/14/86 engineering implications, AAS-1 draft auditability standard, "Auditable Agents" framing

## Strategic read

The "explainability / attribution / audit" cell is empty in BOTH lists — across ~40 tools and 21 topics, nothing occupies the niche the xai revitalization proposals target. That is independent validation of the white space from the project's own curation lens, and it hands xai its launch motion: the revitalized library becomes the anchor entry of a new "Agent Explainability & Audit" category in the tools list, mirroring the original xai ↔ awesome-mlops pairing of 2017-19.
