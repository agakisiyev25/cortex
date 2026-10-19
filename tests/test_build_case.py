from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def make_synthetic(source: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "make_synthetic_case.py"),
            "--out",
            str(source),
        ],
        check=True,
    )


def build_case(source: Path, output: Path) -> dict:
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
    return json.loads((output / "case.json").read_text(encoding="utf-8"))


def test_build_synthetic_case(tmp_path: Path) -> None:
    source = tmp_path / "synthetic"
    output = tmp_path / "case"
    make_synthetic(source)
    case = build_case(source, output)
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

    tumor_slice = output / "slices" / f'{case["landmarks"]["tumor"]:03d}.png'
    pixels = np.asarray(Image.open(tumor_slice).convert("RGB"))
    enhancing_red = (
        (pixels[:, :, 0] > 180)
        & (pixels[:, :, 1] < 120)
        & (pixels[:, :, 2] < 120)
    )
    assert enhancing_red.any()
    assert np.argwhere(enhancing_red)[:, 1].mean() < pixels.shape[1] / 2


def test_mirrored_synthetic_case_is_left_of_brain_midline(tmp_path: Path) -> None:
    source = tmp_path / "synthetic"
    mirrored = tmp_path / "mirrored"
    output = tmp_path / "case"
    make_synthetic(source)
    mirrored.mkdir()

    for filename in ("image.nii.gz", "mask.nii.gz"):
        volume = nib.load(source / filename)
        data = np.asanyarray(volume.dataobj)[::-1].copy()
        affine = volume.affine.copy()
        affine[0, 3] += 500
        nib.save(nib.Nifti1Image(data, affine), mirrored / filename)

    case = build_case(mirrored, output)
    assert case["tumor_side"] == "left"
