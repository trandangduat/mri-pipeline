use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, State, WindowEvent};

struct BackendSidecar {
    child: Mutex<Option<Child>>,
    api_token: String,
}

#[derive(Debug)]
struct StartupFailure {
    runtime: String,
    missing_components: Vec<String>,
    detail: String,
}

impl BackendSidecar {
    fn start(
        resource_dir: Option<PathBuf>,
        app_dir: Option<PathBuf>,
        api_token: String,
    ) -> Result<(Self, String), std::io::Error> {
        let (child, runtime) = spawn_backend(resource_dir, app_dir, &api_token)?;
        Ok((
            Self {
                child: Mutex::new(Some(child)),
                api_token,
            },
            runtime,
        ))
    }

    fn shutdown(&self) {
        if let Ok(mut child) = self.child.lock() {
            if let Some(mut process) = child.take() {
                let _ = process.kill();
                let _ = process.wait();
            }
        }
    }
}

impl Drop for BackendSidecar {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn is_development_build() -> bool {
    cfg!(debug_assertions) && std::env::var_os("NEUROFLOW_FORCE_BUNDLED_BACKEND").is_none()
}

fn sidecar_owns_backend(is_development: bool) -> bool {
    !is_development
}

fn data_root_for_backend(exe_path: &Path, app_dir: Option<&Path>) -> PathBuf {
    if let Ok(root) = std::env::var("NEUROFLOW_PORTABLE_ROOT") {
        return PathBuf::from(root);
    }
    if let (Ok(main_exe), Some(backend_dir)) = (std::env::current_exe(), exe_path.parent()) {
        // Only the opt-in portable layout keeps the desktop executable beside
        // backend/. Installed bundles keep the executable and resource folder
        // separate, so their mutable data stays in app-data.
        if main_exe.parent() == backend_dir.parent() {
            return backend_dir.parent().unwrap_or(backend_dir).to_path_buf();
        }
    }
    app_dir
        .map(PathBuf::from)
        .or_else(|| exe_path.parent().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn find_backend_exe(resource_dir: &Path) -> Option<PathBuf> {
    let backend_name = backend_executable_name();

    // Check next to the running executable (portable folder layout)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let candidate = exe_dir.join("backend").join(backend_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    // Check in Tauri resource directory
    let candidates = [
        resource_dir.join("backend").join(backend_name),
        resource_dir.join(backend_name),
        resource_dir
            .join("_up_")
            .join("_up_")
            .join("backend")
            .join(backend_name),
    ];
    for candidate in &candidates {
        if candidate.exists() {
            return Some(candidate.clone());
        }
    }
    None
}

fn backend_executable_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "neuroflow-backend.exe"
    } else {
        "neuroflow-backend"
    }
}

fn spawn_backend(
    resource_dir: Option<PathBuf>,
    app_dir: Option<PathBuf>,
    api_token: &str,
) -> Result<(Child, String), std::io::Error> {
    if let Some(ref resources) = resource_dir {
        if let Some(exe_path) = find_backend_exe(resources) {
            return spawn_frozen_backend(exe_path, app_dir.as_deref(), api_token);
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::NotFound,
        "Bundled NeuroFlow backend was not found.",
    ))
}

fn spawn_frozen_backend(
    exe_path: PathBuf,
    app_dir: Option<&Path>,
    api_token: &str,
) -> Result<(Child, String), std::io::Error> {
    let data_root = data_root_for_backend(&exe_path, app_dir);
    let resource_root = pyinstaller_resource_root(&exe_path)?;

    let config_root = data_root.join("config");
    let jobs_root = data_root.join("outputs").join("jobs");
    let license_root = data_root.join("licenses");
    let (stdout, stderr) = backend_log_stdio(&data_root);

    let mut cmd = Command::new(&exe_path);
    cmd.args(["server", "--host", "127.0.0.1", "--port", "8765"])
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env_remove("NEUROFLOW_PORTABLE_ROOT")
        .env("NEUROFLOW_RESOURCE_ROOT", &resource_root)
        .env("NEUROFLOW_DATA_ROOT", &data_root)
        .env("NEUROFLOW_CONFIG_ROOT", &config_root)
        .env("NEUROFLOW_JOBS_ROOT", &jobs_root)
        .env("NEUROFLOW_LICENSE_ROOT", &license_root)
        .env("NEUROFLOW_API_TOKEN", api_token)
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);

