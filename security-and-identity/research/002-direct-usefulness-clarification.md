# 002 - Direct usefulness clarification

## Prompt

You mentioned ```Current AIB is not yet directly useful as-is for KAOS core. The implemented project is much more "OAuth2 consent/token-exchange broker for agents accessing third-party services" than the broader "cryptographic agent identity/federated agent trust" described in parts of its docs```. Why is not directly useful as is? Is it because currently the agents access everything through MCPs? but what if we were to integrate this into the mcp servers? or how would thi sbe integrated? Also the last para ```The most immediately relevant slice is AIB's token-vault + RFC 8693/ExtProc path for agents calling protected MCP or third-party APIs on behalf of users``` contradicts the previous as it's saying that as of now it's useful already as agents calling third party apis on behalf of users, which directly cntradicts what was just said. So which one is it?

## Response

You're right to call out the ambiguity. Better phrasing:

**AIB is useful today for a narrow KAOS-adjacent use case, but not directly useful as a drop-in KAOS core integration.**

The reason is not simply "KAOS agents access everything through MCP." It's that KAOS currently treats MCP access as **static infrastructure wiring**: an Agent CRD references MCPServer CRDs, the operator injects MCP URLs, and the agent calls those servers. There is no built-in concept of "this end user granted this agent these scopes for GitHub/Slack/Databricks," nor a token propagation model from user -> agent -> MCP -> third-party API.

AIB's current strongest implemented value is exactly that missing layer: **user-consented delegated OAuth tokens** and **RFC 8693 token exchange**. That becomes useful if KAOS MCP servers are protected resources and/or MCP tools call third-party APIs on behalf of users.

So the distinction is:

| Question | Answer |
|---|---|
| Is AIB useful conceptually for KAOS? | **Yes. Very much.** KAOS needs agent identity, delegated access, consent, audit, and token boundaries as it grows. |
| Is the AIB project direction useful for KAOS? | **Yes.** Its consent/token-vault/token-exchange pieces map well to KAOS MCP and A2A security needs. |
| Is current AIB directly useful by just deploying it next to KAOS? | **Only for a narrow path, not broadly.** It does not automatically secure KAOS agents, A2A calls, MCP calls, or CRD-driven identity without integration work. |

A practical current-state integration would likely be: **Agent calls MCP with a user/subject token -> MCP or gateway/ExtProc exchanges that token through AIB -> MCP receives a scoped third-party access token -> tool calls GitHub/Slack/etc.** In that model, AIB is useful now, but only after KAOS has token propagation and MCP-side enforcement.

What is **not** ready as-is is the broader story: cryptographic agent identities, federated agent trust, automatic KAOS Agent registration, per-agent runtime credentials, A2A authorization, and Kubernetes-native reconciliation. Those are the parts I meant by "not directly useful for KAOS core today."
