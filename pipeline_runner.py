"""Compatibility entrypoint for the MRI pipeline.

Implementation lives under the `pipeline/` package:
- pipeline.config: tool definitions, config dataclasses, callbacks
- pipeline.utils: subject IDs, output discovery, state/resume helpers
- pipeline.docker_ops: image preflight and Docker execution
- pipeline.runner: single-file and batch pipeline execution
- pipeline.cli: command-line interface
"""

from __future__ import annotations

import sys

from pipeline.cli import DEFAULT_BATCH_INPUT_DIR, main
from pipeline.config import *
from pipeline.docker_ops import build_image, ensure_image, format_image_size, image_exists, image_size_bytes, remove_image
from pipeline.runner import run_batch_pipeline, run_pipeline
from pipeline.utils import *
from pipeline.utils import (
    _derive_subject_id,
    _discover_mri_files,
    _duplicate_basenames,
    _file_stem,
    _format_bytes,
    _is_supported_mri_input,
    _load_pipeline_state,
    _pipeline_state_path,
    _write_pipeline_state,
    build_subject_id_map,
)


if __name__ == "__main__":
    sys.exit(main())