    let runtime = exe_path.display().to_string();
    cmd.spawn().map(|child| (child, runtime))
}

/// PyInstaller 6 one-directory bundles put all collected data below
/// ``_internal``.  The sidecar must use that directory as its immutable
/// resource root; using the executable's parent works in source-like folders
/// but loses every packaged atlas/configuration at runtime.
fn pyinstaller_resource_root(exe_path: &Path) -> Result<PathBuf, std::io::Error> {
    let backend_root = exe_path.parent().ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::NotFound,
            "Bundled NeuroFlow backend has no parent directory.",
        )
    })?;
    let resource_root = backend_root.join("_internal");
    if resource_root.is_dir() {
        Ok(resource_root)
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            format!(
                "Bundled NeuroFlow resources are missing: {}",
                resource_root.display()
            ),
        ))
    }
}

fn wait_for_backend_capabilities(api_token: &str) -> Result<(), (Vec<String>, String)> {
    let mut last_error = "The application backend did not answer its health check.".to_string();
    for attempt in 0..20 {
        match backend_capabilities(api_token) {
            Ok(()) => return Ok(()),
            Err((missing, detail)) if !missing.is_empty() => return Err((missing, detail)),
            Err((_, detail)) => last_error = detail,
        }
        if attempt < 19 {
            std::thread::sleep(Duration::from_millis(250));
        }
    }
    Err((Vec::new(), last_error))
}

