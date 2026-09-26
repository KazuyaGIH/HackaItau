"""Carrega e valida os JSONs de governança e os Agent Cards. Sem lógica de decisão (isso é S1.1 policy_engine)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.schemas.agent import AgentCard
from app.core.schemas.context import UserIdentity


class ResourcePolicy(BaseModel):
    row_scope: Literal["case_client", "none"]
    fields: dict[str, list[str]] = Field(default_factory=dict)
    never: list[str] = Field(default_factory=list)

    def fields_for(self, agent_id: str) -> list[str] | None:
        """None = agente não tem entrada → deny por omissão. ["*"] = todos menos `never`."""
        return self.fields.get(agent_id) or self.fields.get("*")


class PurposeSpec(BaseModel):
    description: str
    allowed_data_domains: list[str]


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_identities() -> dict[str, UserIdentity]:
    raw = _read_json(get_settings().governance_dir / "identities.json")
    return {u["user_id"]: UserIdentity(**u) for u in raw["users"]}


@lru_cache
def load_purposes() -> dict[str, PurposeSpec]:
    raw = _read_json(get_settings().governance_dir / "purposes.json")
    return {k: PurposeSpec(**v) for k, v in raw["purposes"].items()}


@lru_cache
def load_resource_policies() -> dict[str, ResourcePolicy]:
    raw = _read_json(get_settings().governance_dir / "resource_policies.json")
    return {k: ResourcePolicy(**v) for k, v in raw.items() if k != "_meta"}


@lru_cache
def load_agent_cards() -> dict[str, AgentCard]:
    cards = {}
    for path in sorted(get_settings().agent_cards_dir.glob("*.json")):
        card = AgentCard(**_read_json(path))
        cards[card.agent_id] = card
    return cards
