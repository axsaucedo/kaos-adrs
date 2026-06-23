# P9 — SDK token lifecycle (learnings)

**Phase**: P9 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-22
**Context**: giving the agent runtime a managed actor-token lifecycle — mint via `client_credentials`, refresh-ahead, rotate the client secret from a mounted file, inject on outbound calls, and refresh-and-replay once on a gateway `401` — all inert unless broker credentials are mounted.

## Key findings

### Refresh-ahead plus a still-valid-cache fallback is what makes "fail-closed" usable

Two failure modes pull in opposite directions: a token must never be used past expiry (so refresh proactively, at ~80% of lifetime), but a transient broker hiccup must not take the agent down if it still holds a valid token. The manager reconciles them by tracking two instants — `_refresh_at` (when to *try* a refresh) and `_expires_at` (when the token is *actually* dead) — and serving the cached token when a refresh fails but `now < _expires_at`, only raising `AIBUnavailable` when there is genuinely no valid token. "Fail-closed" without the still-valid-cache fallback would convert every blip into an outage.

### Inject the managed token at send time, not at context-setup time

The two-identity model already makes the actor "this agent". The temptation is to set the actor token into the request-local context once per request, but the managed token can refresh *between* setting the context and making an outbound call. Injecting from the manager at `httpx.send` time (only when the request carries no actor token, and never overwriting a caller-supplied header) means every outbound call gets the currently-valid token without re-plumbing the context. It also keeps the static-token and caller-supplied paths working unchanged — the manager is a pure fallback.

### The async send path must not call the sync (blocking) acquisition

Outbound injection runs inside `httpx.AsyncClient.send`. Calling the synchronous `manager.token()` there would do a blocking `httpx.post` on the event loop during a refresh and stall every coroutine on the loop. The fix is a parallel `_inject_request_headers_async` that `await`s `token_async()`, wired into the patched async `send`. Any "inject a freshly-acquired credential" hook needs a genuinely async branch — reusing the sync one is a latent event-loop stall, not just a style nit.

### Source the client secret from a file, fall back to env, reload on mtime

Mounting the credential Secret as a file (rather than only as an env var) is what makes rotation possible: env vars are captured at process start and never change, but a file can be re-read. The `_Credential` reads the file, caches its mtime, and re-reads only when the mtime changes — cheap on the hot path, correct on rotation. Keeping the `AGENT_AUTH_CLIENT_SECRET` env as a fallback means the pod still works before the sync service has written the Secret (the operator mounts the Secret reference as optional for the same reason). On an `invalid_client`/`401` during a grant, forcing a `reload()` before the retry catches the just-rotated case immediately instead of waiting for the next mtime poll.

### A reactive 401 retry needs the pre-send actor-token state captured first

The replay-on-401 logic must only fire when the request *actually carried* an actor token and a managed identity is active — otherwise a 401 from an unrelated upstream would trigger a pointless refresh+replay. Capturing `had_actor = HEADER_ACTOR_TOKEN in request.headers` *before* sending, then gating the retry on `had_actor and status == 401 and a manager produced a new token`, keeps the retry surgical. Introducing managed-token injection later subtly changed this: once the manager injects the token, the "no actor header" case only occurs when there is no manager (or it yields no token), so the corresponding unit test had to be re-pointed at a manager whose `token()` returns `None`.

### Test the async lifecycle by priming the cache, not by mocking the loop

Tests that exercise async injection were hanging because the manager's `token_async()` made a real network call (only the sync `httpx.post` was mocked). The clean fix is to prime the manager's cache via the mocked *sync* grant first (`mgr.token()`), so the subsequent async injection serves the cached token with no network at all — far simpler and less brittle than trying to fake `httpx.AsyncClient` globally (which also breaks the `MockTransport` path used by the same test).

### Keep the off-gateway client honest about what it is

`aib/client.py` is a convenience over the broker's `/api/access/check` and `/oauth2/token`, for processes that do *not* sit behind the gateway. It is explicitly not the enforcement boundary — gateway traffic is still authorized by ext_authz and exchanged by ext_proc. Modelling a recoverable denial as a distinct `ReauthenticationRequired` (carrying a reauth URL when the broker supplies one) lets callers drive the user back through consent, while a hard `AccessDenied` is terminal; transport failures surface as `AIBUnavailable` so the client fails closed like the rest of the SDK.
