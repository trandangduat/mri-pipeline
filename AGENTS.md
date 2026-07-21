# AI Agent Guidelines — MRI Pipeline

This document is the **Ultimate Source of Truth** for any AI agent interacting with the MRI Pipeline codebase. It outlines the architecture, where to make specific changes, coding standards, and how to utilize the available skills. 

Read this before making architectural decisions.

## 1. System Architecture

The project has been aggressively refactored into **Deep Modules** with strict separation of concerns.

### Backend (`pipeline/`)
- `runner.py`: The **Orchestrator**. Contains `run_pipeline` and `run_batch_pipeline`. It orchestrates the order of execution but **never** runs Docker directly. It delegates to executors.
- `executor.py`: The **Execution Interface**. Contains `ExecutionRequest` and `LocalDockerExecutor`. All Docker subprocess calls happen here. This decouples the MRI logic from the OS process logic.
- `registry.py`: The **Tool Registry**. Contains `TOOL_DEFS` (definitions of every Docker image, command args, and inputs/outputs) and `STAGE_ORDER`.
- `presets.py`: Contains configurations for specific execution modes (e.g., FreeSurfer 7 vs. FreeSurfer 8).
- `config.py`: Contains pure DataClasses (`PipelineConfig`, `ExportConfig`, `StatsVectorConfig`).
- `docker_ops.py`: **Image Operations Only**. Handles `ensure_image` (Pull/Build/Remove). It does *not* execute pipeline runs.
- `export.py`: Handles copying or converting (using `mri_convert`) final output files to the export folder.
- `reports.py`: Handles generation of benchmark TSVs, pipeline metrics, and JSON logs.
- `workspace.py`: Handles folder creation, output organization, and file permission repairs.
- `hardware.py`: Queries host CPU, logical cores, and RAM size.
- `stats.py`: Parses FreeSurfer stat files into TSV/CSV files.
- `utils.py`: Pure math and string manipulation helpers (e.g., `_as_number`, `_avg`). 

### Frontend (`ui/`)
- GUI execution relies on `tkinter`.
- Separated into Controller classes (`PipelineController`, `JobsController`) and View components (Tabs).
- App Entrypoint: `python gui.py` (Not `ui/main.py`).

## 2. Where and How to Edit

| Goal | Where to edit | Notes |
|---|---|---|
| **Add a new Docker Tool** | `pipeline/registry.py` | Add to `TOOL_DEFS` and update `STAGE_ORDER` if it introduces a new stage. |
| **Change a Preset (e.g. FS7)** | `pipeline/presets.py` | Modify the corresponding list (e.g., `FREESURFER_7_TOOLS`). |
| **Change Docker Execution Logic** | `pipeline/executor.py` | E.g., Adding GPU memory limit params. Modify `ExecutionRequest` and `LocalDockerExecutor`. |
| **Fix RAM/CPU Detection** | `pipeline/hardware.py` | Any OS-level hardware detection logic goes here. |
| **Change Benchmark Output** | `pipeline/reports.py` | Modify `write_batch_reports` or `_step_metrics_row`. |
| **Add new CLI flags** | `pipeline/cli.py` & `pipeline_runner.py` | Ensure arguments map correctly to `PipelineConfig` |

## 3. Coding Practices & Standards

When writing code, agents **MUST** adhere to the following standards:
1. **Deep Modules**: Do not create "God Objects" or "Kitchen Sink" files (like the old `utils.py`). Group related logic into highly cohesive, specialized modules (like `workspace.py`, `hardware.py`).
2. **Avoid Data Clumps**: Do not pass 7-8 individual primitive variables into a function (Primitive Obsession). Encapsulate them into a DataClass (like `ExecutionRequest`).
3. **No Feature Envy**: If a function mostly reads variables from an object, move that function into the object as a method.
4. **Strict Typing**: All files must use type hints and start with `from __future__ import annotations`.
5. **Robust Imports**: Never use wildcard imports (`from module import *`). Avoid circular imports by keeping data structures (`config.py`) separate from business logic (`runner.py`).

## 4. Skills Usage (For AI Agents)

When operating in this codebase, utilize your provided skills effectively:

- **`code-review`**: Run this skill after ANY major refactoring or feature addition. Instruct it to check for code smells (Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Speculative Generality).
- **`codebase-design`**: Use this when extracting a new module or deciding "where a seam goes". It provides a shared vocabulary for designing clean interfaces.
- **`diagnosing-bugs`**: Use this for complex stack traces or performance regressions (e.g., "Why is FreeSurfer hanging?").
- **`research`**: Delegate to this subagent when you need to read extensive documentation or do deep codebase exploration without cluttering the main conversation context.

## 5. Execution Commands

- **Desktop GUI**: `python3 gui.py` (requires `python3-tk` on Linux).
- **Headless Batch CLI**: `python3 pipeline_runner.py --input-dir <path>`
- **Run Python Syntax Check**: `python3 -m compileall pipeline/ ui/`
- **Linter Check (If flake8 is installed)**: `flake8 pipeline/ ui/ --select=F821,E9`
