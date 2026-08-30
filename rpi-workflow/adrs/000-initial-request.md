# 000 — Initial request: RPI (Research–Plan–Implement) workflow plugin

Date: 2026-08-30. This entry captures the initial request that kicked off the `rpi-workflow` effort. It is the requirements baseline that the research documents under [`../research/`](../research/) and later ADRs refer back to. The deliverable is a plugin (likely under `workflow-automations` in the public `agent-skills-marketplace` repo) that packages the owner's RPI workflow as a set of skills. The effort is, deliberately, being developed by following the RPI workflow itself, documented in this section.

## Normalized requirements

### Entry point

- A `/new-project` entry point where the user details the scope of the project; this kicks off the staged workflow below.

### Stage 1 — Research

- Starts by proposing the key areas to research in a `proposed-research.md` for user approval. Mostly external research, plus some internal codebase research for relevant findings.
- On approval, research fans out across multiple subagents producing `research-ref-<n>-<m>-<name>.md` (full captured text, may split into 1.1, 1.2, …) and `research-findings-<n>-<name>.md` (the distilled findings kept as 1, 2, …).
- Must not assume: where multiple viable paths exist, propose parallel spikes to validate, and document the results.

### Stage 2 — ADRs

- Aim for a small set of ADRs; ideally exactly one, unless the change is major with genuinely separable parts (e.g. a frontend large enough to stand apart from the backend).
- Focus on interfaces: examples-first (e.g. for an SDK), reflecting the interfaces and inputs/outputs; also capture architecture decisions such as frameworks and languages.
- Every decision mapped as options with tradeoffs (pros/cons) and a recommendation.
- Be clear on expected behaviour.
- As in research: do not assume — propose parallel spikes where multiple paths exist, and document them.
- Flow: `proposed-adrs.md` for approval → create the ADRs → walk decisions one by one with user input (accept recommendation or choose) → summary of any caveats that could lead to misunderstanding.

### Stage 3 — Plan

- Starts as `proposed-plan.md`; simplified as much as possible: minimal phases, minimal PRs, but each PR must remain reviewable.
- PRs use comprehensive, reviewable commits.
- Defines verification, which must include unit/component testing — but explicitly NOT "1+1=2" input-equals-output tests; those are to be AVOIDED unless they EXPLICITLY make sense. Tests must validate actual multi-step workflows. (Observed failure mode: most tests end up trivially asserting inputs match outputs and are useless.)
- End-to-end verification is king. Playwright visual verification for intense component creation (reference: `zalando-markets/agent-marketplace` → `plugins/databricks/skills/streamlit-verification-playwright`, companion to `create-data-app`); kind-based Kubernetes validation as in the kaos repo for e2e cluster validation.
- Verification must stay effective and agile: parallelise when things take more than a threshold; keep execution fast.
- LEVERAGE manual verification: run scripts iteratively from a gitignored `./tmp` folder; never build a Playwright harness straight away; never assume something works — test it, with the user.
- Review must be intuitive: clear cheatsheets outlining expected usage, ideally introduced in the ADRs and updated in the plan.

### Stage 4 — Implementation

- Carried out PR by PR with review in between; parallelised as much as possible.

## Meta

- Development of this plugin follows the RPI approach itself, documented under `kaos-ai-docs/rpi-workflow/` (this section). Prior sections that already followed this approach (e.g. `memory/`, `duckmemory/`, `security-and-identity/`, `kaos-code-harness/`) are primary internal research material.
- All research must be registered with comprehensive commits as it lands.

## Original request (verbatim)

> I would like to create a new plugin or inside workflow automations that captures my current RPI / research-plan-implement workflow that i have developed. We can actualy read the approach from multiple sessions where i have followed this which means i awnt to create a set of skills for research. and it woudl consist of kicking off the overall /new-project where i could detail thescope of the project. This wold then start with a research stage. This nromally starts firs tby proposing to me what are the key areas to resaerch under a proposed-research.md, which focuses often largely on external resarc, but also with some interanl codebase research to find relevent findings. this will then be documented under proposed-research.md, and once the user approves, this will be kicked off acros smultple subagents as research-ref-n-n-<name>.md and research-findings-n-<name> , the former is the full text of all that is found and could be spit into liek 1.1, 1.2 if erelevnt but the findings are what is kept as 1, or 2, etc. most important, it should also not assume, when relevant it should propose to run parallel spikes to validate anything that can have multiple paths, and document. Then once finalised the resarch, we move to the adrs. here we are aiming to put together a set of adrs. the biggest focus here is to ensure that 1) we keep it simple, idealy only 1 adr, unelss the change is major and requires difernt parts, often only if there is for example an entire separatio of components like a startin with the frontend separate to the backend (being large enogh, 2) focus on interfaces, make sure it's examples first in case eg it's an SDK, it reflects what are the interfaces and inputs/otputs, also if there are architecture decisions such as the frameworks, languages, etc. 3) tehse should be mapped with options each with tradeofsf (pros/cons) and recommendation. 4) it should alos be clear on expected behaviour 5) most important, it should also not assume, when relevant it should propose to run parallel spikes to validate anything that can have multiple paths, and document, similar to resaerch. Then once approved on the prposed-adrs.md then it would create the adrs, and we would go one by one for hte decisions required, with input required from the user to decide (eg or take recommendaiotn, etc), then summary on any caveats that may lead into misunderstanding. --- then once this is approved, moving into the plan, which woudl start agian as proposed-plan.md, which should ocnsist of again simplified as much as possible, restrict the number of phases as much as possible, it should minimise thenumber of PRs as well to split into, but ensure that thse are possible to be reviewed. It should specify that these should be useing comprehensive commits that are reviewable. ALso it shoudl define the verificationwhich should include testing of units/components, and it should be absolutely clear that it's not a 1+1=2 testing that inputs match outputs, but actual workflows that validate multi-step logic; the former should be AVOIDED unless there are cases where it EXPLICITLY makes sense. Iv'e seen too many times wher emost tests end up being just that and it's useless. Verification end to end is king, we'll want to use playwright visual verifications for intense component creation. For this youcan see the https://github.com/zalando-markets/agent-marketplace/tree/main/plugins/databricks/skills/streamlit-verification-playwright which is a companion for the create-data-app as an example; but this is also for end to end validation, youcan see kaos repo for kubernetes validation with kind; however we also need to ensure validation is effective and agile, so we parallelise when things take more than X, and also ensure fast execution; however verifiction is a core part; also make sure to LEVERAGE manual verification, run scripts, make a not eto use the ./tmp folder gitignored to add the scripts there, never just build a playwright harness straight away, run these iteratively, and never just assume something works, test it. with the user, make sure that review is also provided intuitively with clear cheatsheets that outline how it's expected to be used, which ideally also is provided all the way in the ADrs and updated here. --- then implementation woudl be carried out PR by PR with review in between, and parallelise as uch as possible --- Ironcically we will develop this by followong this approach itself. We will docment this under ~/Programming/agenitc/kaos-ai-docs/ here we have multiple sections where we've already done this whcih you will resaerch, which include things like memory, an dmost others actually. So for this, let's kick off with step 1, resaerch. Make sure to already add an entry for this. you can add an entry either in an adr/001-design/. folder in the marketplace repo or in the kaos-ai-docs/ up to you. make sure that you add comprehensive commits ehre as any resaerch is registered. This is important. GO. Also store this in theADR as the initial request
