use std::{
    collections::HashMap,
    env, fs,
    io::Write,
    net::IpAddr,
    os::unix::fs::PermissionsExt,
    path::{Path, PathBuf},
};

use serde_json::{Map, Value};
use url::Url;

use crate::{error::ProxyError, models::ModelInfo};

pub const DEFAULT_WORKBUDDY_BASE_URL: &str = "https://work.freemodel.dev/v1";

#[derive(Clone, Debug)]
pub struct Config {
    pub project_root: PathBuf,
    pub config_file: PathBuf,
    pub base_url: String,
    pub api_key: String,
    pub transport: String,
    pub workbuddy_acp_url: String,
    pub workbuddy_acp_password: String,
    pub workbuddy_acp_cwd: PathBuf,
    pub workbuddy_acp_timeout: f64,
    pub workbuddy_acp_max_attempts: usize,
    pub workbuddy_cli_path: PathBuf,
    pub session_store: PathBuf,
    pub runtime_dir: PathBuf,
    pub default_project: PathBuf,
    pub sidecar_startup_timeout: f64,
    pub sidecar_idle_timeout: f64,
    pub max_history_turns: usize,
    pub host: String,
    pub port: u16,
    pub cors_origins: Vec<String>,
    pub proxy_api_key: String,
    pub max_sidecars: usize,
    pub models: Vec<ModelInfo>,
}

impl Config {
    pub fn load(project_root: impl AsRef<Path>) -> Result<Self, ProxyError> {
        Self::load_with_env(project_root, &env::vars().collect())
    }

