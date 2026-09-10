# Architecture notes

## Request path

1. A compatible client sends `/v1/chat/completions` or `/v1/responses`.
2. The proxy normalizes the request model and resolves a proxy-owned session.
3. The sidecar manager starts or reuses an official CodeBuddy ACP gateway.
4. The ACP transport creates an isolated session and sends the prompt.
5. ACP updates are normalized into Chat Completions deltas or Responses SSE
   events.
6. The proxy closes the ACP connection and keeps only the bounded local session
   history.

## Runtime model catalog

The Windows dashboard reads the current WorkBuddy runtime record under
`~/.workbuddy/local_storage`. The active agent model list is used as the
authoritative picker order, and metadata is sanitized before it is returned by
`/v1/models`. Custom models are read separately from `~/.workbuddy/models.json`
without exposing endpoint URLs or API keys.

The installed `product.internal.json` catalog is only a fallback. This avoids
showing an old package catalog when the WorkBuddy desktop client has already
updated its model picker.

## Trust boundaries

The proxy owns local sessions and sidecars. WorkBuddy owns account access,
upstream quotas, model availability, and the official ACP gateway. The proxy
does not attach to or modify the WorkBuddy GUI conversation store.
