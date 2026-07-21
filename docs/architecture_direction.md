# Architecture Direction: UI vs. Backend Pipeline Refactoring

## Executive Summary
For the next phase of the application's lifecycle, development efforts should **prioritize refactoring the backend pipeline** (`pipeline/runner.py`, `pipeline/docker_ops.py`) rather than rewriting the `tkinter` UI into strict, self-contained Component-based UI elements.

## 1. UI Refactoring (Low ROI)
The current UI resides in `ui/` (e.g., `gui_jobs.py`, `gui_pipeline.py`, `main.py`) and utilizes an MVC-like controller pattern (`PipelineController`, `JobsController`, etc.).
- **Python/Tkinter Norms:** Tkinter is inherently procedural and tightly couples state (`TkVars`) with widget hierarchies and event callbacks. Attempting to force modern "Component-based" paradigms (like React/Vue) on Tkinter involves heavy boilerplate, fights the framework, and breaks standard Tkinter idioms.
- **ROI & Constraints:** The current MVC structure is already a reasonable and pragmatic abstraction for a Tkinter application. Over-engineering the UI layer without changing the underlying framework (e.g., to PyQt or a web framework) yields very low ROI. It does not meaningfully improve the testability or robustness of the core domain.

## 2. Backend Pipeline Refactoring (High ROI)
The backend pipeline handles the core domain logic, Docker execution, data parsing, and orchestration. Currently, it suffers from shallow modules and tangled responsibilities.
- **Codebase Constraints:** Files like `pipeline/runner.py` (650+ lines), `pipeline/config.py` (650+ lines), and `pipeline/utils.py` (670+ lines) mix OS-level I/O, domain business rules (e.g., Freesurfer metrics extraction), configuration maps, and Docker orchestration. `pipeline/docker_ops.py` performs raw subprocess calls without clear abstraction boundaries.
- **Codebase-Design Principles:** Applying the `codebase-design` principles (designing "deep modules"), the backend urgently needs clear **seams** and **interfaces**. The orchestrator (`runner.py`) should not be coupled directly to Docker subprocess mechanics. 
  - Creating a deep module for execution (with a small interface and a large implementation) would yield high **leverage** for callers (the CLI and API in `pipeline_runner.py`), and high **locality** for maintainers.
  - Introducing proper seams enables the use of **Adapters** (e.g., a `MockExecutor` adapter) to finally make the pipeline testable without requiring Docker or real MRI files.
- **Alignment with `AGENTS.md`:** `AGENTS.md` notes that commands are constructed on the host via `ToolContext`. Abstracting this execution layer into a deep module will fortify headless batch execution modes and make the system much more AI-navigable.

## Conclusion
Pause any deep structural rewrites of the `tkinter` UI. Instead, focus on extracting deep modules out of `pipeline/runner.py` and `pipeline/docker_ops.py` to establish clean seams for tool execution, metric extraction, and state tracking. This will maximize maintainability, testability, and the reliability of both headless and GUI workflows.
