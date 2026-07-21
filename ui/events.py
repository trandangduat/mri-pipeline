from __future__ import annotations

from typing import Callable, Any

class EventEmitter:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event_name: str, callback: Callable) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)

    def off(self, event_name: str, callback: Callable) -> None:
        if event_name in self._listeners:
            try:
                self._listeners[event_name].remove(callback)
            except ValueError:
                pass

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        for callback in self._listeners.get(event_name, []):
            callback(*args, **kwargs)

# Global event bus for the application UI
ui_events = EventEmitter()

# Common Event Names
EVENT_LOG_MESSAGE = "log_message"
EVENT_JOB_STATUS_CHANGED = "job_status_changed"
EVENT_RUN_TARGET_CHANGED = "run_target_changed"
EVENT_VALIDATION_REQUESTED = "validation_requested"
EVENT_IMAGE_RUN_UPDATED = "image_run_updated"
EVENT_PIPELINE_STARTED = "pipeline_started"
EVENT_PIPELINE_STOPPED = "pipeline_stopped"
