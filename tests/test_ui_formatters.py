from __future__ import annotations

import pytest
from ui.formatters import truncate_middle, format_duration, format_bytes, format_percent

def test_truncate_middle():
    # Normal case
    assert truncate_middle("hello world", 30) == "hello world"
    assert truncate_middle("a" * 40, 10) == "aaaa...aaa"
    
    # max_len is odd
    assert truncate_middle("a" * 10, 5) == "a...a"
    
    # max_len is very small
    assert truncate_middle("abcdef", 4) == "a..."
    assert truncate_middle("abcdef", 3) == "..."
    
    # max_len is even, half will be (6-3)//2 = 1
    assert truncate_middle("abcdefgh", 6) == "ab...h"

def test_format_duration():
    assert format_duration(None) == ""
    assert format_duration(0) == "0s"
    assert format_duration(-5) == "0s"
    assert format_duration(45) == "45s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3600) == "1h 0m"
    assert format_duration(3665) == "1h 1m"

def test_format_bytes():
    assert format_bytes(None) == ""
    assert format_bytes(0) == "0 MB"
    assert format_bytes(-100) == "0 MB"
    
    # B and KB have no decimal points in the formatter
    assert format_bytes(500) == "500 B"
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(1536) == "2 KB" # round(1.5) is 2 in format string '{.0f}' wait, actually f"{1.5:.0f}" might be "2"
    
    # MB and above have 1 decimal point
    assert format_bytes(1024 * 1024) == "1.0 MB"
    assert format_bytes(1024 * 1024 * 1.5) == "1.5 MB"
    assert format_bytes(1024 * 1024 * 1024 * 2.3) == "2.3 GB"

def test_format_percent():
    assert format_percent(None) == ""
    assert format_percent(0) == "0%"
    assert format_percent(50) == "50%"
    assert format_percent(33.33) == "33%"
    assert format_percent(99.9) == "100%"
