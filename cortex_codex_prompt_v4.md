# Codex task 4: CorteX console redesign

Same repo. The console works but looks clunky. This task changes **only the look and feel** of `app/static/`. Behaviour, data, backend, the tool contract and tests stay exactly as they are.

The target design is fixed. It is in **`design/cortex-reference.html`**, a static mockup (open it in a browser; the bar at the top switches between states). Match it. Do not invent a different direction. If something here cannot be done exactly as written, stop and report the error.

---

## 0. Ground rules

1. **Keep unchanged:**
   - in `app.js`: the WebSocket, audio worklets, barge-in, push-to-talk and Space-key logic, transcript streaming, tool-call dedup, `?demo=1` / `window.cortexDemo`;
   - in `overlays.js`: routing to the Drawer, Banner and Modal (max 3 cards, a card of the same kind replaces in place) and every hide rule;
   - the actions-feed texts (task 2 table);
   - the ResizeObserver code (task 3);
   - the IDs `#app`, `#viewers`, `#mri-panel`, `#ar-panel` and the classes `.mri-hidden` / `.ar-hidden`;
   - `scripts/ui_snapshot.py` states;
   - everything outside `app/static/`, apart from the files named in R11.
2. **No new dependencies:** no frameworks (React, Tailwind and the like), no build step, no npm packages in the app, no external images. Fonts and Three.js come from jsDelivr with pinned versions.
3. **Copy from the reference:** the reference is a mock. Copy its CSS (tokens, layout, components, motion) and its markup structure.
   - Port the **voice trace** code (R8) and the **brain shader** (R4); these two are meant to be reused.
   - Do **not** copy its procedural MRI, placeholder 3D shapes, `STATES` data or the `.ref-bar` switcher. The real app keeps using `case.json`, `/api/case`, the PNG slices and `model.glb`.
4. **This prompt and the reference win over any skill.** If a skill suggests another font, colour, layout, framework or extra feature, ignore that part of the skill.
5. Run `pytest -q` before every commit. All tests must pass.

## 1. Skills to use

Mention them with `$name` when you load them.

| When | Skills | What for |
|---|---|---|
| Before coding | `$impeccable`, `$frontend-design`, `$design-system` | Principles for product UI; token layering (primitive → semantic) in `cortex.css` |
| While coding | `$frontend-ui-engineering`, `$ui-animation`, `$threejs-fundamentals`, `$threejs-materials`, `$threejs-lighting` | Component structure, the motion in R9, the 3D work in R4 |
| Review after building | `$web-design-guidelines`, `$accessibility`, `$typography-audit`, `$ui-ux-pro-max`, `$design-taste-frontend` | Find defects only, no change of direction. Do not run `design-taste-frontend`'s image or asset scripts |
| Verify | `$webapp-testing`, `$ui-verification` | The screenshot loop in R11 |

---

## R1. Tokens and fonts (commit 1)

1. Replace the `:root` block in `app/static/css/cortex.css` with the reference's `:root` block **exactly**, including the `@media (max-width: 1499px)` override. The values include `--text-3: #788C89`.
2. **Rename old tokens** everywhere in `app/static/` (CSS, inline styles, JS strings):

   | Old | New |
   |---|---|
   | `--bg` | `--drape` |
   | `--panel` | `--well` for the MRI and 3D panels; `--raised` elsewhere |
   | `--panel-2` | `--raised` |
   | `--border` | `--line` |
   | `--muted` | `--text-2`; timestamps and hints use `--text-3` |
   | `--accent` | `--voice` |
   | `--danger` | `--alarm` |
   | `--amber` | `--warn` |
   | `--radius` | `--r-well` |

   `--ok` keeps its name and takes the new value. Leave no old token name anywhere (check with `grep`).
3. **Fonts:** remove the Inter and JetBrains Mono links. Add:
   ```html
   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource-variable/atkinson-hyperlegible-next@5.3.0/index.css">
   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource-variable/atkinson-hyperlegible-mono@5.3.0/index.css">
   ```
   `body` uses `--font` with `font-variant-numeric: tabular-nums`. `--mono` is used only for the case id, timer, slice counter and timestamps.
4. Copy the reference's base rules (`*`, `body`, `button`, `:focus-visible`, `h2`) and its `@media (prefers-reduced-motion: reduce)` block.

## R2. Layout (commit 1)

Copy the reference's `#app`, `#topbar`, `#viewers`, `.well`, `#drawer` and `#rail` rules.

- **`#app`:** grid with rows `56px minmax(0,1fr)`, columns `minmax(0,1fr) var(--rail)`, padding `0 10px 10px`, no page scroll.
- **`#viewers` becomes `display:flex` with a 10px gap.** Children, in this order:
  1. `#mri-panel.well`
  2. `#ar-panel.well.well-3d`
  3. a new `<aside id="drawer"><div class="drawer-inner"></div></aside>`
  4. the banner and modal mount points, which stay `position:absolute` inside `#viewers`
