#!/usr/bin/env python3
"""Smoke-test a running CorteX Gemini Live WebSocket session."""

import asyncio
import json
from collections import deque

import websockets


URL = 'ws://localhost:8080/ws/smoke/smoke1'


async def smoke() -> int:
    messages: deque[str] = deque(maxlen=5)

    try:
        async with websockets.connect(URL) as websocket:
            await websocket.send(json.dumps({
                'type': 'text',
                'content': 'Cortex, show the hemoglobin.',
            }))

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 40
            while loop.time() < deadline:
                try:
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=deadline - loop.time(),
                    )
                except asyncio.TimeoutError:
                    break

                if isinstance(message, bytes):
                    message = message.decode(errors='replace')
                messages.append(message)
                if 'display_patient_data' in message:
                    return 0
    except Exception as exc:
        messages.append(f'{type(exc).__name__}: {exc}')

    print('Last 5 messages:')
    for message in messages:
        print(message)
    return 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(smoke()))
