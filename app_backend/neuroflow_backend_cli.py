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

    print(f"Unknown command: {command}", file=sys.stderr)
    print("Usage: neuroflow-backend [server|worker] [args...]", file=sys.stderr)
    return 1


def _run_server(argv: list[str]) -> int:
    from app_backend.server import main as server_main

    return server_main(argv)


def _run_worker(argv: list[str]) -> int:
    from pipeline.job_worker import main as worker_main

    return worker_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