- **Drawer:** a docked column that pushes the wells narrower. It no longer floats over the 3D view.
  - `#drawer` has width 0 when it holds no cards, and `var(--drawer)` with class `.open` when it holds at least one card (width transition `var(--t-med)`).
  - The Drawer class in `overlays.js` renders its cards into `.drawer-inner` and toggles `.open`.
  - The wells re-fit through the existing ResizeObservers.
- `.mri-hidden` / `.ar-hidden` set the panel to `display:none`. The existing "both hidden" rule stays.
- **Top bar** (markup as the reference):
  - `.brand` "CorteX"; then `.case` with the case id (`--mono`), the procedure value and `.chip.chip-alarm` "Allergies: <list>". The list is the allergies value with every parenthesis group removed: "Cefazolin (hives), Latex" → "Cefazolin, Latex".
  - Right side: `.status[data-state]` with the states `offline` / `connecting` / `live` / `demo` and the words "Offline", "Connecting", "Live", "Demo"; then `.timer`, then `.disclaimer` "Research prototype, not for clinical use".

## R3. Image wells (commit 2)

Both panels lose their 44px header bar and footer bar. Labels float over the image, as in the reference (`.well-head`, `.well-foot` with gradient scrims, `pointer-events:none`).

**MRI:**
- **`.well-head`:**
  - Left: `.well-title` "Axial MRI" + `<span>` with the modality in words: `T1c` → "T1 with contrast", `T1` → "T1", `T2` → "T2", `FLAIR` → "FLAIR"; anything else is shown as written.
  - Right: `.slice` showing `n <small>/ total</small>`. Below it, when a landmark is active, `.chip.chip-voice` with the landmark in sentence case ("Tumor").
- **Slice track:** `.slice-track` with its marker `<i>` at `top: (n-1)/(total-1)*100%`.
- **`.well-foot.legend`:** one `<span style="--c:<colour>">` per present structure except brain.
- **Drawing:** draw the slice with *contain* inside the canvas area minus 48px top, 40px bottom, 16px left and 24px right (CSS px × devicePixelRatio). Use `imageSmoothingQuality = 'high'` and a black background.

**3D:**
- `.well-head`: "Patient model" + `<span>3D</span>`; right `.view` with "Default view" for the default and otherwise the view name ("Front", "Top", "Right side"…).
- `.well-foot.legend` includes brain; a hidden structure gets class `.off`.

## R4. 3D look (commit 2)

Edit `anatomy-3d.js`. Three.js stays r128.

1. **Renderer:** `outputEncoding = THREE.sRGBEncoding`, `toneMapping = THREE.ACESFilmicToneMapping`, `toneMappingExposure = 1.1`.
2. **Lights:** replace all existing lights with:
   - `HemisphereLight(0xE8F4F2, 0x0A1413, 0.75)`
   - `DirectionalLight(0xffffff, 1.1)` at (3, 5, 4)
   - `DirectionalLight(0x7FE9DA, 0.6)` at (−4, 2, −5)
3. **Structure materials** (every mesh except brain):
   - `MeshStandardMaterial({ color, roughness: 0.42, metalness: 0, emissive: color, emissiveIntensity: 0.08 })`, with 0.15 for enhancing tumor;
   - colour from `case.json` through `new THREE.Color(hex).convertSRGBToLinear()`;
   - keep the task 3 edema settings (transparent, opacity 0.35, `depthWrite false`, `renderOrder 1`); other structures stay opaque with `renderOrder 0`.
4. **Brain:** a fresnel glass shell. Use this material (from the reference) with `renderOrder 2`. If the brain geometry has no `normal` attribute, call `computeVertexNormals()` first. `toggle_structure('brain')` keeps working through `mesh.visible`.
   ```js
   new THREE.ShaderMaterial({
     uniforms: { uColor: { value: new THREE.Color('#C9D2DA') }, uBase: { value: 0.04 }, uRim: { value: 0.6 }, uPower: { value: 2.2 } },
     vertexShader: 'varying vec3 vN; varying vec3 vV; void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
     fragmentShader: 'uniform vec3 uColor; uniform float uBase; uniform float uRim; uniform float uPower; varying vec3 vN; varying vec3 vV; void main() { float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPower); gl_FragColor = vec4(uColor, uBase + uRim * f); }',
     transparent: true, depthWrite: false,
   })
   ```