fn backend_capabilities(api_token: &str) -> Result<(), (Vec<String>, String)> {
    let health = backend_json("/health").map_err(|error| (Vec::new(), error))?;
    if health.get("ok").and_then(|value| value.as_bool()) != Some(true) {
        return Err((
            Vec::new(),
            "The application backend health check did not succeed.".to_string(),
        ));
    }
    let capabilities = backend_json_with_token("/capabilities/runtime", api_token)
        .map_err(|error| (Vec::new(), error))?;
    if capabilities.get("ok").and_then(|value| value.as_bool()) == Some(true) {
        return Ok(());
    }
    let missing = capabilities
        .get("components")
        .and_then(|value| value.as_array())
        .map(|components| {
            components
                .iter()
                .filter(|component| {
                    component.get("ok").and_then(|value| value.as_bool()) != Some(true)
                })
                .filter_map(|component| component.get("label").and_then(|value| value.as_str()))
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    Err((
        missing,
        "Required application backend components are unavailable.".to_string(),
    ))
}

fn backend_json(path: &str) -> Result<serde_json::Value, String> {
    backend_json_request(path, None)
}

fn backend_json_with_token(path: &str, api_token: &str) -> Result<serde_json::Value, String> {
    backend_json_request(path, Some(api_token))
}

fn backend_json_request(path: &str, api_token: Option<&str>) -> Result<serde_json::Value, String> {
    let address = "127.0.0.1:8765".parse().expect("valid loopback address");
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(300))
        .map_err(|error| format!("Cannot reach the application backend: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|error| format!("Cannot configure the application backend connection: {error}"))?;
    stream
        .write_all(
            format!(
                "GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n{}Connection: close\r\n\r\n",
                api_token
                    .map(|token| format!("Authorization: Bearer {token}\r\n"))
                    .unwrap_or_default(),
            )
            .as_bytes(),
        )
        .map_err(|error| format!("Cannot request application backend status: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Cannot read application backend status: {error}"))?;
    let (headers, body) = response
        .split_once("\r\n\r\n")
        .ok_or_else(|| "The application backend returned an invalid response.".to_string())?;
    if !headers.starts_with("HTTP/1.1 200") {
        return Err(format!(
            "The application backend returned {}.",
            headers.lines().next().unwrap_or("an invalid status")
        ));
    }
    serde_json::from_str(body)
        .map_err(|error| format!("The application backend returned invalid status data: {error}"))
}

fn generate_api_token() -> Result<String, std::io::Error> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error.to_string()))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

#[tauri::command]
fn backend_token(sidecar: State<'_, BackendSidecar>) -> String {
    sidecar.api_token.clone()
}

fn startup_failure_message(failure: &StartupFailure) -> (String, String) {
    let title = if failure.missing_components.is_empty() {
        "Backend unavailable"
    } else {
        "Backend diagnostics"
    };
    let components = if failure.missing_components.is_empty() {
        String::new()
    } else {
        format!(
            "\n\nMissing components: {}",
            failure.missing_components.join(", ")
        )
    };
    let remediation = "\n\nRepair or reinstall NeuroFlow, then start the application again.";
    (
        title.to_string(),
        format!(
            "NeuroFlow could not start before its main window was created.\n\nSelected runtime: {}{}\n\n{}{}",
            failure.runtime, components, failure.detail, remediation
        ),
    )
}

fn show_startup_failure(failure: &StartupFailure) {
    let (title, message) = startup_failure_message(failure);
    rfd::MessageDialog::new()
        .set_title(title)
        .set_description(message)
        .set_level(rfd::MessageLevel::Error)
        .show();
}

fn backend_log_stdio(portable_root: &Path) -> (Stdio, Stdio) {
    let log_dir = portable_root.join("logs");
    if fs::create_dir_all(&log_dir).is_err() {
        return (Stdio::null(), Stdio::null());
    }

    let stdout = open_append_log(&log_dir.join("neuroflow-backend.out.log"));
    let stderr = open_append_log(&log_dir.join("neuroflow-backend.err.log"));
    (stdout, stderr)
}

fn open_append_log(path: &Path) -> Stdio {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map(Stdio::from)
        .unwrap_or_else(|_| Stdio::null())
}

#[cfg(test)]
#[allow(clippy::manual_find)]
fn find_resource_backend_root(resources: PathBuf) -> Option<PathBuf> {
    for candidate in [resources.clone(), resources.join("_up_").join("_up_")] {
        if candidate.join("app_backend").exists() && candidate.join("pipeline").exists() {
            return Some(candidate);
        }
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                window.state::<BackendSidecar>().shutdown();
            }
        })
        .setup(|app| {
            if !sidecar_owns_backend(is_development_build()) {
                app.manage(BackendSidecar {
                    child: Mutex::new(None),
                    api_token: String::new(),
                });
                return Ok(());
            }
            let resource_dir = app.path().resource_dir().ok();
            let app_dir = app.path().app_data_dir().ok();
            let api_token = match generate_api_token() {
                Ok(token) => token,
                Err(error) => return Err(error.into()),
            };
            let (sidecar, runtime) = match BackendSidecar::start(resource_dir, app_dir, api_token) {
                Ok(started) => started,
                Err(error) => {
                    let failure = StartupFailure {
                        runtime: "bundled NeuroFlow backend".to_string(),
                        missing_components: Vec::new(),
                        detail: format!("The application backend could not be started: {error}"),
                    };
                    show_startup_failure(&failure);
                    return Err(error.into());
                }
            };
            if let Err((missing_components, detail)) =
                wait_for_backend_capabilities(&sidecar.api_token)
            {
                let failure = StartupFailure {
                    runtime,
                    missing_components,
                    detail,
                };
                show_startup_failure(&failure);
                sidecar.shutdown();
                return Err(std::io::Error::new(std::io::ErrorKind::Other, failure.detail).into());
            }
            app.manage(sidecar);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_token])
        .run(tauri::generate_context!())
        .expect("error while running MRI Pipeline Tauri application");
}

#[cfg(test)]
mod tests {
    use super::{
        backend_executable_name, data_root_for_backend, find_backend_exe,
        find_resource_backend_root, pyinstaller_resource_root, sidecar_owns_backend,
        startup_failure_message, StartupFailure,
    };
    use std::fs;
    use std::path::{Path, PathBuf};

