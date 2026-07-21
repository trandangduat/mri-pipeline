from __future__ import annotations

from pathlib import Path

from pip._internal.req.constructors import install_req_from_line


def test_requirements_lines_are_valid() -> None:
    for path in (Path("requirements.txt"), Path("requirements-dev.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
                continue
            install_req_from_line(stripped)
