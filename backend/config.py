"""Central configuration. All secrets are read from the environment.

Two providers are supported and auto-selected per call site:

* Chat completions (slide generation, file analysis): Azure OpenAI via the
  OpenAI SDK with ``base_url`` pointing at the Azure v1 compatibility
  endpoint (``…/openai/v1/``). This lets the OpenAI SDK target Azure with
  the deployment name used as ``model`` and no manual ``api-version``.
* Realtime voice: Azure OpenAI Realtime if ``AZURE_OPENAI_REALTIME_ENDPOINT``
  is set, otherwise falls back to ``wss://api.openai.com/v1/realtime``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


# GPT-5.x chat deployments live on the Cognitive Services "v1" resource
# (the same resource that hosts the realtime endpoint), not on the Foundry
# project resource. When the chat deployment is one of these, chat requests
# are routed to the realtime resource's /openai/v1/ path using the realtime
# API key.
AZURE_V1_MODELS = {"gpt-5.2-chat", "gpt-5.3-chat", "gpt-5.4-mini"}


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy backend/.env.example to backend/.env and fill it in."
        )
    return value


@dataclass(frozen=True)
class AzureChatConfig:
    endpoint: str
    api_key: str
    deployment: str


@dataclass(frozen=True)
class RealtimeConfig:
    provider: str  # "azure" | "openai"
    url: str
    api_key: str
    auth_header: str  # "api-key" for Azure, "Authorization" for OpenAI


def _build_azure_ws_url(endpoint: str, api_version: str, deployment: str) -> str:
    """Normalize an Azure realtime endpoint to a ``wss://`` URL with required
    query params. If the caller has already baked ``api-version`` and
    ``deployment`` into the endpoint (as the Azure portal often does), those
    values are trusted verbatim — we only fill in whichever are missing.
    """

    base = endpoint.strip().rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]

    if "?" in base:
        path, _, query = base.partition("?")
    else:
        path, query = base, ""

    params = [p for p in query.split("&") if p]
    have_keys = {p.split("=", 1)[0] for p in params}
    if "api-version" not in have_keys:
        params.append(f"api-version={api_version}")
    if "deployment" not in have_keys:
        params.append(f"deployment={deployment}")

    return f"{path}?{'&'.join(params)}"


def _normalize_chat_endpoint(raw: str) -> str:
    """Append ``/openai/v1/`` unless it's already present. The v1 compatibility
    path lets the OpenAI SDK target Azure (classic resources and Foundry
    projects alike) without a manual ``api-version`` query param.
    """

    endpoint = raw.strip().rstrip("/")
    if not endpoint.endswith("openai/v1"):
        endpoint = f"{endpoint}/openai/v1"
    return f"{endpoint}/"


def _resource_base(endpoint: str) -> str:
    """Extract the scheme + host (``https://<host>``) from any Azure
    endpoint variant (chat, realtime, https or wss)."""

    normalized = endpoint.strip()
    if normalized.startswith("wss://"):
        normalized = "https://" + normalized[len("wss://") :]
    elif normalized.startswith("ws://"):
        normalized = "http://" + normalized[len("ws://") :]

    parsed = urlparse(normalized)
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    if not host:
        raise RuntimeError(f"Could not parse Azure host from: {endpoint!r}")
    return f"{scheme}://{host}"


def azure_chat_config() -> AzureChatConfig:
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini").strip()

    if deployment in AZURE_V1_MODELS:
        rt_endpoint = _require("AZURE_OPENAI_REALTIME_ENDPOINT")
        rt_key = (
            os.environ.get("AZURE_OPENAI_REALTIME_API_KEY", "").strip()
            or _require("AZURE_OPENAI_API_KEY")
        )
        endpoint = f"{_resource_base(rt_endpoint)}/openai/v1/"
        return AzureChatConfig(
            endpoint=endpoint,
            api_key=rt_key,
            deployment=deployment,
        )

    return AzureChatConfig(
        endpoint=_normalize_chat_endpoint(_require("AZURE_OPENAI_ENDPOINT")),
        api_key=_require("AZURE_OPENAI_API_KEY"),
        deployment=deployment,
    )


def realtime_config() -> RealtimeConfig:
    azure_endpoint = os.environ.get("AZURE_OPENAI_REALTIME_ENDPOINT", "").strip()
    # Realtime is commonly hosted on a separate Azure resource (different
    # region). Prefer a dedicated key if provided; otherwise fall back to the
    # chat resource's key for the single-resource setup.
    azure_key = (
        os.environ.get("AZURE_OPENAI_REALTIME_API_KEY", "").strip()
        or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    )
    azure_deployment = os.environ.get(
        "AZURE_OPENAI_REALTIME_DEPLOYMENT", "gpt-4o-realtime-preview"
    )
    api_version = os.environ.get(
        "AZURE_OPENAI_REALTIME_API_VERSION", "2024-10-01-preview"
    )

    if azure_endpoint and azure_key:
        url = _build_azure_ws_url(azure_endpoint, api_version, azure_deployment)
        return RealtimeConfig(
            provider="azure",
            url=url,
            api_key=azure_key,
            auth_header="api-key",
        )

    openai_key = _require("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview")
    return RealtimeConfig(
        provider="openai",
        url=f"wss://api.openai.com/v1/realtime?model={model}",
        api_key=openai_key,
        auth_header="Authorization",
    )


VOICE: str = os.environ.get("VOICE", "alloy")

ALLOWED_ORIGIN: str = os.environ.get("ALLOWED_ORIGIN", "http://localhost:5173")


TURN_DETECTION: dict = {
    "type": "server_vad",
    "threshold": 0.5,
    "silence_duration_ms": 700,
    "create_response": True,
}
