use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

struct BackendSidecar {
    child: Mutex<Option<Child>>,
}

impl BackendSidecar {
    fn start(resource_dir: Option<PathBuf>, app_dir: Option<PathBuf>) -> Self {
        let child = match spawn_backend(resource_dir, app_dir) {
            Ok(process) => Some(process),
            Err(error) => {
                eprintln!("Failed to start MRI Pipeline Python backend: {error}");
                None
            }
        };
        Self {
            child: Mutex::new(child),
        }
    }
}

impl Drop for BackendSidecar {
    fn drop(&mut self) {
        if let Ok(mut child) = self.child.lock() {
            if let Some(process) = child.as_mut() {
                let _ = process.kill();
                let _ = process.wait();
            }
        }
    }
}

fn resolve_python(repo_root: &Path) -> PathBuf {
    std::env::var("MRI_PIPELINE_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            let venv_python = if cfg!(target_os = "windows") {
                repo_root.join(".venv").join("Scripts").join("python.exe")
            } else {
                repo_root.join(".venv").join("bin").join("python")
            };
            if venv_python.exists() {
                venv_python
            } else {
                PathBuf::from("python3")
            }
        })
}

fn cleanup_stale_backend(python: &Path, repo_root: &Path) {
    let _ = Command::new(python)
        .args([
            "-m",
            "app_backend.dev_cleanup",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--backend-root",
            repo_root.to_str().unwrap_or("."),
        ])
        .current_dir(repo_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

fn portable_root_from_app_dir(app_dir: &Path) -> PathBuf {
    if let Ok(root) = std::env::var("NEUROFLOW_PORTABLE_ROOT") {
        return PathBuf::from(root);
    }
    app_dir.to_path_buf()
}

fn find_backend_exe(resource_dir: &Path) -> Option<PathBuf> {
    // Check next to the running executable (portable folder layout)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let candidate = exe_dir.join("backend").join("neuroflow-backend.exe");
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    // Check in Tauri resource directory
    let candidates = [
        resource_dir.join("backend").join("neuroflow-backend.exe"),
        resource_dir.join("neuroflow-backend.exe"),
        resource_dir
            .join("_up_")
            .join("_up_")
            .join("backend")
            .join("neuroflow-backend.exe"),
    ];
    for candidate in &candidates {
        if candidate.exists() {
            return Some(candidate.clone());
        }
    }
    None
}

fn spawn_backend(resource_dir: Option<PathBuf>, app_dir: Option<PathBuf>) -> Result<Child, std::io::Error> {
    if let Some(ref resources) = resource_dir {
        if let Some(exe_path) = find_backend_exe(resources) {
            return spawn_frozen_backend(exe_path, app_dir.as_deref());
        }
    }
    spawn_dev_backend(resource_dir)
}

fn spawn_frozen_backend(exe_path: PathBuf, app_dir: Option<&Path>) -> Result<Child, std::io::Error> {
    let portable_root = app_dir
        .map(|d| portable_root_from_app_dir(d))
        .unwrap_or_else(|| {
            exe_path
                .parent()
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("."))
        });

    let config_root = portable_root.join("config");
    let jobs_root = portable_root.join("outputs").join("jobs");
    let license_root = portable_root.join("licenses");

    let mut cmd = Command::new(&exe_path);
    cmd.args(["server", "--host", "127.0.0.1", "--port", "8765"])
        .env("NEUROFLOW_PORTABLE_ROOT", &portable_root)
        .env("NEUROFLOW_CONFIG_ROOT", &config_root)
        .env("NEUROFLOW_JOBS_ROOT", &jobs_root)
        .env("NEUROFLOW_LICENSE_ROOT", &license_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    cmd.spawn()
}

fn spawn_dev_backend(resource_dir: Option<PathBuf>) -> Result<Child, std::io::Error> {
    let repo_root = backend_root(resource_dir);
    let python = resolve_python(&repo_root);
    cleanup_stale_backend(&python, &repo_root);

    Command::new(python)
        .args([
            "-m",
            "app_backend.server",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ])
        .current_dir(&repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
}

fn backend_root(resource_dir: Option<PathBuf>) -> PathBuf {
    if let Ok(root) = std::env::var("MRI_PIPELINE_ROOT") {
        return PathBuf::from(root);
    }
    if let Some(resources) = resource_dir {
        if let Some(candidate) = find_resource_backend_root(resources) {
            return candidate;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

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
        .setup(|app| {
            let resource_dir = app.path().resource_dir().ok();
            let app_dir = app
                .path()
                .app_data_dir()
                .ok()
                .and_then(|d| d.parent().map(PathBuf::from));
            app.manage(BackendSidecar::start(resource_dir, app_dir));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running MRI Pipeline Tauri application");
}

#[cfg(test)]
mod tests {
    use super::{find_backend_exe, find_resource_backend_root};
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
        fs::write(backend_dir.join("neuroflow-backend.exe"), b"fake").unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, Some(backend_dir.join("neuroflow-backend.exe")));
    }

    #[test]
    fn finds_backend_exe_at_resource_root() {
        let resources = test_dir("exe-resource-root");
        fs::create_dir_all(&resources).unwrap();
        fs::write(resources.join("neuroflow-backend.exe"), b"fake").unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, Some(resources.join("neuroflow-backend.exe")));
    }

    #[test]
    fn returns_none_when_no_backend_exe() {
        let resources = test_dir("no-exe");
        fs::create_dir_all(&resources).unwrap();

        let found = find_backend_exe(&resources);

        assert_eq!(found, None);
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
