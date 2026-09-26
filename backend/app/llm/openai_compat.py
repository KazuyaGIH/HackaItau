"""Provider OpenAI-compatible (chat/completions, json mode). Único módulo que toca a rede para LLM.

A chave vem de Settings e só entra no header Authorization. Antes de enviar, verifica que nenhum
valor secreto aparece nas mensagens (defesa em profundidade: ARCHITECTURE.md §11.5).
"""

import time

import httpx
from pydantic import BaseModel

from app.core.schemas.agent import LLMUsage
from app.llm.provider import LLMResponse, Message, ToolSchema


class LLMError(Exception):
    """Falha de transporte/provider. O runtime decide entre erro e ScriptedFallback."""


class SecretInPromptError(LLMError):
    """Um valor secreto apareceria no prompt. Nunca enviado."""


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        secret_values: list[str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY ausente")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._timeout = timeout_seconds
        self._secrets = [s for s in secret_values if s]
        self._transport = transport

    def _check_secrets(self, messages: list[Message]) -> None:
        for m in messages:
            for s in self._secrets:
                if s in m.content:
                    raise SecretInPromptError("secret detectado no prompt; chamada bloqueada")

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        tools: list[ToolSchema] | None = None,
    ) -> LLMResponse:
        if tools:
            raise LLMError("tool-calling dinâmico é P1; não habilitado")
        self._check_secrets(messages)
        body: dict = {
            "model": model,
            "temperature": temperature,
            "messages": [m.model_dump() for m in messages],
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                resp = await client.post(self._url, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"provider indisponível: {type(exc).__name__}") from exc
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code >= 400:
            raise LLMError(f"provider respondeu HTTP {resp.status_code}")

        data = resp.json()
        try:
            content = data["choices"][0]["message"].get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("resposta do provider sem choices[0].message") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                model=data.get("model", model),
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
                latency_ms=latency,
            ),
        )
