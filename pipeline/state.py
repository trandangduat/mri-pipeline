from __future__ import annotations

import os
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
import logging

from .config import PipelineConfig

log = logging.getLogger(__name__)

@dataclass
class StageResult:
    stage: str
    tool: str
    success: bool
    output_file: str = ""
    outputs_found: list[str] | None = None
    error: str = ""
    duration_sec: float = 0.0

class PipelineTracker:
    def __init__(self, logs_dir: str, config: PipelineConfig, subject_dir: str):
        self.logs_dir = logs_dir
        self.state_file = Path(logs_dir) / "pipeline_state.json"
        
        state = self._load() if config.resume else {}
        if not state:
            state = {
                "version": 2,
                "input_file": os.path.abspath(config.input_file),
                "subject_id": config.subject_id,
                "subject_dir": subject_dir,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "stages": {},
            }
        self.state = state

    def _load(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self) -> None:
        self.state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.state_file)

    def mark_started(self, selected_tools: list[str]) -> None:
        self.state["status"] = "running"
        self.state["selected_tools"] = selected_tools
        self._save()

    def mark_paused(self, after_stage: str = "") -> None:
        self.state["status"] = "PAUSED"
        if after_stage:
            self.state["paused_after_stage"] = after_stage
        self._save()

    def mark_completed(self, success: bool) -> None:
        self.state["status"] = "SUCCESS" if success else "FAILED"
        self.state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._save()



    def mark_stage_running(self, stage: str, tool: str) -> None:
        stages = self.state.setdefault("stages", {})
        s_data = stages.setdefault(stage, {})
        s_data["tool"] = tool
        s_data["status"] = "running"
        s_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def mark_stage_completed(self, result: StageResult) -> None:
        stages = self.state.setdefault("stages", {})
        s_data = stages.setdefault(result.stage, {})
        s_data["tool"] = result.tool
        s_data["status"] = "completed" if result.success else "failed"
        s_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if result.output_file:
            s_data["output_file"] = result.output_file
        if result.outputs_found is not None:
            s_data["output_files_found"] = result.outputs_found
        if result.error:
            s_data["error"] = result.error
        if result.duration_sec > 0:
            s_data["duration_sec"] = result.duration_sec
        self._save()

    def add_exported_outputs(self, stage: str, exported: list[str], error: str = "") -> None:
        stages = self.state.setdefault("stages", {})
        s_data = stages.setdefault(stage, {})
        s_data["exported_outputs"] = exported
        if error:
            s_data["export_error"] = error
        self._save()

    def set_stats_vectors(self, generated: list[str], warnings: list[str]) -> None:
        self.state["stats_vectors"] = {
            "generated": generated,
            "warnings": warnings
        }
        self._save()

    def find_existing_outputs(self, subject_dir: str, possible_names: list[str], possible_globs: list[str] | None = None) -> list[str]:
        found: list[str] = []
        sd = Path(subject_dir)
        for name in possible_names:
            match = None
            for candidate in [sd / "mri" / name, sd / "stats" / name, sd / name]:
                if candidate.exists():
                    match = str(candidate)
                    break
            if match is None:
                matches = list(sd.rglob(name))
                if matches:
                    match = str(matches[0])
            if match and match not in found:
                found.append(match)
        for pattern in possible_globs or []:
            for match in sorted(p for p in sd.rglob(pattern) if p.is_file()):
                path = str(match)
                if path not in found:
                    found.append(path)
        return found

    def resume_output_for_stage(self, subject_dir: str, stage: str, tool_key: str, output_files: list[str], output_globs: list[str] | None = None) -> tuple[str | None, list[str]]:
        stage_state = self.state.get("stages", {}).get(stage, {})
        recorded_outputs = [p for p in stage_state.get("output_files_found", []) if p]
        if stage_state.get("status") == "completed" and stage_state.get("tool") == tool_key and recorded_outputs and all(Path(p).exists() for p in recorded_outputs):
            saved_output = stage_state.get("output_file")
            if saved_output and Path(saved_output).exists():
                return saved_output, recorded_outputs
            return recorded_outputs[0], recorded_outputs

        # Resume after interruption: trust verified files on disk, not only JSON state.
        found_outputs = self.find_existing_outputs(subject_dir, output_files, output_globs)
        return (found_outputs[0], found_outputs) if found_outputs else (None, [])
