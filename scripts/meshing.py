"""Mesh helpers adapted from agakisiyev25/glioma-segmentation-webapp.

Source: https://github.com/agakisiyev25/glioma-segmentation-webapp
Paths: backend/app/meshing.py and backend/app/geometry.py
"""

from __future__ import annotations

import logging

import numpy as np
import trimesh
from scipy import ndimage, sparse
from skimage import measure


log = logging.getLogger(__name__)

MAX_FACES_BEFORE_SMOOTHING = 1_500_000


def _as_affine(affine) -> np.ndarray:
    matrix = np.asarray(affine, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError(f"affine must be 4x4, got {matrix.shape}")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0]):
        raise ValueError("affine bottom row must be [0, 0, 0, 1]")
    return matrix


def voxel_to_world(ijk, affine) -> np.ndarray:
    """Map voxel indices to world mm (RAS)."""
    matrix = _as_affine(affine)
    points = np.asarray(ijk, dtype=np.float64)
    if points.shape[-1] != 3:
        raise ValueError(f"ijk must have a trailing dimension of 3, got {points.shape}")
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def is_left_handed(affine) -> bool:
    """True when the voxel-to-world mapping flips handedness."""
    return bool(np.linalg.det(_as_affine(affine)[:3, :3]) < 0)


def marching_cubes_world(mask: np.ndarray, affine: np.ndarray) -> trimesh.Trimesh | None:
    """Iso-surface of a binary mask, vertices in world mm. No smoothing."""
    binary = np.asarray(mask).astype(bool)
    if not binary.any():
        return None

    box = ndimage.find_objects(binary.astype(np.uint8))[0]
    offset = np.array([axis.start for axis in box], dtype=np.float64)
    padded = np.pad(binary[box], 1, mode="constant", constant_values=False)

    vertices, faces, _, _ = measure.marching_cubes(
        padded.astype(np.float32), level=0.5, allow_degenerate=False
    )
    vertices_voxel = vertices - 1.0 + offset
    vertices_world = voxel_to_world(vertices_voxel, affine)

    if not is_left_handed(affine):
        faces = faces[:, ::-1]

    return trimesh.Trimesh(vertices=vertices_world, faces=faces, process=False)


def _umbrella_laplacian(mesh: trimesh.Trimesh) -> sparse.csr_matrix:
    """Row-normalised vertex adjacency: each vertex to mean of neighbours."""
    edges = mesh.edges_unique
    count = len(mesh.vertices)
    rows = np.concatenate([edges[:, 0], edges[:, 1]])
    columns = np.concatenate([edges[:, 1], edges[:, 0]])
    adjacency = sparse.coo_matrix(
        (np.ones(len(rows)), (rows, columns)), shape=(count, count)
    ).tocsr()
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    degree[degree == 0] = 1.0
    return (sparse.diags(1.0 / degree) @ adjacency).tocsr()


def _decimate(mesh: trimesh.Trimesh, face_count: int) -> trimesh.Trimesh:
    try:
        return mesh.simplify_quadric_decimation(face_count=face_count)
    except Exception as error:
        log.warning("Mesh decimation skipped: %r", error)
        return mesh


def smooth_and_decimate(
    mesh: trimesh.Trimesh, *, smooth_iterations: int, target_faces: int
) -> trimesh.Trimesh:
    result = mesh
    if len(result.faces) > MAX_FACES_BEFORE_SMOOTHING:
        log.warning("Very large surface (%d faces); pre-decimating", len(result.faces))
        result = _decimate(result, MAX_FACES_BEFORE_SMOOTHING)
    if smooth_iterations > 0 and len(result.faces) >= 4:
        result = trimesh.smoothing.filter_taubin(
            result.copy(),
            lamb=0.5,
            nu=0.53,
            iterations=smooth_iterations,
            laplacian_operator=_umbrella_laplacian(result),
        )
    if target_faces > 0 and len(result.faces) > target_faces:
        result = _decimate(result, target_faces)
    result.remove_unreferenced_vertices()
    return result


def mask_to_mesh(
    mask: np.ndarray,
    affine: np.ndarray,
    *,
    smooth_iterations: int = 10,
    target_faces: int = 40000,
) -> trimesh.Trimesh | None:
    mesh = marching_cubes_world(mask, affine)
    if mesh is None:
        return None
    return smooth_and_decimate(
        mesh, smooth_iterations=smooth_iterations, target_faces=target_faces
    )


def clean_brain_mask(mask: np.ndarray) -> np.ndarray:
    """Keep the largest connected component and fill enclosed holes."""
    binary = np.asarray(mask).astype(bool)
    if not binary.any():
        return binary
    labelled, count = ndimage.label(binary)
    if count > 1:
        sizes = ndimage.sum_labels(binary, labelled, index=np.arange(1, count + 1))
        binary = labelled == (int(np.argmax(sizes)) + 1)
    return ndimage.binary_fill_holes(binary)