    pub fn load_with_env(
        project_root: impl AsRef<Path>,
        environment: &HashMap<String, String>,
    ) -> Result<Self, ProxyError> {
        let project_root = project_root.as_ref().to_path_buf();
        let config_file = project_root.join("config.json");
        let saved = read_object(&config_file);
        let get = |name: &str, fallback: Value| -> Value {
            saved
                .get(name)
                .cloned()
                .or_else(|| environment.get(name).map(|v| Value::String(v.clone())))
                .unwrap_or(fallback)
        };
        let text = |name: &str, fallback: &str| -> String {
            value_text(get(name, Value::String(fallback.into())))
        };

        let base_url = text("FREEMODEL_BASE_URL", DEFAULT_WORKBUDDY_BASE_URL)
            .trim()
            .trim_end_matches('/')
            .to_string();
        let protected = is_protected_workbuddy_url(&base_url)?;
        let transport_default = if protected { "workbuddy_acp" } else { "http" };
        let transport = text("FREEMODEL_TRANSPORT", transport_default)
            .trim()
            .to_lowercase();
        if transport != "http" && transport != "workbuddy_acp" {
            return Err(ProxyError::Invalid(format!(
                "Unsupported FREEMODEL_TRANSPORT: {transport}"
            )));
        }
        if protected && transport != "workbuddy_acp" {
            return Err(ProxyError::Invalid(
                "https://work.freemodel.dev requires FREEMODEL_TRANSPORT=workbuddy_acp".into(),
            ));
        }

        let home = environment
            .get("HOME")
            .map(PathBuf::from)
            .or_else(env::home_dir)
            .unwrap_or_else(|| PathBuf::from("."));
        let mut api_key = text("FREEMODEL_API_KEY", "").trim().to_string();
        if api_key.is_empty() {
            let auth = read_object(&home.join(".codex/auth.json"));
            api_key = auth
                .get("FREEMODEL_API_KEY")
                .or_else(|| auth.get("OPENAI_API_KEY"))
                .map(|value| value_text(value.clone()))
                .unwrap_or_default()
                .trim()
                .to_string();
        }
        let acp_cwd = expand_path(
            &text("WORKBUDDY_ACP_CWD", project_root.to_string_lossy().as_ref()),
            &home,
        );
        let startup = parse_f64(
            get("PROXY_SIDECAR_STARTUP_TIMEOUT", Value::from(90.0)),
            "PROXY_SIDECAR_STARTUP_TIMEOUT",
        )?;
        let idle = parse_f64(
            get("PROXY_SIDECAR_IDLE_TIMEOUT", Value::from(900.0)),
            "PROXY_SIDECAR_IDLE_TIMEOUT",
        )?;
        let acp_timeout = parse_f64(
            get("WORKBUDDY_ACP_TIMEOUT", Value::from(180.0)),
            "WORKBUDDY_ACP_TIMEOUT",
        )?;
        let attempts = parse_usize(
            get("WORKBUDDY_ACP_MAX_ATTEMPTS", Value::from(4)),
            "WORKBUDDY_ACP_MAX_ATTEMPTS",
        )?;
        let max_history = parse_usize(
            get("PROXY_MAX_HISTORY_TURNS", Value::from(100)),
            "PROXY_MAX_HISTORY_TURNS",
        )?;
        let max_sidecars = parse_usize(
            get("PROXY_MAX_SIDECARS", Value::from(16)),
            "PROXY_MAX_SIDECARS",
        )?;
        if !startup.is_finite()
            || !acp_timeout.is_finite()
            || !idle.is_finite()
            || startup <= 0.0
            || acp_timeout <= 0.0
            || attempts == 0
            || max_history == 0
            || max_sidecars == 0
            || idle < 0.0
        {
            return Err(ProxyError::Invalid(
                "Timeouts and limits are outside their valid range".into(),
            ));
        }
        let port_raw = text("PROXY_PORT", "40589")
            .parse::<u16>()
            .map_err(|_| ProxyError::Invalid("PROXY_PORT must be between 1 and 65535".into()))?;
        if port_raw == 0 {
            return Err(ProxyError::Invalid(
                "PROXY_PORT must be between 1 and 65535".into(),
            ));
        }
        let host = text("PROXY_HOST", "127.0.0.1").trim().to_string();
        if host.is_empty() {
            return Err(ProxyError::Invalid("PROXY_HOST must not be empty".into()));
        }
        let proxy_api_key = text("PROXY_API_KEY", "").trim().to_string();
        if !is_loopback_host(&host) && proxy_api_key.is_empty() {
            return Err(ProxyError::Invalid(
                "PROXY_API_KEY is required when PROXY_HOST is not loopback".into(),
            ));
        }
        let cors_origins = text("PROXY_CORS_ORIGINS", "http://127.0.0.1,http://localhost")
            .split(',')
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(str::to_string)
            .collect();
        let default_project = canonical_project_path(&expand_path(
            &text(
                "PROXY_DEFAULT_PROJECT",
                project_root.to_string_lossy().as_ref(),
            ),
            &home,
        ))?;
        let configured_cli = text("WORKBUDDY_CLI_PATH", "");
        let workbuddy_cli_path = if configured_cli.trim().is_empty() {
            find_executable_on_path("codebuddy", environment.get("PATH").map(String::as_str))
                .unwrap_or_else(|| PathBuf::from("codebuddy"))
        } else {
            expand_path(configured_cli.trim(), &home)
        };

        Ok(Self {
            project_root: project_root.clone(),
            config_file,
            base_url,
            api_key,
            transport,
            workbuddy_acp_url: text("WORKBUDDY_ACP_URL", "")
                .trim_end_matches('/')
                .to_string(),
            workbuddy_acp_password: text("WORKBUDDY_ACP_PASSWORD", ""),
            workbuddy_acp_cwd: acp_cwd,
            workbuddy_acp_timeout: acp_timeout,
            workbuddy_acp_max_attempts: attempts,
            workbuddy_cli_path,
            session_store: expand_path(
                &text(
                    "PROXY_SESSION_STORE",
                    project_root
                        .join(".proxy-sessions.json")
                        .to_string_lossy()
                        .as_ref(),
                ),
                &home,
            ),
            runtime_dir: expand_path(
                &text(
                    "PROXY_RUNTIME_DIR",
                    project_root
                        .join(".proxy-runtime")
                        .to_string_lossy()
                        .as_ref(),
                ),
                &home,
            ),
            default_project,
            sidecar_startup_timeout: startup,
            sidecar_idle_timeout: idle,
            max_history_turns: max_history,
            host,
            port: port_raw,
            cors_origins,
            proxy_api_key,
            max_sidecars,
            models: available_models(environment, &home),
        })
    }

    pub fn save_api_key(&self, key: &str) -> Result<(), ProxyError> {
        let mut object = read_object(&self.config_file);
        object.insert("FREEMODEL_API_KEY".into(), Value::String(key.trim().into()));
        let bytes =
            serde_json::to_vec_pretty(&object).map_err(|e| ProxyError::Internal(e.to_string()))?;
        let parent = self.config_file.parent().unwrap_or(Path::new("."));
        fs::create_dir_all(parent)
            .map_err(|e| ProxyError::Internal(format!("Unable to create config directory: {e}")))?;
        let mut temp = tempfile::Builder::new()
            .prefix(".workbuddy-config.")
            .tempfile_in(parent)
            .map_err(|e| ProxyError::Internal(format!("Unable to create config file: {e}")))?;
        temp.as_file()
            .set_permissions(fs::Permissions::from_mode(0o600))
            .map_err(|e| ProxyError::Internal(format!("Unable to protect config file: {e}")))?;
        temp.write_all(&bytes)
            .and_then(|_| temp.as_file().sync_all())
            .map_err(|e| ProxyError::Internal(format!("Unable to save API key: {e}")))?;
        temp.persist(&self.config_file)
            .map_err(|e| ProxyError::Internal(format!("Unable to save API key: {}", e.error)))?;
        fs::set_permissions(&self.config_file, fs::Permissions::from_mode(0o600))
            .map_err(|e| ProxyError::Internal(format!("Unable to protect config file: {e}")))
    }
}

