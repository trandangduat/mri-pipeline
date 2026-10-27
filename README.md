# NeuroFlow

NeuroFlow is a desktop application for MRI processing.
It uses a React interface, a Tauri desktop shell, and a Python backend.
Users can run processing tools locally or on a server through SSH.
The NeuroFLOW scheduler manages task order, resource limits, and job recovery.

## Source code structure

```text
neuroflow-source-20261027/
├── .github/workflows/           Native package workflows
├── app_backend/                Desktop API, configuration, and job control
├── assets/atlases/mni/          Atlas text labels and source references
├── configs/
│   ├── baselines/              Scheduler source fingerprints
│   └── neuroflow/
│       ├── presets/            Pipeline stage definitions
│       └── profiles/           Runtime and memory profiles
├── docker/                     Dockerfiles and processing tool wrappers
├── info/                       Feature names used for statistics output
├── NeuroFLOW-private/          Complete scheduler source folder
│   ├── config/                 Scheduler presets and resource profiles
│   ├── docs/                   Scheduler documentation
│   ├── examples/               Scheduler integration examples
│   ├── experiments/            Experiment definitions and supporting files
│   ├── schemas/                Configuration and result schemas
│   ├── scripts/                Scheduler helper scripts
│   ├── src/neuroflow/          Scheduler library implementation
│   ├── tests/                  Scheduler tests
│   └── pyproject.toml          Scheduler package definition
├── packaging/                  Native build scripts and packaging guides
├── pipeline/                   MRI stages, tool execution, and result handling
├── remote/                     SSH connections, remote jobs, and file transfer
├── scripts/
│   └── build_atlas_release_assets.py
├── tauri-app/
│   ├── scripts/                Desktop development launchers and checks
│   ├── src/                    React interface and application state
│   ├── src-tauri/              Rust shell, native configuration, and icons
│   ├── test/                   Interface tests
│   └── package.json            JavaScript dependencies and commands
├── tests/                      Backend, pipeline, and SSH tests
├── normalize_volumes.py        Volume normalization utility
├── packaging_resources.py      Native package resource selection
├── pipeline_runner.py          Pipeline command entry point
├── requirements.txt            Python application dependencies
├── requirements-dev.txt        Python test dependencies
├── run-gui.bat                 Windows GUI launcher
├── run-gui.ps1                 PowerShell GUI launcher
└── README.md                   Source structure and GUI setup
```

The desktop interface sends requests to `app_backend`.
Local workers execute the stages defined in `pipeline`.
Server jobs use `remote` to transfer files and start workers through SSH.
The scheduler selects tasks and resource allocations.
The pipeline executor starts the selected processing containers.

The archive keeps the scheduler, packaging, desktop application, and test source folders.
Their documents, tests, examples, and helper scripts remain included.
Only `build_atlas_release_assets.py` remains in the root `scripts` folder.
This rule does not remove scripts inside `NeuroFLOW-private` or `tauri-app`.

Local dependency folders, compiled output, caches, MRI scans, and atlas binaries are omitted.
Text labels and feature definitions remain because the application uses them as configuration.

## Requirements

| Component | Requirement |
| --- | --- |
| Python | Python 3.11 or newer |
| Node.js | Node.js 22.12 or newer, with npm |
| Rust | Rust and Cargo, installed through rustup |
| Desktop dependencies | Tauri 2 system dependencies for the selected operating system |
| Local processing | Docker with Linux containers and the required tool images |
| Server processing | An accessible SSH server with Python, Docker, and the required tool images |
| Processing data | Input MRI files or a DICOM series folder |
| Tool licences | A FreeSurfer licence when selected tools require it |

Install the platform dependencies listed in the [Tauri 2 prerequisites](https://v2.tauri.app/start/prerequisites/).

- Windows requires Microsoft C++ Build Tools and WebView2.
- macOS requires Xcode Command Line Tools for desktop development.
- Linux requires the listed WebKitGTK and other system libraries for its distribution.

You can open the GUI without Docker.
Processing jobs require a working local or server execution environment.
Supply omitted atlas assets separately when selected tools require them.

## Setup on Windows

1. Extract the ZIP to a writable folder.
2. Open PowerShell in the extracted `neuroflow-source` folder.
3. Create the Python environment and install the application dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e "./NeuroFLOW-private[simulation]"
```

The scheduler installation supplies YAML and JSON schema support through its `simulation` dependency group.
Installing this group does not run simulations.

4. Install the desktop interface dependencies.

```powershell
cd tauri-app
npm ci
```

5. Start the GUI.

```powershell
npm run tauri dev
```

The first launch compiles the Rust desktop shell.
The launcher also starts the Python backend and the interface development server.
It creates required temporary build folders automatically.
You do not need to start the backend separately.

After setup, `run-gui.bat` or `run-gui.ps1` can start the GUI from the source folder.

## Setup on Linux or macOS

Install the platform dependencies first.
Open a terminal in the extracted `neuroflow-source` folder.

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install -e "./NeuroFLOW-private[simulation]"
cd tauri-app
npm ci
npm run tauri dev
```

Keep the terminal open while using the GUI.
Use Ctrl+C to stop the development session.

## Run a job from the GUI

### Local execution

1. Start Docker and enable Linux containers.
2. Open NeuroFlow and select the local runtime target.
3. Open Tools Configuration and download the required processing images.
4. Select a pipeline preset in Pipeline Configuration.
5. Select one MRI file, a DICOM series folder, or batch input.
6. Select a writable output folder.
7. Select a valid FreeSurfer licence when the chosen tools require it.
8. Set CPU threads, RAM allocation, and available GPU options.
9. Select Start Pipeline and review the startup checks.
10. Open Jobs Monitor to view progress, logs, and results.

Local startup checks use the CPU and RAM available to the Docker engine.
The selected resources must fit the processing profile.

### Server execution through SSH

1. Select the server runtime target.
2. Enter the server address, SSH port, user name, and authentication details.
3. Set the server workspace and Python settings.
4. Connect to the server and check its environment.
5. Use Tools Configuration to check or download the required server images.
6. Select local inputs for upload, or select inputs already on the server.
7. Provide a server staging folder when uploading local inputs.
8. Set the server output folder, pipeline options, resources, and required licence.
9. Select Start Pipeline.
10. Use Jobs Monitor to inspect the job and download results.

Server execution uses the server's processing resources.
The desktop computer still needs the GUI and Python backend dependencies.

## Startup problems

| Problem | Action |
| --- | --- |
| Python imports are missing | Repeat dependency installation with the Python executable inside `.venv`. |
| The application uses an old checkout | Remove environment overrides that point to the old source folder. |
| Rust compilation fails | Check the Tauri system dependencies and installed compiler tools. |
| Docker is unavailable | Start Docker before starting a local processing job. |
| A processing image is missing | Download it through Tools Configuration for the selected runtime target. |
| An atlas asset is missing | Supply the required atlas data separately or select another available atlas. |
| Local resources are insufficient | Adjust the allocation, choose a smaller pipeline, or use server execution. |

Common path overrides include `MRI_PIPELINE_PYTHON`, `NEUROFLOW_RESOURCE_ROOT`, `NEUROFLOW_PORTABLE_ROOT`, and `NEUROFLOW_SOURCE_DIR`.
The development interface normally uses port 1420.
The Python backend normally uses port 8765.

For native installer builds, see [the packaging guide](packaging/README.md) and the platform guides inside `packaging`.
