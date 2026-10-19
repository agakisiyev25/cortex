"""
ORION FastAPI Server — main.py
===============================
Wires ADK's LiveRequestQueue to the browser via WebSocket.
Modelled on the ADK's own adk_web_server.py /run_live endpoint.

Architecture:
  Browser ──WebSocket──► upstream_task() ──LiveRequestQueue──► Vertex AI
  Browser ◄─WebSocket── downstream_task() ◄─── run_live() events ─── Vertex AI

CRITICAL: Run uvicorn from inside the app/ directory:
  cd app/
  uvicorn main:app --reload
Running from the project root causes ModuleNotFoundError for orion_orchestrator.
"""

import asyncio
import base64
from contextlib import aclosing
import json
import logging
import os

from dotenv import load_dotenv

# load_dotenv MUST come before importing cortex_agent so that model settings
# are set when agent.py reads os.environ at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

from cortex_agent import root_agent
import cortex_agent.tools as cortex_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('orion')


# ---------------------------------------------------------------------------
# Module-level singletons — created once at startup, shared across connections
# ---------------------------------------------------------------------------

session_service = InMemorySessionService()

runner = Runner(
    app_name='cortex',
    agent=root_agent,
    session_service=session_service,
)

APP_NAME = 'cortex'
MODEL = os.environ.get('GEMINI_LIVE_MODEL', 'gemini-3.8-live')
USE_VERTEX = os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', 'FALSE').strip().lower() in ('1', 'true')
AUDIO_MIME = 'audio/pcm' if USE_VERTEX else 'audio/pcm;rate=16000'

app = FastAPI(title='CorteX')

# Serve static files (JS, CSS, etc.)
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index():
    return FileResponse('static/index.html')


@app.get('/console')
async def console():
    return FileResponse('static/index.html')


@app.get('/health')
async def health():
    return {'status': 'ok', 'model': MODEL}


@app.get('/api/case')
async def api_case():
    return {'case': cortex_tools.CASE, 'patient': cortex_tools._PATIENT_DATA}


if os.environ.get('CORTEX_DEV') == '1':
    agent_tool_names = {
        getattr(tool, '__name__', getattr(tool, 'name', None))
        for tool in root_agent.tools
    }

    @app.post('/dev/tool/{name}')
    async def dev_tool(name: str, args: dict):
        if name not in agent_tool_names:
            raise HTTPException(status_code=404, detail='Unknown tool')
        tool_function = getattr(cortex_tools, name)
        result = tool_function(**args)
        return {'name': name, 'args': args, 'response': result}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket('/ws/{user_id}/{session_id}')
