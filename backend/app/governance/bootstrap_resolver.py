"""Bootstrap Client Resolver (ARCHITECTURE.md §9.1). Fora do Tool Registry; inacessível a agentes.

Usa SOMENTE a permissão do usuário. Devolve no máximo {client_id, name}. Não lista, não aceita wildcard/prefixo.
"""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel

from app.core.events import EventLog
from app.core.schemas.context import UserIdentity
from app.core.schemas.events import EventType
from app.data.repository import DataRepository

MIN_NAME_LEN = 6
CLIENT_ID_RE = re.compile(r"^CLIENTE-\d{3,}$")
REQUIRED_PERMISSION = "client_profile"
_WILDCARDS = ("*", "%", "?")


class ClientRef(BaseModel):
    client_id: str
    name: str


class ResolveResult(BaseModel):
    status: Literal["ok", "not_found", "ambiguous", "denied"]
    client: ClientRef | None = None
    count: int = 0
    reason: str | None = None

    @classmethod
    def ok(cls, client: ClientRef) -> "ResolveResult":
        return cls(status="ok", client=client, count=1)

    @classmethod
    def not_found(cls) -> "ResolveResult":
        return cls(status="not_found")

    @classmethod
    def ambiguous(cls, count: int) -> "ResolveResult":
        return cls(status="ambiguous", count=count)

    @classmethod
    def denied(cls, reason: str) -> "ResolveResult":
        return cls(status="denied", reason=reason)


def normalize(text: str) -> str:
    """Casefold + remove acentos + colapsa espaços/pontuação leve. Igualdade exata depois disso."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s\-]", " ", ascii_.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_client_id(ref: str) -> bool:
    return bool(CLIENT_ID_RE.match(ref.strip().upper()))


class BootstrapClientResolver:
    def __init__(self, repo: DataRepository) -> None:
        self._repo = repo

    def resolve(self, user: UserIdentity, client_ref: str | None, events: EventLog | None = None) -> ResolveResult:
        if REQUIRED_PERMISSION not in user.permissions_read:
            result = ResolveResult.denied("resource_not_authorized_for_user")
            self._audit(events, user, result)
            return result

        raw = (client_ref or "").strip()
        if not raw or any(w in raw for w in _WILDCARDS):
            result = ResolveResult.not_found()
            self._audit(events, user, result)
            return result

        if is_client_id(raw):
            ref = raw.upper()
        else:
            ref = normalize(raw)
            if len(ref) < MIN_NAME_LEN:
                result = ResolveResult.not_found()
                self._audit(events, user, result)
                return result

        matches = self._repo.find_clients_exact(ref)
        if len(matches) == 0:
            result = ResolveResult.not_found()
        elif len(matches) > 1:
            result = ResolveResult.ambiguous(count=len(matches))
        else:
            m = matches[0]
            result = ResolveResult.ok(ClientRef(client_id=m["client_id"], name=m["name"]))
        self._audit(events, user, result)
        return result

    @staticmethod
    def _audit(events: EventLog | None, user: UserIdentity, result: ResolveResult) -> None:
        if events is None:
            return
        payload = {
            "user_id": user.user_id,
            "matched": result.status == "ok",
            "ambiguous": result.status == "ambiguous",
            "denied": result.status == "denied",
        }
        if result.client:
            payload["client_id"] = result.client.client_id
        events.emit(EventType.BOOTSTRAP_RESOLVED, payload)
