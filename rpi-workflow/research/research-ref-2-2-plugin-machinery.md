# Research ref 2-2 — Claude Code plugin/skill machinery

Captured material for [Area 2](proposed-research.md) sub-track 2, verified against the official docs at `code.claude.com/docs` in August 2026. Distilled version in [research-findings-2-machinery-and-prior-art](research-findings-2-machinery-and-prior-art.md).

Primary sources: <https://code.claude.com/docs/en/plugins.md>, <https://code.claude.com/docs/en/plugins-reference.md>, <https://code.claude.com/docs/en/skills.md>, <https://code.claude.com/docs/en/sub-agents.md>, <https://code.claude.com/docs/en/workflows.md>, <https://code.claude.com/docs/en/permission-modes.md>, <https://code.claude.com/docs/en/hooks.md>, <https://code.claude.com/docs/en/permissions.md>, <https://code.claude.com/docs/en/memory.md>, <https://code.claude.com/docs/en/agent-teams.md>.

## 1. Plugin anatomy

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json          # required manifest — the ONLY file in this directory
├── skills/<skill-name>/SKILL.md
├── commands/                # legacy; skills/ is preferred for new plugins
├── agents/                  # custom subagent definitions
├── hooks/hooks.json
├── .mcp.json
├── .lsp.json
├── monitors/monitors.json
├── bin/                     # executables added to Bash PATH, plugin-scoped
├── settings.json            # defaults applied when the plugin is enabled
└── README.md
```

Hard rule: `commands/`, `agents/`, `skills/`, `hooks/` must **not** live inside `.claude-plugin/`; only `plugin.json` does. A single-skill plugin may put `SKILL.md` at the plugin root instead of using `skills/`.

`plugin.json` fields: `name` (required; becomes the namespace), `displayName`, `description`, `version`, `author{name,email}`, `homepage`, `repository`, `license`, path overrides `skills`/`agents`/`hooks`/`mcpServers`/`lspServers`/`monitors`, `dependencies` (other plugins), `userConfig` (prompts at enable time). If `version` is omitted, Claude Code falls back to the git SHA or a package.json version.

Marketplace distribution is a repo containing `.claude-plugin/marketplace.json` listing plugins by `name`/`description`/`version`/`author`/`source`/`category`/`keywords`; install is `/plugin marketplace add <owner>/<repo>` then `/plugin install <plugin>@<marketplace>`. (Confirmed against the live `humanlayer/skills` and `humanlayer/riptide-rpi` manifests in ref 2-1.)

Skills in a plugin are namespaced and invoked as `/<plugin-name>:<skill-name>` — exactly what HumanLayer's `/rpi:create-research` naming shows.

## 2. Skills vs agents vs slash commands

| Type | Invocation | Context behaviour | Use for |
|---|---|---|---|
| **Skill** | user-typed `/name` **and/or** model-invoked from its `description` | body loads only when invoked, then stays in context for the rest of the session | reusable procedures, instructions Claude should follow |
| **Agent (subagent)** | model-invoked, or explicitly by name | fresh isolated context window; does **not** inherit parent conversation history | delegated work, isolated context, parallel research |
| **Workflow** | keyword or `/saved-name` | a JS script that orchestrates many subagents | large repeatable fan-out |
| **Built-in slash command** | user-typed only | fixed non-LLM logic | `/plugin`, `/config`, etc. |

Custom "commands" in the old `commands/` sense are now effectively skills with `disable-model-invocation: true`. The docs steer new plugins to `skills/`.

Progressive disclosure is the important property: only the skill `name` + `description` sit in context until a skill is invoked, so a plugin can carry many stage skills cheaply. The corollary is that the `description` is the entire routing surface — HumanLayer's deliberately over-specified description (see ref 2-1 §4.1) is the practical response.

## 3. SKILL.md frontmatter — as documented Aug 2026

All fields are optional; `description` is the one that matters.

```yaml
---
name: my-skill
description: "when to use this skill"
when_to_use: "extra trigger phrases"     # appended to description; ~1536 char cap on the pair
argument-hint: "[issue-number]"
arguments: [issue, branch]                # enables $issue / $branch substitution
disable-model-invocation: true            # user-only: Claude will not auto-invoke
user-invocable: false                     # Claude-only: hidden from the / menu
allowed-tools: "Read Grep Bash"
disallowed-tools: "AskUserQuestion"
model: "sonnet"                           # or "inherit"
effort: "low|medium|high|xhigh|max"
context: "fork"                           # run the skill body in a forked subagent context
agent: "researcher"                       # which subagent type, when context: fork
background: false                         # with context: fork, wait for the result
hooks: {...}                              # register hooks for the duration of the skill
paths: ["src/**/*.ts"]                    # only surface when working on matching files
shell: "bash"
metadata: {key: value}                    # free-form; ignored by Claude
license: "MIT"
compatibility: "Claude Code v2.1.200+"
---
```

Both `user-invocable` and `disable-model-invocation` are documented and are the two halves of the same axis: `disable-model-invocation: true` makes a skill user-only (the right setting for a stage entry point the model should never fire spontaneously); `user-invocable: false` makes it model-only.

Portability caveat: the **Agent Skills spec** subset accepted for upload to claude.ai is only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Everything else in the list above is a Claude Code extension and will fail an upload with "Unexpected key(s)". Irrelevant if we only ship a Claude Code plugin, relevant if we ever want the skills usable on claude.ai.

Substitutions available in the skill body: `$ARGUMENTS`, `$0`/`$1`/`$ARGUMENTS[N]`, `$name` for named arguments, and the environment-style `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`. `${CLAUDE_PLUGIN_DATA}` is a persistent per-plugin data directory that survives plugin updates — a possible home for cross-project workflow state, though for our purposes the docs directory in the user's repo is the better store.

## 4. Subagent fan-out

A skill with `context: fork` executes its body in an isolated subagent. What crosses the boundary: project CLAUDE.md, MCP servers, project/user skills, the spawn prompt (the skill body), the tools permitted by `allowed-tools`, and the model. What does **not**: the parent conversation history and the parent's context-window contents. Results return to the caller.

For wider fan-out the documented mechanism is **dynamic workflows** — a JS script using `agent()`, `pipeline()` (sequential) and `parallel()` (concurrent):

```javascript
const results = await parallel(found.files.map(file => agent(`Audit ${file}.`)))
```

Documented limits: up to **16 concurrent agents** (fewer on CPU-limited containers), up to **1,000 agents total per run**, up to **4,096 items** in one `parallel()`/`pipeline()` call, and agents sharing a prompt-cache prefix with the first agent stagger their start by up to 5s (`CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`).

For our purposes the simpler and better-trodden path is the one HumanLayer uses: the stage skill body simply *instructs* the main agent to spawn N Task/Agent subagents in parallel, one per research area, and to wait for all of them before synthesising. That needs no workflow scripting and keeps each subagent's prompt data-driven from the approved `proposed-research.md`.

**Agent teams** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) are a different, heavier model: separate full sessions with peer-to-peer messaging and a shared task list, at multiple-full-context token cost. Not appropriate for research fan-out; possibly interesting much later for parallel PR implementation.

## 5. Approval gates — what actually returns control to the user

Ranked by how reliably each halts the agent:

1. **Plan mode** — entered via `--permission-mode plan`, Shift+Tab, or a `/plan` prefix. Claude may read and run read-only Bash but is blocked from edits. When done it calls `ExitPlanMode`, which raises an approval prompt offering "Yes and use auto mode" / "Yes, manually approve edits" / "No, keep planning". Approving exits plan mode and switches permission mode; denying keeps planning. This is the documented, purpose-built approval gate for multi-step workflows.
2. **Permission prompts** (default/manual mode) — a tool call the permission rules do not allow raises a Yes/No/Yes-and-don't-ask-again prompt. Reliable, but it gates *tool calls*, not workflow stages.
3. **Hooks** — `PermissionRequest` can auto-allow or block a request programmatically; `PreToolUse` exit code 2 blocks a call and feeds the reason back to Claude, but does **not** prompt the user. `Stop` hooks can intercept the end of a turn. Hooks are the mechanism for enforcing a gate the model might otherwise skip, e.g. blocking Edit/Write outside the docs directory until an approval marker exists.
4. **AskUserQuestion** — presents structured options to the user. The subagent report asserts it "does not halt the session"; that is contested and worth treating as **uncertain** — in interactive sessions it does surface a choice UI and the model waits for the answer, but it is unsuitable for a free-text approval of a long document, and it is unavailable in non-interactive/`-p` runs. Treat it as a *choice* mechanism (pick option A/B/C for an ADR decision), not as the primary stage gate.
5. **Plain prose "STOP and wait for the user"** — what HumanLayer's original prompts use. It works often but is exactly the "magic words" failure they measured at ~50% skip rate (ref 2-1 §3). Should not be the *only* gate.

Implication: a stage gate should be layered — prose instruction to stop, plus a hard mechanism (plan mode for the stage entry, or a hook that blocks writes past the gate) rather than prose alone.

## 6. Cross-session state and stage handoff

Documented persistence mechanisms:

- **CLAUDE.md** (`./CLAUDE.md`, `./.claude/CLAUDE.md`, `~/.claude/CLAUDE.md`, `/etc/claude-code/CLAUDE.md`) — instructions loaded at session start, not stage results. Useful for the workflow's own conventions, not for carrying stage output. Note HumanLayer's `<important if="you are using the rpi:create-research skill">` trick for making CLAUDE.md content stage-conditional.
- **Auto memory** (`~/.claude/projects/<project>/memory/`, first 200 lines of `MEMORY.md` loaded at session start, per git repo, shared across worktrees) — Claude's own notes; not designed as a stage-handoff channel.
- **Session resume** (`claude --resume <session-id>`) — continues the *same* session; it does not solve "a different, fresh session picks up stage 3".
- **`.claude/settings.json`** — configuration, not runtime state.
- **Agent-team inboxes** (`~/.claude/teams/<team>/inboxes/<agent>.json`) — experimental, agent-teams only.
- **Files on disk** — any path the skill chooses.

**Key confirmation for spike S2:** there is **no official Claude Code convention for a docs-directory handoff between workflow stages**. Files-on-disk is a purely user-side convention. The docs do not define it, endorse a location, or provide tooling for it. Everything the ecosystem does here — HumanLayer's `thoughts/tasks/<slug>/NN-*.md`, spec-kit's `specs/NNN-feature/`, OpenSpec's `changes/`, our own `kaos-ai-docs/<section>/` — is a convention the tool author invents and the skill body enforces.

That is good news rather than bad: it means the handoff design is entirely ours, it costs nothing platform-side, and it is testable purely by opening a fresh session and pointing it at the directory. S2 is therefore a cheap and high-value spike — and the prior art (ref 2-1 §4.1: "Based on which files exist, suggest the next skill to use") already shows the shape that works.

## 7. Validation and evaluation tooling

- **`claude plugin validate ./your-plugin`** — public. Structure/manifest/SKILL.md format checks; `--strict` turns warnings into errors. No behavioural testing. Cheap to wire into CI for the marketplace repo.
- **`claude plugin eval`** — early access, gated per organisation; prints an early-access notice and exits when not enabled. Runs eval cases (a `prompt.md` plus `graders/`) in isolated plugin-test sessions, optionally against a no-plugin baseline arm, and emits an HTML report plus `aggregate-result.json`. Documented grader types: `regex`, `tool_used`, `tool_order`, `file_exists`, `llm` (judge), `baseline`. Exit codes 0 pass / 1 fail / 2 partial / 130 interrupted / 143 terminated. If it becomes available to us it is close to an ideal fit for verifying a workflow plugin, since `file_exists` and `tool_order` graders test *workflow shape* rather than input-equals-output — exactly the kind of test the initial request demands.
- **`/skill-doctor`** — early access; an in-session per-skill usage/token report with never-invoked warnings. Not a linter.

## 8. Constraints that bear directly on the plugin's shape

- Skill bodies stay in context once loaded, so a monolithic four-stage skill pays its full token cost for the entire session, while four stage skills each pay only when that stage runs. This reinforces HumanLayer's <40-instructions-per-stage finding from a completely different direction.
- Namespacing means stage skills are individually addressable as `/rpi:research`, `/rpi:adrs`, … and therefore usable standalone, which is one of the comparison axes named for spike S1.
- `disable-model-invocation: true` on the stage skills prevents Claude spontaneously deciding to "do the plan stage" mid-conversation; the entry-point skill (and only it) can stay model-invocable so that "I want to start a new project" routes correctly.
- Subagents get no parent history, so every research subagent prompt must be self-contained — which is why the approved `proposed-research.md` needs to carry enough per-area detail to seed a subagent prompt verbatim.
