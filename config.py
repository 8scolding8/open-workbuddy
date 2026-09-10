"""Configuration for the Open WorkBuddy API Proxy."""

import os
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_WORKBUDDY_BASE_URL = "https://work.freemodel.dev/v1"


def load_saved_key() -> str:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                key = data.get("FREEMODEL_API_KEY", "").strip()
                if key:
                    return key
        except Exception:
            pass
    # Fallback to ~/.codex/auth.json
    codex_auth = Path.home() / ".codex" / "auth.json"
    if codex_auth.exists():
        try:
            with open(codex_auth, "r") as f:
                cdata = json.load(f)
                key = (cdata.get("FREEMODEL_API_KEY") or cdata.get("OPENAI_API_KEY") or "").strip()
                if key:
                    return key
        except Exception:
            pass
    return ""


def load_saved_value(name: str, default=""):
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get(name, default)
        except Exception:
            pass
    return default


def load_saved_base_url() -> str:
    return str(load_saved_value("FREEMODEL_BASE_URL", "")).strip()


def save_key(key: str):
    data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            pass
    data["FREEMODEL_API_KEY"] = key.strip()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_value(name: str, value):
    """Persist a non-secret user preference without exposing existing secrets."""
    data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data[name] = value
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def upstream_hostname(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid FREEMODEL_BASE_URL: {base_url}")
    return parsed.hostname.lower()


def is_protected_workbuddy_url(base_url: str) -> bool:
    return upstream_hostname(base_url) == "work.freemodel.dev"


DEFAULT_BASE_URL = (
    os.environ.get("FREEMODEL_BASE_URL")
    or load_saved_base_url()
    or DEFAULT_WORKBUDDY_BASE_URL
).rstrip("/")
DEFAULT_API_KEY = os.environ.get("FREEMODEL_API_KEY") or load_saved_key()
PROXY_API_KEY = str(
    os.environ.get("PROXY_API_KEY")
    or load_saved_value("PROXY_API_KEY", "")
).strip()

TRANSPORT = str(
    os.environ.get("FREEMODEL_TRANSPORT")
    or load_saved_value(
        "FREEMODEL_TRANSPORT",
        "workbuddy_acp" if is_protected_workbuddy_url(DEFAULT_BASE_URL) else "http",
    )
).strip().lower()
if TRANSPORT not in {"http", "workbuddy_acp"}:
    raise ValueError(f"Unsupported FREEMODEL_TRANSPORT: {TRANSPORT}")
if is_protected_workbuddy_url(DEFAULT_BASE_URL) and TRANSPORT != "workbuddy_acp":
    raise ValueError(
        "https://work.freemodel.dev requires FREEMODEL_TRANSPORT=workbuddy_acp"
    )

WORKBUDDY_ACP_URL = str(
    os.environ.get("WORKBUDDY_ACP_URL")
    or load_saved_value("WORKBUDDY_ACP_URL", "http://127.0.0.1:44741")
).rstrip("/")
WORKBUDDY_ACP_PASSWORD = str(
    os.environ.get("WORKBUDDY_ACP_PASSWORD")
    or load_saved_value("WORKBUDDY_ACP_PASSWORD", "")
)
WORKBUDDY_ACP_CWD = str(
    os.environ.get("WORKBUDDY_ACP_CWD")
    or load_saved_value("WORKBUDDY_ACP_CWD", str(Path(__file__).parent))
)
WORKBUDDY_ACP_TIMEOUT = float(
    os.environ.get("WORKBUDDY_ACP_TIMEOUT")
    or load_saved_value("WORKBUDDY_ACP_TIMEOUT", 180)
)
WORKBUDDY_ACP_MAX_ATTEMPTS = int(
    os.environ.get("WORKBUDDY_ACP_MAX_ATTEMPTS")
    or load_saved_value("WORKBUDDY_ACP_MAX_ATTEMPTS", 4)
)
if WORKBUDDY_ACP_TIMEOUT <= 0:
    raise ValueError("WORKBUDDY_ACP_TIMEOUT must be greater than zero")
if WORKBUDDY_ACP_MAX_ATTEMPTS < 1:
    raise ValueError("WORKBUDDY_ACP_MAX_ATTEMPTS must be at least one")

PROJECT_ROOT = Path(__file__).parent

WORKBUDDY_MODEL = str(
    os.environ.get("WORKBUDDY_MODEL")
    or load_saved_value("WORKBUDDY_MODEL", "hy3")
).strip()
if not WORKBUDDY_MODEL:
    raise ValueError("WORKBUDDY_MODEL must not be empty")


def _model_entry(
    raw: dict,
    *,
    source: str,
    created: int | None = None,
    fallback_id: str = "",
) -> dict | None:
    """Expose only non-sensitive model metadata to OpenAI-compatible clients."""
    model_id = str(raw.get("id") or fallback_id or "").strip()
    if not model_id:
        return None
    return {
        "id": model_id,
        "object": "model",
        "created": int(raw.get("created") or created or 0),
        "owned_by": "workbuddy",
        "display_name": str(raw.get("name") or raw.get("display_name") or model_id),
        "supports_tools": raw.get("supportsToolCall") is True,
        "supports_reasoning": raw.get("supportsReasoning"),
        "supports_images": raw.get("supportsImages") is True,
        "max_input_tokens": raw.get("maxInputTokens"),
        "max_output_tokens": raw.get("maxOutputTokens"),
        "source": source,
    }


def _json_data_records(path: Path):
    """Yield data records from a WorkBuddy local-storage JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    records = payload if isinstance(payload, list) else [payload]
    for record in records:
        if not isinstance(record, dict):
            continue
        data = record.get("data")
        yield data if isinstance(data, dict) else record


def find_workbuddy_runtime_configs() -> list[Path]:
    """Find WorkBuddy's current runtime catalog without assuming one entry id."""
    configured = str(
        os.environ.get("WORKBUDDY_RUNTIME_MODEL_CONFIG")
        or load_saved_value("WORKBUDDY_RUNTIME_MODEL_CONFIG", "")
    ).strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    runtime_dir = Path.home() / ".workbuddy" / "local_storage"
    if runtime_dir.is_dir():
        candidates.extend(sorted(
            runtime_dir.glob("wb_entry_*.info"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ))
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        key = str(candidate.resolve()).lower()
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def load_runtime_workbuddy_models() -> list[dict]:
    """Load the model list used by the current WorkBuddy agent configuration."""
    for runtime_config in find_workbuddy_runtime_configs():
        try:
            records = _json_data_records(runtime_config)
            if records is None:
                continue
            for data in records:
                raw_models = data.get("models")
                if not isinstance(raw_models, list):
                    continue
                by_id: dict[str, dict] = {}
                for raw in raw_models:
                    if not isinstance(raw, dict):
                        continue
                    model_id = str(raw.get("id") or "").strip()
                    if model_id:
                        by_id.setdefault(model_id.lower(), raw)

                # WorkBuddy's agent list is the runtime equivalent of the
                # model picker shown in the desktop app. Preserve that order
                # instead of exposing stale or hidden catalog entries.
                active_ids: list[str] = []
                active_seen: set[str] = set()
                agents = data.get("agents")
                if isinstance(agents, list):
                    for agent in agents:
                        if not isinstance(agent, dict) or not isinstance(agent.get("models"), list):
                            continue
                        for value in agent["models"]:
                            model_id = str(value or "").strip()
                            if model_id and model_id.lower() not in active_seen:
                                active_ids.append(model_id)
                                active_seen.add(model_id.lower())

                ordered_ids = active_ids or [
                    str(raw.get("id") or "").strip()
                    for raw in raw_models
                    if isinstance(raw, dict) and str(raw.get("id") or "").strip()
                ]
                models: list[dict] = []
                created = int(runtime_config.stat().st_mtime)
                for model_id in ordered_ids:
                    raw = by_id.get(model_id.lower(), {"id": model_id})
                    entry = _model_entry(raw, source="runtime", created=created, fallback_id=model_id)
                    if entry is not None:
                        models.append(entry)
                if models:
                    return models
        except OSError:
            continue
    return []


def find_workbuddy_custom_models() -> Path | None:
    configured = str(
        os.environ.get("WORKBUDDY_CUSTOM_MODELS_CONFIG")
        or load_saved_value("WORKBUDDY_CUSTOM_MODELS_CONFIG", "")
    ).strip()
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path.home() / ".workbuddy" / "models.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_workbuddy_custom_models() -> list[dict]:
    """Load custom model IDs while deliberately discarding endpoint secrets."""
    path = find_workbuddy_custom_models()
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        raw_models = payload
    elif isinstance(payload, dict):
        raw_models = payload.get("models", [])
    else:
        return []
    if not isinstance(raw_models, list):
        return []
    models: list[dict] = []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or "").strip()
        if not model_id or raw.get("supportsToolCall") is False:
            continue
        entry = _model_entry(raw, source="custom", created=int(path.stat().st_mtime))
        if entry is not None:
            models.append(entry)
    return models


def find_workbuddy_product_config() -> Path | None:
    configured = str(os.environ.get("WORKBUDDY_PRODUCT_CONFIG") or "").strip()
    candidates = [Path(configured)] if configured else []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Programs"
            / "WorkBuddy"
            / "resources"
            / "app.asar.unpacked"
            / "cli"
            / "product.internal.json"
        )
    candidates.append(
        Path.home()
        / "AppData"
        / "Local"
        / "Programs"
        / "WorkBuddy"
        / "resources"
        / "app.asar.unpacked"
        / "cli"
        / "product.internal.json"
    )
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def load_workbuddy_product_models() -> list[dict]:
    product_config = find_workbuddy_product_config()
    if product_config is None:
        return []
    try:
        data = json.loads(product_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []
    models = []
    created = int(product_config.stat().st_mtime)
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or "").strip()
        if not model_id:
            continue
        # The catalog also contains image/completion-only entries. The proxy
        # exposes agent-capable WorkBuddy models that can serve this API.
        if raw.get("supportsToolCall") is not True and model_id != WORKBUDDY_MODEL:
            continue
        entry = _model_entry(raw, source="installed", created=created)
        if entry is not None:
            models.append(entry)
    return models


