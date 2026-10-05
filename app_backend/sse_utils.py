from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

SSEEvent = dict[str, JsonValue]


def step_event(step: str, status: str, detail: str = "", **extra: JsonValue) -> SSEEvent:
    data: dict[str, JsonValue] = {"step": step, "status": status}
    if detail:
        data["detail"] = detail
    data.update(extra)
    return {"event": "step", "data": data}


def complete_event(ok: bool, **kwargs: JsonValue) -> SSEEvent:
    return {"event": "complete", "data": {"ok": ok, **kwargs}}
