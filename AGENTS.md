# Development commands

Use Python 3.11.

## Setup and tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Rebuild the synthetic case

```bash
python scripts/make_synthetic_case.py --out data/synthetic
python scripts/build_case.py \
  --image data/synthetic/image.nii.gz \
  --mask data/synthetic/mask.nii.gz \
  --out app/static/case
```

## Run the server

```bash
cp .env.example .env
# Fill GOOGLE_API_KEY in .env
cd app && uvicorn main:app --port 8080
```

With the server running and a real `GOOGLE_API_KEY`, run the WebSocket smoke test from the repository root:

```bash
python scripts/smoke_ws.py
```
