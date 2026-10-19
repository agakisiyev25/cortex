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
        "tumor_side",
        "default_view",
        "mask_source",
        "modality",
        "display_names",
        "colors",
    }
    png_files = list((output / "slices").glob("*.png"))
    assert case["slices"]["count"] == len(png_files)
    assert case["slices"]["count"] <= 160
    assert case["tumor_side"] == "right"
    assert case["default_view"] == {"x": 15, "y": 35}
    assert case["mask_source"] == "CorteX segmentation"
    assert case["modality"] == "T1c"
    assert case["display_names"]["non_enhancing_core"] == "Necrotic core"
    assert case["colors"]["enhancing_tumor"] == "#E0332B"

    scene = trimesh.load(output / "model.glb")
    assert set(scene.geometry) == set(case["structures"])
    assert all(volume > 0 for volume in case["volumes_cm3"].values())
