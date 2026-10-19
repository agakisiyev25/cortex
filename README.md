# CorteX

CorteX is a voice-controlled AI co-pilot for the operating room. It uses the Gemini Live API to display patient data, MRI slices, a patient-specific 3D brain model, safety checklists, drug checks, and operative documentation while providing short spoken replies.

## Local run

```bash
cp .env.example .env
# Fill GOOGLE_API_KEY in .env
pip install -r requirements.txt
cd app && uvicorn main:app --port 8080
```

Open http://localhost:8080.

## Voice controls

Push-to-talk is the default. Once CorteX is connected, hold Space or press and hold the orb while speaking, then release it to send the utterance. Space is ignored while the typed-command field has focus.

Use the toggle below the orb to switch to Hands-free mode, which continuously sends microphone audio until you disconnect.

## Rebuild the real demo case

The committed web assets use `PatientID_0006_Timepoint_6` from MU-Glioma-Post:

```bash
python scripts/build_case.py \
  --image data/real/PatientID_0006_Timepoint_6_brain_t1c.nii.gz \
  --mask data/real/PatientID_0006_Timepoint_6_tumorMask.nii.gz \
  --out app/static/case --case-id PT-0006-T6 \
  --mask-source "Reference segmentation (MU-Glioma-Post)" --modality T1c
```

## Rebuild with a model prediction

```bash
python scripts/build_case.py \
  --image data/real/PatientID_0006_Timepoint_6_brain_t1c.nii.gz \
  --mask <prediction.nii.gz> \
  --out app/static/case --case-id PT-0006-T6 \
  --mask-source "CorteX nnU-Net prediction" --modality T1c
```

The mask must be our segmentation model's prediction. If the trained model uses different label numbering, pass `--labels` with names and numbers matching those used when the model was trained.

## UI demo and screenshots

Start the server with the development-only tool endpoint enabled:

```bash
cd app
CORTEX_DEV=1 uvicorn main:app --port 8080
```

Open http://localhost:8080/?demo=1 to test the console without a Gemini Live connection. To generate the prescribed UI snapshots from the repository root:

```bash
python -m playwright install chromium
python scripts/ui_snapshot.py
```

The images are written to `ui_snapshots/`. `CORTEX_DEV` must not be set on Replit or in any production deployment.

## Replit

1. Import the GitHub repository into Replit.
2. Add these Secrets:
   - `GOOGLE_API_KEY`
   - `GOOGLE_GENAI_USE_VERTEXAI=FALSE`
   - `GEMINI_LIVE_MODEL=gemini-3.8-live`
   - `VOICE_NAME=Puck`
3. Press Run and open the app in its own browser tab. The microphone may be blocked inside the preview pane.
4. Deploy as a Reserved VM because sessions use long-lived WebSockets.

## Voice commands

- “CorteX, brief me on this patient.”
- “Run the time-out.”
- “Jump to the tumor.”
- “Show the 3D model.”
- “Generate the operative report.”

Playbooks:

- Briefing: “Brief me”, “Case briefing”, or “Patient rundown”.
- Safety time-out: “Run the timeout”, “Time out”, “WHO checklist”, or “Safety check”.
- Operative report: “Generate the report”, “Operative report”, or “Summarize the case”.
- Drug check: “Can I give cefazolin?”, “Is propofol safe?”, or “Check vancomycin”.
