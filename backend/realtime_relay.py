"""Bidirectional WebSocket relay: browser <-> FastAPI <-> Realtime API.

Responsibilities:

* Keep the provider API key server-side (never reaches the browser).
* Inject the deck-aware session.update on connect.
* Forward binary audio from the browser as ``input_audio_buffer.append``.
* Forward every Realtime event to the browser as-is (used for transcript +
  audio playback) while also intercepting ``response.function_call_arguments.done``
  to run the tool locally and emit frontend-friendly events
  (``slide_change``, ``cursor_move``).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from config import RealtimeConfig
from session_config import build_session_update
from slide_functions import SlideNavigator, handle_function_call
from slide_store import Deck

logger = logging.getLogger(__name__)


class RealtimeRelay:
    def __init__(self, deck: Deck, rt: RealtimeConfig) -> None:
        self.deck = deck
        self.rt = rt
        self.navigator = SlideNavigator(deck["id"])

    def _headers(self) -> dict[str, str]:
        if self.rt.auth_header == "api-key":
            return {"api-key": self.rt.api_key}
        return {
            "Authorization": f"Bearer {self.rt.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

    async def relay(self, browser_ws: WebSocket) -> None:
        headers = self._headers()
        # ``websockets<14`` (this project pins 13.1) exposes the legacy client
        # as the top-level ``websockets.connect`` and uses ``extra_headers``.
        # The newer asyncio client at ``websockets.asyncio.client.connect``
        # uses ``additional_headers``. We use the legacy one here because it
        # is what's installed, and the legacy client silently mis-forwards
        # ``additional_headers`` into ``loop.create_connection()``.
        try:
            async with websockets.connect(
                self.rt.url,
                extra_headers=headers,
                max_size=16 * 1024 * 1024,
            ) as provider_ws:
                logger.info("Connected to Realtime (%s)", self.rt.provider)
                await provider_ws.send(
                    json.dumps(build_session_update(self.deck["slides"]))
                )

                browser_task = asyncio.create_task(
                    self._browser_to_provider(browser_ws, provider_ws)
                )
                provider_task = asyncio.create_task(
                    self._provider_to_browser(provider_ws, browser_ws)
                )

                done, pending = await asyncio.wait(
                    [browser_task, provider_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    if task.exception():
                        logger.error("Relay task error: %s", task.exception())
        except WebSocketDisconnect:
            logger.info("Browser disconnected before provider handshake")
        except Exception as exc:
            logger.exception("Relay failure: %s", exc)
            await self._safe_close(browser_ws, code=1011, reason="relay_error")

    async def _browser_to_provider(
        self,
        browser_ws: WebSocket,
        provider_ws: websockets.WebSocketClientProtocol,
    ) -> None:
        try:
            while True:
                message = await browser_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    return

                audio: Optional[bytes] = message.get("bytes")
                text: Optional[str] = message.get("text")

                if audio is not None:
                    encoded = base64.b64encode(audio).decode("ascii")
                    await provider_ws.send(
                        json.dumps({"type": "input_audio_buffer.append", "audio": encoded})
                    )
                elif text is not None:
                    if await self._intercept_client_event(text, provider_ws, browser_ws):
                        continue
                    await provider_ws.send(text)
        except WebSocketDisconnect:
            return
        except ConnectionClosed:
            return
        except Exception as exc:
            logger.exception("browser->provider error: %s", exc)

    async def _intercept_client_event(
        self,
        text: str,
        provider_ws: websockets.WebSocketClientProtocol,
        browser_ws: WebSocket,
    ) -> bool:
        """Return True if the message was a client-only control event."""

        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return False

        etype = event.get("type", "")
        if not isinstance(etype, str) or not etype.startswith("client."):
            return False

        if etype == "client.manual_slide":
            new_index = self.navigator.go_to(int(event.get("index", 0)))
            slide = self.navigator.current()
            await browser_ws.send_text(
                json.dumps(
                    {"type": "slide_change", "new_index": new_index, "slide": slide}
                )
            )
            narration_hint = (
                f"The user manually navigated to slide {new_index + 1}: "
                f'"{slide.get("title", "")}". Run the per-slide sequence from '
                "the start: point_at('title') with a one-sentence framing, then "
                "narrate EVERY bullet in order beginning with bullet_0, then "
                "continue the flow per your instructions."
            )
            await provider_ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": narration_hint}],
                        },
                    }
                )
            )
            await provider_ws.send(json.dumps({"type": "response.create"}))
            return True

        return False

    async def _provider_to_browser(
        self,
        provider_ws: websockets.WebSocketClientProtocol,
        browser_ws: WebSocket,
    ) -> None:
        try:
            async for raw in provider_ws:
                try:
                    event: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "response.function_call_arguments.done":
                    await self._handle_function_call(event, provider_ws, browser_ws)
                    continue

                await browser_ws.send_text(raw)
        except ConnectionClosed:
            return
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.exception("provider->browser error: %s", exc)

    async def _handle_function_call(
        self,
        event: dict[str, Any],
        provider_ws: websockets.WebSocketClientProtocol,
        browser_ws: WebSocket,
    ) -> None:
        name = event.get("name", "")
        arguments = event.get("arguments", "{}")
        call_id = event.get("call_id", "")

        result = await handle_function_call(name, arguments, self.navigator)

        browser_event = result.get("browser_event")
        if browser_event is not None:
            await browser_ws.send_text(json.dumps(browser_event))

        await provider_ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result.get("tool_output", {})),
                    },
                }
            )
        )
        await provider_ws.send(json.dumps({"type": "response.create"}))

        logger.info("Function %s(%s) handled", name, arguments)

    async def _safe_close(self, ws: WebSocket, code: int, reason: str) -> None:
        try:
            await ws.close(code=code, reason=reason)
        except Exception:
            pass
