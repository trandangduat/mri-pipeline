"""Streamlit GUI — batch MRI pipeline, manual path, live container CPU/RAM charts."""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from pipeline_runner import (
    BatchImageResult,
    PipelineConfig,
    STAGE_LABELS,
    STAGE_ORDER,
    StepResult,
    _discover_mri_files,
    _duplicate_basenames,
    _format_bytes,
    build_subject_id_map,
    run_batch_pipeline,
    run_pipeline,
)

st.set_page_config(page_title="MRI Pipeline", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.main .block-container { max-width: 1400px; padding-top: 0.75rem; }
h1 { display: none; }
.log-box {
    background: #0f172a; color: #e2e8f0; border-radius: 6px;
    padding: 10px 12px; font-family: ui-monospace, monospace; font-size: 12px;
    max-height: 280px; overflow-y: auto; white-space: pre-wrap;
    border: 1px solid #1e293b;
}
.log-box .ts { color: #64748b; }
.log-box .running { color: #38bdf8; }
.log-box .success { color: #4ade80; }
.log-box .failed { color: #f87171; }
.stepper {
    display: flex; gap: 0; margin: 12px 0 8px 0; width: 100%;
}
.stepper .step {
    flex: 1; text-align: center; position: relative; padding: 0 4px;
}
.stepper .step::before {
    content: ""; position: absolute; top: 14px; left: -50%; right: 50%;
    height: 2px; background: #e2e8f0; z-index: 0;
}
.stepper .step:first-child::before { display: none; }
.stepper .dot {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%; font-size: 12px; font-weight: 700;
    border: 2px solid #cbd5e1; background: #f8fafc; color: #64748b;
    position: relative; z-index: 1;
}
.stepper .step.pending .dot { border-color: #cbd5e1; background: #f8fafc; color: #94a3b8; }
.stepper .step.running .dot { border-color: #0ea5e9; background: #e0f2fe; color: #0369a1; }
.stepper .step.success .dot { border-color: #22c55e; background: #dcfce7; color: #15803d; }
.stepper .step.failed .dot { border-color: #ef4444; background: #fee2e2; color: #b91c1c; }
.stepper .step.running .dot::after {
    content: ""; position: absolute; inset: -4px; border-radius: 50%;
    border: 2px solid #38bdf8; animation: pulse 1.2s ease infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
.stepper .label {
    display: block; margin-top: 6px; font-size: 0.72rem; color: #475569;
    line-height: 1.2; max-width: 100%; word-wrap: break-word;
}
.stepper .step.running .label { color: #0369a1; font-weight: 600; }
.stepper .step.success .label { color: #15803d; }
.stepper .step.failed .label { color: #b91c1c; }
</style>
""", unsafe_allow_html=True)

PROJECT_ROOT = Path(__file__).parent
DEFAULT_INPUT = PROJECT_ROOT / "data"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs"
LICENSE_DIR = PROJECT_ROOT / "license"
METRICS_NOTE = "CPU/RAM lấy từ `docker stats` của **container pipeline** (không phải tổng máy host)."

_DEFAULTS = {
    "pipe_log": [],
    "pipe_build_log": [],
    "batch_results": None,
    "batch_queue": [],
    "running": False,
    "progress_pct": 0.0,
    "current_stage": "",
    "step_status": {},
    "file_list": [],
    "catalog_root": "",
    "last_recursive": True,
    "metrics_history": [],
    "metrics_container": "",
    "subject_id_map": {},
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

TOOL_OPTIONS = {
    "reorientation": ["mri_convert", "nibabel"],
    "brain_extraction": ["synthstrip", "hdbet"],
    "segmentation": ["synthseg_freesurfer", "synthseg_standalone", "fastsurfervinn"],
    "bias_correction": ["ants_n4"],
    "template_registration": ["synthmorph"],
    "white_matter_segmentation": ["wm_seg"],
}

_STEP_ICONS = {"pending": "○", "running": "●", "success": "✓", "failed": "✗"}


def _chk_key(path: str) -> str:
    return "chk_" + hashlib.md5(path.encode()).hexdigest()[:12]


def display_name(path: str, root: str) -> str:
    try:
        return str(Path(path).relative_to(Path(root).expanduser()))
    except ValueError:
        return Path(path).name


def init_queue(paths: list[str], subject_id_map: dict[str, str] | None = None) -> list[dict]:
    sid_map = subject_id_map or {}
    return [
        {
            "path": p,
            "name": Path(p).name,
            "subject_id": sid_map.get(p, Path(p).stem),
            "status": "pending",
            "duration_sec": None,
            "peak_ram": None,
            "peak_cpu": None,
            "error": "",
        }
        for p in paths
    ]


def update_queue(queue: list[dict], path: str, **kw) -> None:
    for row in queue:
        if row["path"] == path:
            row.update(kw)
            break


def stepper_html(step_status: dict[str, str]) -> str:
    """Horizontal stepper from stage -> status map."""
    parts = ['<div class="stepper">']
    for i, stage in enumerate(STAGE_ORDER, start=1):
        stt = step_status.get(stage, "pending")
        short = STAGE_LABELS[stage].split("&")[0].strip()
        icon = _STEP_ICONS.get(stt, "○")
        parts.append(
            f'<div class="step {stt}">'
            f'<span class="dot">{icon}</span>'
            f'<span class="label">{i}. {short}</span>'
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def stepper_from_results(steps: list[StepResult]) -> str:
    by_stage = {s.stage: s for s in steps}
    status_map = {}
    for stage in STAGE_ORDER:
        if stage in by_stage:
            status_map[stage] = "success" if by_stage[stage].success else "failed"
        else:
            status_map[stage] = "pending"
    return stepper_html(status_map)


def log_html(entries: list[dict], tail: int = 80) -> str:
    lines = []
    for e in entries[-tail:]:
        lines.append(
            f'<span class="ts">[{e["ts"]}]</span> '
            f'<span class="{e.get("status", "")}">{e["status"].upper()} — {e["msg"]}</span>'
        )
    return f'<div class="log-box">{"<br>".join(lines)}</div>' if lines else ""


def queue_rows(queue: list[dict]) -> list[dict]:
    icons = {"pending": "○", "running": "●", "ok": "✓", "failed": "✗"}
    return [
        {
            "#": i,
            "": icons.get(r["status"], "·"),
            "File": r["name"],
            "Output ID": (r.get("subject_id") or "")[:40],
            "Status": r["status"],
            "Time (s)": f"{r['duration_sec']:.0f}" if r.get("duration_sec") else "",
            "Peak RAM": _format_bytes(r.get("peak_ram")) if r.get("peak_ram") else "",
            "Peak CPU": f"{r['peak_cpu']:.0f}%" if r.get("peak_cpu") else "",
            "Error": (r.get("error") or "")[:50],
        }
        for i, r in enumerate(queue, 1)
    ]


def steps_table_rows(steps: list[StepResult]) -> list[dict]:
    rows = []
    for i, s in enumerate(steps, 1):
        rows.append({
            "#": i,
            "Bước": STAGE_LABELS.get(s.stage, s.stage),
            "Tool": s.tool.replace("_", " "),
            "": "✓" if s.success else "✗",
            "Thời gian (s)": f"{s.duration_sec:.0f}",
            "RAM container (peak)": _format_bytes(s.peak_ram_bytes),
            "CPU container (peak)": f"{s.peak_cpu_pct:.0f}%" if s.peak_cpu_pct is not None else "—",
            "Lỗi": s.error or "",
        })
    return rows


def refresh_catalog(input_dir: str, recursive: bool) -> None:
    root = str(Path(input_dir).expanduser())
    files = _discover_mri_files(root, recursive=recursive)
    st.session_state.catalog_root = root
    st.session_state.last_recursive = recursive
    st.session_state.file_list = files
    st.session_state.subject_id_map = build_subject_id_map(files, root) if files else {}
    for p in files:
        key = _chk_key(p)
        if key not in st.session_state:
            st.session_state[key] = True


def checkbox_label(
    path: str, root: str, subject_id_map: dict[str, str], dup_names: set[str],
) -> str:
    rel = display_name(path, root)
    sid = subject_id_map.get(path, "")
    if sid and (Path(path).name in dup_names or sid != Path(path).stem):
        short_sid = sid if len(sid) <= 48 else sid[:45] + "…"
        return f"{rel}  →  {short_sid}"
    return rel


def _metrics_snapshots(history: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Snapshot history once (thread-safe) and build CPU/RAM frames with monotonic x."""
    snap = list(history)
    if not snap:
        return None
    times: list[float] = []
    for i, h in enumerate(snap):
        t = float(h.get("t") or 0.0)
        if i > 0 and t <= times[-1]:
            t = times[-1] + 0.1
        times.append(t)
    cpu_df = pd.DataFrame(
        {"CPU (%)": [float(h.get("cpu") or 0.0) for h in snap]},
        index=pd.Index(times, name="Giây"),
    )
    ram_df = pd.DataFrame(
        {"RAM (MiB)": [float(h.get("ram_mib") or 0.0) for h in snap]},
        index=pd.Index(times, name="Giây"),
    )
    return cpu_df, ram_df


def render_dual_metrics_charts(history: list[dict], placeholder, container_label: str = "") -> None:
    with placeholder.container():
        if container_label:
            st.caption(f"{METRICS_NOTE} Container: `{container_label[:48]}`")
        else:
            st.caption(METRICS_NOTE)
        frames = _metrics_snapshots(history)
        if frames is None:
            st.caption("Biểu đồ cập nhật khi bước pipeline đang chạy trong Docker.")
            return
        cpu_df, ram_df = frames
        cpu_col, ram_col = st.columns(2)
        with cpu_col:
            st.caption("CPU container (%)")
            st.line_chart(cpu_df, height=200)
        with ram_col:
            st.caption("RAM container (MiB)")
            st.line_chart(ram_df, height=200)


def render_run_logs(pipe_log: list, build_log: list, batch_results: list | None) -> None:
    log_pipe, log_docker = st.columns(2)
    with log_pipe:
        st.markdown("**Log pipeline**")
        if pipe_log:
            st.markdown(log_html(pipe_log), unsafe_allow_html=True)
        else:
            st.caption("—")
    with log_docker:
        st.markdown("**Docker build / pull**")
        if build_log:
            st.code("\n".join(build_log[-150:]), language="bash")
        else:
            st.caption("—")
    if batch_results:
        for r in batch_results:
            logs_dir = Path(r.subject_dir) / "logs"
            if not logs_dir.is_dir():
                continue
            log_files = sorted(logs_dir.glob("*.log"))
            if not log_files:
                continue
            st.markdown(f"**Tool logs — {Path(r.input_file).name}**")
            for lf in log_files:
                st.caption(lf.name)
                try:
                    text = lf.read_text(encoding="utf-8", errors="replace")
                    st.code(text[-4000:] if len(text) > 4000 else text, language="text")
                except OSError as e:
                    st.text(str(e))


def render_result_steps(r: BatchImageResult) -> None:
    """Visible stepper + table (no expander)."""
    st.markdown(f"**{Path(r.input_file).name}** — {'thành công' if r.success else 'thất bại'}")
    if r.steps:
        st.markdown(stepper_from_results(r.steps), unsafe_allow_html=True)
        st.dataframe(steps_table_rows(r.steps), use_container_width=True, hide_index=True)
    st.divider()


# ===========================================================================
# 1. Input
# ===========================================================================

st.markdown("**Ảnh input**")

default_root = st.session_state.catalog_root or str(
    DEFAULT_INPUT if DEFAULT_INPUT.exists() else PROJECT_ROOT
)
path_col, rec_col, scan_col = st.columns([5, 1, 1])
with path_col:
    input_dir = st.text_input(
        "Thư mục dataset",
        value=default_root,
        placeholder="C:\\Users\\...\\MRI\\ADNI hoặc /mnt/c/.../data",
        label_visibility="collapsed",
    )
with rec_col:
    recursive = st.checkbox("Đệ quy", value=st.session_state.last_recursive)
with scan_col:
    rescan = st.button("Quét lại", use_container_width=True)

root_path = str(Path(input_dir).expanduser())
if rescan or st.session_state.catalog_root != root_path or st.session_state.last_recursive != recursive:
    refresh_catalog(input_dir, recursive)

file_list: list[str] = st.session_state.file_list
selected_files: list[str] = []

if not file_list:
    st.caption("Không có file .nii / .nii.gz / .mgz — nhập đường dẫn thư mục và bấm **Quét lại**.")
else:
    t_all, t_none, t_info = st.columns([1, 1, 3])
    with t_all:
        if st.button("Chọn tất cả", use_container_width=True, disabled=st.session_state.running):
            for p in file_list:
                st.session_state[_chk_key(p)] = True
            st.rerun()
    with t_none:
        if st.button("Bỏ chọn", use_container_width=True, disabled=st.session_state.running):
            for p in file_list:
                st.session_state[_chk_key(p)] = False
            st.rerun()
    with t_info:
        n_now = sum(1 for p in file_list if st.session_state.get(_chk_key(p), False))
        st.caption(f"{n_now}/{len(file_list)} file · `{root_path}`")

    sid_map = st.session_state.subject_id_map
    dup_names = _duplicate_basenames(file_list)
    if dup_names:
        st.info(
            f"**{len(dup_names)}** tên file trùng nhau (vd. `001.mgz`) — mỗi ảnh dùng **thư mục cha / đường dẫn** "
            f"làm ID output, không ghi đè lẫn nhau."
        )

    list_box = st.container(height=260)
    with list_box:
        for p in file_list:
            label = checkbox_label(p, root_path, sid_map, dup_names)
            if st.checkbox(label, key=_chk_key(p), disabled=st.session_state.running):
                selected_files.append(p)

st.divider()

# ===========================================================================
# 2. Progress
# ===========================================================================

st.markdown("**Tiến độ**")

queue = st.session_state.batch_queue
total = len(queue) if queue else len(selected_files)
done = sum(1 for r in queue if r["status"] in ("ok", "failed")) if queue else 0
pct = st.session_state.progress_pct if st.session_state.running else (done / total if total else 0.0)

p1, p2 = st.columns([3, 1])
with p1:
    st.progress(min(pct, 1.0))
with p2:
    if total:
        st.caption(f"{done}/{total} xong")

if st.session_state.running or st.session_state.step_status:
    st.markdown(stepper_html(st.session_state.step_status), unsafe_allow_html=True)
    if st.session_state.current_stage:
        st.caption(st.session_state.current_stage)

_chart_ph = st.empty()
render_dual_metrics_charts(
    st.session_state.metrics_history,
    _chart_ph,
    st.session_state.metrics_container,
)

if queue:
    st.dataframe(queue_rows(queue), use_container_width=True, hide_index=True)
elif selected_files and not st.session_state.running:
    st.dataframe(
        [{"#": i, "File": Path(p).name, "Status": "chờ chạy"} for i, p in enumerate(selected_files, 1)],
        use_container_width=True,
        hide_index=True,
    )

_log_section = st.empty()

def _render_logs_panel(pipe_log: list, build_log: list, title: str = "Logs") -> None:
    with _log_section.container():
        st.markdown(f"**{title}**")
        log_pipe, log_docker = st.columns(2)
        with log_pipe:
            st.caption("Pipeline")
            if pipe_log:
                st.markdown(log_html(pipe_log), unsafe_allow_html=True)
            else:
                st.caption("—")
        with log_docker:
            st.caption("Docker build / pull")
            if build_log:
                st.code("\n".join(build_log[-120:]), language="bash")
            else:
                st.caption("—")


if not st.session_state.running and not st.session_state.batch_results:
    if st.session_state.pipe_log or st.session_state.pipe_build_log:
        _render_logs_panel(st.session_state.pipe_log, st.session_state.pipe_build_log)

st.divider()

# ===========================================================================
# 3. Results
# ===========================================================================

st.markdown("**Kết quả**")

if st.session_state.batch_results:
    ok = sum(1 for r in st.session_state.batch_results if r.success)
    st.caption(f"{ok}/{len(st.session_state.batch_results)} ảnh thành công")
    st.dataframe(
        [
            {
                "": "✓" if r.success else "✗",
                "File": Path(r.input_file).name,
                "Tổng thời gian (s)": f"{r.duration_sec:.0f}",
                "Output": Path(r.subject_dir).name,
            }
            for r in st.session_state.batch_results
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Các bước pipeline**")
    for r in st.session_state.batch_results:
        render_result_steps(r)

    if st.session_state.metrics_history:
        st.markdown("**Biểu đồ CPU/RAM container (bước cuối)**")
        render_dual_metrics_charts(
            st.session_state.metrics_history,
            st.empty(),
            st.session_state.metrics_container,
        )

    st.markdown("**Logs**")
    render_run_logs(
        st.session_state.pipe_log,
        st.session_state.pipe_build_log,
        st.session_state.batch_results,
    )
else:
    st.caption("—")

_live_prog = st.empty()
_live_chart = st.empty()
_live_queue = st.empty()

# ===========================================================================
# Sidebar
# ===========================================================================

with st.sidebar:
    output_dir = st.text_input("Output", value=str(DEFAULT_OUTPUT))
    device = st.selectbox("Device", ["cpu", "gpu"])
    threads = st.slider("Threads", 1, 16, 4)

    with st.expander("Pipeline tools", expanded=False):
        selected_tools: dict[str, str] = {}
        for stage in STAGE_ORDER:
            opts = TOOL_OPTIONS.get(stage, [])
            if opts:
                selected_tools[stage] = st.selectbox(
                    STAGE_LABELS[stage],
                    opts,
                    format_func=lambda x: x.replace("_", " ").title(),
                    key=f"tool_{stage}",
                )

    if not (LICENSE_DIR / "license.txt").exists():
        st.warning("Thiếu license.txt")

    run_clicked = st.button(
        f"Chạy ({len(selected_files)})",
        type="primary",
        use_container_width=True,
        disabled=len(selected_files) == 0 or st.session_state.running,
    )

# ===========================================================================
# Run
# ===========================================================================

if run_clicked and selected_files:
    st.session_state.running = True
    st.session_state.batch_results = None
    st.session_state.metrics_history = []
    st.session_state.metrics_container = ""
    st.session_state.pipe_log = []
    st.session_state.pipe_build_log = []

    paths = list(selected_files)
    dup_basenames = _duplicate_basenames(paths)
    sid_map = build_subject_id_map(paths, root_path)
    shared: dict = {
        "log": [],
        "build_log": [],
        "batch_results": None,
        "done": False,
        "progress_pct": 0.0,
        "current_stage": "Khởi tạo…",
        "step_status": {s: "pending" for s in STAGE_ORDER},
        "queue": init_queue(paths, sid_map),
        "sid_map": sid_map,
        "dup_basenames": dup_basenames,
        "metrics_history": [],
        "metrics_container": "",
    }

    def _on_progress(stage: str, status: str, pct: float, msg: str):
        shared["log"].append({
            "stage": stage, "status": status, "pct": pct, "msg": msg,
            "ts": time.strftime("%H:%M:%S"),
        })
        if stage == "batch":
            shared["progress_pct"] = pct
        else:
            shared["progress_pct"] = max(shared["progress_pct"], pct)
        shared["current_stage"] = msg
        if status in ("success", "failed", "running") and stage in STAGE_ORDER:
            shared["step_status"][stage] = status

    def _on_build_log(line: str):
        shared["build_log"].append(line)

    def _on_metrics(stage: str, tool: str, cpu, ram, elapsed, container_name: str):
        if container_name:
            shared["metrics_container"] = container_name
        shared["metrics_history"].append({
            "t": round(elapsed, 1),
            "cpu": float(cpu) if cpu is not None else 0.0,
            "ram_mib": (ram / (1024 ** 2)) if ram else 0.0,
            "stage": stage,
        })

    def _on_image_start(input_file: str, idx: int, total: int):
        update_queue(shared["queue"], input_file, status="running")
        shared["step_status"] = {s: "pending" for s in STAGE_ORDER}
        shared["current_stage"] = f"[{idx}/{total}] {Path(input_file).name}"
        shared["metrics_history"] = []
        shared["metrics_container"] = ""

    def _on_image_done(result: BatchImageResult, idx: int, total: int):
        peak_ram = max((s.peak_ram_bytes or 0 for s in result.steps), default=0) or None
        peak_cpu = max((s.peak_cpu_pct or 0 for s in result.steps), default=0) or None
        update_queue(
            shared["queue"],
            result.input_file,
            status="ok" if result.success else "failed",
            duration_sec=result.duration_sec,
            peak_ram=peak_ram,
            peak_cpu=peak_cpu,
            error=result.error,
        )
        shared["progress_pct"] = idx / total if total else 1.0
        shared["current_stage"] = f"[{idx}/{total}] xong — {Path(result.input_file).name}"
        shared["log"].append({
            "stage": "batch",
            "status": "success" if result.success else "failed",
            "pct": shared["progress_pct"],
            "msg": f"{'OK' if result.success else 'FAIL'}: {Path(result.input_file).name}",
            "ts": time.strftime("%H:%M:%S"),
        })

    def _worker():
        if len(paths) == 1:
            config = PipelineConfig(
                input_file=paths[0],
                output_dir=output_dir,
                subject_id=sid_map[paths[0]],
                license_dir=str(LICENSE_DIR),
                device=device,
                threads=threads,
                selected_tools=selected_tools,
            )
            steps = run_pipeline(
                config,
                on_progress=_on_progress,
                on_build_log=_on_build_log,
                on_metrics=_on_metrics,
            )
            ok = bool(steps) and all(s.success for s in steps)
            peak_ram = max((s.peak_ram_bytes or 0 for s in steps), default=0) or None
            peak_cpu = max((s.peak_cpu_pct or 0 for s in steps), default=0) or None
            shared["batch_results"] = [
                BatchImageResult(
                    input_file=paths[0],
                    subject_id=config.subject_id,
                    subject_dir=str(Path(output_dir) / config.subject_id),
                    success=ok,
                    duration_sec=sum(s.duration_sec for s in steps),
                    steps=steps,
                )
            ]
            update_queue(
                shared["queue"], paths[0],
                status="ok" if ok else "failed",
                duration_sec=shared["batch_results"][0].duration_sec,
                peak_ram=peak_ram,
                peak_cpu=peak_cpu,
            )
            shared["progress_pct"] = 1.0
        else:
            shared["batch_results"] = run_batch_pipeline(
                input_dir=root_path,
                output_dir=output_dir,
                license_dir=str(LICENSE_DIR),
                device=device,
                threads=threads,
                selected_tools=selected_tools,
                input_files=paths,
                on_progress=_on_progress,
                on_build_log=_on_build_log,
                on_image_start=_on_image_start,
                on_image_done=_on_image_done,
                on_metrics=_on_metrics,
            )
        shared["done"] = True

    threading.Thread(target=_worker, daemon=True).start()

    while not shared["done"]:
        st.session_state.batch_queue = shared["queue"]
        st.session_state.progress_pct = shared["progress_pct"]
        st.session_state.current_stage = shared["current_stage"]
        st.session_state.step_status = shared["step_status"]
        st.session_state.metrics_history = list(shared["metrics_history"])
        st.session_state.metrics_container = shared["metrics_container"]
        st.session_state.pipe_log = list(shared["log"])
        st.session_state.pipe_build_log = list(shared["build_log"])

        with _live_prog.container():
            st.progress(min(shared["progress_pct"], 1.0))
            st.markdown(stepper_html(shared["step_status"]), unsafe_allow_html=True)
            st.caption(shared["current_stage"])

        render_dual_metrics_charts(
            list(shared["metrics_history"]),
            _live_chart,
            shared["metrics_container"],
        )

        with _live_queue.container():
            st.dataframe(queue_rows(shared["queue"]), use_container_width=True, hide_index=True)

        _render_logs_panel(shared["log"], shared["build_log"], title="Logs (đang chạy)")

        time.sleep(1.0)

    st.session_state.pipe_log = shared["log"]
    st.session_state.pipe_build_log = shared["build_log"]
    st.session_state.batch_results = shared["batch_results"]
    st.session_state.batch_queue = shared["queue"]
    st.session_state.metrics_history = list(shared["metrics_history"])
    st.session_state.metrics_container = shared["metrics_container"]
    st.session_state.running = False
    st.session_state.progress_pct = 1.0
    st.rerun()
