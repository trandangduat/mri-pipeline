"""Streamlit GUI for the MRI Processing Pipeline.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from pipeline_runner import (
    PipelineConfig,
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    image_exists,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MRI Pipeline",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
.main .block-container { max-width: 1400px; padding-top: 1.5rem; }
.log-box {
    background: #0f172a; color: #e2e8f0; border-radius: 8px;
    padding: 14px 16px; font-family: 'Courier New', monospace; font-size: 12.5px;
    max-height: 420px; overflow-y: auto; white-space: pre-wrap;
    line-height: 1.5; border: 1px solid #1e293b;
}
.log-box .ts { color: #64748b; }
.log-box .running { color: #38bdf8; }
.log-box .success { color: #4ade80; }
.log-box .failed { color: #f87171; }
.log-box .build { color: #fbbf24; }
div[data-testid="stMetric"] {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 10px 14px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

for key, default in [
    ("pipe_log", []),
    ("pipe_build_log", []),
    ("pipe_results", None),
    ("pipe_done", False),
    ("running", False),
    ("progress_pct", 0.0),
    ("current_stage", ""),
    ("step_status", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT = Path(__file__).parent / "pipeline_output"
DEFAULT_WORK = Path(__file__).parent / "pipeline_work"
LICENSE_DIR = Path(__file__).parent / "license"

TOOL_OPTIONS = {
    "reorientation": ["mri_convert", "nibabel"],
    "brain_extraction": ["synthstrip", "hdbet"],
    "segmentation": ["synthseg_freesurfer", "synthseg_standalone", "fastsurfervinn"],
    "bias_correction": ["ants_n4"],
}


def find_mri_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    files = []
    for p in sorted(directory.rglob("*")):
        if p.name.endswith(".nii") or p.name.endswith(".nii.gz") or p.name.endswith(".mgz"):
            files.append(str(p.relative_to(directory)))
    return files


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("MRI Processing Pipeline")
st.caption("Docker-based MRI preprocessing with real-time progress tracking")
st.divider()

# ---------------------------------------------------------------------------
# Main layout: Config (left) + Status (right)
# ---------------------------------------------------------------------------

col_config, col_status = st.columns([2, 1], gap="large")

# --- Left: Configuration ---
with col_config:
    st.subheader("Configuration")

    # Input
    st.markdown("**Input MRI**")
    mri_files = find_mri_files(DATA_DIR)
    input_mode = st.radio("Source", ["Browse data/", "Upload file", "Custom path"], horizontal=True, label_visibility="collapsed")

    input_file = ""
    if input_mode == "Browse data/" and mri_files:
        selected = st.selectbox("File", mri_files, label_visibility="collapsed")
        input_file = str(DATA_DIR / selected) if selected else ""
    elif input_mode == "Upload file":
        uploaded = st.file_uploader("Upload NIfTI", type=["nii", "nii.gz", "mgz"], label_visibility="collapsed")
        if uploaded:
            upload_dir = Path(__file__).parent / "uploads"
            upload_dir.mkdir(exist_ok=True)
            dest = upload_dir / uploaded.name
            dest.write_bytes(uploaded.getvalue())
            input_file = str(dest)
    else:
        input_file = st.text_input("Path", placeholder="/path/to/scan.nii.gz", label_visibility="collapsed")

    # Subject + Device in one row
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Subject ID**")
        subject_id = st.text_input("Subject", value="sub-002", label_visibility="collapsed")
    with c2:
        st.markdown("**Device**")
        device = st.selectbox("Device", ["cpu", "gpu"], label_visibility="collapsed")
    with c3:
        st.markdown("**Threads**")
        threads = st.slider("Threads", 1, 16, 4, label_visibility="collapsed")

    # Output dirs
    st.markdown("**Directories**")
    c1, c2 = st.columns(2)
    with c1:
        output_dir = st.text_input("Output", value=str(DEFAULT_OUTPUT), label_visibility="collapsed")
    with c2:
        work_dir = st.text_input("Work", value=str(DEFAULT_WORK), label_visibility="collapsed")

    # Tool selection
    st.markdown("**Pipeline Tools**")
    selected_tools = {}
    for stage in STAGE_ORDER:
        options = TOOL_OPTIONS.get(stage, [])
        if options:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.caption(STAGE_LABELS[stage])
            with c2:
                choice = st.selectbox(
                    stage,
                    options,
                    index=0,
                    key=f"tool_{stage}",
                    format_func=lambda x: x.replace("_", " ").title(),
                    label_visibility="collapsed",
                )
                selected_tools[stage] = choice

    # License status
    license_exists = (LICENSE_DIR / "license.txt").exists()
    if license_exists:
        st.success("FreeSurfer license found", icon=":material/check_circle:")
    else:
        st.warning("No FreeSurfer license -- some tools will fail", icon=":material/warning:")

    # Docker image status
    with st.expander("Docker Image Status"):
        for stage in STAGE_ORDER:
            tool_key = selected_tools.get(stage)
            if tool_key and tool_key in TOOL_DEFS:
                img = TOOL_DEFS[tool_key]["image"]
                exists = image_exists(img)
                status = "local" if exists else "will pull from Hub"
                st.text(f"  [{status}]  {img}")

# --- Right: Status + Run ---
with col_status:
    st.subheader("Pipeline Status")

    # Run button
    can_run = bool(input_file) and bool(subject_id) and not st.session_state.running
    run_clicked = st.button(
        "Run Pipeline",
        type="primary",
        use_container_width=True,
        disabled=not can_run,
    )

    st.divider()

    # Step status cards
    for stage in STAGE_ORDER:
        tool = selected_tools.get(stage, "--")
        step_st = st.session_state.step_status.get(stage, "pending")
        icon_map = {"pending": "[ ]", "running": "[~]", "success": "[+]", "failed": "[x]"}
        color_map = {"pending": "#94a3b8", "running": "#0ea5e6", "success": "#22c55e", "failed": "#ef4444"}

        icon = icon_map[step_st]
        color = color_map[step_st]
        label = STAGE_LABELS[stage]
        tool_display = tool.replace("_", " ").title()

        st.markdown(
            f'<div style="padding:6px 0;border-left:3px solid {color};padding-left:10px;margin-bottom:4px">'
            f'<span style="font-family:monospace;color:{color}">{icon}</span> '
            f'<strong>{label}</strong><br>'
            f'<span style="font-size:0.85em;color:#64748b">{tool_display}</span></div>',
            unsafe_allow_html=True,
        )

    # Progress
    st.divider()
    progress_bar = st.progress(st.session_state.progress_pct)
    status_ph = st.empty()
    if st.session_state.running:
        status_ph.info(f"Running: {st.session_state.current_stage}")

# ---------------------------------------------------------------------------
# Log section
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Logs")

log_tab, build_tab = st.tabs(["Pipeline", "Docker Build"])

log_ph = log_tab.empty()
build_ph = build_tab.empty()


def render_logs():
    # Pipeline log
    if st.session_state.pipe_log:
        html = ""
        for entry in st.session_state.pipe_log:
            css = entry["status"]
            html += f'<span class="ts">[{entry["ts"]}]</span> <span class="{css}">{entry["status"].upper()} — {entry["msg"]}</span><br>'
        log_ph.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)
    elif not st.session_state.running:
        log_ph.info("No log output yet.")

    # Docker build log
    if st.session_state.pipe_build_log:
        build_text = "\n".join(st.session_state.pipe_build_log)
        build_ph.code(build_text, language="bash")
    elif not st.session_state.running:
        build_ph.info("No Docker build output.")


render_logs()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

if st.session_state.pipe_results:
    st.divider()
    st.subheader("Results")

    # Summary table
    rows = []
    total_build = 0.0
    total_run = 0.0
    for r in st.session_state.pipe_results:
        total_build += r.build_duration_sec
        total_run += r.duration_sec
        rows.append({
            "Stage": STAGE_LABELS[r.stage],
            "Tool": r.tool.replace("_", " ").title(),
            "Status": "OK" if r.success else "FAILED",
            "Build (s)": f"{r.build_duration_sec:.0f}" if r.build_duration_sec > 0 else "-",
            "Run (s)": f"{r.duration_sec:.0f}",
            "Total (s)": f"{r.build_duration_sec + r.duration_sec:.0f}",
        })
    rows.append({
        "Stage": "TOTAL",
        "Tool": "",
        "Status": "",
        "Build (s)": f"{total_build:.0f}",
        "Run (s)": f"{total_run:.0f}",
        "Total (s)": f"{total_build + total_run:.0f}",
    })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Detail per step
    for r in st.session_state.pipe_results:
        status_icon = "+" if r.success else "x"
        time_info = f"run: {r.duration_sec:.0f}s"
        if r.build_duration_sec > 0:
            time_info = f"build: {r.build_duration_sec:.0f}s + run: {r.duration_sec:.0f}s"
        with st.expander(f"[{status_icon}] {STAGE_LABELS[r.stage]} -- {r.tool} ({time_info})", expanded=not r.success):
            if r.success:
                st.success(f"Completed in {r.duration_sec:.0f}s" +
                           (f" (build: {r.build_duration_sec:.0f}s)" if r.build_duration_sec > 0 else ""))
                if r.output_files:
                    for f in r.output_files:
                        st.code(f)
            else:
                st.error(f"Failed: {r.error}")
                if r.log_text:
                    st.code(r.log_text[-1500:])

    # Output files
    if all(r.success for r in st.session_state.pipe_results):
        stats_dir = Path(output_dir) / "stats"
        if stats_dir.exists():
            st.subheader("Output Stats")
            for tsv in sorted(stats_dir.glob("*.tsv")):
                with st.expander(tsv.name):
                    try:
                        lines = tsv.read_text().strip().split("\n")
                        if len(lines) > 1:
                            headers = lines[0].split("\t")
                            data = [dict(zip(headers, l.split("\t"))) for l in lines[1:]]
                            st.dataframe(data, use_container_width=True)
                        else:
                            st.code(lines[0])
                    except Exception as e:
                        st.error(str(e))

        work_path = Path(work_dir)
        if work_path.exists():
            nifti = sorted(work_path.glob("*.nii.gz"))
            if nifti:
                st.subheader("Generated Files")
                for f in nifti:
                    st.code(f"{f.name}  ({f.stat().st_size / 1024 / 1024:.1f} MB)")

# ---------------------------------------------------------------------------
# Pipeline execution (background thread + polling)
# ---------------------------------------------------------------------------

if run_clicked:
    shared = {
        "log": [],
        "build_log": [],
        "results": None,
        "done": False,
        "progress_pct": 0.0,
        "current_stage": "Initializing",
        "step_status": {},
    }

    def _on_progress(stage: str, status: str, pct: float, msg: str):
        shared["log"].append({
            "stage": stage, "status": status, "pct": pct, "msg": msg,
            "ts": time.strftime("%H:%M:%S"),
        })
        shared["progress_pct"] = pct
        shared["current_stage"] = msg
        if status in ("success", "failed", "running"):
            shared["step_status"][stage] = status

    def _on_build_log(line: str):
        shared["build_log"].append(line)

    def _worker():
        config = PipelineConfig(
            input_file=input_file,
            output_dir=output_dir,
            work_dir=work_dir,
            subject_id=subject_id,
            license_dir=str(LICENSE_DIR),
            device=device,
            threads=threads,
            selected_tools=selected_tools,
        )
        results = run_pipeline(config, on_progress=_on_progress, on_build_log=_on_build_log)
        shared["results"] = results
        shared["done"] = True

    threading.Thread(target=_worker, daemon=True).start()

    while not shared["done"]:
        progress_bar.progress(shared["progress_pct"])
        status_ph.info(f"Running: {shared['current_stage']}")

        # Render pipeline log
        if shared["log"]:
            html = ""
            for entry in shared["log"]:
                css = entry["status"]
                html += f'<span class="ts">[{entry["ts"]}]</span> <span class="{css}">{entry["status"].upper()} — {entry["msg"]}</span><br>'
            log_ph.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)

        # Render build log
        if shared["build_log"]:
            build_ph.code("\n".join(shared["build_log"]), language="bash")

        time.sleep(2)

    # Done
    st.session_state.pipe_log = shared["log"]
    st.session_state.pipe_build_log = shared["build_log"]
    st.session_state.pipe_results = shared["results"]
    st.session_state.pipe_done = True
    st.session_state.running = False
    st.session_state.progress_pct = 1.0
    st.session_state.current_stage = "Done"
    st.session_state.step_status = shared["step_status"]

    progress_bar.progress(1.0)
    status_ph.success("Pipeline completed.")
    render_logs()
    st.rerun()