    #[test]
    fn finds_backend_at_resource_root() {
        let resources = test_dir("resource-root");
        create_backend_dirs(&resources);

        let found = find_resource_backend_root(resources.clone());

        assert_eq!(found, Some(resources));
    }

    #[test]
    fn finds_backend_at_tauri_relative_resource_root() {
        let resources = test_dir("relative-resource-root");
        let backend_root = resources.join("_up_").join("_up_");
        create_backend_dirs(&backend_root);

        let found = find_resource_backend_root(resources);

        assert_eq!(found, Some(backend_root));
    }

    #[test]
    fn finds_backend_exe_in_backend_subdir() {
        let resources = test_dir("exe-backend-subdir");
        let backend_dir = resources.join("backend");
        fs::create_dir_all(&backend_dir).unwrap();
        fs::write(backend_dir.join(backend_executable_name()), b"fake").unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, Some(backend_dir.join(backend_executable_name())));
    }

    #[test]
    fn finds_backend_exe_at_resource_root() {
        let resources = test_dir("exe-resource-root");
        fs::create_dir_all(&resources).unwrap();
        fs::write(resources.join(backend_executable_name()), b"fake").unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, Some(resources.join(backend_executable_name())));
    }

    #[test]
    fn returns_none_when_no_backend_exe() {
        let resources = test_dir("no-exe");
        fs::create_dir_all(&resources).unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, None);
    }

    #[test]
    fn portable_layout_uses_sibling_data_directory() {
        let portable = test_dir("portable-root");
        let exe_path = portable.join("backend").join(backend_executable_name());
        fs::create_dir_all(exe_path.parent().unwrap()).unwrap();

        let root = data_root_for_backend(&exe_path, Some(&portable));

        // The test process itself is not inside the portable directory, so an
        // installed layout must still prefer its application-data directory.
        assert_eq!(root, portable);
    }

    #[test]
    fn uses_pyinstaller_internal_directory_for_immutable_resources() {
        let backend_root = test_dir("pyinstaller-internal-root");
        let executable = backend_root.join(backend_executable_name());
        fs::write(&executable, b"fake").unwrap();
        let internal = backend_root.join("_internal");
        fs::create_dir_all(&internal).unwrap();
        fs::write(internal.join("normalize_volumes.py"), b"# bundled").unwrap();

        let root = pyinstaller_resource_root(&executable).unwrap();

        assert_eq!(root, internal);
        assert!(root.join("normalize_volumes.py").is_file());
    }

    #[test]
    fn rejects_backend_layout_without_pyinstaller_internal_resources() {
        let backend_root = test_dir("missing-pyinstaller-internal-root");
        let executable = backend_root.join(backend_executable_name());
        fs::write(&executable, b"fake").unwrap();

        let error = pyinstaller_resource_root(&executable).unwrap_err();

        assert_eq!(error.kind(), std::io::ErrorKind::NotFound);
        assert!(error.to_string().contains("_internal"));
    }

    #[test]
    fn development_build_leaves_backend_to_the_node_launcher() {
        assert!(!sidecar_owns_backend(true));
        assert!(sidecar_owns_backend(false));
    }

    #[test]
    fn packaged_startup_failure_directs_repair_instead_of_python_setup() {
        let failure = StartupFailure {
            runtime: "C:/NeuroFlow/backend/neuroflow-backend.exe".to_string(),
            missing_components: Vec::new(),
            detail: "Cannot reach the application backend.".to_string(),
        };

        let (title, message) = startup_failure_message(&failure);

        assert_eq!(title, "Backend unavailable");
        assert!(message.contains("Repair or reinstall NeuroFlow"));
        assert!(!message.contains("venv"));
    }

    fn test_dir(name: &str) -> PathBuf {
        let path =
            std::env::temp_dir().join(format!("mri-pipeline-tauri-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).expect("failed to create temp test dir");
        path
    }

    fn create_backend_dirs(path: &Path) {
        fs::create_dir_all(path.join("app_backend")).expect("failed to create app_backend dir");
        fs::create_dir_all(path.join("pipeline")).expect("failed to create pipeline dir");
    }
}
