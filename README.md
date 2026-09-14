# ⚡ open-workbuddy

<p align="center"><b>WorkBuddy, opened up.</b><br>
An OpenAI-compatible local proxy for WorkBuddy's official ACP gateway.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/Rust-1.97%2B-orange?logo=rust" alt="Rust 1.97 or newer"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python" alt="Python 3.11 or newer"></a>
</p>

`open-workbuddy` lets local clients speak to the models already available in WorkBuddy through familiar OpenAI endpoints. It provides a small Rust proxy/TUI, a Windows ACP runtime, a live model catalog, and an OpenCodex-inspired local integration dashboard.

The project uses the official WorkBuddy/CodeBuddy ACP transport. It does not extract WorkBuddy tokens, imitate private HTTP authentication, or send client credentials to the protected service.

## What it does

- Translates OpenAI Chat Completions and Responses requests to WorkBuddy ACP.
- Preserves streaming text and explicit upstream failures.
- Correlates every ACP prompt to its response message, rejecting replayed
  history instead of mixing it into the caller's completion.
- Reuses an active loopback WorkBuddy/CodeBuddy gateway when one is available,
  then starts an isolated sidecar only as a fallback.
- Reads the current WorkBuddy runtime model picker instead of relying on an old static catalog.
- Exposes a local dashboard for model selection, endpoint discovery, and copyable examples.
- Provides a Rust TUI for sessions, projects, model selection, diagnostics, and logs.
- Keeps API keys, session history, runtime state, and logs out of Git through `.gitignore`.

## Architecture

```text
OpenAI-compatible client
          │
          │ /v1/responses or /v1/chat/completions
          ▼
┌─────────────────────────────┐
│       open-workbuddy        │
│  request parser + router    │
│  OpenAI protocol bridge     │
│  model picker + session store│
└──────────────┬──────────────┘
               │ official local ACP
               ▼
      WorkBuddy CodeBuddy ACP gateway
               │
               ▼
         WorkBuddy models
```

The dashboard is available at `http://127.0.0.1:40589/#integrations/keys` after the Windows launcher starts.

## Quick start on Windows

Prerequisites:

1. WorkBuddy is installed and already signed in, then left running while the
   proxy is used.
2. The official `codebuddy` launcher is available in the WorkBuddy installation.
3. Python 3.11 or newer is installed.

Create the Python environment once:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
```

Start the proxy and dashboard:

```powershell
.\launch-workbuddy-proxy.ps1
```

The launcher reuses a healthy listener on port `40589`, starts a hidden background process when needed, waits for `/health`, and opens the dashboard. The desktop shortcut created by the local setup performs the same workflow.

To create that shortcut after cloning:

```powershell
.\setup-windows-shortcut.ps1
```

The script writes `Open WorkBuddy Proxy.lnk` to the current Windows user's
Desktop. It can be pointed at another checkout or port with `-Project` and
`-Port`.

The Windows launcher uses the Python ACP runtime. The Rust TUI and Rust
sidecar lifecycle currently target Unix/Linux because they use Unix process
groups and `/proc`; a native Windows Rust build is not part of the supported
Windows path.

When WorkBuddy is running, the Windows runtime first looks for live loopback
ACP registrations in `.workbuddy\sessions`, `.codebuddy\sessions`, and the
older `.workbuddy-ai\sessions` directory. This reuses the official logged-in
gateway without reading its credentials. If no live registration exists, the
proxy starts a dedicated official CodeBuddy sidecar; that fallback requires the
official CLI itself to have a usable account session.

The direct server script is also available:

```powershell
.\start-windows.ps1 -Project (Get-Location).Path -Port 40589
```

## API usage

Base URL:

```text
http://127.0.0.1:40589/v1
```

Chat Completions:

```powershell
$body = @{
  model = "hy3"
  messages = @(@{ role = "user"; content = "你好，WorkBuddy" })
  stream = $false
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Uri "http://127.0.0.1:40589/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer local-proxy" } `
  -Body $body
```

Responses API:

```json
{
  "model": "hy3",
  "input": "你好，WorkBuddy"
}
```

Endpoints:

| Endpoint | Purpose |
| --- | --- |
| `/v1` | Base URL for compatible clients |
| `/v1/chat/completions` | Chat Completions |
| `/v1/responses` | Responses API |
| `/v1/models` | Current WorkBuddy model list |
| `/health` | Local health check |
| `/proxy/config` | Loopback-only dashboard configuration |
| `/proxy/model` | Loopback-only default model selection |

## Models

The Windows Python dashboard follows the model picker currently exposed by
WorkBuddy, then adds other tool-capable entries from the installed catalog and
safe custom configuration. The Rust runtime reads the same runtime record when
available and otherwise uses its configured/static fallback catalog. Typical
IDs include:

