"""JsonMockRepository: implementação P0 de DataRepository sobre data/mock/*.json (ARCHITECTURE.md §8)."""

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.governance.bootstrap_resolver import normalize

Record = dict[str, Any]


class JsonMockRepository:
    def __init__(self, mock_dir: Path | None = None) -> None:
        self._dir = mock_dir or get_settings().mock_data_dir
        self._cache: dict[str, list[Record]] = {}

    def _records(self, name: str) -> list[Record]:
        if name not in self._cache:
            raw = json.loads((self._dir / f"{name}.json").read_text(encoding="utf-8"))
            if raw.get("_meta", {}).get("mock") is not True:
                raise ValueError(f"{name}.json sem _meta.mock=true — só dados fictícios são aceitos no P0")
            self._cache[name] = [dict(r) for r in raw["records"]]
        return self._cache[name]

    @staticmethod
    def _one(records: list[Record], key: str, value: str) -> Record | None:
        for r in records:
            if r.get(key) == value:
                return dict(r)
        return None

    def get_client(self, client_id: str) -> Record | None:
        return self._one(self._records("clients"), "client_id", client_id)

    def find_clients_exact(self, name_or_id: str) -> list[Record]:
        ref_id = name_or_id.strip().upper()
        ref_name = normalize(name_or_id)
        out = []
        for r in self._records("clients"):
            if r["client_id"].upper() == ref_id or normalize(r["name"]) == ref_name:
                out.append({"client_id": r["client_id"], "name": r["name"]})
        return out

    def get_financials(self, client_id: str) -> Record | None:
        return self._one(self._records("financials"), "client_id", client_id)

    def get_agro_profile(self, client_id: str) -> Record | None:
        return self._one(self._records("agro_profiles"), "client_id", client_id)

    def get_market_data(self, commodity: str) -> Record | None:
        return self._one(self._records("market_data"), "commodity", commodity.strip().lower())

    def list_documents(self, client_id: str, scenario_tags: list[str]) -> list[Record]:
        active = set(scenario_tags)
        out = []
        for r in self._records("documents"):
            if r.get("client_id") != client_id:
                continue
            tags = set(r.get("scenario_tags", []))
            if tags and not tags & active:
                continue
            out.append(dict(r))
        return out

    def list_products(self, purpose: str) -> list[Record]:
        return [dict(r) for r in self._records("products") if r.get("purpose") == purpose]

    def list_historical_cases(self, filters: dict[str, Any]) -> list[Record]:
        return []  # P1
