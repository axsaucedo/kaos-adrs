# Security & identity — phase 2 design

This folder opens the second design phase for KAOS security and identity. The first phase lives in [`../security-and-identity/`](../security-and-identity/) and ran through implementation (phases P0–P17, PR `axsaucedo/kaos#267`); its investigation ended with a verdict that invalidates the core assumption of its own [ADR 0001](../security-and-identity/adrs/adr_0001_enforcement-topology-and-policy-engine.md): AIB's OPA-in-ext_proc cannot authorize internal KAOS traffic, because the authorization decision is structurally coupled to an RFC 8693 token exchange that KAOS does not perform and cannot skip (see [research/001](./research/001-why-aib-cannot-authorize-internal-traffic.md)).

This phase therefore restarts the design from that verdict, with two candidate directions framed by the project owner:

1. **Option 1** — find a workaround that lets AIB deliver authorization despite the exchange coupling.
2. **Option 2** — keep AIB for a **subset**: agent authentication only (explicitly excluding token exchange), and deliver authorization through Keycloak-sourced user facts evaluated by a KAOS-run OPA.

A further flaw carried over from phase 1 must be solved regardless of the option chosen: the implemented authorization model only expresses **agent → resource**; there is no workflow that authorizes the full **user + agent + resource** triple (see [research/003](./research/003-user-agent-resource-authz-gap.md)).

## Layout

- [`research/`](./research/) — condensed, evidence-backed insights from the phase-1 investigation and fresh codebase inspection. These are the facts the ADRs cite; refer back here rather than re-deriving.
- [`adrs/`](./adrs/) — the new decision records, starting from [adr_high_level_components](./adrs/adr_high_level_components.md), which indexes the major ADRs and the options each must weigh before any is fleshed out.

Conventions follow [`../security-and-identity/CONVENTIONS.md`](../security-and-identity/CONVENTIONS.md): no hard line wraps inside paragraphs or list items, cross-references as markdown links, `adr_NNNN_slug.md` naming.
