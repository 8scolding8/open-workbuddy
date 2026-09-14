# Architecture notes

## Request path

1. A compatible client sends `/v1/chat/completions` or `/v1/responses`.
2. The proxy normalizes the request model and resolves a proxy-owned session.
3. The runtime reuses a live loopback WorkBuddy/CodeBuddy ACP gateway when one
   is registered; otherwise the sidecar manager starts an official CodeBuddy
   ACP gateway.
4. The ACP transport creates an isolated session and sends the prompt.
5. Each prompt carries a fresh ACP correlation/message ID; only matching
   `agent_message_chunk` events are accepted, so replayed gateway history cannot
   leak into the response.
6. ACP updates are normalized into Chat Completions deltas or Responses SSE
   events.
7. The proxy closes the ACP connection and keeps only the bounded local session
   history.

## Runtime model catalog

The Python dashboard/runtime and the Rust runtime read the current WorkBuddy
runtime record under `~/.workbuddy/local_storage` when it is available. Active
agent models are listed first, followed by other tool-capable entries from the
same catalog; metadata is sanitized before it is returned by `/v1/models`.

The Windows Python path additionally merges safe custom models from
`~/.workbuddy/models.json` and entries from the installed
`product.internal.json` catalog without exposing endpoint URLs or API keys.
The Rust path intentionally keeps its catalog parser small: it uses the runtime
record or an explicitly configured `WORKBUDDY_RUNTIME_MODEL_CONFIG`, then falls
back to its built-in list. The exact catalog remains dependent on the installed
WorkBuddy version and account.

## Trust boundaries

The proxy owns local sessions and any sidecars it starts. WorkBuddy owns account
access, upstream quotas, model availability, and the official ACP gateway. A
reused gateway is addressed only through its loopback ACP endpoint; the proxy
does not read its credentials or modify the WorkBuddy GUI conversation store.
