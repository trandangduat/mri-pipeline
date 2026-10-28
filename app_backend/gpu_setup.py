"""GPU preflight events and isolated, explicitly requested repairs."""
from __future__ import annotations

import copy
import secrets
import threading
import time
from dataclasses import dataclass, field

from pipeline.gpu_readiness import check_gpu, failure, gpu_enabled
from app_backend.sse_utils import complete_event, step_event


@dataclass
class Repair:
    state: str = "running"
    phase: str = "checking"
    detail: str = "Checking GPU setup..."
    result: dict = field(default_factory=dict)
    done: threading.Event = field(default_factory=threading.Event)


class GPUSetupService:
    def __init__(self):
        self._lock = threading.Lock()
        self._tickets: dict[str, dict] = {}
        self._running: set[str] = set()

    def register(self, result: dict, request: dict, runner=None) -> dict:
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            now = time.monotonic()
            expired = [key for key, value in self._tickets.items()
                       if now - value["created"] > 3600 and
                       (value["operation"] is None or value["operation"].done.is_set())]
            for key in expired:
                del self._tickets[key]
            if len(self._tickets) >= 128:
                raise RuntimeError("Too many GPU setup sessions. Close old sessions and retry later.")
            self._tickets[ticket] = {
                "created": now, "request": copy.deepcopy(request), "runner": runner,
                "diagnostic": copy.deepcopy(result), "operation": None,
            }
        return {**result, "ticket": ticket}

    def check_events(self, request: dict, runner=None):
        if not gpu_enabled(request):
            return
        stop = threading.Event()
        done = threading.Event()
        outcome = {}
        def check():
            try:
                if runner is None:
                    outcome.update(check_gpu(request, stop))
                else:
                    outcome.update(runner.check_gpu(request, stop))
            except Exception:
                # SSH exceptions may contain authentication material. Transport logs
                # keep their existing redaction; the public result stays generic.
                outcome.update(failure("GPU_SETUP_UNKNOWN", "GPU setup could not be verified on the execution host."))
            finally:
                done.set()
        thread = threading.Thread(target=check, daemon=True)
        yield step_event("gpu", "running", "Checking GPU access in the processing image...")
        thread.start()
        try:
            while not done.wait(0.5):
                yield step_event("gpu", "running", "Checking GPU access in the processing image...")
            if outcome.get("ready"):
                yield step_event("gpu", "done", str(outcome["summary"]))
            else:
                registered = self.register(outcome, request, runner)
                yield step_event("gpu", "failed", str(outcome["summary"]), gpu_solutions=registered)
                yield complete_event(False, error=str(outcome["summary"]))
        finally:
            stop.set()

    def _entry(self, ticket: str) -> dict:
        entry = self._tickets.get(ticket)
        if entry is None or (time.monotonic() - entry["created"] > 3600 and
                             (entry["operation"] is None or entry["operation"].done.is_set())):
            raise ValueError("GPU setup session expired. Run preflight again.")
        return entry

    def status(self, ticket: str) -> dict:
        with self._lock:
            entry = self._entry(ticket)
            operation = entry["operation"]
            if operation is None:
                return {"ok": True, "state": "available"}
            return self._snapshot(operation)

    @staticmethod
    def _snapshot(operation: Repair) -> dict:
        return {
            "ok": operation.state != "failed", "state": operation.state,
            "phase": operation.phase, "detail": operation.detail,
            "complete": operation.done.is_set(), **operation.result,
        }

    def start(self, ticket: str, action: str) -> Repair:
        with self._lock:
            entry = self._entry(ticket)
            if not any(item.get("can_execute") and item.get("action_id") == action
                       for item in entry["diagnostic"].get("solutions", [])):
                raise ValueError("This GPU repair is not available. Follow the setup instructions.")
            if entry["operation"] is not None:
                return entry["operation"]
            target = entry["diagnostic"].get("target", {}).get("fingerprint")
            if not target or target in self._running:
                raise ValueError("Another GPU setup is running on this host. Wait, then run preflight again.")
            operation = Repair()
            entry["operation"] = operation
            self._running.add(target)
            threading.Thread(target=self._run, args=(entry, action, target, operation), daemon=True).start()
            return operation

    def _run(self, entry: dict, action: str, target: str, operation: Repair):
        def emit(item):
            with self._lock:
                operation.phase = str(item.get("phase", "running"))
                operation.detail = str(item.get("detail", ""))[:2000]
        try:
            runner = entry["runner"]
            if runner is None:
                from pipeline.gpu_setup import repair_gpu
                result = repair_gpu(entry["request"], target, action, emit)
            else:
                result = runner.repair_gpu(entry["request"], target, action, emit)
            with self._lock:
                operation.result = result
                operation.state = "repaired" if result.get("ok") else "failed"
                operation.detail = ("GPU check passed. Close this dialog and start the pipeline again."
                                    if result.get("ok") else str(result.get("error", "GPU setup failed."))[:2000])
        except Exception:
            with self._lock:
                operation.state = "failed"
                operation.result = {"ok": False, "error": "GPU setup failed. Run preflight again and follow the remaining instructions."}
                operation.detail = operation.result["error"]
        finally:
            with self._lock:
                self._running.discard(target)
                operation.done.set()

    def stream(self, ticket: str, action: str):
        operation = self.start(ticket, action)
        # The repair runs independently of the HTTP connection. Closing its dialog
        # cannot interrupt dpkg or start an MRI job.
        while not operation.done.is_set():
            with self._lock:
                snapshot = self._snapshot(operation)
            yield {"event": "step", "data": snapshot}
            operation.done.wait(0.5)
        with self._lock:
            snapshot = self._snapshot(operation)
        yield {"event": "complete", "data": snapshot}


SERVICE = GPUSetupService()