def load_workbuddy_models() -> list[dict]:
    """Prefer WorkBuddy's live picker, then custom models, then static fallback."""
    runtime_models = load_runtime_workbuddy_models()
    models = runtime_models or load_workbuddy_product_models()
    seen = {str(item.get("id") or "").lower() for item in models}
    for item in load_workbuddy_custom_models():
        model_id = str(item.get("id") or "")
        if model_id.lower() not in seen:
            models.append(item)
            seen.add(model_id.lower())
    return models


def find_codebuddy_on_path() -> str | None:
    resolved = shutil.which("codebuddy")
    if resolved:
        return resolved
    # WorkBuddy's packaged launcher has no extension. Windows' shutil.which
    # only checks PATHEXT-backed names, so also inspect exact PATH entries.
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / "codebuddy"
        if candidate.is_file():
            return str(candidate)
    return None


_configured_codebuddy = str(
    os.environ.get("WORKBUDDY_CLI_PATH")
    or load_saved_value("WORKBUDDY_CLI_PATH", "")
).strip()
WORKBUDDY_CLI_PATH = str(
    Path(_configured_codebuddy).expanduser()
    if _configured_codebuddy
    else Path(find_codebuddy_on_path() or "codebuddy")
)
PROXY_SESSION_STORE = str(
    Path(
        os.environ.get("PROXY_SESSION_STORE")
        or load_saved_value("PROXY_SESSION_STORE", str(PROJECT_ROOT / ".proxy-sessions.json"))
    ).expanduser()
)
PROXY_RUNTIME_DIR = str(
    Path(
        os.environ.get("PROXY_RUNTIME_DIR")
        or load_saved_value("PROXY_RUNTIME_DIR", str(PROJECT_ROOT / ".proxy-runtime"))
    ).expanduser()
)
PROXY_DEFAULT_PROJECT = str(
    Path(
        os.environ.get("PROXY_DEFAULT_PROJECT")
        or load_saved_value("PROXY_DEFAULT_PROJECT", WORKBUDDY_ACP_CWD)
    ).expanduser()
)
PROXY_SIDECAR_STARTUP_TIMEOUT = float(
    os.environ.get("PROXY_SIDECAR_STARTUP_TIMEOUT")
    or load_saved_value("PROXY_SIDECAR_STARTUP_TIMEOUT", 30)
)
PROXY_SIDECAR_IDLE_TIMEOUT = float(
    os.environ.get("PROXY_SIDECAR_IDLE_TIMEOUT")
    or load_saved_value("PROXY_SIDECAR_IDLE_TIMEOUT", 900)
)
PROXY_MAX_HISTORY_TURNS = int(
    os.environ.get("PROXY_MAX_HISTORY_TURNS")
    or load_saved_value("PROXY_MAX_HISTORY_TURNS", 100)
)
if PROXY_SIDECAR_STARTUP_TIMEOUT <= 0:
    raise ValueError("PROXY_SIDECAR_STARTUP_TIMEOUT must be greater than zero")
