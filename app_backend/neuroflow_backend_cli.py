from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        return _run_server(sys.argv[1:])

    command = sys.argv[1]
    rest = sys.argv[2:]

    if command == "server":
        return _run_server(rest)
    if command == "worker":
        return _run_worker(rest)
    if command == "check":
        return _run_check()

    print(f"Unknown command: {command}", file=sys.stderr)
    print("Usage: neuroflow-backend [server|worker|check] [args...]", file=sys.stderr)
    return 1


def _run_server(argv: list[str]) -> int:
    from app_backend.server import main as server_main

    return server_main(argv)


def _run_worker(argv: list[str]) -> int:
    from pipeline.job_worker import main as worker_main

    return worker_main(argv)


def _run_check() -> int:
    import importlib
    import traceback

    print("=== NeuroFlow Backend Dependency Diagnostics ===")
    failed = False
    for mod, label in [("yaml", "PyYAML"), ("cryptography", "cryptography"), ("paramiko", "Paramiko")]:
        try:
            m = importlib.import_module(mod)
            path = getattr(m, "__file__", "built-in")
            print(f"  [OK] {label} ({mod}) -> {path}")
        except Exception as exc:
            print(f"  [FAIL] {label} ({mod}): {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
