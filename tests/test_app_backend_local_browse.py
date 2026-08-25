from __future__ import annotations

import os
from pathlib import Path

from app_backend.local_browse import browse_local_path


def test_browse_local_path_rejects_empty_or_invalid_path() -> None:
    assert browse_local_path({}) == {"ok": False, "error": "path is required"}
    assert browse_local_path({"path": ""}) == {"ok": False, "error": "path is required"}
    assert browse_local_path({"path": "/path/with/\x00/nul"}) == {"ok": False, "error": "Invalid path"}


def test_browse_local_path_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    result = browse_local_path({"path": str(missing)})
    assert result["ok"] is False
    assert "Path not found" in str(result["error"])


def test_browse_local_path_single_nii_dataset(tmp_path: Path) -> None:
    scan1 = tmp_path / "sub-01" / "T1w.nii.gz"
    scan1.parent.mkdir()
    scan1.write_bytes(b"data12345")

    result = browse_local_path({"path": str(tmp_path), "max_depth": 1})
    assert result["ok"] is True
    assert result["image_count"] == 1
    assert result["has_multi_subject_conflict"] is False
    entry = result["entries"][0]
    assert entry["name"] == "T1w.nii.gz"
    assert entry["subject_label"] == "sub-01"
    assert entry["is_dicom_series"] is False
    assert entry["size"] == len(b"data12345")


def test_browse_local_path_dicom_series_as_root(tmp_path: Path) -> None:
    dicom_dir = tmp_path / "dicom_root"
    dicom_dir.mkdir()
    for i in range(1, 6):
        (dicom_dir / f"slice_{i:03d}.dcm").write_bytes(b"slice_payload")

    result = browse_local_path({"path": str(dicom_dir)})
    assert result["ok"] is True
    assert result["image_count"] == 1
    assert result["has_multi_subject_conflict"] is False
    entry = result["entries"][0]
    assert entry["name"] == "dicom_root"
    assert entry["path"] == str(dicom_dir.resolve())
    assert entry["is_dicom_series"] is True
    assert entry["slice_count"] == 5
    assert entry["size"] == 5 * len(b"slice_payload")


def test_browse_local_path_mixed_batch_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    # Subject 1: Single NIfTI volume
    sub1_dir = dataset / "sub-01"
    sub1_dir.mkdir()
    (sub1_dir / "sub-01_T1w.nii.gz").write_bytes(b"nifti_data")

    # Subject 2: DICOM series folder with 10 slices
    sub2_dir = dataset / "sub-02"
    sub2_dir.mkdir()
    for i in range(10):
        (sub2_dir / f"IMG_{i:04d}.dcm").write_bytes(b"dcm_bytes")

    # Subject 3: DICOM series with .ima extension
    sub3_dir = dataset / "sub-03"
    sub3_dir.mkdir()
    for i in range(4):
        (sub3_dir / f"MR.{i}.ima").write_bytes(b"ima_bytes")

    result = browse_local_path({"path": str(dataset), "max_depth": 1})
    assert result["ok"] is True
    assert result["image_count"] == 3
    assert result["has_multi_subject_conflict"] is False

    entries = {e["subject_label"]: e for e in result["entries"]}

    sub1 = entries["sub-01"]
    assert sub1["name"] == "sub-01_T1w.nii.gz"
    assert sub1["is_dicom_series"] is False

    sub2 = entries["sub-02"]
    assert sub2["name"] == "sub-02"
    assert sub2["is_dicom_series"] is True
    assert sub2["slice_count"] == 10
    assert sub2["size"] == 10 * len(b"dcm_bytes")

    sub3 = entries["sub-03"]
    assert sub3["name"] == "sub-03"
    assert sub3["is_dicom_series"] is True
    assert sub3["slice_count"] == 4
    assert sub3["size"] == 4 * len(b"ima_bytes")


def test_browse_local_path_detects_multi_subject_conflict(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    # Subject 1 has 2 volumes: 1 NIfTI and 1 DICOM series
    sub1_dir = dataset / "sub-01"
    sub1_dir.mkdir()
    (sub1_dir / "sub-01_T1w.nii.gz").write_bytes(b"nifti")
    sub1_dcm = sub1_dir / "dicom_series"
    sub1_dcm.mkdir()
    for i in range(3):
        (sub1_dcm / f"slice_{i}.dcm").write_bytes(b"dcm")

    result = browse_local_path({"path": str(dataset), "max_depth": 2})
    assert result["ok"] is True
    assert result["image_count"] == 2
    assert result["has_multi_subject_conflict"] is True


def test_browse_local_path_shallow_mode(tmp_path: Path) -> None:
    folder = tmp_path / "shallow_test"
    folder.mkdir()

    sub_dir = folder / "subdir_a"
    sub_dir.mkdir()

    img_file = folder / "test.nii.gz"
    img_file.write_bytes(b"nii_bytes")

    txt_file = folder / "readme.txt"
    txt_file.write_bytes(b"hello")

    res = browse_local_path({"path": str(folder), "purpose": "browse", "recursive": False})
    assert res["ok"] is True
    assert res["path"] == str(folder.resolve())
    assert len(res["dirs"]) == 1
    assert res["dirs"][0]["name"] == "subdir_a"
    assert res["dirs"][0]["kind"] == "directory"
    assert len(res["files"]) == 2
    filenames = [f["name"] for f in res["files"]]
    assert "test.nii.gz" in filenames
    assert "readme.txt" in filenames
    assert len(res["entries"]) == 3

