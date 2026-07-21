"""Compatibility entrypoint for the MRI pipeline.

Implementation lives under the `pipeline/` package:
- pipeline.config: config dataclasses and callbacks
- pipeline.registry: tool definitions and stage metadata
- pipeline.discovery: subject IDs and MRI input discovery
- pipeline.docker_ops: image preflight and Docker execution
- pipeline.runner: single-file and batch pipeline execution
- pipeline.cli: command-line interface
"""

from __future__ import annotations

import sys

from pipeline.cli import DEFAULT_BATCH_INPUT_DIR, main
from pipeline.config import (
    BatchImageResult,
    BuildLogCallback,
    EXPORT_OUTPUT_ITEMS,
    ExportConfig,
    MetricsCallback,
    PipelineConfig,
    ProgressCallback,
    PROJECT_ROOT,
    STAT_VECTOR_DEFS,
    StatsVectorConfig,
    StepResult,
    ToolContext,
)
from pipeline.docker_ops import build_image, ensure_image, format_image_size, image_exists, image_size_bytes, remove_image
from pipeline.runner import run_batch_pipeline, run_pipeline
from pipeline.registry import (
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    tool_display_name,
    tool_key_from_display,
)
from pipeline.discovery import (
    _derive_subject_id,
    _discover_mri_files,
    _duplicate_basenames,
    _is_supported_mri_input,
    build_subject_id_map,
)
from pipeline.utils import _file_stem
from pipeline.reports import _format_bytes
# Note: state functions are now encapsulated in PipelineTracker


if __name__ == "__main__":
    sys.exit(main())
