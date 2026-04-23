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

        # Before creating the next response, tell the model EXACTLY what to do
        # next based on the tool that just fired and the current deck position.
        # Without this nudge the model tends to produce short responses and
        # stop partway through the per-slide sequence.
        hint = self._next_step_hint(name, arguments)
        response_event: dict[str, Any] = {"type": "response.create"}
        if hint:
            response_event["response"] = {"instructions": hint}
        await provider_ws.send(json.dumps(response_event))

        logger.info("Function %s(%s) handled", name, arguments)

    def _next_step_hint(self, name: str, arguments: str) -> Optional[str]:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        slide = self.navigator.current()
        bullets = slide.get("bullets") or []
        n_bullets = len(bullets)
        cur_idx = self.navigator.index
        last_idx = self.navigator.last_index
        is_last_slide = cur_idx >= last_idx

        if name == "point_at":
            target = str(args.get("target", ""))
            if target == "title":
                if n_bullets == 0:
                    return None
                return (
                    "You just pointed at the title. Say ONE short sentence "
                    "framing this slide (do not read the title back), then "
                    "immediately call point_at('bullet_0') and narrate "
                    "bullet_0 in 1-2 sentences that expand on its detail "
                    "with a concrete example or implication."
                )
            if target.startswith("bullet_"):
                try:
                    n = int(target.split("_", 1)[1])
                except ValueError:
                    return None
                if n + 1 < n_bullets:
                    return (
                        f"You just pointed at bullet_{n} and narrated it. "
                        f"Do NOT stop. Immediately call point_at('bullet_{n + 1}') "
                        f"and narrate bullet_{n + 1} in 1-2 sentences. "
                        f"Remaining bullets on this slide: "
                        f"{', '.join(f'bullet_{i}' for i in range(n + 1, n_bullets))}."
                    )
                # Finished the last bullet on this slide.
                if not is_last_slide:
                    return (
                        f"You just narrated the LAST bullet on slide "
                        f"{cur_idx + 1}. Immediately call point_at('next_button') "
                        f"and then change_slide('next'). Do not pause."
                    )
                return (
                    "You just narrated the last bullet on the FINAL slide. "
                    "Wrap up with one short synthesizing sentence and invite "
                    "questions. Do NOT call change_slide."
                )
            if target == "next_button":
                return (
                    "You just pointed at the next button. Immediately call "
                    "change_slide('next'). Do not say anything between the "
                    "two calls."
                )
            if target == "prev_button":
                return (
                    "You just pointed at the prev button. Immediately call "
                    "change_slide('prev')."
                )
            return None

        if name in ("change_slide", "go_to_slide"):
            if is_last_slide:
                return (
                    f"You are now on the FINAL slide (slide {cur_idx + 1} of "
                    f"{last_idx + 1}). Run the per-slide sequence: "
                    f"point_at('title') with a one-sentence framing, then "
                    f"narrate every bullet in order starting with bullet_0. "
                    f"After the last bullet, wrap with one synthesizing "
                    f"sentence and invite questions. Do NOT call change_slide."
                )
            return (
                f"You are now on slide {cur_idx + 1} of {last_idx + 1}. "
                f"Run the per-slide sequence WITHOUT stopping: "
                f"point_at('title') with a one-sentence framing, then for "
                f"each bullet in order (bullet_0 first) call point_at and "
                f"narrate in 1-2 sentences. After the final bullet, call "
                f"point_at('next_button') and change_slide('next')."
            )

        if name == "download_deck":
            return (
                "You just triggered the PDF download. Confirm in one short "
                "sentence, then resume the presentation flow from where you "
                "left off."
            )

        return None

    async def _safe_close(self, ws: WebSocket, code: int, reason: str) -> None:
        try:
            await ws.close(code=code, reason=reason)
        except Exception:
            pass