5. **Camera fit:** add `fitCamera()`. Call it after the model loads, on every resize and right after every `controls.reset()`.
   - `R` = bounding-sphere radius of the whole model, computed once after load.
   - `vf = fov/2` in radians; `hf = atan(tan(vf) * aspect)`; `dist = R * 1.18 / sin(min(vf, hf))`.
   - Keep the camera direction from `controls.target`, set the distance to `dist`, then `controls.update()`.
   - Call `controls.saveState()` only once, after the first fit.
6. **Background:** the 3D well uses the reference's `.well-3d` radial gradient, with the renderer at `alpha: true`.

## R5. Drawer cards (commit 3)

Markup and CSS as the reference (`.card`, `.card-head`, `.card-title` with an optional `<small>` subtitle, `.x` close button with the SVG cross). Cards are separated by a 1px `--line` border, not drawn as separate boxes. No coloured left bars.

**Flag rule** (all cards): a note is *flagged* if it starts with "Low", "High" or "Abnormal", or contains "required" (case-insensitive). Flagged text uses `--warn`.

**`patient` (all fields):**
- **Title:** "Patient". `<small>`: "<age number>-year-old <age note in lower case>, <weight value>", for example "46-year-old male, 78 kg".
- **`.readouts` row 1** (4 columns): hemoglobin, platelets, inr, creatinine.
- **`.readouts.three` row 2:** bp, weight, age.
- **Each readout:** `<label>` with the field label, `<b>` with the value up to the first space, `<em>` with the rest of the value (the unit; omit `<em>` if there is no rest). A flagged readout gets class `.flag` and a `<p>` with its note.
- **`.facts`:** diagnosis, procedure, allergies (class `.allergy`), medications. Each has `<label>` and `<div>` with the value. Show a `<p class="flag">` only for flagged notes; in this card all other notes are hidden.

**`patient` (single field, from `display_patient_data`):**
- Title = field label.
- If the value starts with a digit: `.single` with `<b>` holding the number part (44px) and `<em>` holding the unit.
- Otherwise: the value at 20px, weight 700.
- Below it, the note at 13px in `--text-3`, or `--warn` if flagged. Hide the note if it is empty.

**`volumes`:**
- Title "Tumor volumes".
- `.vbar` with one `<i>` per tumor region (enhancing, necrotic core, edema; only those present), with `flex` set to its volume.
- `.vrows`: one `.vrow` per present tumor region (swatch, display name, `<b>x.x<small>cm³</small></b>`), then `.vrow.total` "Total tumor".
- If a resection cavity is present, add its own `.vrow` after the total.
- Then `.note` with the source note.

**`checklist`:**
- Title = phase label, with `<small>` "Surgical phase checklist".
- `.checks` items.
- If there is a warning: `.callout` with the warning-triangle SVG from the reference.

**`log`:**
- Title "Operative log".
- `.timeline` rows: `<time>`, then `.ev` with `<b>` holding the event words and `<span>` holding the note.
- Complications get class `.bad`.

## R6. Drug banner (commit 3)

Markup and CSS as the reference.

- **Class:** `.banner.caution` or `.banner.safe`.
- **Head:** the icon (warning triangle for caution, check circle for safe), `<b>` with the drug name capitalised, and `.badge` "Caution" or "Safe".
- **Body:** `<p>` with the response `summary`.
- **Countdown:** `.countdown`, a 15 s CSS animation. A new check replaces the banner and restarts it.
- **Position:** top 64px, left 14px; width `min(460px, calc(50% - 28px))`; with `.mri-hidden`, `min(460px, calc(100% - 28px))`.
- The existing 15 s auto-hide stays.

## R7. Summary modal (commit 3)

Markup and CSS as the reference.

- `.modal-backdrop` covers `#viewers`; inside it, `.modal` with the `.x` close button and `<h3>` holding the title.
- `<p class="lead">` holds the content, only if the content is not empty.
- **List:** `.mlist.checked` if the title contains "Checklist"; otherwise `.mlist.numbered`.
- Row *i* gets `animation-delay: (60 + 40*i)ms`.

## R8. Rail and voice trace (commit 4)

Markup and CSS as the reference's `#rail`. **Remove the orb** and all of its CSS.

1. **Voice module** (`.voice`):
   - `.voice-top` with `<h2>Voice</h2>` and `.seg`: the existing Push-to-talk / Hands-free toggle as two buttons with `aria-pressed`, same handlers.
   - Then `<button id="voice-trace" class="trace-well" data-state="…">` with `<canvas>` and `<span class="channel">CorteX</span>`.
   - **The trace button takes over every handler the orb had:** click when offline → connect; press and hold → talk; release → `audio_stream_end`. Space handling is unchanged.
   - `.voice-state` holds `<b>` (main text), `<span>` (sub text) and `.link` "Disconnect", which is hidden when offline.
