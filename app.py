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
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
.main .block-container { max-width: 1200px; padding-top: 1rem; }
.stMetric > div { background: #f0f9ff; border-radius: 12px; padding: 12px; border: 1px solid #bae6fd; }
.log-box {
    background: #1e293b; color: #e2e8f0; border-radius: 8px;
    padding: 16px; font-family: monospace; font-size: 13px;
    max-height: 400px; overflow-y: auto; white-space: pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state init
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


def find_mri_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    files = []
    for p in sorted(directory.rglob("*")):
        if p.name.endswith(".nii") or p.name.endswith(".nii.gz") or p.name.endswith(".mgz"):
            files.append(str(p.relative_to(directory)))
    return files


# ---------------------------------------------------------------------------
# Sidebar — Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://img.icons8.com/color/96/brain.png", width=64)
    st.title("MRI Pipeline")
    st.caption("Configure your MRI processing workflow")

    st.divider()

    # --- Input ---
    st.subheader("📁 Input")
    mri_files = find_mri_files(DATA_DIR)
    input_mode = st.radio("Input source", ["Browse data/", "Upload file", "Custom path"], horizontal=True)

    input_file = ""
    if input_mode == "Browse data/" and mri_files:
        selected = st.selectbox("Select MRI file", mri_files)
        input_file = str(DATA_DIR / selected) if selected else ""
    elif input_mode == "Upload file":
        uploaded = st.file_uploader("Upload NIfTI", type=["nii", "nii.gz", "mgz"])
        if uploaded:
            upload_dir = Path(__file__).parent / "uploads"
            upload_dir.mkdir(exist_ok=True)
            dest = upload_dir / uploaded.name
            dest.write_bytes(uploaded.getvalue())
            input_file = str(dest)
    else:
        input_file = st.text_input("Path to MRI file", placeholder="/path/to/scan.nii.gz")

    # --- Subject ---
    st.subheader("👤 Subject")
    subject_id = st.text_input("Subject ID (BIDS)", value="sub-002", placeholder="sub-001")

    # --- Output ---
    st.subheader("📂 Output")
    output_dir = st.text_input("Output directory", value=str(DEFAULT_OUTPUT))
    work_dir = st.text_input("Work directory", value=str(DEFAULT_WORK))

    # --- Execution ---
    st.subheader("⚙️ Execution")
    device = st.selectbox("Device", ["cpu", "gpu"], index=0)
    threads = st.slider("Threads", 1, 16, 4)

    # --- Tool selection ---
    st.subheader("🔧 Tool Selection")
    tool_options = {
        "reorientation": ["mri_convert", "nibabel"],
        "brain_extraction": ["synthstrip", "hdbet"],
        "segmentation": ["synthseg_freesurfer", "synthseg_standalone", "fastsurfervinn"],
        "bias_correction": ["ants_n4"],
    }

    selected_tools = {}
    for stage in STAGE_ORDER:
        options = tool_options.get(stage, [])
        if options:
            choice = st.selectbox(
                STAGE_LABELS[stage],
                options,
                index=0,
                format_func=lambda x: x.replace("_", " ").title(),
            )
            selected_tools[stage] = choice

    with st.expander("🐳 Docker Image Status"):
        for stage in STAGE_ORDER:
            tool_key = selected_tools.get(stage)
            if tool_key and tool_key in TOOL_DEFS:
                img = TOOL_DEFS[tool_key]["image"]
                exists = image_exists(img)
                st.text(f"{'✅' if exists else '🔨 will auto-build'}  {img}")

    st.divider()

    license_exists = (LICENSE_DIR / "license.txt").exists()
    if license_exists:
        st.success("✅ FreeSurfer license found")
    else:
        st.warning("⚠️ No FreeSurfer license — some tools will fail")

    can_run = bool(input_file) and bool(subject_id) and not st.session_state.running
    run_clicked = st.button(
        "🚀 Run Pipeline",
        type="primary",
        use_container_width=True,
        disabled=not can_run,
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("🧠 MRI Processing Pipeline")
st.caption("Docker-based MRI preprocessing with real-time progress tracking")

# --- Pipeline steps overview ---
st.subheader("Pipeline Steps")
cols = st.columns(len(STAGE_ORDER))
for i, stage in enumerate(STAGE_ORDER):
    with cols[i]:
        tool = selected_tools.get(stage, "—")
        step_st = st.session_state.step_status.get(stage, "pending")
        icon = {"pending": "⏳", "running": "🔄", "success": "✅", "failed": "❌"}[step_st]
        st.metric(
            label=f"{icon} {STAGE_LABELS[stage]}",
            value=tool.replace("_", " ").title(),
        )

# --- Progress bar ---
progress_bar = st.progress(st.session_state.progress_pct)

# --- Status ---
status_ph = st.empty()
if st.session_state.running:
    status_ph.info(f"⏳ Pipeline running... **{st.session_state.current_stage}**")

# --- Log output ---
st.subheader("📋 Execution Log")
log_ph = st.empty()
build_log_ph = st.empty()

def render_log():
    # Main pipeline log
    if st.session_state.pipe_log:
        html = ""
        for entry in st.session_state.pipe_log:
            color = {"running": "#0ea5e6", "success": "#22c55e", "failed": "#ef4444",
                     "build": "#f59e0b"}.get(entry["status"], "#94a3b8")
            html += f'<span style="color:{color}">[{entry["ts"]}] {entry["status"].upper()} — {entry["msg"]}</span><br>'
        log_ph.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)
    elif not st.session_state.running:
        log_ph.info("No log output yet. Configure and run the pipeline.")

    # Docker build log (collapsible)
    if st.session_state.pipe_build_log:
        with build_log_ph.expander("🐳 Docker Build Log", expanded=False):
            build_text = "\n".join(st.session_state.pipe_build_log[-200:])
            st.code(build_text, language="bash")

render_log()

# --- Results ---
if st.session_state.pipe_results:
    st.subheader("Results")

    # Summary table
    summary_data = []
    total_build = 0.0
    total_run = 0.0
    for r in st.session_state.pipe_results:
        total_build += r.build_duration_sec
        total_run += r.duration_sec
        summary_data.append({
            "Stage": STAGE_LABELS[r.stage],
            "Tool": r.tool.replace("_", " ").title(),
            "Status": "✅" if r.success else "❌",
            "Build (s)": f"{r.build_duration_sec:.0f}" if r.build_duration_sec > 0 else "-",
            "Run (s)": f"{r.duration_sec:.0f}",
            "Total (s)": f"{r.build_duration_sec + r.duration_sec:.0f}",
        })
    summary_data.append({
        "Stage": "**TOTAL**",
        "Tool": "",
        "Status": "",
        "Build (s)": f"**{total_build:.0f}**",
        "Run (s)": f"**{total_run:.0f}**",
        "Total (s)": f"**{total_build + total_run:.0f}**",
    })
    st.dataframe(summary_data, use_container_width=True, hide_index=True)

    for r in st.session_state.pipe_results:
        icon = "✅" if r.success else "❌"
        time_info = f"run: {r.duration_sec:.0f}s"
        if r.build_duration_sec > 0:
            time_info = f"build: {r.build_duration_sec:.0f}s + run: {r.duration_sec:.0f}s"
        with st.expander(f"{icon} {STAGE_LABELS[r.stage]} — {r.tool} ({time_info})", expanded=not r.success):
            if r.success:
                st.success(f"Completed in {r.duration_sec:.0f}s" +
                           (f" (build: {r.build_duration_sec:.0f}s)" if r.build_duration_sec > 0 else ""))
                if r.output_files:
                    st.write("**Output files:**")
                    for f in r.output_files:
                        st.code(f)
            else:
                st.error(f"Failed: {r.error}")
                if r.log_text:
                    st.code(r.log_text[-1000:])

    if all(r.success for r in st.session_state.pipe_results):
        stats_dir = Path(output_dir) / "stats"
        if stats_dir.exists():
            st.subheader("📊 Output Stats")
            for tsv in sorted(stats_dir.glob("*.tsv")):
                with st.expander(f"📄 {tsv.name}"):
                    try:
                        lines = tsv.read_text().strip().split("\n")
                        if len(lines) > 1:
                            headers = lines[0].split("\t")
                            rows = [l.split("\t") for l in lines[1:]]
                            st.dataframe([dict(zip(headers, r)) for r in rows], use_container_width=True)
                        else:
                            st.code(lines[0])
                    except Exception as e:
                        st.error(f"Error: {e}")

        work_path = Path(work_dir)
        if work_path.exists():
            nifti = sorted(work_path.glob("*.nii.gz"))
            if nifti:
                st.subheader("🖼️ Generated NIfTI Files")
                for f in nifti:
                    st.code(f"{f.name}  ({f.stat().st_size / 1024 / 1024:.1f} MB)")

# ---------------------------------------------------------------------------
# Pipeline execution (background thread + polling)
# ---------------------------------------------------------------------------

if run_clicked:
    # All shared state lives in a plain dict — safe for background threads
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
        entry = {"stage": stage, "status": status, "pct": pct, "msg": msg,
                 "ts": time.strftime("%H:%M:%S")}
        shared["log"].append(entry)
        shared["progress_pct"] = pct
        shared["current_stage"] = msg
        if status in ("success", "failed"):
            shared["step_status"][stage] = status
        elif status == "running":
            shared["step_status"][stage] = "running"

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

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    # Polling loop: read from shared dict, update Streamlit UI
    while not shared["done"]:
        progress_bar.progress(shared["progress_pct"])
        status_ph.info(f"⏳ Pipeline running... **{shared['current_stage']}**")

        # Render log from shared
        if shared["log"]:
            html = ""
            for entry in shared["log"]:
                color = {"running": "#0ea5e6", "success": "#22c55e", "failed": "#ef4444",
                         "build": "#f59e0b"}.get(entry["status"], "#94a3b8")
                html += f'<span style="color:{color}">[{entry["ts"]}] {entry["status"].upper()} — {entry["msg"]}</span><br>'
            log_ph.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)

        if shared["build_log"]:
            with build_log_ph.expander("🐳 Docker Build Log", expanded=False):
                st.code("\n".join(shared["build_log"][-200:]), language="bash")

        time.sleep(2)

    # Done — copy results into session_state and do final render
    st.session_state.pipe_log = shared["log"]
    st.session_state.pipe_build_log = shared["build_log"]
    st.session_state.pipe_results = shared["results"]
    st.session_state.pipe_done = True
    st.session_state.running = False
    st.session_state.progress_pct = 1.0
    st.session_state.current_stage = "Done"
    st.session_state.step_status = shared["step_status"]

    progress_bar.progress(1.0)
    status_ph.success("✅ Pipeline completed!")
    render_log()
    st.rerun()
