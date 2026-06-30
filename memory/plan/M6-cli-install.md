# CLI install integration and samples — implementation plan

**Branch (KAOS)**: `feat/memory-cli-install`, stacked off `feat/memory-store-crd` (M4); PR targets `feat/memory-store-crd` (rebase onto M5's tip if M5 lands first).
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M4 → M6 → M7`. M6 makes the memory components installable through the existing `kaos system install` integration-flag pattern and ships samples. It depends on M4 (the chart must already render the CRD, controller RBAC, and memory-service image). It is independent of M5's enforcement work, so it can proceed in parallel and rebase onto M5's tip if M5 lands first. **Before starting, re-read [`../impl/learnings/M4-memory-store-crd.md`](../impl/learnings/M4-memory-store-crd.md)** for the chart values/RBAC the installer must set.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run `cd kaos-cli && pytest tests/ -v` locally (dry-run YAML validation); KIND available for a real install check. Alpha: breaking changes OK.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M6-cli-install.md` and write `impl/progress/M6-*.md` + `impl/learnings/M6-*.md`.

## Problem statement

Provide a turnkey on-ramp consistent with the rest of KAOS: a `kaos system install --memory-enabled` switch that installs/upgrades the chart with the memory components, an **opt-in development Postgres** provisioning step (explicit, never the production default) for `external` mode, and sample resources (a `MemoryStore` and a memory-enabled Agent) so a user can stand the feature up end to end. The CLI work mirrors the existing integration-flag pattern (`--gateway-enabled`, `--metallb-enabled`, `--monitoring-enabled`, and the already-present `--redis-enabled`).

## Current-state grounding (researched)

- **Flag pattern.** `kaos-cli/kaos_cli/system/__init__.py:42-230` defines install flags and forwards them via `install_command(...)` (`:239-260`). Existing component flags: `--gateway-enabled` (`:75-79`), `--metallb-enabled` (`:80-84`), `--monitoring-enabled` (`:70-74`), and — directly relevant — **`--redis-enabled`** (`:85-89`).
- **Helm plumbing.** `kaos-cli/kaos_cli/install.py:575-642` builds Helm `--set` args; component installers use `helm upgrade --install ... --namespace ... --create-namespace` (`:373-514`, `:645-715`). `_install_redis` (`:474-514`) is the closest precedent for an optional in-cluster datastore — the **dev Postgres provisioning** mirrors it.
- **Chart targets (from M4).** M4 added `defaultImages.memoryService` + `DEFAULT_MEMORY_SERVICE_IMAGE`, the `MemoryStore` CRD in `chart/crds/`, and controller RBAC. The installer only needs to flip the chart values / install the optional dev Postgres; it does not change the chart shape.
- **Dev-Postgres posture.** [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): Postgres is bring-your-own in `external` mode, but the CLI installer can provision an **opt-in** development Postgres as a first-class explicit step alongside gateway/load-balancer provisioning — never the production default.
- **Samples + dry-run tests.** Samples live under the samples surface (`kaos_cli/samples/`, `operator/config/samples`); `kaos-cli/tests/test_cli_integration.py` uses Typer `CliRunner` with `--dry-run` YAML assertions.

## Design plan (how it fits)

- **`--memory-enabled`.** Add the flag to `system/__init__.py` mirroring `--redis-enabled`; thread it through `install_command` into a Helm value (e.g. `memory.enabled=true`) so the operator/chart deploys the memory controller path. Keep it a pure integration flag — the `MemoryStore` itself is a user-applied resource (or a sample), not auto-created, matching how other CRDs work.
- **`--memory-postgres-enabled` (dev Postgres).** Add an explicit opt-in flag that provisions a development Postgres (with the `pgvector` extension) via a `_install_memory_postgres` helper modelled on `_install_redis`, and surfaces its connection as a Secret the `external`-mode `MemoryStore` sample references. Document loudly that this is dev-only.
- **Samples.** Add a `MemoryStore` sample (`local` mode for zero-dependency, plus an `external` variant referencing the dev-Postgres secret) and a memory-enabled Agent sample (`storeRef`, `shortTermTokenBudget`, `rollingSummary`, `recall.presentation`, `failureMode`, `scope`), wired into the samples list/deploy commands.
- **Dry-run tests.** Extend `test_cli_integration.py` to assert the new flags render the expected Helm values and that the samples validate.

## Numbered TODOs

1. **`--memory-enabled` flag + plumbing.** Add the flag (`system/__init__.py`, mirroring `--redis-enabled:85-89`), thread it through `install_command`/`install.py` into the Helm `--set` (e.g. `memory.enabled=true`). **Validate**: dry-run test asserts the flag sets the value; `cd kaos-cli && pytest tests/ -k memory -v`.

2. **Dev Postgres provisioning (opt-in).** Add `--memory-postgres-enabled` + `_install_memory_postgres` (modelled on `_install_redis:474-514`) provisioning a dev Postgres with `pgvector` and writing a connection Secret; gate it clearly as dev-only. **Validate**: dry-run/unit test asserts the helper renders the Postgres install and the secret; document the secret name/key the `external` sample uses; `pytest tests/ -k postgres -v`.

3. **MemoryStore + Agent samples.** Add a `local`-mode `MemoryStore` sample, an `external`-mode variant referencing the dev-Postgres secret, and a memory-enabled Agent sample; wire them into the samples list/deploy/delete commands. **Validate**: dry-run YAML validation of each sample; `pytest tests/ -k samples -v`.

4. **Real install check + PR.** On local KIND, run `kaos system install --memory-enabled` (and a second run with `--memory-postgres-enabled`), apply the samples, and confirm the memory service and a memory-enabled agent come up and work end to end. Suppress to `./tmp/null`. **Validate**: the install + sample flow works locally; `cd kaos-cli && pytest tests/ -v`. Write `impl/progress/M6-*.md` + `impl/learnings/M6-*.md`, copy this plan, push `feat/memory-cli-install`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (M0–M6) and post it as a PR comment.

## Validation per task

- Per-TODO: `cd kaos-cli && python -m pytest tests/ -v` (dry-run YAML assertions run in CI). The real-install check is local KIND and documented in `REPORT.md`.

## Commit / PR strategy

- `feat/memory-cli-install` stacked off `feat/memory-store-crd` (rebase onto M5's tip if M5 lands first); one comprehensive commit per TODO; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.

## Out of scope (later phases)

Granular install override flags (external Postgres endpoints, custom issuers) beyond the single switch and the opt-in dev Postgres; HA tuning, metrics, durable-queue decision, e2e promotion, and the full user/operator documentation (M7).
