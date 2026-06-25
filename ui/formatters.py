"""Formatting helpers for the MRI Pipeline GUI."""

from __future__ import annotations

def truncate_middle(text: str, max_len: int = 30) -> str:
    if len(text) <= max_len:
        return text
    half = (max_len - 3) // 2
    return text[:half] + "..." + text[-half:]

def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return ""
    seconds = float(seconds)
    if seconds <= 0:
        return "0s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"

def format_bytes(value: int | float | None) -> str:
    if value is None:
        return ""
    value = float(value)
    if value <= 0:
        return "0 MB"
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if idx < 2:
        return f"{value:.0f} {units[idx]}"
    return f"{value:.1f} {units[idx]}"

def format_percent(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.0f}%"