async def websocket_endpoint(websocket: WebSocket, user_id: str, session_id: str):
    """
    One WebSocket connection per surgeon session.
    Runs two concurrent async tasks:
      upstream_task()   — browser → Vertex AI (audio, video, text)
      downstream_task() — Vertex AI → browser (events: audio, text, function calls)

    Task lifecycle follows the ADK's own adk_web_server.py /run_live endpoint:
      - asyncio.wait(FIRST_EXCEPTION): only stop on errors, not on normal turn completion
      - task.result() re-raises exceptions for proper error handling
      - aclosing() ensures the live_events async generator is always cleaned up
    """
    await websocket.accept()
    logger.info('WebSocket connected: user=%s session=%s', user_id, session_id)

    # Build RunConfig
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=os.environ.get('VOICE_NAME', 'Puck'),
                )
            )
        ),
    )

    # Get or create session (supports reconnection)
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        logger.info('Created new session: %s', session_id)
    else:
        logger.info('Resumed existing session: %s', session_id)

    # LiveRequestQueue: the inbox for messages going upstream to Gemini.
    # Must be created per-connection, not at module level.
    live_request_queue = LiveRequestQueue()

    async def upstream_task():
        """
        Reads from the WebSocket and forwards to Vertex AI via LiveRequestQueue.

        Message types:
          binary frames    → raw PCM audio (16kHz, Int16, mono)
          JSON text        → {'type': 'text', 'content': '...'}

        Exceptions are NOT caught here — they propagate so that
        asyncio.wait(FIRST_EXCEPTION) fires and tears down the session cleanly.
        """
        # Buffer audio until we have ~100ms worth before forwarding.
        # AudioWorklet sends 128-sample chunks (~8ms at 16kHz) — very high
        # message frequency. Accumulating to 3200 bytes (100ms) matches the
        # ADK Dev UI pattern and reduces API call rate.
        # IMPORTANT: Vertex AI Live API requires exactly 'audio/pcm' — the
        # rate suffix 'audio/pcm;rate=16000' triggers error 1007.
        _AUDIO_CHUNK_BYTES = 3200  # 100ms at 16kHz s16le mono
        _audio_buf = bytearray()

        while True:
            message = await websocket.receive()

            if 'bytes' in message and message['bytes']:
                _audio_buf.extend(message['bytes'])
                while len(_audio_buf) >= _AUDIO_CHUNK_BYTES:
                    chunk = bytes(_audio_buf[:_AUDIO_CHUNK_BYTES])
                    del _audio_buf[:_AUDIO_CHUNK_BYTES]
                    live_request_queue.send_realtime(
                        types.Blob(data=chunk, mime_type=AUDIO_MIME)
                    )

            elif 'text' in message and message['text']:
                try:
                    payload = json.loads(message['text'])
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get('type', '')

                if msg_type == 'text':
                    # Text input (debug/testing path — not used in voice demo)
                    text_content = payload.get('content', '')
                    if text_content:
                        live_request_queue.send_content(
                            types.Content(
                                role='user',
                                parts=[types.Part(text=text_content)],
                            )
                        )

                elif msg_type == 'audio_stream_end':
                    if _audio_buf:
                        live_request_queue.send_realtime(
                            types.Blob(data=bytes(_audio_buf), mime_type=AUDIO_MIME)
                        )
                        _audio_buf.clear()
                    live_request_queue.send_audio_stream_end()

    async def downstream_task():
        """
        Reads events from Vertex AI and forwards them to the browser as JSON.

        Uses aclosing() to guarantee the async generator is cleaned up even if
        the task is cancelled mid-iteration (matches ADK's own implementation).

        by_alias=True outputs camelCase field names (e.g. turnComplete, inlineData)
        consistent with the ADK Dev UI frontend convention.
        """
        async with aclosing(runner.run_live(
            session=session,
            live_request_queue=live_request_queue,
            run_config=run_config,
        )) as live_events:
          try:
            async for event in live_events:
                event_json = event.model_dump_json(exclude_none=True, by_alias=True)
                await websocket.send_text(event_json)

          except (ValueError, KeyError, TypeError) as exc:
            # Tool-not-found errors (e.g. model calls agent name as a tool)
            # or malformed function calls. Notify browser, then re-raise so
            # asyncio.wait(FIRST_EXCEPTION) fires and the WebSocket closes
            # cleanly. Without re-raise, upstream_task keeps the socket open
            # but downstream is dead — UI shows "active" but stops responding.
            logger.warning('Recoverable live error: %s', exc)
            try:
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': f'Session error: {exc}',
                }))
            except Exception:
                pass
            raise

    # ---------------------------------------------------------------------------
    # Run both tasks — mirrors adk_web_server.py's /run_live implementation:
    #   FIRST_EXCEPTION: only cancel when a task raises, not on normal turn
    #   completion. This allows multi-turn conversations without reconnecting.
    #   task.result() re-raises exceptions for structured error handling.
    # ---------------------------------------------------------------------------
    up   = asyncio.create_task(upstream_task())
    down = asyncio.create_task(downstream_task())
    done, pending = await asyncio.wait([up, down], return_when=asyncio.FIRST_EXCEPTION)

    try:
        for task in done:
            task.result()   # re-raise any exception from completed tasks
    except WebSocketDisconnect:
        logger.info('Client disconnected: session=%s', session_id)
    except Exception as exc:
        logger.error('Live session error: session=%s error=%s', session_id, exc, exc_info=True)
    finally:
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        # CRITICAL: always close the queue to prevent zombie Vertex AI sessions
        # that would count against the concurrent session quota.
        live_request_queue.close()
        logger.info('Session closed: %s', session_id)
        try:
            await websocket.close()
        except Exception:
            pass
