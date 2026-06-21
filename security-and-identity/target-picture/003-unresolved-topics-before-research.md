# 003 - Unresolved topics before research

## Prompt

1. ok. 2. ok, this needs to be fleshed out, also to understand whether the complexity is worth it, and whether it makes sense to add this complexity in kaos vs a 3rd party lib, vs an AIB component. 3. ok. 4. ok. 5. ok, but needs to be fleshed out further. 6. ok. 7. ok. 8. preflight approval may be indeeed best, but we need to assess whether this is doable, otherwise we can also approach with fail with approval url then retry (eg expired permission, etc); async task pause/resume I would like to verify if the current async capabilities within chaos are capable of supporting this; now that I think about it, though, the return with request to approve is not a completely invalid approach, as also this is something that could be validated as part of the KAUS UI itself. We should assess whether KAUS admin UI/user UI can be used to Easily approve programmatically the request and then send it again. 9. This didn't understand my question. I'm not only asking which parts of this are mostly Security vs Agent specific. What I'm asking is whether this could be achieved equally as easily, or even easier, if using something like Keycloak and/or OPA as the tool instead of AIB. 10. ok; yes use certmanager as well for easy provisioning, etc. --- Ok, before moving to the research plan, I would like to go through these topics. It seems most are resolved. Just provide an outline on the ones that aren't, and then we'll move to the research and go face-by-face after approving the research plan.

## Response

Most topics are now settled enough to proceed. The unresolved topics to flesh out before finalizing the research plan are:

## 1. Workload identity complexity and ownership

Open question:

```text
Do we need explicit workload identity beyond KAOS logical resource identity,
and if yes, should this be implemented in KAOS, AIB, or delegated to existing infrastructure?
```

Why unresolved:

- ServiceAccounts are Kubernetes-native and likely the simplest workload anchor.
- But using them for AIB credential issuance, token exchange, or runtime identity adds complexity.
- It is not yet proven that this complexity is necessary for initial KAOS security.

Options to evaluate:

| Option | Owner | Notes |
|---|---|---|
| No explicit workload identity initially | KAOS | Simpler; use logical agent/resource identity only. Weaker against spoofing. |
| Kubernetes ServiceAccount binding | KAOS + AIB | Likely best minimal workload identity; uses native pod identity. |
| AIB-issued workload credentials | AIB | Stronger AIB control; requires secure bootstrap/injection/rotation. |
| Mesh/SPIFFE workload identity | Third-party infra | Strongest generic workload identity; more operational complexity. |

Decision needed:

- Is workload identity required for initial implementation?
- If yes, is ServiceAccount binding enough?
- What does AIB need to verify: SA token, pod metadata, or only CRD/service identity?

## 2. Metadata/source-of-truth grey areas

Open question:

```text
Which metadata should be authoritative in KAOS vs AIB when it is both operational and security-relevant?
```

Mostly clear:

- Kubernetes owns object existence, namespace/name, UID.
- KAOS owns desired topology and runtime status.
- AIB owns security policy, grants, consent, token vault.

Still needs detail:

| Grey area | Why it matters |
|---|---|
| Owner/team/display metadata | Useful for consent/approval UI; could live in KAOS or AIB. |
| Requested permission profile | KAOS can declare requested capability; AIB must approve. |
| Route/resource mapping | KAOS creates routes; AIB needs protected-resource mapping. |
| Autonomous run metadata | KAOS owns execution; AIB owns grant/expiry. |
| Tool-level resource taxonomy | MCP knows tools; AIB/policy needs normalized resources/actions. |

Decision needed:

- Which of these become explicit KAOS fields?
- Which remain AIB-admin-managed?
- Which are derived by AIB CRD watcher?

## 3. Approval and consent execution model

Open question:

```text
Given KAOS's synchronous multi-agent flow, how should missing consent/admin approval/runtime approval be handled?
```

Candidate flows:

| Flow | Why considered |
|---|---|
| Preflight approval | Best if required permissions are known before execution. |
| Fail with approval URL then retry | Simple, deterministic, works for expired/missing grants. |
| UI-mediated approve-and-resubmit | Could fit KAOS UI/user UI if it can preserve prompt/session context. |
| Async task pause/resume | Best UX but requires durable task state and deterministic resume. |
| Blocking synchronous wait | Simple conceptually, risky due to timeouts and long approval latency. |

