# Codex task 2: CorteX — real glioma case, push-to-talk, new console UI

You are continuing the CorteX repo you built in task 1 (commits `phase 0` … `phase 4`). This plan is complete; all decisions are made. Do not redesign beyond it, add features, or swap libraries. If a step cannot be done exactly as written, stop and report the exact error output.

Keep all existing tests passing. Work in the phases below, in order, with one commit per phase.

---

## What changed since task 1 (why)

1. The live voice test worked end to end, but in a noisy room the always-on microphone transcribed other people's speech in random languages, and CorteX replied in Turkish. → **Push-to-talk** and **English-only replies**.
2. Every conversation turn was written into the operative log as "AI LOG", burying real events. → **Operative log holds clinical events only.**
3. The UI wastes half the screen on an empty stage, the MRI is stretched, the 3D model is tiny. → **New console layout** (section 4).
4. The demo must use a **real MU-Glioma-Post case** with meshes built the same way as the team's own segmentation web app: <https://github.com/agakisiyev25/glioma-segmentation-webapp>.

---

## Phase A: real case pipeline

### A1. Reuse the web app's meshing

1. `git clone --depth 1 https://github.com/agakisiyev25/glioma-segmentation-webapp /tmp/gsw` (reference only, never committed).
2. Create `scripts/meshing.py` by copying from `/tmp/gsw/backend/app/meshing.py` the functions `marching_cubes_world`, `_umbrella_laplacian`, `_decimate`, `smooth_and_decimate`, `mask_to_mesh`, `clean_brain_mask` and the constant `MAX_FACES_BEFORE_SMOOTHING`, plus the functions they import from `/tmp/gsw/backend/app/geometry.py` (`voxel_to_world`, `is_left_handed`) placed in the same file. Change relative imports accordingly. Add a header comment crediting the source repo and path.
3. Add `fast-simplification==0.1.9` to `requirements-dev.txt`.

### A2. Rewrite the meshing part of `scripts/build_case.py`

Keep the CLI and everything about slices, landmarks and volumes, with these changes:

