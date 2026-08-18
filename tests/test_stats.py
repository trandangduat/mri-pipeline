from __future__ import annotations

import csv

from pipeline.config import StatsVectorConfig
from pipeline.stats import StatsGenerator


def test_stats_generator_reads_fastsurfer_aparc_mapped_thickness(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)

    stats_text = "\n".join(
        [
            "# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd",
            "caudalanteriorcingulate 1243 798 1994 2.509 0.871 0.100 0.021 11 1.0",
        ]
    )
    (stats_dir / "lh.aparc.DKTatlas.mapped.stats").write_text(stats_text, encoding="utf-8")

    config = StatsVectorConfig(
        enabled_stats={"cortical_thickness": True},
        atlases={"cortical_thickness": ["aparc"]},
    )
    StatsGenerator(config).generate(str(subject_dir), "subject")

    with open(stats_dir / "vectors" / "cortical_thickness_features.tsv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    values = {row["feature"]: row["value"] for row in rows}
    assert values["lh_caudalanteriorcingulate"] == "2.509"
