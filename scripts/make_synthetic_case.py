#!/usr/bin/env python3
"""Generate the synthetic CorteX brain MRI and segmentation mask."""

from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np


SHAPE = (160, 192, 160)
ORIGIN = (-80.0, -96.0, -80.0)


def build_synthetic_case(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    x = np.arange(SHAPE[0], dtype=np.float32)[:, None, None] + ORIGIN[0]
    y = np.arange(SHAPE[1], dtype=np.float32)[None, :, None] + ORIGIN[1]
    z = np.arange(SHAPE[2], dtype=np.float32)[None, None, :] + ORIGIN[2]

    brain = (x / 65.0) ** 2 + (y / 80.0) ** 2 + (z / 60.0) ** 2 <= 1.0
    rng = np.random.default_rng(42)
    image = np.zeros(SHAPE, dtype=np.float32)
    noise = rng.normal(0.0, 0.03, size=SHAPE).astype(np.float32)
    image[brain] = 0.55 + noise[brain]

    ventricle_left = (
        ((x + 10.0) / 6.0) ** 2
        + ((y - 5.0) / 22.0) ** 2
        + ((z - 10.0) / 10.0) ** 2
        <= 1.0
    )
    ventricle_right = (
        ((x - 10.0) / 6.0) ** 2
        + ((y - 5.0) / 22.0) ** 2
        + ((z - 10.0) / 10.0) ** 2
        <= 1.0
    )
    image[ventricle_left | ventricle_right] = 0.25

    tumor_distance = np.sqrt(
        (x - 30.0) ** 2 + (y - 35.0) ** 2 + (z - 15.0) ** 2
    )
    non_enhancing_core = tumor_distance <= 9.0
    enhancing_tumor = (tumor_distance > 9.0) & (tumor_distance <= 14.0)
    edema = (tumor_distance > 14.0) & (tumor_distance <= 24.0) & brain

    mask = np.zeros(SHAPE, dtype=np.uint8)
    mask[non_enhancing_core] = 1
    mask[enhancing_tumor] = 3
    mask[edema] = 2
    image[non_enhancing_core] = 0.30
    image[enhancing_tumor] = 1.00
    image[edema] = 0.75

    cavity_distance = np.sqrt(
        (x - 30.0) ** 2 + (y - 12.0) ** 2 + (z - 15.0) ** 2
    )
    resection_cavity = (cavity_distance <= 8.0) & (mask == 0)
    mask[resection_cavity] = 4
    image[resection_cavity] = 0.05

    np.clip(image, 0.0, 1.0, out=image)
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = ORIGIN

    nib.save(nib.Nifti1Image(image.astype(np.float32), affine), out_dir / "image.nii.gz")
    nib.save(nib.Nifti1Image(mask.astype(np.uint8), affine), out_dir / "mask.nii.gz")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build_synthetic_case(args.out)


if __name__ == "__main__":
    main()
