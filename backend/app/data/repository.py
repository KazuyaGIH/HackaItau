"""Abstração da fonte física de dados (ARCHITECTURE.md §8). Agentes nunca importam isto; só handlers de tools."""

from typing import Any, Protocol


class DataRepository(Protocol):
    def get_client(self, client_id: str) -> dict[str, Any] | None: ...

    def find_clients_exact(self, name_or_id: str) -> list[dict[str, Any]]:
        """Usado só pelo Bootstrap Resolver. Match exato por ID ou igualdade de nome normalizado. Sem wildcard."""
        ...

    def get_financials(self, client_id: str) -> dict[str, Any] | None: ...

    def get_agro_profile(self, client_id: str) -> dict[str, Any] | None: ...

    def get_market_data(self, commodity: str) -> dict[str, Any] | None: ...

    def list_documents(self, client_id: str, scenario_tags: list[str]) -> list[dict[str, Any]]:
        """Documentos do cliente; inclui os marcados com `scenario_tags` ativos (ex.: "adversarial")."""
        ...

    def list_products(self, purpose: str) -> list[dict[str, Any]]: ...

    def list_historical_cases(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """P1."""
        ...


class KnowledgeRetriever(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Devolve chunks {doc_id, chunk_index, title, text, score}."""
        ...