```text
hy3
hy4-preview
deepseek-v4.1-flash
glm-5.3
glm-5.3-flash
glm-5.2
glm-5.1
glm-5v-turbo
minimax-m3
kimi-k3-1
deepseek-v4-pro
```

The exact list is runtime- and account-dependent. The dashboard uses the exact ID returned by `/v1/models`; display names such as `MiniMax-M3` and `Kimi-K3` are not substitutes for `minimax-m3` and `kimi-k3-1`.

To change the default model from the dashboard, choose a model and select **设为默认**. The proxy recycles existing sidecars before the next request and persists the non-secret preference locally.

## Codex and other clients

Configure compatible clients with the base URL and a local placeholder key when the client requires one. If `PROXY_API_KEY` is set, use that exact local key; it is never sent to WorkBuddy. For Codex-style configuration:

```toml
model = "hy3"
model_provider = "open_workbuddy"

[model_providers.open_workbuddy]
name = "open-workbuddy"
base_url = "http://127.0.0.1:40589/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
```

Use a deterministic project/session route when the client supports custom headers:

```http
X-WorkBuddy-Project: C:\path\to\project
X-WorkBuddy-Session: proxy-<session-id>
```

If those headers are omitted, the proxy derives a stable automatic session from the configured default project and request context.

## Configuration

The Rust and Windows runtimes use the following important settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PROXY_HOST` | `127.0.0.1` | Bind address; non-loopback values require `PROXY_API_KEY` |
| `PROXY_PORT` | `40589` | Local API/dashboard port |
| `WORKBUDDY_MODEL` | `hy3` | Default model ID |
| `WORKBUDDY_CLI_PATH` | auto-discovered | Official `codebuddy` launcher |
| `WORKBUDDY_CONFIG_DIR` | auto-discovered | Optional WorkBuddy ACP session/config root |
| `CODEBUDDY_CONFIG_DIR` | auto-discovered | Optional CodeBuddy ACP session/config root |
| `WORKBUDDY_RUNTIME_MODEL_CONFIG` | auto-discovered | Optional runtime catalog file |
| `WORKBUDDY_CUSTOM_MODELS_CONFIG` | `~/.workbuddy/models.json` | Optional custom model catalog |
| `PROXY_DEFAULT_PROJECT` | repository directory | Project used by headerless clients |
| `PROXY_API_KEY` | empty | Local Bearer key; required for non-loopback binds |

The upstream compatibility variables `FREEMODEL_BASE_URL`, `FREEMODEL_TRANSPORT`, and `FREEMODEL_API_KEY` are retained because the protected WorkBuddy service is reached through that service contract. They are local configuration names, not credentials committed to this repository.

## Security boundaries

- The proxy binds to loopback by default.
- Startup rejects a non-loopback bind unless `PROXY_API_KEY` is configured.
- Management routes are loopback-only.
- Client API keys are not forwarded as WorkBuddy credentials.
- The proxy uses the official local ACP gateway rather than copying private authentication headers.
- `config.json`, session stores, runtime directories, logs, Python environments, and build output are ignored.
- Do not expose an unauthenticated `0.0.0.0` listener to a LAN or the public internet.

WorkBuddy account access must already be available to the official WorkBuddy/CodeBuddy client. A service-side quota or account error is not fixed by changing the local proxy port or sidecar count.

`/health` reports `active_gateway_count` and `gateway_mode`. A healthy local
proxy with `gateway_mode: sidecar_on_demand` only proves that the HTTP server is
running; it does not prove that the official client is logged in or that a
model completion will succeed.

## Development

Rust checks:

```bash
cargo fmt --check
cargo check --all-targets
cargo test --all-targets
```

Python compatibility tests:

```powershell
py -m pip install -r requirements-windows.txt
py -m unittest discover -s . -p "test_*.py"
```

The Windows ACP path can be smoke-tested with the installed WorkBuddy client. Deterministic tests use local fakes and do not require private upstream credentials.

## Project status

The core proxy, model dashboard, model switching, Windows background launcher, and WorkBuddy ACP smoke path are implemented. The protected WorkBuddy service remains dependent on the official WorkBuddy account session and its upstream availability.

## Provenance

`open-workbuddy` is an independent WorkBuddy-focused project. Its integration-page information architecture was developed after studying the public OpenCodex project, but this repository is not affiliated with OpenCodex and does not use OpenCodex branding or demo assets. See [CREDITS.md](CREDITS.md) for attribution and boundaries.

WorkBuddy and CodeBuddy are trademarks or product names of their respective owners. This project is not an official WorkBuddy release.

## License

Released under the [MIT License](LICENSE).
