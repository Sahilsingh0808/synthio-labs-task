"""OpenAI SDK client wired to Azure via ``base_url``.

Points at the Azure v1 compatibility endpoint (``…/openai/v1/``). In that
mode, the OpenAI SDK talks to Azure using the deployment name in the
``model`` field, with no manual ``api-version`` handling required.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from config import azure_chat_config


def _is_gpt5_or_o_series(model_name: str) -> bool:
    m = (model_name or "").lower()
    return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3")


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    cfg = azure_chat_config()
    # Endpoint is normalized to ``/openai/v1/`` in config.py — the v1
    # compatibility path rejects ``api-version`` and derives it from the
    # URL itself, so we intentionally omit ``default_query``.
    return OpenAI(base_url=cfg.endpoint, api_key=cfg.api_key)


def chat_deployment() -> str:
    return azure_chat_config().deployment


def token_kwargs(max_tokens: int, model: str | None = None) -> dict:
    """Return the correct token-limit kwarg for the active deployment."""

    deployment = model or chat_deployment()
    if _is_gpt5_or_o_series(deployment):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}