pub fn upstream_hostname(base_url: &str) -> Result<String, ProxyError> {
    let parsed = Url::parse(base_url)
        .map_err(|_| ProxyError::Invalid(format!("Invalid FREEMODEL_BASE_URL: {base_url}")))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(ProxyError::Invalid(format!(
            "Invalid FREEMODEL_BASE_URL: {base_url}"
        )));
    }
    parsed
        .host_str()
        .map(|v| v.to_lowercase())
        .ok_or_else(|| ProxyError::Invalid(format!("Invalid FREEMODEL_BASE_URL: {base_url}")))
}

pub fn is_protected_workbuddy_url(base_url: &str) -> Result<bool, ProxyError> {
    Ok(upstream_hostname(base_url)? == "work.freemodel.dev")
}

fn read_object(path: &Path) -> Map<String, Value> {
    fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}
fn value_text(value: Value) -> String {
    value
        .as_str()
        .map(str::to_string)
        .unwrap_or_else(|| value.to_string().trim_matches('"').to_string())
}
fn parse_f64(value: Value, name: &str) -> Result<f64, ProxyError> {
    value_text(value)
        .parse()
        .map_err(|_| ProxyError::Invalid(format!("{name} must be a number")))
}
fn parse_usize(value: Value, name: &str) -> Result<usize, ProxyError> {
    value_text(value)
        .parse()
        .map_err(|_| ProxyError::Invalid(format!("{name} must be a positive integer")))
}
fn expand_path(value: &str, home: &Path) -> PathBuf {
    if value == "~" {
        home.to_path_buf()
    } else if let Some(rest) = value.strip_prefix("~/") {
        home.join(rest)
    } else {
        PathBuf::from(value)
    }
}
fn find_executable_on_path(name: &str, path: Option<&str>) -> Option<PathBuf> {
    env::split_paths(path?)
        .map(|directory| directory.join(name))
        .find(|candidate| {
            candidate
                .metadata()
                .map(|metadata| metadata.is_file() && metadata.permissions().mode() & 0o111 != 0)
                .unwrap_or(false)
        })
}
fn canonical_project_path(path: &Path) -> Result<PathBuf, ProxyError> {
    let canonical = fs::canonicalize(path).map_err(|_| {
        ProxyError::Invalid(format!(
            "PROXY_DEFAULT_PROJECT directory does not exist: {}",
            path.display()
        ))
    })?;
    if !canonical.is_dir() {
        return Err(ProxyError::Invalid(format!(
            "PROXY_DEFAULT_PROJECT is not a directory: {}",
            canonical.display()
        )));
    }
    Ok(canonical)
}

fn is_loopback_host(host: &str) -> bool {
    host.eq_ignore_ascii_case("localhost")
        || host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
}

fn available_models(environment: &HashMap<String, String>, home: &Path) -> Vec<ModelInfo> {
    let mut candidates = Vec::new();
    if let Some(configured) = environment
        .get("WORKBUDDY_RUNTIME_MODEL_CONFIG")
        .filter(|value| !value.trim().is_empty())
    {
        candidates.push(PathBuf::from(configured));
    }
    let runtime_dir = home.join(".workbuddy/local_storage");
    if let Ok(entries) = fs::read_dir(runtime_dir) {
        candidates.extend(entries.filter_map(|entry| {
            let path = entry.ok()?.path();
            let name = path.file_name()?.to_str()?;
            (name.starts_with("wb_entry_") && name.ends_with(".info") && path.is_file())
                .then_some(path)
        }));
    }
    candidates.sort_by_key(|path| {
        std::cmp::Reverse(
            fs::metadata(path)
                .and_then(|metadata| metadata.modified())
                .ok(),
        )
    });

    for path in candidates {
        let Ok(bytes) = fs::read(path) else { continue };
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            continue;
        };
        if let Some(models) = runtime_models(&value)
            && !models.is_empty()
        {
            return models;
        }
    }

    [
        "hy3",
        "deepseek-v4.1-flash",
        "glm-5.3",
        "glm-5.3-flash",
        "glm-5.2",
        "glm-5.1",
        "glm-5v-turbo",
        "minimax-m3",
        "kimi-k3-1",
    ]
    .into_iter()
    .map(|id| model_info(id, 1_785_164_333))
    .collect()
}

