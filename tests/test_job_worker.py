from __future__ import annotations

import importlib


def test_job_worker_module_imports_after_report_refactor() -> None:
    importlib.import_module("pipeline.job_worker")
