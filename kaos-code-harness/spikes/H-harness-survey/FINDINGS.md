# Spike H — which harness to build against

**Question.** Which of `pi`, Codex CLI, Claude Code, Hermes is cheapest to containerize, drive headlessly, and run in CI — and is that the same one that should be the headline harness?

**Gate: passed.** Three of four harnesses were driven end to end, headlessly, against a local mock endpoint with a fake credential.

## How it was tested

`mock-modelapi/server.py` is a ~200-line OpenAI/Anthropic-compatible server standing in for a KAOS ModelAPI. It speaks three wire formats (`/v1/chat/completions`, `/v1/responses`, `/v1/messages`), scripts responses in advance, and records what each harness actually sent — including the tool list, so "which tools does this harness advertise" is measured rather than assumed.

`pi/run-headless.sh` is the reproducible case; the other harnesses were driven ad hoc against the same mock.

## Result

| | `pi` 0.84.2 | Codex CLI 0.144.1 | Claude Code 2.1.224 | Hermes 0.15.0 |
|---|---|---|---|---|
| License | MIT | Apache-2.0 | Proprietary | MIT |
| KAOS can ship an image | **Yes** | **Yes** | **No** — BYO | Yes |
| Ran headless end to end | **✅ verified** | **✅ verified** | **✅ verified** | ❌ not reached |
| Headless entry | `-p` | `codex exec --json` | `-p` | `-z` (untested) |
| Arbitrary base URL | ✅ `models.json` provider | ✅ `model_providers.*` TOML | ✅ `ANTHROPIC_BASE_URL` | ⚠️ supported, config-file only |
| **Wire format** | OpenAI **chat completions** | **Responses only** | **Anthropic Messages only** | OpenAI-compatible |
| Ran with a *fake* credential | **✅** | **✅** | **✅** | not reached |
| Native FS/shell tools strippable | **✅ `--no-builtin-tools`** | ⚠️ `tools.*` namespace, no core strip found | **✅ `--disallowedTools`** | ⚠️ `-t` toolsets, untested |
| Tools advertised on the wire | `bash, edit, read, write` | `exec_command, multi_agent_v1, request_user_input, update_plan, view_image, write_stdin` | 22, incl. `Agent, Bash, Edit, Read, Write, WebFetch, Task*` | — |
| Session dir configurable | ✅ `--session-dir` | ✅ `CODEX_HOME` | ✅ `HOME`/`--resume` | ✅ |
| Resume / fork | `--resume`, `--fork`, `--session-id` | `resume --last`, `--ephemeral` | `--resume`, `--continue` | `--resume`, `--continue` |
| ACP | community `pi-acp` 0.0.33 | Zed adapter | Zed adapter | **native `hermes acp`** |

## Findings that change the design

### 1. Wire-format fragmentation is the real `ModelAPI` constraint, and it is worse than expected

Design question 8 assumed the split was "Claude Code is Claude-only, everyone else is OpenAI-compatible." That is wrong. There are **three mutually incompatible wire formats** across three harnesses:

- `pi` → `/v1/chat/completions`
- Codex → `/v1/responses`. Chat Completions is **removed**, not deprecated. Verified: `wire_api = "chat"` is rejected outright with *"`wire_api = \"chat\"` is no longer supported."*
- Claude Code → `/v1/messages`. Pointing it at an OpenAI-shaped endpoint 404s silently and surfaces as *"There's an issue with the selected model."*

KAOS's `ModelAPI` today serves only chat completions — `_resolve_model` builds `OpenAIChatModel(base_url=model_api_url + "/v1")`. So **exactly one of the three works with `ModelAPI` as it stands.** LiteLLM can serve all three (it has an Anthropic `/v1/messages` passthrough and Responses support), but that is a `ModelAPI` change, not a harness-driver change, and it belongs in the plan.

### 2. Spike S's premise is largely wrong — native tools *are* strippable

The stated blocker for splitting the loop from execution was that harnesses ship native filesystem/shell tools that cannot be removed. Measured on the wire:

- `pi --no-builtin-tools` → tool list goes from `bash,edit,read,write` to **empty**, while extension tools stay enabled. This flag exists precisely for the split-execution case.
- Claude Code `--disallowedTools Bash Edit Write Read Glob Grep WebFetch WebSearch Agent NotebookEdit` → all filesystem, shell, and network tools **disappear from the request**; only session-level tools (`Task*`, `Skill`, `EnterWorktree`) remain.

An important secondary finding: **`--allowedTools` does not do this.** With `--allowedTools Read`, all 22 tools were still advertised — it is a *permission* allowlist governing auto-approval, not a tool-availability filter. Only `--disallowedTools` changes what the model sees. Conflating the two would be an easy and silent design error.

Codex is the outlier: a `tools.*` config namespace exists, but no way was found to remove `exec_command`, its core execution tool.

### 3. Every tested harness runs in CI with a fake credential

This is the finding that most changes the recommendation. All three harnesses completed a full turn against `http://127.0.0.1` with `Authorization: Bearer not-needed`. Claude Code needed only `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` and one env var to silence unknown-model window enforcement.

The prior argument for `pi` was that it is "the only harness that can run in KAOS's e2e suite with no external credential." **That argument does not survive contact with the evidence** — Claude Code and Codex are equally testable against a mock. What `pi` uniquely retains is that KAOS may *ship its image* (MIT), and that it needs no wire-format work to reach `ModelAPI`.

### 4. Hermes is a poor fit for this, and it is not close

Hermes exposes **50+ subcommands** — WhatsApp, Slack, cron, kanban, webhooks, portal, computer-use. It is a personal-assistant platform in which coding is one capability, structurally much closer to OpenClaw than to a coding harness. It was also the only harness that could not be driven from a cold start: `--provider openai` fails with `Unknown provider`, because providers must be registered through `hermes model` or a config file rather than env vars. Native ACP is its genuine advantage, and it is the only one of the four that has it.

## Recommendation for design question 3

**Build against `pi` first; make Claude Code the headline harness.** The split the prior draft proposed survives, but for one reason rather than three:

- `pi` is MIT (KAOS ships the image), needs **zero `ModelAPI` work** (already chat completions), and has the cleanest tool-stripping flag. That is enough.
- The CI argument is void — any of the three can be mock-tested.
- Codex is the strongest *second* runtime: Apache-2.0, real approval requests, `app-server` JSON-RPC. Its cost is a `ModelAPI` Responses endpoint.
- **Hermes should be dropped** from the candidate set unless native ACP turns out to be decisive in spike D.

Sequence: `pi` → Claude Code → Codex. Hermes only if spike D says ACP wins.

## Not verified

- Hermes end to end — blocked on interactive provider registration; not pursued further given finding 4.
- Container builds — the Docker daemon was not running on this machine, so no `Dockerfile` was built. All harnesses installed cleanly as local packages (`npm`, `brew`), which is the substantive part of image feasibility, but image size and base-image choice remain open.
- Copilot CLI — not installed and not tested; its redistribution terms already rule out a KAOS-shipped image.
- Whether stripping Claude Code's tools leaves a *useful* agent. Tools vanish from the wire, but no task was run against a remote-MCP toolset to see whether it still completes work. That is spike S's job.