Specific research needed:

- Can KAOS infer likely permission needs before execution from Agent/MCP metadata?
- Can current KAOS A2A async task/autonomous capabilities support a blocked state?
- Does KAOS UI/admin UI exist or plan to exist in a way that can approve and resubmit?
- How does this work if approval is discovered inside a worker agent after several loops?

Likely initial bias:

- Prefer **preflight where possible**.
- Use **fail-with-approval URL + retry/resubmit** as the minimal robust fallback.
- Treat pause/resume as future unless current async task state can support it safely.

## 4. AIB vs Keycloak/OPA/service mesh/external tooling

Open question:

```text
Which problems are actually easier or better solved by existing authn/authz tools instead of AIB?
```

This is the main architectural challenge still unresolved.

Areas to compare:

| Capability | AIB | Keycloak | OPA/Rego | Service mesh / Envoy |
|---|---|---|---|---|
| Human login / OIDC | Not primary unless extended | Strong | No | Gateway can integrate |
| User consent for agent delegation | Strong fit / existing AIB feature | Possible via UMA/AuthZ, but less agent-specific | Policy only, no UX/token vault | No |
| Token vault for third-party OAuth tokens | Strong AIB fit | Possible but not the same focus | No | No |
| RFC 8693 token exchange | Implemented in AIB | Possible depending setup | No | Can call external service |
| Generic resource policy | Present via CEL/policy hooks | Strong | Strong | Enforcement point |
| Workload mTLS | No | No | No | Strong with mesh |
| Tool-level authz | Needs integration | Possible if modeled as resources/scopes | Strong if input is provided | Possible with body parsing/OPA |
| Admin approval workflow | Potential AIB addition | Stronger existing admin model | Policy only | No |

Research needs to answer:

- Is AIB best viewed as a **token broker + consent vault**, not a general auth platform?
- Should generic authorization decisions be delegated to OPA/Keycloak?
- Should AIB keep CEL, add OPA/Rego support, or remain policy-engine-agnostic?
- What can KAOS implement first without committing too deeply to AIB?

## 5. Enforcement topology

Open question:

```text
For first implementation, should enforcement happen at Gateway/ExtProc, sidecar, native runtime, or a combination?
```

Still needs detail because it affects everything:

- User identity propagation.
- MCP tool-level auth.
- AIB token exchange.
- Approval/consent errors.
- Synchronous vs async behavior.
- Operational overhead.

Options to compare:

| Option | Main advantage | Main concern |
|---|---|---|
| Gateway/ExtProc | Central, low app changes | Requires traffic routing and maybe body parsing |
| Sidecar/local proxy | Per-workload flexibility, no app changes | Pod overhead and injection complexity |
| Native FastMCP/runtime | Best protocol context | Requires app/runtime changes |
| Mesh + external auth | Strong baseline security | Operationally heavy for KAOS default |

Decision needed:

- What is the smallest useful topology for KAOS?
- What is the production-recommended topology?
- Can sidecar/gateway be MCP-aware enough without modifying MCP servers?

## 6. TLS/cert-manager baseline

Mostly resolved:

- Keep this simple.
- Use cert-manager for TLS certificate provisioning/renewal where needed.
- Avoid custom certificate lifecycle.
- Do not add secret-manager complexity in the initial target.

Still to clarify:

- Gateway TLS only vs optional in-cluster mTLS.
- Whether cert-manager becomes required or recommended.
- How local/dev clusters work without production cert infrastructure.

## Proposed next step

Before executing the full research plan, resolve these six outlines into research questions and acceptance criteria:

1. Workload identity complexity and ownership.
2. Metadata/source-of-truth grey areas.
3. Approval and consent execution model.
4. AIB vs Keycloak/OPA/service mesh/external tooling.
5. Enforcement topology.
6. TLS/cert-manager baseline.

The most important two to research first are:

1. **AIB vs external tooling boundary** - determines whether AIB is central or narrow.
2. **Approval/consent execution model** - determines whether the target fits KAOS's synchronous multi-agent architecture.