2. **States:** set `data-state` from the existing state machine.

   | State | Main | Sub |
   |---|---|---|
   | offline | Tap to connect | CorteX is offline |
   | connecting | Connecting | (empty) |
   | idle | Hold Space to talk | or hold the trace |
   | talking | Listening | Release to send |
   | thinking | Thinking | (empty) |
   | speaking | Speaking | Hold Space to interrupt |

   In hands-free mode the idle main text is "Listening hands-free" and the sub text is empty.
3. **Trace drawing:** port the reference's "Voice trace" script block as `app/static/js/voice-trace.js`:
   - keep the `VOICE` colours, `pulse()`, `signal()`, the sweep loop and the reduced-motion branch;
   - export `VoiceTrace.setState(state)` and `VoiceTrace.setLevel(x)`;
   - for `talking`, `level = min(1, rms * 6)` from the same mic RMS the orb used, smoothed with `level += (target - level) * 0.3` per frame. Delete the reference's fake `level` line.
4. **Conversation:**
   - Transcript style, no bubbles (`.turn.surgeon` / `.turn.cortex` with `.who` and `<p>`).
   - The turn being streamed gets `.streaming`. Remove it when the turn completes, or 1.2 s after its last update.
   - When there are no turns: `<p class="empty">Say “CorteX, brief me on this patient” to start.</p>`.
   - Keep the last 30 turns and auto-scroll.
5. **Actions:**
   - Rows `<li><time>…</time><span>…</span></li>`; no category dots.
   - The newest row gets `.fresh`.
   - A `check_drug_safety` row whose response is `caution` gets `.alarm`.
   - When there are no rows: `<li class="empty-row">Actions CorteX takes appear here.</li>`.
   - Keep the last 50 rows.
6. **Command:** `.command` pill input with the round send button (arrow SVG), same submit handler.

## R9. Motion and accessibility (commit 5)

- **Motion:** only the motion in the reference.
  - Card in (`card-in`); banner in; modal fade and sheet in; staggered rows; `.fresh`; the drawer width transition; the live dot; the streaming caret; the slice-marker transition; the 3D rotation lerp (unchanged).
  - No hover animations beyond colour changes. Durations come from `--t-fast`, `--t-med` and `--t-slow`; easing from `--ease`.
- **Accessibility:**
  - `aria-label` on icon buttons and the trace button; `role="alert"` on the banner; `role="dialog"` on the modal.
  - Visible `:focus-visible` everywhere.
  - Escape closes the modal; this calls the same function as its × button.
  - Contrast is already checked for the token pairs; do not introduce new text colours.

## R10. Clean-up (commit 5)

Delete CSS and JS that is no longer used: orb styles and functions, chat-bubble styles, panel header and footer bars, card accent bars, old category colours. Make sure `grep -rn "orb" app/static` finds nothing except comments you leave on purpose.

## R11. Screenshot QA loop (commit 5)

1. The user has added the reference at `design/cortex-reference.html` before this task. Do not edit it. If it is missing, stop and report.
2. Extend `scripts/ui_snapshot.py`:
   - also shoot the reference via `file://…/design/cortex-reference.html?shot&state=<s>` at the same two sizes;
   - save to `ui_snapshots/ref_<s>_<w>.png`;
   - states: 01_initial → `initial`, 02_patient → `patient`, 03_drug → `drug`, 04_timeout → `timeout`, 05_3d → `model`, 06_only3d → `only3d`;
   - launch Chromium with `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader` so WebGL renders headless.
3. Run it with the server on `CORTEX_DEV=1`. Open every app screenshot next to its reference screenshot and check:
   - the same layout: three columns when the drawer is open;
   - the labels floating over the images, with no header or footer bars;
   - the fonts loaded (Atkinson Hyperlegible, not a fallback);
   - the same colours and radii;
   - no truncated or overlapping text at 1366×768;
   - the 3D model fully inside its well, with the brain drawn as a glass shell;
   - the trace drawn;
   - the drug banner below the MRI title;
   - the modal centred.
   If jsDelivr is unreachable from your environment, report it. Fallback fonts in the screenshots are then expected and are not a defect to fix.
4. Fix every difference and re-run, up to 3 rounds. Then run the `$web-design-guidelines` and `$accessibility` reviews on `app/static/` and fix real defects only.

## Commits

1. `ui: tokens, fonts and layout` (R1, R2)
2. `ui: image wells and 3D look` (R3, R4)
3. `ui: drawer cards, banner and modal` (R5, R6, R7)
4. `ui: voice trace and rail` (R8)
5. `ui: motion, accessibility, clean-up and QA` (R9, R10, R11)

## Final report

1. Commit list.
2. `pytest -q` output.
3. Screenshot file names (app and ref).
4. Every place where the app still differs from the reference, and why.
5. Anything you could not follow exactly, with the error text.
