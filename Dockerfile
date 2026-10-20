FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/

# main.py serves static/ by relative path, so uvicorn must run from app/.
WORKDIR /srv/app

# Railway injects PORT. One worker only: sessions and the event log live in memory.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
