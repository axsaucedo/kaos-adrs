# Spike S — split the agent loop from the execution sandbox

**Question.** Can the harness hold the agent loop while a separate pod owns the workspace and executes — and what does the harness lose?

**Gate: passed, 4/4.** The split works end to end. The suspected blocker was not real.

## What was built

`sandbox_mcp.py` — the execution pod, as an MCP server over streamable HTTP, exposing `remote_write`, `remote_read`, `remote_list`, `remote_bash`, all confined to `SANDBOX_ROOT`. In KAOS terms this is an `MCPServer` CR: a separate Deployment on a port speaking HTTP, which is the only transport KAOS supports anyway (every entry in `kaos-mcp-runtimes` is `transport: http`, and stdio is a documented deferred item).

`run-split.sh` — the harness pod, as `claude -p` with all ten native filesystem, shell, and network tools disallowed and only the remote sandbox available.

```
RESULT pass=4 fail=0
  PASS  remote sandbox tools present
  PASS  no native filesystem/shell tool leaked (none)
  PASS  file created in the SANDBOX process
  PASS  path traversal blocked
```

The tool list actually observed on the wire, with all native tools stripped:

```
DesignSync EnterWorktree ExitWorktree ListMcpResourcesTool ReadMcpResourceDirTool
ReadMcpResourceTool ReportFindings ScheduleWakeup SendMessage Skill TaskCreate
TaskGet TaskList TaskOutput TaskStop TaskUpdate Workflow
mcp__sandbox__remote_bash mcp__sandbox__remote_list
mcp__sandbox__remote_read mcp__sandbox__remote_write
```

No `Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Agent`, or `NotebookEdit`. The harness then wrote `hello.txt` **in the sandbox process**, and a `../escaped.txt` traversal attempt was refused.

## The suspected blocker was wrong

The design draft argued the split would fail because "Claude Code, Codex, and `pi` all ship native Bash/Read/Edit tools bound to the local filesystem, and forcing MCP-only execution means discarding the tuned toolset that is most of the reason to use a harness."

Half of that is wrong and half is unresolved.

**Wrong:** the tools *can* be removed, cleanly, through a supported flag. Claude Code's `--disallowedTools` strips them from the wire entirely, and spike H established `pi --no-builtin-tools` does the same while keeping extension tools. This is not a hack; `--no-builtin-tools` exists precisely for delegated execution.

**Still open:** whether the resulting agent is as *good*. That is a model-quality question this spike cannot answer, because the model was scripted. See "Not verified".

## What it costs

Three real costs surfaced, none fatal:

1. **Tool names change, and system prompts reference the old ones.** The model sees `mcp__sandbox__remote_write`, not `Write`. Harness system prompts are tuned around their native tool names, so there is a prompt/tool mismatch that scripted responses hide completely.
2. **An extra network hop per tool call.** Every file read and shell command becomes an HTTP round trip to another pod. For a harness that reads dozens of files this is a latency multiplier, unmeasured here.
3. **Residual harness-internal tools remain.** `Task*`, `Skill`, `EnterWorktree`, `Workflow` survive the strip. They are session-management rather than filesystem access, so they do not breach the boundary — but `EnterWorktree` in particular implies a local git checkout the split architecture says does not exist, so the harness's own model of the world is now inconsistent with reality.

## Two testing traps worth recording

Both cost real time here and would cost it again:

- **Claude Code issues a toolless preflight request** (title/topic generation) before the real agent turn. A scripted mock that pops a response per request is then off by one, and the tool call never reaches the agent loop — presenting exactly as "the split does not work." The mock now serves preflight without consuming the script.
- **An unreachable MCP server is silent.** Claude Code reports no error; the tools are simply absent. A TCP-port readiness check is not enough, because a cold `uv run` takes ~15s to actually serve. The runner now probes `list_tools` before starting.

Both traps produce the same symptom — a plausible-looking false negative — which is worth knowing before anyone concludes this architecture is infeasible.

## What this implies for design question 2

Option S is **feasible**, and it composes with existing KAOS primitives better than any other option:

```
Agent CR      → the harness pod: agent loop, no filesystem, no git
MCPServer CR  → the sandbox pod: workspace, git, execution
```

Both already exist. No new CRD, no new controller, no new transport. It also gives the best isolation story available: the executing pod can carry `runtimeClassName: gvisor` and a hardened `SecurityContext` independently of the reasoning pod, and KAOS's gateway already mediates agent→MCPServer traffic per resource, so the existing authz model applies unchanged to the boundary that now matters.

The honest counterweight is that Option S is the **most** architecture for the least immediate gain: it splits one workload into two, doubles the pod count per session, adds a hop per tool call, and — unlike Option A — cannot be validated as "the operator can't tell the difference," because it genuinely is a different topology. Spike A showed the plain `Agent` flavour already ships Mode 2 with zero changes.

So the sequencing that the evidence supports is: **Option A first, Option S as the isolation upgrade** when running untrusted generated code matters more than latency — not as the starting point.

## Not verified

- **Whether a real model performs well with remote tools.** The model was scripted throughout, so this proves the *mechanism*, not the *quality*. The prompt/tool-name mismatch in cost 1 above is precisely the risk, and it needs a real model on a real task to settle. This is the single most important follow-up.
- Latency cost per tool call — not measured.
- `pi` was not run in the split configuration. Spike H proved `--no-builtin-tools` strips its toolset, but `pi`'s MCP client support is community-extension-only, so wiring it to a remote sandbox is likely harder than for Claude Code and was not attempted.
- No Kubernetes deployment; both processes ran locally over HTTP on loopback. Pod-to-pod behaviour, NetworkPolicy interaction, and gateway mediation are untested.
- Codex was not tested here: spike H found no way to remove its core `exec_command` tool, so the split may simply not apply to it.
