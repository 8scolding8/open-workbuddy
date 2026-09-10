# Contributing to open-workbuddy

## Before opening a change

- Keep the proxy loopback-first and do not add private-token extraction.
- Never commit `config.json`, API keys, WorkBuddy session data, logs, or local
  model endpoint credentials.
- Keep model IDs exact and distinguish display names from request IDs.
- Preserve explicit failure behavior for incomplete or malformed streams.

## Local checks

```bash
cargo fmt --check
cargo check --all-targets
cargo test --all-targets
```

For the Windows ACP compatibility layer:

```powershell
py -m pip install -r requirements-windows.txt
py -m unittest discover -s . -p "test_*.py"
```

Use local fakes for deterministic tests. A live WorkBuddy smoke test is useful
only when an official local ACP gateway is already available and the prompt is
innocuous.
