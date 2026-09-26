"""Handlers das tools read/search (S1.7/S1.8). Devolvem registros BRUTOS; row/field filtering é do Gateway."""

from typing import Any

from app.tools.deps import ToolDeps
from app.tools.registry import register_handler

Records = list[dict[str, Any]]


def _as_list(record: dict[str, Any] | None) -> Records:
    return [record] if record else []


async def get_client_profile(params: dict[str, Any], deps: ToolDeps) -> Records:
    return _as_list(deps.repo.get_client(params["client_id"]))


async def get_client_financials(params: dict[str, Any], deps: ToolDeps) -> Records:
    return _as_list(deps.repo.get_financials(params["client_id"]))


async def get_agro_profile(params: dict[str, Any], deps: ToolDeps) -> Records:
    return _as_list(deps.repo.get_agro_profile(params["client_id"]))


async def get_market_data(params: dict[str, Any], deps: ToolDeps) -> Records:
    return _as_list(deps.repo.get_market_data(params["commodity"]))


async def get_available_documents(params: dict[str, Any], deps: ToolDeps) -> Records:
    return deps.repo.list_documents(params["client_id"], list(deps.scenario_tags))


async def get_product_catalog(params: dict[str, Any], deps: ToolDeps) -> Records:
    return deps.repo.list_products(params["purpose"])


async def search_policy(params: dict[str, Any], deps: ToolDeps) -> Records:
    return deps.knowledge.search(params["query"], top_k=params.get("top_k", 3))


DATA_HANDLERS = {
    "get_client_profile": get_client_profile,
    "get_client_financials": get_client_financials,
    "get_agro_profile": get_agro_profile,
    "get_market_data": get_market_data,
    "get_available_documents": get_available_documents,
    "get_product_catalog": get_product_catalog,
    "search_policy": search_policy,
}


def install_data_handlers() -> None:
    for name, handler in DATA_HANDLERS.items():
        register_handler(name, handler)