- **Colours** (same as the web app's `labels.py`), used for the 2D overlay, the 3D materials and the UI legend:
  - `non_enhancing_core` `#F2C200` (label 1, display name "Necrotic core")
  - `edema` `#2FA84F` (label 2, "Edema")
  - `enhancing_tumor` `#E0332B` (label 3, "Enhancing tumor")
  - `resection_cavity` `#2F7DE1` (label 4, "Resection cavity")
  - `brain` `#C9D2DA`
- **Meshes:** for `brain` use `clean_brain_mask(brain_mask)` then `mask_to_mesh(..., smooth_iterations=20, target_faces=80000)`. For each label use `mask_to_mesh(labels == value, affine, smooth_iterations=10, target_faces=30000)`. These return vertices in world mm (RAS) with correct winding.
- **Axis conversion** (unchanged rule from task 1, applied after meshing): `three = np.column_stack([-v[:, 0], v[:, 2], v[:, 1]])`.
- Combine all meshes into one `model.glb` as in task 1 (one node per structure, PBR material with the colours above, `metallicFactor=0`, `roughnessFactor=0.7`).
- **Slice range:** export only axial slices from 2 slices below to 2 slices above the brain mask's z-extent (clamped to the volume). Landmarks and `slices.count` refer to this exported range, numbered from 1.
- **2D overlay:** fill alpha 0.40 with the colours above, plus a 1-pixel outline of each region in the same colour at full opacity (outline = mask minus its binary erosion, computed on the displayed 2D slice).
- New `case.json` keys:
  - `"tumor_side": "right" | "left"`: sign of the RAS x-coordinate of the centroid of labels 1–3 (x > 0 → right). If labels 1–3 are empty, use label 4; if all empty, `"right"`.
  - `"default_view": {"x": 15, "y": 35}` if `tumor_side` is right, `{"x": 15, "y": -35}` if left (degrees; turns the tumor side toward the camera).
  - `"mask_source"`: string given by a new CLI option `--mask-source` (default `"CorteX segmentation"`).
  - `"modality"`: new CLI option `--modality` (default `"T1c"`).
  - `"display_names"`: the display-name map above; `"colors"`: the colour map above.
- Update `tests/test_build_case.py` for the new keys, the exported slice range (`count` ≤ volume depth) and that every present structure appears in the GLB.
- Regenerate the synthetic case and keep it working (it is the test fixture).

### A3. Build the real case (decided: PatientID_0006_Timepoint_6)

The MRI files are already in `data/real/` (committed earlier for review). Use only the `.nii.gz` files; ignore the uncompressed `.nii` duplicates. None of the masks are model predictions; they are the dataset's reference masks.

1. Build exactly this case:
   ```
   python scripts/build_case.py \
     --image data/real/PatientID_0006_Timepoint_6_brain_t1c.nii.gz \
     --mask  data/real/PatientID_0006_Timepoint_6_tumorMask.nii.gz \
     --out app/static/case --case-id PT-0006-T6 \
     --mask-source "Reference segmentation (MU-Glioma-Post)" --modality T1c
   ```
   Keep the default `--labels` (it matches the model contract: 1 NETC, 2 edema, 3 ET, 4 cavity). Expected volumes from the voxel counts (1 mm³ voxels): necrotic core ≈ 0.3 cm³, edema ≈ 77.7 cm³, enhancing ≈ 18.8 cm³, cavity ≈ 22.4 cm³. If the printed volumes differ by more than 0.2 cm³, stop and report.
2. Then stop tracking the raw MRI files so the repo stays small for Replit (the files stay on disk): `git rm -r --cached data/real` and add `*.nii`, `*.nii.gz` and `data/` to `.gitignore`.
3. Keep the synthetic case working as the test fixture (tests build it in a temp folder; it must no longer live in `app/static/case`).
4. Add to `CREDITS.md`: the MU-Glioma-Post dataset (The Cancer Imaging Archive) and the meshing code source.
5. Add to `README.md` how to rebuild with a model prediction later: same command with `--mask <prediction.nii.gz> --mask-source "CorteX nnU-Net prediction"`.

Commit `phase A: real case + web app meshing`.

---

## Phase B: backend changes

### B1. Push-to-talk support in `app/main.py`

In `upstream_task`, handle a new text message `{"type": "audio_stream_end"}`: first send any bytes left in `_audio_buf` with `send_realtime` (same MIME type), clear the buffer, then call `live_request_queue.send_audio_stream_end()`. Nothing else in the audio path changes.

### B2. Operative log = clinical events only

- `tools.log_ai_interaction`: remove the line that appends to `_SESSION_LOG`. It still returns the entry.
- `main.py`: stop sending `{'type': 'ai_log', ...}` to the browser (delete that block). Keep the transcription tracking variables only if still used; otherwise remove them.
- Add a test: after `log_ai_interaction('a', 'b')`, `show_event_log()` contains no entry of type `ai_interaction`.

### B3. Patient record follows the real tumor side

In `tools.py`, after loading `CASE`: `SIDE = CASE.get('tumor_side', 'right')`. Change these `_PATIENT_DATA` values (everything else unchanged):
- `diagnosis`: value `f"Recurrent glioma — {SIDE} hemisphere"`, note `"Recurrence on follow-up MRI"`
- `procedure`: value `f"{SIDE.capitalize()} craniotomy for tumor resection"`, note `"Neuronavigation-guided"`

`get_tumor_measurements` value string uses the display names: `"Enhancing tumor 8.4 cm³ · Necrotic core 3.1 cm³ · Edema 45.7 cm³ · Resection cavity 1.0 cm³"` (present regions only, in this order), note `f"{CASE['mask_source']} · {CASE['modality']}"`.

### B4. Agent instruction edits (`agent.py`)

Replace two sections of `INSTRUCTION` exactly:

```
## WAKE-WORD RULE (MOST IMPORTANT)
Respond to clear commands about patient data, the MRI, the 3D model, checklists, drugs or documentation, with or without the word "CorteX". If what you hear is a fragment, a greeting, noise or unrelated conversation, do not answer and do not call any tool.

## LANGUAGE
Always reply in English, even if the transcript looks like another language: the room may be noisy and transcription can be wrong. Never switch languages. Tool arguments are always the exact English identifiers listed below.
```

Also change the `hide_all_overlays` docstring and the TOOL REFERENCE line to: "clears patient cards, checklists, logs, drug alerts and summaries; the MRI and 3D views stay". Change `show_only_ar` docstring to: "hide the MRI and all cards, show only the 3D model".

### B5. Dev-only tool endpoint (for UI testing without voice)

In `main.py`, only when `os.environ.get('CORTEX_DEV') == '1'`, register `POST /dev/tool/{name}`: body is a JSON object of arguments; it calls the tool function of that name from `cortex_agent.tools` (only names in the agent's tool list; otherwise 404) and returns `{"name": name, "args": args, "response": result}`. When `CORTEX_DEV` is not `1`, the route must not exist (test both cases).

Run `pytest -q`. Commit `phase B: push-to-talk, clean log, dev endpoint`.

---

## Phase C: new console UI

Replace the console's look entirely. Keep `app.js`'s WebSocket and audio code (connect, disconnect, worklets, barge-in, event parsing, tool-call dedup). Everything visual is new.

### C1. Files

- `app/static/index.html`: rewrite (new structure below).
- New `app/static/css/cortex.css`: all styles. No inline `<style>` blocks.
- New `app/static/js/overlays.js`: the drawer, banner and modal (section C5).
- Edit `ct-viewer.js` (C3) and `anatomy-3d.js` (C4).
- Delete `clinical-panel.js`, `checklist-panel.js`, `log-panel.js`, `summary-panel.js` and their script tags.
- Scripts: Three.js r128 + GLTFLoader (already), plus `https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js`. Fonts: Google Fonts `Inter` (400, 500, 600, 700) and `JetBrains Mono` (500).

### C2. Layout and style

Design tokens (CSS variables on `:root`):

```
--bg #0B0F14; --panel #111820; --panel-2 #16202A; --border #223040;
--text #E6EDF3; --muted #8B9BAB; --accent #4FC3F7;
--ok #3FB950; --danger #F85149; --amber #D29922;
--radius 14px; --font Inter; --mono "JetBrains Mono"
```

Whole page is one screen, no page scroll, must fit 1366×768 and 1920×1080. Body background `--bg`, text `--text`.

```
┌──────────────────────────────────────────────────────────────── top bar (56px) ─┐
│ CorteX   Case CASE-ID · <procedure> · [Allergies: Cefazolin, Latex]   ● LIVE 04:12 │
├──────────────────────────────┬──────────────────────────────┬──────────────────────┤
│ MRI panel                    │ 3D panel                     │ Right rail (380px)   │
│                              │                              │  push-to-talk orb    │
│                              │        (drawer overlays      │  status text         │
│                              │         right side of the    │  ──────────────────  │
│                              │         viewer area)         │  Conversation        │
│                              │                              │  ──────────────────  │
│ legend                       │ legend · view name           │  Actions feed        │
│                              │                              │  typed command box   │
└──────────────────────────────┴──────────────────────────────┴──────────────────────┘
```

- **Grid:** `#app` = CSS grid, rows `56px minmax(0,1fr)`, columns `minmax(0,1fr) 380px`, 12px gap and 12px padding. Row 2 column 1 = `#viewers`, itself a grid with two equal columns (`#mri-panel`, `#ar-panel`) and 12px gap. Below 1280px wide, the rail is 320px.
- **View collapse:** `#viewers.mri-hidden` → columns `0 1fr` (MRI panel `display:none`); `#viewers.ar-hidden` → `1fr 0`. If both are hidden, show both placeholders (do not collapse both).
- **Panels:** background `--panel`, 1px `--border`, radius `--radius`, `overflow:hidden`. Panel header 44px: title in 13px uppercase letter-spacing 0.08em `--muted`, right-side meta in `--mono` 13px.
- **Top bar:** "CorteX" 20px weight 700; then the case strip in `--muted` 14px: case id, procedure value, allergies chip. Data source: add `GET /api/case` to `main.py` (always enabled, not dev-only) returning `{"case": tools.CASE, "patient": tools._PATIENT_DATA}`; the page fetches it on load. The allergy chip: background `rgba(248,81,73,.12)`, text `--danger`, radius 999px, padding 2px 10px. Right side: status pill (`OFFLINE` grey, `CONNECTING` amber, `LIVE` green with pulsing dot) and a session timer `mm:ss` from connect. A small text "Research prototype · not for clinical use" in 12px `--muted` at the far right.

### C3. MRI panel (`#mri-panel`, edit `ct-viewer.js`)

- Header: left "MRI · <modality> · Axial"; right "Slice n / total" (mono) and, when set, a landmark chip (accent colour) like "TUMOR".
- Body: black background, the PNG drawn with **contain** (keep aspect ratio, centred). Use `devicePixelRatio` for a sharp canvas.
- A 4px vertical position track on the body's right edge: track `--border`, marker 14px tall `--accent` at `slice/total`.
- Footer (32px): legend of present structures except `brain`: 10px round swatch + display name, 12px `--muted`.
- Mouse wheel over the image moves one slice (up = superior).
- On load, show the `tumor` landmark slice immediately (no waiting for a command).
- `hide()` adds `.mri-hidden` to `#viewers`; any `navigate` or `jumpToLandmark` removes it.

### C4. 3D panel (`#ar-panel`, edit `anatomy-3d.js`)

- Header: left "3D · Patient-specific model"; right the current view name (mono): Front, Back, Right side, Left side, Top, Bottom, or "Default" (from the `rotate_model` table in task 1; anything else shows "Custom").
- Renderer with `alpha: true`, `antialias: true`, pixel ratio `min(devicePixelRatio, 2)`. Panel body background: `radial-gradient(circle at 50% 40%, #1B2733 0%, #0B0F14 75%)`.
- Lights: `HemisphereLight(0xffffff, 0x223040, 0.9)`, `DirectionalLight(0xffffff, 0.8)` at (3, 5, 4), a second `DirectionalLight(0x88ccff, 0.35)` at (−4, 2, −3).
- `OrbitControls` for mouse orbit and zoom, damping on, pan off. Save the default camera with `controls.saveState()` after the model loads.
- Brain material: transparent, opacity 0.14, `depthWrite false`, `renderOrder 2`. Other structures: opaque, `renderOrder 1`.
- After load, apply `case.json` `default_view` as the model's rotation (x then y, degrees) and show "Default".
- `rotate(axis, degrees)`: `controls.reset()`, then `model.rotation.set(0,0,0)`, then set the axis. Animate the change over 400 ms with easing (lerp the rotation inside the render loop).
- `reset()`: all structures visible, rotation back to `default_view`, `controls.reset()`.
- Footer legend like the MRI's, but each chip reflects visibility: hidden structures shown at 40% opacity with line-through. Include `brain`.
- `hide()` adds `.ar-hidden` to `#viewers`; `reset`, `rotate` and `toggleStructure` remove it.
- On load the 3D view is visible with the default view (no waiting for a command).

### C5. Overlays (`overlays.js`)

All three overlay types are absolutely positioned inside `#viewers` (which is `position: relative`), above both panels.

**Drawer** (`Drawer`): right side of `#viewers`, 12px from the edges, width 400px, max height 100% minus 24px, vertical stack of cards with 10px gap, scrolls inside if needed. Newest card on top; max 3 cards (drop the oldest). A card with the same `kind` replaces the old one in place. Each card: background `--panel-2`, 1px `--border`, radius 12px, a 3px left accent bar in the card's colour, header (13px uppercase title + close ×), body. Cards enter with a 180 ms slide-in from the right and fade.

Card kinds:
- `patient`: from `display_all_patient_data` → all fields as rows (label 12px `--muted`; value 15px weight 600; note 12px). A row whose note is not one of "Normal", "Normal renal function", "Adequate for surgery", "Normal coagulation" or empty shows its note in `--amber`. The `allergies` row value shows in `--danger`. Accent `--accent`.
- `patient` from `display_patient_data(field)` → same card kind with only that field, value 28px. Accent `--accent`.
- `volumes`: from `get_tumor_measurements` → one row per region taken from the response's top-level `volumes_cm3` (colours and display names from `case.json`): swatch, display name, value in mono `x.x cm³`; total of the tumor regions (enhancing + necrotic core + edema) as the last row; source note from the render command's `note`. Accent `--accent`.
- `checklist`: from `get_surgical_phase` → phase label, four items with empty square checkboxes, warning (if any) in an amber callout. Accent `--amber`.
- `log`: from `show_event_log` and each `log_event` → timeline rows: mono time, event type in plain words (`timeout_complete` → "Time-out complete", `incision` → "Incision", `tumor_resected` → "Tumor resected", `specimen_sent` → "Specimen sent", `complication` → "Complication" (row in `--danger`), `milestone` → "Milestone", `note` → "Note"), then the note. `log_event` opens the card if closed and appends. Accent `--ok`.

Hide tools: `hide_patient_data` removes `patient`; `hide_surgical_checklist` removes `checklist`; `hide_event_log` removes `log`; `hide_all_overlays` removes all cards, the banner and the modal; `show_only_ar` does the same and also hides the MRI.

**Banner** (`Banner`): for `check_drug_safety` responses. Top-centre of `#viewers`, 12px from the top, max width 640px. `safety_status == 'caution'` → background `rgba(248,81,73,.14)`, border `--danger`, title "⚠ <DRUG> — CAUTION" in `--danger`; `'safe'` → green equivalents with "✓ <DRUG> — SAFE". Body: the response `summary`. Auto-hide after 15 s; a new check replaces it.

**Modal** (`Modal`): for `show_agent_summary`. Centred over `#viewers` with a `rgba(5,8,11,.6)` backdrop covering `#viewers` only. Card width `min(880px, 90%)`, max height 85%, scrolls inside. Title 26px weight 700, content paragraph 16px, then bullets as rows. If the title contains "Checklist", each bullet gets a green check circle; otherwise bullets are numbered. Close × top right. A new summary replaces the old one.

Routing: `handleFunctionResponse` sends `clinical` responses to the drawer (`patient` / `volumes`) or banner (`drug_check`), `checklist` to the drawer, `log` to the drawer and `summary` to the modal. Delete the old panel calls.

### C6. Right rail

Vertical flex: orb section (fixed), Conversation (flex 1, scrolls), Actions (fixed 200px, scrolls), typed command form (fixed).

**Orb + push-to-talk:**
- 120px circle, centred. States and labels under it (14px):
  - offline: grey orb, "Tap to connect"
  - connecting: amber, "Connecting…"
  - idle: accent glow, "Hold SPACE or the orb to talk"
  - talking: bright accent; the orb scales `1 + min(rms·4, 0.25)` from the live mic level; "Listening…"
  - thinking: slow pulse, "Thinking…" (from release until the first CorteX audio or transcription, max 8 s)
  - speaking: soft ripple, "Speaking…" (while audio chunks arrive; back to idle 600 ms after the last)
- Click on the orb when offline → `connect()`.
- When connected: press and hold the orb (pointer events) or hold the Space key → talking. Space is ignored while focus is in the typed input. On start: call the existing barge-in function so CorteX stops speaking. On release: send `{"type":"audio_stream_end"}`.
- `audioRecorderHandler` sends PCM only while talking. The mic stays open the whole session; only sending is gated.
- A small toggle under the orb: "Push-to-talk" (default) / "Hands-free". In hands-free mode, all audio is sent (task 1 behaviour) and Space does nothing.
- A small "Disconnect" text button under the toggle when connected.

**Conversation:** chat bubbles. Surgeon right-aligned (`--panel-2`), CorteX left-aligned (accent-tinted `rgba(79,195,247,.10)`). Each turn updates its bubble in place while streaming, as in task 1. Keep the last 30 bubbles. Auto-scroll to bottom.

**Actions feed:** one row per dispatched tool call: mono time, coloured dot by category (patient = accent, MRI = `#B392F0`, 3D = `#56D4BC`, procedure/log = `--ok`, drug = `--danger`, display = `--muted`), and plain words:

| Tool | Text |
|---|---|
| display_patient_data | Patient: {field label} |
| display_all_patient_data | Patient record opened |
| hide_patient_data | Patient card closed |
| navigate_scan | MRI {up/down} {count} → slice {n} |
| jump_to_landmark | MRI → {landmark, words} (slice {n}) |
| hide_scan | MRI hidden |
| rotate_model | 3D → {view name} |
| toggle_structure | 3D: {display name} {shown/hidden} |
| reset_3d_view | 3D reset |
| hide_3d | 3D hidden |
| get_tumor_measurements | Tumor volumes measured |
| get_surgical_phase | Checklist: {phase label} |
| hide_surgical_checklist | Checklist closed |
| check_drug_safety | Drug check: {drug} |
| log_event | Logged: {event words} |
| show_event_log / hide_event_log | Operative log opened / closed |
| show_agent_summary | {title} |
| hide_all_overlays | Display cleared |
| show_only_ar | 3D only |

Slice numbers and labels come from the function response when available (write the row when the response arrives; if the response never comes, write it from the call args after 1 s). Keep the last 50 rows, newest on top.

**Typed command:** as task 1, restyled: input `--panel-2`, 1px `--border`, radius 10px, 40px tall, send button accent.

**Remove:** the Agents & Tools card, tool chips, the routing log, tooltips (`TIPS`) and the "Try saying…" list.

### C7. Demo mode for UI testing

If the page URL has `?demo=1`, do not open the WebSocket. Expose `window.cortexDemo = { call(name, args) }`, which posts to `/dev/tool/{name}` and feeds the result through the same `dispatchRenderCommand` and `handleFunctionResponse` code (plus the actions feed), and `say(role, text)`, which adds a conversation bubble. The status pill shows `DEMO`.

### C8. Screenshots

New `scripts/ui_snapshot.py` (dev only; add `playwright` to `requirements-dev.txt`; run `python -m playwright install chromium`). With a server running with `CORTEX_DEV=1`, it opens `http://localhost:8080/?demo=1` at 1920×1080 and 1366×768 and saves PNGs to `ui_snapshots/` (gitignored) for these states:

1. `01_initial` (page loaded)
2. `02_patient`: `say('surgeon','Brief me on this patient')`, `call display_all_patient_data`, `call get_tumor_measurements`, `call get_surgical_phase {phase: positioning}`, `say('cortex','Forty-six-year-old male…')`
3. `03_drug`: `call check_drug_safety {drug_name: cefazolin}`
4. `04_timeout`: `call hide_all_overlays`, `call log_event {event_type: timeout_complete, note: 'WHO time-out verified'}`, `call show_agent_summary {title: 'WHO Surgical Safety Checklist', content: '', bullets: ['Patient: 46-year-old male', 'Procedure: …', 'Allergies: Cefazolin (hives), Latex', 'Essential imaging displayed']}`
5. `05_3d`: `call hide_all_overlays`, `call rotate_model {axis: x, degrees: 90}`, `call toggle_structure {structure: edema, visible: false}`
6. `06_only3d`: `call show_only_ar`

Wait 800 ms after each state before the screenshot. If Playwright cannot be installed in your environment, skip and report it.

Commit `phase C: console UI`.

---

## Phase D: docs

Update `README.md`: push-to-talk usage (hold Space or the orb), hands-free toggle, how to rebuild the real case (A3), `CORTEX_DEV=1` + `?demo=1` + `scripts/ui_snapshot.py` for UI checks, and that `CORTEX_DEV` must not be set on Replit. Commit `phase D: docs`.

---

## Out of scope

Live segmentation in CorteX, uploads, the web app's React frontend, multi-planar views, new agent tools, new voice commands, landing pages, auth.

## Final report

1. Commit list.
2. `pytest -q` output.
3. The volumes printed by `build_case.py` for PT-0006-T6 and the computed `tumor_side`.
4. Screenshot file names (and attach the images if your interface allows), or why they were skipped.
5. Every place you could not follow the plan exactly, with the error text.
