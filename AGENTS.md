# AGENTS.md — MRI Pipeline

## Entrypoints

| Entrypoint | Command | When to use |
|---|---|---|
| Tkinter GUI | `python gui.py` | Desktop GUI; needs `python3-tk` on Linux |
| Batch CLI | `python pipeline_runner.py --input-dir <path>` | Headless batch processing |
| Python API | `from pipeline_runner import PipelineConfig, run_pipeline` | Embedding in other scripts |

If `.venv/` or `venv/` exists in the project root, activate it first: `. .venv/bin/activate` and use `python` from there. Else create one, don't install packages globally.

## Pipeline 

Each stage picks a tool from `TOOL_DEFS` (defined at `pipeline_runner.py`). Every tool runs as a **Docker container** via `subprocess`. Docker images come from registries (`mkdayyyy/`, `duattran05/`, `magicianfrog/`). Images are pulled on first use by `ensure_image()` — no manual `docker pull`.

## CLI flags

```bash
python pipeline_runner.py --input-dir <path> --device cpu --threads 4 --resume
```

`--resume` skips completed stages via `pipeline_state.json`. Other flags: `--non-recursive`, `--json-events`, `--ensure-images-only`, `--stop-file <path>`. Each stage also has a tool-override flag (e.g. `--segmentation`, `--brain-extraction`).

## GUI 
- **Theme & Typography**: Uses `sv-ttk` (SunValley theme) with the `Inter` font globally enforced for a modern look.
- **Icons**: Uses 20x20 PNG icons sourced from Icons8 ("iOS Filled" style) (stored in `ui/icons/`). Loaded dynamically via `tk.PhotoImage` in the toolbar.

## Architecture Notes
- **Docker Execution**: `TOOL_DEFS` in `pipeline/config.py` uses `command_builder` instead of Python wrappers inside Docker. Docker commands are constructed on the host via `ToolContext` and run via `bash -c`. No need to rebuild images just to change arguments.
- **Freesurfer Flags**: To run `mri_synthseg` on CPU, the correct flag is `--cpu` (not `--nocpu`).
- **Tool Mapping**: `white_matter_segmentation` stage uses `mri_binarize` instead of `wm_seg`.
