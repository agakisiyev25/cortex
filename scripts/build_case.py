#!/usr/bin/env python3
"""Build browser-ready CorteX case assets from an MRI and label mask."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from skimage import filters

from meshing import clean_brain_mask, mask_to_mesh


DEFAULT_LABELS = (
    "1:non_enhancing_core,2:edema,3:enhancing_tumor,4:resection_cavity"
)
ALLOWED_STRUCTURES = {
    "non_enhancing_core",
    "edema",
    "enhancing_tumor",
    "resection_cavity",
}
STRUCTURE_ORDER = [
    "enhancing_tumor",
    "non_enhancing_core",
    "edema",
    "resection_cavity",
]
COLORS = {
    "brain": "#C9D2DA",
    "non_enhancing_core": "#F2C200",
    "edema": "#2FA84F",
    "enhancing_tumor": "#E0332B",
    "resection_cavity": "#2F7DE1",
}
DISPLAY_NAMES = {
    "brain": "Brain",
    "non_enhancing_core": "Necrotic core",
    "edema": "Edema",
    "enhancing_tumor": "Enhancing tumor",
    "resection_cavity": "Resection cavity",
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


COLOURS = {name: hex_to_rgb(value) for name, value in COLORS.items()}


def parse_labels(value: str) -> dict[int, str]:
    label_map: dict[int, str] = {}
    try:
        for item in value.split(","):
            number_text, name = item.split(":", 1)
            number = int(number_text)
            if name not in ALLOWED_STRUCTURES:
                raise ValueError(
                    f"unknown structure name {name!r}; allowed names: "
                    + ", ".join(sorted(ALLOWED_STRUCTURES))
                )
            if number in label_map:
                raise ValueError(f"duplicate label number: {number}")
            label_map[number] = name
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "labels must use the format "
            "1:non_enhancing_core,2:edema,3:enhancing_tumor,4:resection_cavity"
        ) from exc
    return label_map


def clean_output(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    slices_dir = out_dir / "slices"
    if slices_dir.exists():
        shutil.rmtree(slices_dir)
    for filename in ("case.json", "model.glb"):
        path = out_dir / filename
        if path.exists():
            path.unlink()


def largest_component(mask: np.ndarray) -> np.ndarray:
    components, count = ndimage.label(mask)
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(components.ravel())
    sizes[0] = 0
    return components == int(np.argmax(sizes))


def load_volume(path: Path) -> nib.Nifti1Image:
    return nib.as_closest_canonical(nib.load(str(path)))


def make_brain_mask(
    image_data: np.ndarray,
    brain_mask_path: Path | None,
    expected_shape: tuple[int, ...],
) -> np.ndarray:
    if brain_mask_path is not None:
        brain_image = load_volume(brain_mask_path)
        brain_data = np.asarray(brain_image.get_fdata())
        if brain_data.shape != expected_shape:
            raise ValueError(
                "brain mask shape does not match image shape: "
                f"{brain_data.shape} != {expected_shape}"
            )
        return brain_data > 0

    if np.count_nonzero(image_data == 0) / image_data.size > 0.10:
        automatic = image_data > 0
    else:
        automatic = image_data > filters.threshold_otsu(image_data)
    return ndimage.binary_fill_holes(largest_component(automatic))


def normalise_image(image_data: np.ndarray) -> np.ndarray:
    non_zero = image_data[image_data != 0]
    if non_zero.size == 0:
        raise ValueError("image contains no non-zero voxels")
    low, high = np.percentile(non_zero, (1, 99))
    if high <= low:
        raise ValueError("image non-zero intensity range is empty after percentile clipping")
    clipped = np.clip(image_data, low, high)
    return ((clipped - low) / (high - low) * 255.0).astype(np.uint8)


def write_slices(
    image_data: np.ndarray,
    mask_data: np.ndarray,
    brain_mask: np.ndarray,
    label_map: dict[int, str],
    voxel_sizes: tuple[float, ...],
    out_dir: Path,
    slice_start: int,
    slice_end: int,
) -> int:
    slices_dir = out_dir / "slices"
    slices_dir.mkdir(parents=True)
    grey = normalise_image(image_data)
    nx, ny, _ = image_data.shape
    brain_projection = np.any(
        brain_mask[:, :, slice_start:slice_end + 1],
        axis=2,
    )
    brain_x, brain_y = np.where(brain_projection)
    crop_width = int(brain_x.max() - brain_x.min() + 1)
    crop_height = int(brain_y.max() - brain_y.min() + 1)
    pad_x = int(np.ceil(crop_width * 0.06))
    pad_y = int(np.ceil(crop_height * 0.06))
    x_start = max(0, int(brain_x.min()) - pad_x)
    x_end = min(nx, int(brain_x.max()) + 1 + pad_x)
    y_start = max(0, int(brain_y.min()) - pad_y)
    y_end = min(ny, int(brain_y.max()) + 1 + pad_y)
    physical_width = (x_end - x_start) * voxel_sizes[0]
    physical_height = (y_end - y_start) * voxel_sizes[1]
    scale = 512.0 / max(physical_width, physical_height)
    output_size = (
        max(1, round(physical_width * scale)),
        max(1, round(physical_height * scale)),
    )
    font = ImageFont.load_default()

    for output_index, k in enumerate(range(slice_start, slice_end + 1), start=1):
        sl = grey[x_start:x_end, y_start:y_end, k]
        segmentation = mask_data[x_start:x_end, y_start:y_end, k]
        disp = np.flipud(sl.T)[:, ::-1]
        mask_disp = np.flipud(segmentation.T)[:, ::-1]
        rgb = np.repeat(disp[:, :, None], 3, axis=2).astype(np.float32)
        for label, name in label_map.items():
            selected = mask_disp == label
            if selected.any():
                colour = np.asarray(COLOURS[name], dtype=np.float32)
                rgb[selected] = rgb[selected] * 0.60 + colour * 0.40
                outline = selected & ~ndimage.binary_erosion(selected)
                rgb[outline] = colour

        image = Image.fromarray(np.rint(rgb).astype(np.uint8), mode="RGB")
        image = image.resize(output_size, Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        right_bounds = draw.textbbox((0, 0), "R", font=font)
        text_height = right_bounds[3] - right_bounds[1]
        draw.text(
            (12, (image.height - text_height) / 2 - right_bounds[1]),
            "R",
            fill=(255, 255, 255),
            font=font,
        )
        left_bounds = draw.textbbox((0, 0), "L", font=font)
        text_width = left_bounds[2] - left_bounds[0]
        text_height = left_bounds[3] - left_bounds[1]
        draw.text(
            (
                image.width - 12 - text_width - left_bounds[0],
                (image.height - text_height) / 2 - left_bounds[1],
            ),
            "L",
            fill=(255, 255, 255),
            font=font,
        )
        image.save(slices_dir / f"{output_index:03d}.png")
    return slice_end - slice_start + 1


def largest_area_slice(mask: np.ndarray, labels: list[int]) -> int | None:
    if not labels:
        return None
    areas = np.count_nonzero(np.isin(mask, labels), axis=(0, 1))
    if int(areas.max()) == 0:
        return None
    return int(np.argmax(areas)) + 1


def compute_landmarks(
    mask_data: np.ndarray,
    brain_mask: np.ndarray,
    label_map: dict[int, str],
    slice_start: int,
) -> dict[str, int]:
    labels_by_name = {name: label for label, name in label_map.items()}
    brain_slices = np.flatnonzero(np.any(brain_mask, axis=(0, 1)))
    if brain_slices.size == 0:
        raise ValueError("brain mask is empty")
    mid_brain = int((brain_slices[0] + brain_slices[-1]) // 2) + 1 - slice_start

    tumor_labels = [
        labels_by_name[name]
        for name in ("enhancing_tumor", "non_enhancing_core")
        if name in labels_by_name
    ]
    tumor = largest_area_slice(mask_data, tumor_labels)
    if tumor is not None:
        tumor -= slice_start
    if tumor is None and "edema" in labels_by_name:
        tumor = largest_area_slice(mask_data, [labels_by_name["edema"]])
        if tumor is not None:
            tumor -= slice_start
    if tumor is None:
        tumor = mid_brain

    non_cavity_labels = [
        label for label, name in label_map.items() if name != "resection_cavity"
    ]
    tumor_extent = np.flatnonzero(
        np.any(np.isin(mask_data, non_cavity_labels), axis=(0, 1))
    )
    if tumor_extent.size:
        tumor_bottom = int(tumor_extent[0]) + 1 - slice_start
        tumor_top = int(tumor_extent[-1]) + 1 - slice_start
    else:
        tumor_bottom = tumor
        tumor_top = tumor

    landmarks = {
        "tumor": tumor,
        "tumor_top": tumor_top,
        "tumor_bottom": tumor_bottom,
        "mid_brain": mid_brain,
    }
    cavity_label = labels_by_name.get("resection_cavity")
    if cavity_label is not None and np.any(mask_data == cavity_label):
        cavity = largest_area_slice(mask_data, [cavity_label])
        if cavity is not None:
            landmarks["resection_cavity"] = cavity - slice_start
    return landmarks


def add_mesh(scene: trimesh.Scene, name: str, source: trimesh.Trimesh) -> None:
    vertices = np.asarray(source.vertices)
    three = np.column_stack((-vertices[:, 0], vertices[:, 2], vertices[:, 1]))
    red, green, blue = COLOURS[name]
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[red, green, blue, 255],
        metallicFactor=0.0,
        roughnessFactor=0.7,
    )
    visual = trimesh.visual.TextureVisuals(material=material)
    mesh = trimesh.Trimesh(
        vertices=three,
        faces=np.asarray(source.faces),
        visual=visual,
        process=False,
    )
    scene.add_geometry(mesh, node_name=name, geom_name=name)


def write_model(
    brain_mask: np.ndarray,
    mask_data: np.ndarray,
    label_map: dict[int, str],
    affine: np.ndarray,
    out_dir: Path,
) -> None:
    scene = trimesh.Scene()
    brain_mesh = mask_to_mesh(
        clean_brain_mask(brain_mask),
        affine,
        smooth_iterations=20,
        target_faces=80000,
    )
    if brain_mesh is None:
        raise ValueError("brain mask is empty")
    add_mesh(scene, "brain", brain_mesh)
    labels_by_name = {name: label for label, name in label_map.items()}
    for name in STRUCTURE_ORDER:
        label = labels_by_name.get(name)
        if label is None:
            continue
        binary = mask_data == label
        if not np.any(binary):
            continue
        label_mesh = mask_to_mesh(
            binary,
            affine,
            smooth_iterations=10,
            target_faces=30000,
        )
        if label_mesh is not None:
            add_mesh(scene, name, label_mesh)
    scene.export(out_dir / "model.glb")
    check = trimesh.load(out_dir / "model.glb")
    print("GLB geometries:", ", ".join(check.geometry.keys()))


def compute_tumor_side(
    mask_data: np.ndarray,
    brain_mask: np.ndarray,
    label_map: dict[int, str],
    affine: np.ndarray,
) -> str:
    labels_by_name = {name: label for label, name in label_map.items()}
    primary_labels = [
        labels_by_name[name]
        for name in ("non_enhancing_core", "edema", "enhancing_tumor")
        if name in labels_by_name
    ]
    selected = np.isin(mask_data, primary_labels)
    if not selected.any() and "resection_cavity" in labels_by_name:
        selected = mask_data == labels_by_name["resection_cavity"]
    if not selected.any():
        return "right"
    tumor_centroid_voxel = np.argwhere(selected).mean(axis=0)
    brain_centroid_voxel = np.argwhere(brain_mask).mean(axis=0)
    tumor_centroid_ras = nib.affines.apply_affine(affine, tumor_centroid_voxel)
    brain_centroid_ras = nib.affines.apply_affine(affine, brain_centroid_voxel)
    return "right" if tumor_centroid_ras[0] > brain_centroid_ras[0] else "left"


def build_case(args: argparse.Namespace) -> None:
    try:
        label_map = parse_labels(args.labels)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    clean_output(args.out)
    image = load_volume(args.image)
    mask = load_volume(args.mask)
    if image.ndim == 4:
        raise SystemExit("error: image is 4-D; provide a single 3-D modality")
    if image.ndim != 3:
        raise SystemExit(f"error: image must be 3-D, got {image.ndim}-D")
    if mask.ndim != 3:
        raise SystemExit(f"error: mask must be 3-D, got {mask.ndim}-D")
    if image.shape != mask.shape:
        raise SystemExit(
            f"error: image and mask shapes differ: {image.shape} != {mask.shape}"
        )

    image_data = np.asarray(image.get_fdata(dtype=np.float32))
    mask_data = np.rint(mask.get_fdata()).astype(np.int32)
    try:
        brain_mask = make_brain_mask(image_data, args.brain_mask, image.shape)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    brain_slices = np.flatnonzero(np.any(brain_mask, axis=(0, 1)))
    if brain_slices.size == 0:
        raise SystemExit("error: brain mask is empty")
    slice_start = max(0, int(brain_slices[0]) - 2)
    slice_end = min(image.shape[2] - 1, int(brain_slices[-1]) + 2)

    slice_count = write_slices(
        image_data,
        mask_data,
        brain_mask,
        label_map,
        image.header.get_zooms(),
        args.out,
        slice_start,
        slice_end,
    )
    landmarks = compute_landmarks(mask_data, brain_mask, label_map, slice_start)

    voxel_volume = float(np.prod(image.header.get_zooms()[:3]))
    labels_by_name = {name: label for label, name in label_map.items()}
    volumes: dict[str, float] = {}
    structures = ["brain"]
    for name in STRUCTURE_ORDER:
        label = labels_by_name.get(name)
        if label is None:
            continue
        count = int(np.count_nonzero(mask_data == label))
        if count:
            volumes[name] = round(count * voxel_volume / 1000.0, 1)
            structures.append(name)

    try:
        write_model(brain_mask, mask_data, label_map, image.affine, args.out)
    except ValueError as exc:
        raise SystemExit(f"error: could not build model: {exc}") from exc

    tumor_side = compute_tumor_side(mask_data, brain_mask, label_map, image.affine)
    default_view = {"x": 15, "y": 35 if tumor_side == "right" else -35}
    print("Volumes (cm³):", json.dumps(volumes, sort_keys=True))
    print("Tumor side:", tumor_side)

    case = {
        "case_id": args.case_id,
        "source": {
            "image": args.image.name,
            "mask": args.mask.name,
            "label_map": {str(number): name for number, name in label_map.items()},
        },
        "slices": {
            "count": slice_count,
            "base_url": "/static/case/slices",
            "pad": 3,
            "plane": "axial",
            "order": "inferior_to_superior",
        },
        "landmarks": landmarks,
        "volumes_cm3": volumes,
        "structures": structures,
        "model_url": "/static/case/model.glb",
        "tumor_side": tumor_side,
        "default_view": default_view,
        "mask_source": args.mask_source,
        "modality": args.modality,
        "display_names": DISPLAY_NAMES,
        "colors": COLORS,
    }
    (args.out / "case.json").write_text(
        json.dumps(case, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--labels", default=DEFAULT_LABELS)
    parser.add_argument("--case-id", default="CASE-001")
    parser.add_argument("--brain-mask", type=Path)
    parser.add_argument("--mask-source", default="CorteX segmentation")
    parser.add_argument("--modality", default="T1c")
    args = parser.parse_args()
    build_case(args)


if __name__ == "__main__":
    main()
