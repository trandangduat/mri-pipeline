use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, WindowEvent};

struct BackendSidecar {
    child: Mutex<Option<Child>>,
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
    ) -> Result<(Self, String), std::io::Error> {
        let (child, runtime) = spawn_backend(resource_dir, app_dir)?;
        Ok((
            Self {
                child: Mutex::new(Some(child)),
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

fn portable_root_for_backend(exe_path: &Path, app_dir: Option<&Path>) -> PathBuf {
    if let Ok(root) = std::env::var("NEUROFLOW_PORTABLE_ROOT") {
        return PathBuf::from(root);
    }
    if let Some(exe_dir) = exe_path.parent() {
        if exe_dir.file_name().and_then(|name| name.to_str()) == Some("backend") {
            if let Some(portable_dir) = exe_dir.parent() {
                return portable_dir.to_path_buf();
            }
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

fn spawn_backend(resource_dir: Option<PathBuf>, app_dir: Option<PathBuf>) -> Result<(Child, String), std::io::Error> {
    if let Some(ref resources) = resource_dir {
        if let Some(exe_path) = find_backend_exe(resources) {
            return spawn_frozen_backend(exe_path, app_dir.as_deref());
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::NotFound,
        "Bundled NeuroFlow backend was not found.",
    ))
}

fn spawn_frozen_backend(exe_path: PathBuf, app_dir: Option<&Path>) -> Result<(Child, String), std::io::Error> {
    let portable_root = portable_root_for_backend(&exe_path, app_dir);

    let config_root = portable_root.join("config");
    let jobs_root = portable_root.join("outputs").join("jobs");
    let license_root = portable_root.join("licenses");
    let (stdout, stderr) = backend_log_stdio(&portable_root);

    let mut cmd = Command::new(&exe_path);
    cmd.args(["server", "--host", "127.0.0.1", "--port", "8765"])
        .env("NEUROFLOW_PORTABLE_ROOT", &portable_root)
        .env("NEUROFLOW_CONFIG_ROOT", &config_root)
        .env("NEUROFLOW_JOBS_ROOT", &jobs_root)
        .env("NEUROFLOW_LICENSE_ROOT", &license_root)
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);

    let runtime = exe_path.display().to_string();
    cmd.spawn().map(|child| (child, runtime))
}

fn wait_for_backend_capabilities() -> Result<(), (Vec<String>, String)> {
    let mut last_error = "The application backend did not answer its health check.".to_string();
    for attempt in 0..20 {
        match backend_capabilities() {
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

fn backend_capabilities() -> Result<(), (Vec<String>, String)> {
    let health = backend_json("/health").map_err(|error| (Vec::new(), error))?;
    if health.get("ok").and_then(|value| value.as_bool()) != Some(true) {
        return Err((Vec::new(), "The application backend health check did not succeed.".to_string()));
    }
    let capabilities = backend_json("/capabilities/runtime").map_err(|error| (Vec::new(), error))?;
    if capabilities.get("ok").and_then(|value| value.as_bool()) == Some(true) {
        return Ok(());
    }
    let missing = capabilities
        .get("components")
        .and_then(|value| value.as_array())
        .map(|components| {
            components
                .iter()
                .filter(|component| component.get("ok").and_then(|value| value.as_bool()) != Some(true))
                .filter_map(|component| component.get("label").and_then(|value| value.as_str()))
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    Err((missing, "Required application backend components are unavailable.".to_string()))
}

fn backend_json(path: &str) -> Result<serde_json::Value, String> {
    let address = "127.0.0.1:8765".parse().expect("valid loopback address");
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(300))
        .map_err(|error| format!("Cannot reach the application backend: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|error| format!("Cannot configure the application backend connection: {error}"))?;
    stream
        .write_all(format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").as_bytes())
        .map_err(|error| format!("Cannot request application backend status: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Cannot read application backend status: {error}"))?;
    let (headers, body) = response
        .split_once("\r\n\r\n")
        .ok_or_else(|| "The application backend returned an invalid response.".to_string())?;
    if !headers.starts_with("HTTP/1.1 200") {
        return Err(format!("The application backend returned {}.", headers.lines().next().unwrap_or("an invalid status")));
    }
    serde_json::from_str(body).map_err(|error| format!("The application backend returned invalid status data: {error}"))
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
        format!("\n\nMissing components: {}", failure.missing_components.join(", "))
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
                });
                return Ok(());
            }
            let resource_dir = app.path().resource_dir().ok();
            let app_dir = app
                .path()
                .app_data_dir()
                .ok()
                .and_then(|d| d.parent().map(PathBuf::from));
            let (sidecar, runtime) = match BackendSidecar::start(
                resource_dir,
                app_dir,
            ) {
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
            if let Err((missing_components, detail)) = wait_for_backend_capabilities() {
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
        .run(tauri::generate_context!())
        .expect("error while running MRI Pipeline Tauri application");
}

#[cfg(test)]
mod tests {
    use super::{
        backend_executable_name, find_backend_exe, find_resource_backend_root,
        portable_root_for_backend, sidecar_owns_backend, startup_failure_message, StartupFailure,
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
    fn portable_root_uses_parent_of_backend_dir() {
        let portable = test_dir("portable-root");
        let exe_path = portable.join("backend").join(backend_executable_name());
        fs::create_dir_all(exe_path.parent().unwrap()).unwrap();

        let root = portable_root_for_backend(&exe_path, Some(Path::new("/tmp/app-data")));

        assert_eq!(root, portable);
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
        let path = std::env::temp_dir().join(format!(
            "mri-pipeline-tauri-{name}-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).expect("failed to create temp test dir");
        path
    }

    fn create_backend_dirs(path: &Path) {
        fs::create_dir_all(path.join("app_backend")).expect("failed to create app_backend dir");
        fs::create_dir_all(path.join("pipeline")).expect("failed to create pipeline dir");
    }
}
