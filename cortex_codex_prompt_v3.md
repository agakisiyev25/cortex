# Codex task 3: CorteX fixes after UI review

Same repo. Small, exact fixes only. Do not change anything not listed. Keep all tests passing. One commit per fix group (F1–F4). If something cannot be done exactly as written, stop and report the error.

---

## F1. Tumor side is wrong (critical)

**Bug:** `tumor_side` uses the sign of the RAS x-coordinate of the tumor centroid. MU-Glioma-Post affines do not put x = 0 on the brain midline, so the result is meaningless. For PT-0006-T6 the MRI (radiological view, "R" on the left) and the 3D view both show the tumor in the **patient's right** hemisphere, but `case.json` says `"left"`.

**Fix in `scripts/build_case.py`:**
1. Compute, in RAS world mm (apply the canonical affine to voxel centroids): `x_tumor` = centroid x of labels 1–3 (fallback label 4), `x_brain` = centroid x of the brain mask.
2. `tumor_side = "right" if x_tumor > x_brain else "left"`. `default_view` follows it as before.
3. On every slice PNG, also draw a white "L" 12 px from the **right** edge, vertically centred (the "R" stays on the left).

**Tests (add to `tests/test_build_case.py`):**
- Synthetic case (tumor at +30 mm, right) → `tumor_side == "right"`.
- Mirrored synthetic case: flip image and mask on the first axis (`data[::-1]`, so the tumor is now in the left hemisphere), keep the same affine but add +500 to its x translation (so every world x is positive, which breaks the old sign test) → `tumor_side == "left"`.
- In the PNG at the `tumor` landmark, the centroid of pixels coloured enhancing-red (R > 180, G < 120, B < 120) has x < image width / 2. Radiological view: a right-sided tumor appears on the screen's left.

**Then rebuild PT-0006-T6** with the same command as task 2 and report `tumor_side` (expected: `right`) and the top-bar procedure text (expected: "Right craniotomy for tumor resection").

Commit `fix: tumor side relative to brain midline`.

---

## F2. Bigger MRI image

In `build_case.py`, crop every axial slice to the brain mask's in-plane bounding box (union over all exported slices), expanded by 6 % of its size on each side and clamped to the image. Apply the same crop to all slices, before resizing to 512 px longest side. Rebuild PT-0006-T6.

Commit `fix: crop MRI slices to brain`.

---

## F3. 3D viewer

1. **Resize bug:** the 3D view is stretched when the panel changes width (for example after `show_only_ar`). Add a `ResizeObserver` on the 3D canvas container: on every size change call `renderer.setSize(w, h, false)`, set `camera.aspect = w / h` and `camera.updateProjectionMatrix()`. Do the same for the MRI canvas (redraw the current slice).
2. **Edema transparency:** the edema mesh hides the tumor. Edema material: `transparent = true`, `opacity = 0.35`, `depthWrite = false`, `renderOrder = 1`. Enhancing tumor, necrotic core and cavity: opaque, `renderOrder = 0`. Brain unchanged (opacity 0.14, `renderOrder = 2`).

Commit `fix: 3D resize and edema transparency`.

---

## F4. Overlay layout

1. **Drug banner** must not cover panel headers or the drawer. Position: `top: 56px; left: 12px; max-width: calc(50% - 24px)` inside `#viewers`, so it sits over the MRI panel below its header. When the MRI is hidden (`.mri-hidden`), use `left: 12px; max-width: calc(100% - 436px)`.
2. **Drawer width:** 400 px, and 340 px when the viewport is narrower than 1500 px.
3. **Compact patient card** (`display_all_patient_data`): show fields in a 2-column grid (label 11px `--muted` above value 14px weight 600). `diagnosis`, `procedure`, `allergies` and `medications` span both columns. Show a field's note only if it is not one of the normal notes (as before, in `--amber`). Allergies value stays `--danger`.
4. **Screenshot script:** in state `04_timeout`, take the procedure bullet text from `GET /api/case` (`patient.procedure.value`) instead of the literal "…".
5. Re-run `scripts/ui_snapshot.py`.

Commit `fix: overlay layout`.

---

## Final report

1. Commit list.
2. `pytest -q` output.
3. `tumor_side` and the procedure text after the rebuild.
4. Screenshot file names.
5. Anything you could not follow exactly, with the error text.
