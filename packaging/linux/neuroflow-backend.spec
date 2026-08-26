# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for neuroflow-backend on Linux (one-dir mode)."""

import os

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app_backend", "neuroflow_backend_cli.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, "app_backend"), "app_backend"),
        (os.path.join(PROJECT_ROOT, "pipeline"), "pipeline"),
        (os.path.join(PROJECT_ROOT, "remote"), "remote"),
        (os.path.join(PROJECT_ROOT, "configs", "neuroflow"), "configs/neuroflow"),
        (os.path.join(PROJECT_ROOT, "pipeline_runner.py"), "."),
        (os.path.join(PROJECT_ROOT, "requirements.txt"), "."),
    ],
    hiddenimports=[
        "app_backend",
        "app_backend.server",
        "app_backend.config_store",
        "app_backend.environment",
        "app_backend.jobs",
        "app_backend.licenses",
        "app_backend.metadata",
        "app_backend.progress",
        "app_backend.remote",
        "app_backend.run_request",
        "app_backend.tools",
        "app_backend.sse_utils",
        "app_backend.paths",
        "app_backend.neuroflow_backend_cli",
        "pipeline",
        "pipeline.job_worker",
        "pipeline.config",
        "pipeline.jobs",
        "pipeline.runner",
        "pipeline.executor",
        "pipeline.discovery",
        "pipeline.docker_ops",
        "pipeline.export",
        "pipeline.hardware",
        "pipeline.presets",
        "pipeline.registry",
        "pipeline.reports",
        "pipeline.state",
        "pipeline.stats",
        "pipeline.utils",
        "pipeline.workspace",
        "pipeline.neuroflow_adapter",
        "remote",
        "pandas",
        "pandas._libs",
        "pandas._libs.tslibs",
        "paramiko",
        "paramiko.transport",
        "paramiko.ssh_gss",
        "PIL",
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "numpy.testing"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="neuroflow-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="neuroflow-backend",
)