fn runtime_models(value: &Value) -> Option<Vec<ModelInfo>> {
    let records = value
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_else(|| std::slice::from_ref(value));
    for record in records {
        let data = record
            .get("data")
            .filter(|value| value.is_object())
            .unwrap_or(record);
        let Some(raw_models) = data.get("models").and_then(Value::as_array) else {
            continue;
        };
        let mut by_id = HashMap::new();
        let mut catalog_ids = Vec::new();
        let mut tool_capable_ids = Vec::new();
        for raw in raw_models {
            let Some(id) = raw.get("id").and_then(Value::as_str).map(str::trim) else {
                continue;
            };
            if id.is_empty() {
                continue;
            }
            let key = id.to_lowercase();
            by_id.entry(key).or_insert(raw);
            catalog_ids.push(id.to_string());
            if raw.get("supportsToolCall").and_then(Value::as_bool) == Some(true) {
                tool_capable_ids.push(id.to_string());
            }
        }

        let mut active_ids = Vec::new();
        let mut active_seen = std::collections::HashSet::new();
        if let Some(agents) = data.get("agents").and_then(Value::as_array) {
            for agent in agents {
                let Some(models) = agent.get("models").and_then(Value::as_array) else {
                    continue;
                };
                for model in models {
                    let Some(id) = model.as_str().map(str::trim) else {
                        continue;
                    };
                    if !id.is_empty() && active_seen.insert(id.to_lowercase()) {
                        active_ids.push(id.to_string());
                    }
                }
            }
        }

        let ordered_ids = if !active_ids.is_empty() {
            let mut ordered = active_ids;
            ordered.extend(
                tool_capable_ids
                    .into_iter()
                    .filter(|id| !active_seen.contains(&id.to_lowercase())),
            );
            ordered
        } else if !tool_capable_ids.is_empty() {
            tool_capable_ids
        } else {
            catalog_ids
        };
        let models = ordered_ids
            .into_iter()
            .map(|id| {
                let raw = by_id.get(&id.to_lowercase()).copied();
                let created = raw
                    .and_then(|value| value.get("created"))
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
                model_info(&id, created)
            })
            .collect::<Vec<_>>();
        if !models.is_empty() {
            return Some(models);
        }
    }
    None
}

fn model_info(id: &str, created: i64) -> ModelInfo {
    ModelInfo {
        id: id.to_string(),
        object: "model".into(),
        created,
        owned_by: "workbuddy".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_protected_host() {
        assert!(is_protected_workbuddy_url("https://work.freemodel.dev/v1").unwrap());
        assert!(!is_protected_workbuddy_url("https://work.freemodel.dev.attacker/v1").unwrap());
    }

    #[test]
    fn runtime_catalog_prefers_active_models_then_adds_tool_capable_models() {
        let root = tempfile::tempdir().unwrap();
        let project = root.path().join("project");
        let home = root.path().join("home");
        let runtime = home.join(".workbuddy/local_storage");
        std::fs::create_dir_all(&runtime).unwrap();
        std::fs::create_dir(&project).unwrap();
        std::fs::write(
            runtime.join("wb_entry_test.info"),
            serde_json::json!({
                "data": {
                    "models": [
                        {"id":"hy3","supportsToolCall":true},
                        {"id":"deepseek-v4.1-flash","supportsToolCall":true},
                        {"id":"hunyuan-image-alpha","supportsToolCall":false}
                    ],
                    "agents": [{"models":["deepseek-v4.1-flash"]}]
                }
            })
            .to_string(),
        )
        .unwrap();
        let environment = HashMap::from([
            ("HOME".into(), home.to_string_lossy().to_string()),
            (
                "PROXY_DEFAULT_PROJECT".into(),
                project.to_string_lossy().to_string(),
            ),
        ]);

        let config = Config::load_with_env(&project, &environment).unwrap();
        let ids = config
            .models
            .iter()
            .map(|model| model.id.as_str())
            .collect::<Vec<_>>();
        assert_eq!(ids, ["deepseek-v4.1-flash", "hy3"]);
    }
}

