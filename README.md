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

## Build a real case

```bash
python scripts/build_case.py \
  --image <t1c.nii.gz> \
  --mask <our_model_prediction.nii.gz> \
  --out app/static/case
```

The mask must be our segmentation model's prediction. If the trained model uses different label numbering, pass `--labels` with names and numbers matching those used when the model was trained.

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