if PROXY_SIDECAR_IDLE_TIMEOUT < 0:
    raise ValueError("PROXY_SIDECAR_IDLE_TIMEOUT must not be negative")
if PROXY_MAX_HISTORY_TURNS < 1:
    raise ValueError("PROXY_MAX_HISTORY_TURNS must be at least one")

CLIENT_HEADERS = {}

# Advertise the exact WorkBuddy model selected by the proxy.
AVAILABLE_MODELS = load_workbuddy_models() or [
    _model_entry(
        {"id": WORKBUDDY_MODEL, "name": WORKBUDDY_MODEL, "supportsToolCall": True},
        source="fallback",
    )
]


def refresh_available_models() -> list[dict]:
    """Refresh the in-memory catalog so a WorkBuddy UI update is visible immediately."""
    models = load_workbuddy_models()
    if not models:
        models = [
            _model_entry(
                {"id": WORKBUDDY_MODEL, "name": WORKBUDDY_MODEL, "supportsToolCall": True},
                source="fallback",
            )
        ]
    if not any(str(item.get("id") or "").lower() == WORKBUDDY_MODEL.lower() for item in models):
        selected = _model_entry(
            {"id": WORKBUDDY_MODEL, "name": WORKBUDDY_MODEL, "supportsToolCall": True},
            source="selected",
        )
        if selected is not None:
            models.append(selected)
    AVAILABLE_MODELS[:] = [item for item in models if item is not None]
    return AVAILABLE_MODELS

DEFAULT_PORT = int(os.environ.get("PROXY_PORT", "40589"))
DEFAULT_HOST = os.environ.get("PROXY_HOST", "127.0.0.1").strip()
if not 1 <= DEFAULT_PORT <= 65535:
    raise ValueError("PROXY_PORT must be between 1 and 65535")
if not DEFAULT_HOST:
    raise ValueError("PROXY_HOST must not be empty")
