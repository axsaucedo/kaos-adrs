# kaos-code-harness

Design and spike work for running a real coding harness (Claude Code, Copilot CLI, Codex CLI, `pi`, Hermes) as a Kubernetes-backed workload under KAOS, instead of on a laptop.

## Where things are

| Path | What |
|---|---|
| `SPIKE-PLAN.md` | The spike tracks, their gates, and what each must produce |
| `spikes/H-harness-survey/` | Which harness is cheapest to containerize and drive headlessly |
| `spikes/A-agent-flavour/` | Can a harness be an `Agent` flavour with **no** new CRD? |
| `spikes/C-new-crd/` | What `AgentHarness` + `CodingSession` actually costs |
| `spikes/S-split-sandbox/` | Loop in one pod, execution in a sandbox pod — feasible? |
| `spikes/D-driver-contract/` | ACP as a uniform contract vs per-harness native drivers |
| `RESULTS.md` | Written once spikes land; feeds back into the design discussion |

## Upstream context

The design discussion this work serves lives in the `kaos` repo at
`.humanlayer/tasks/kaos-extension-to-coding-harness/05-design-discussion-coding-harness-interface.md`,
backed by two research documents in the same directory (`03-` ecosystem landscape, `04-` KAOS interface).

## Decisions already made

These are settled and the spikes should not relitigate them:

- **Mode 2 ships first** — the developer keeps Claude Code local; KAOS supplies cluster-side workers reached through an MCP server.
- **Workspace**: initContainer clone into an `emptyDir`; the pushed branch is the output; unpushed local commits do not transfer.
- **Session durability**: mount the harness's own config root and use its native `--resume`. KAOS does not parse transcripts.
- **Human gate for v1**: sandbox plus pull-request review. No approval callback yet.
- **Model plane**: `modelAPIRef` optional; attribution headers as a fast follow.

## Open, and what the spikes decide

1. **Does this need a new CRD at all?** (spikes A, C, S)
2. **Which harness to build against first?** (spike H)
3. **What contract does the driver speak to the harness?** (spike D)
4. **Does the client surface need its own `kaos code` group?** (follows 1)
