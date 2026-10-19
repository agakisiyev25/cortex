from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import trimesh


ROOT = Path(__file__).resolve().parents[1]


def test_build_synthetic_case(tmp_path: Path) -> None:
    source = tmp_path / "synthetic"
    output = tmp_path / "case"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "make_synthetic_case.py"),
            "--out",
            str(source),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_case.py"),
            "--image",
            str(source / "image.nii.gz"),
            "--mask",
            str(source / "mask.nii.gz"),
            "--out",
            str(output),
        ],
        check=True,
    )

    case = json.loads((output / "case.json").read_text(encoding="utf-8"))
    assert set(case) == {
        "case_id",
        "source",
        "slices",
        "landmarks",
        "volumes_cm3",
        "structures",
        "model_url",
    }
    png_files = list((output / "slices").glob("*.png"))
    assert case["slices"]["count"] == len(png_files)

    scene = trimesh.load(output / "model.glb")
    assert set(scene.geometry) == {
        "brain",
        "enhancing_tumor",
        "non_enhancing_core",
        "edema",
        "resection_cavity",
    }
    assert all(volume > 0 for volume in case["volumes_cm3"].values())
