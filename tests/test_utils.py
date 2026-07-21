import pytest
from pipeline.utils import (
    _file_stem,
    _safe_container_name,
    _parse_docker_memory,
    _parse_docker_stats_line,
    _avg,
    _median,
    _min,
    _max,
    _number_values
)

def test_file_stem():
    assert _file_stem("scan.nii.gz") == "scan"
    assert _file_stem("scan.nii") == "scan"
    assert _file_stem("my_brain.mgz") == "my_brain"
    assert _file_stem("12345.dcm") == "12345"
    assert _file_stem("unknown_file.txt") == "unknown_file"
    assert _file_stem("no_extension") == "no_extension"

def test_safe_container_name():
    # Should strip invalid chars and keep within limits, adding uuid
    name1 = _safe_container_name("my/bad@name", "part2")
    assert "my-bad-name-part2" in name1
    assert len(name1.split("-")[-1]) == 8  # UUID part
    
    # Should fallback to mri-pipeline if empty after stripping
    name2 = _safe_container_name("___")
    assert name2.startswith("mri-pipeline-")

def test_parse_docker_memory():
    assert _parse_docker_memory("100 B") == 100
    assert _parse_docker_memory("1.5 KB") == 1500
    assert _parse_docker_memory("2.5 MB") == 2500000
    assert _parse_docker_memory("1 GiB") == 1073741824
    assert _parse_docker_memory("10.5 MiB") == int(10.5 * (1024 ** 2))
    assert _parse_docker_memory("invalid") is None
    assert _parse_docker_memory("100") is None # missing unit

def test_parse_docker_stats_line():
    cpu, ram = _parse_docker_stats_line("12.5% | 1.5 GiB / 16 GiB")
    assert cpu == 12.5
    assert ram == int(1.5 * (1024 ** 3))
    
    cpu, ram = _parse_docker_stats_line("-- | --")
    assert cpu is None
    assert ram is None
    
    cpu, ram = _parse_docker_stats_line("0.00% | 0 B / 0 B")
    assert cpu == 0.0
    assert ram == 0

def test_math_utils():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _avg(values) == 3.0
    assert _median(values) == 3.0
    assert _min(values) == 1.0
    assert _max(values) == 5.0
    
    empty = []
    assert _avg(empty) is None
    assert _median(empty) is None
    assert _min(empty) is None
    assert _max(empty) is None

def test_number_values():
    rows = [
        {"val": 10},
        {"val": "20.5"},
        {"val": None},
        {"val": ""},
        {"val": "invalid"},
        {"other": 30} # missing key
    ]
    assert _number_values(rows, "val") == [10.0, 20.5]
