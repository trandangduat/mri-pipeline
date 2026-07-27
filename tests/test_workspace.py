from __future__ import annotations

from pipeline.workspace import _organize_output


def test_organize_output_preserves_freesurfer_subject_directory(tmp_path) -> None:
    subject_dir = tmp_path / "sub-01"
    freesurfer_mri = subject_dir / "freesurfer" / "sub-01" / "mri"
    freesurfer_stats = subject_dir / "freesurfer" / "sub-01" / "stats"
    freesurfer_mri.mkdir(parents=True)
    freesurfer_stats.mkdir(parents=True)
    orig = freesurfer_mri / "orig.mgz"
    stats = freesurfer_stats / "aseg.stats"
    orig.write_text("mgz", encoding="utf-8")
    stats.write_text("stats", encoding="utf-8")

    _organize_output(str(subject_dir))

    assert orig.exists()
    assert stats.exists()
    assert not (subject_dir / "mri" / "orig.mgz").exists()
    assert not (subject_dir / "stats" / "aseg.stats").exists()
