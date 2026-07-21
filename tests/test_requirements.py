from __future__ import annotations

from pathlib import Path

from pip._internal.req.constructors import install_req_from_line


def test_requirements_lines_are_valid() -> None:
    for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            install_req_from_line(stripped)
