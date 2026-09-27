"""Tool Registry — allowlist global (ARCHITECTURE.md §8).

Só o que está aqui existe. Não há tools de SQL, shell, Python, HTTP, browser ou filesystem.
`resolve_client` NÃO é tool: vive em governance/bootstrap_resolver.py e é inacessível a agentes.
Handlers são registrados por S1 (data/knowledge) e S2 (calc) via `register_handler`.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.schemas.tools import ToolHandler, ToolSpec, client_id_param


class ClientIdParams(BaseModel):
    client_id: str


class CommodityParams(BaseModel):
    commodity: str


class QueryParams(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    top_k: int = Field(default=3, ge=1, le=5)


class PurposeParams(BaseModel):
    purpose: str
    crop: str | None = None


class HistoricalFilters(BaseModel):
    crop: str | None = None
    region: str | None = None
    product_family: str | None = None


class AssumptionSetParams(BaseModel):
    """Premissas numéricas definidas por CÓDIGO (risk/baseline.py). Cada valor tem source_id."""

    planted_area_hectares: float
    productivity: float  # sacas/ha
    price: float  # R$/saca
    cost_per_hectare: float
    requested_amount: float
    net_debt: float
    ebitda: float
    baseline_policy: str  # "declared" | "historical"
    sources: dict[str, str]  # nome da premissa → source_id
    thresholds_source_ids: list[str] = Field(default_factory=list)


class CreditMetricsParams(BaseModel):
    assumptions: AssumptionSetParams


class StressParams(BaseModel):
    assumptions: AssumptionSetParams
    scenario_ids: list[str]  # ids de cenários definidos em policies (fixos), não pelo LLM


TOOL_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="get_client_profile",
            description="Perfil cadastral mínimo do cliente do case.",
            params_model=ClientIdParams,
            resource_domain="client_profile",
            kind="read",
            extract_client_ids=client_id_param,
            key_param="client_id",
        ),
        ToolSpec(
            name="get_client_financials",
            description="Demonstrações financeiras resumidas do cliente do case.",
            params_model=ClientIdParams,
            resource_domain="client_financials",
            kind="read",
            extract_client_ids=client_id_param,
            key_param="client_id",
        ),
        ToolSpec(
            name="get_agro_profile",
            description="Perfil agro: cultura, área, produtividade esperada e histórica, custo/ha.",
            params_model=ClientIdParams,
            resource_domain="agro_profile",
            kind="read",
            extract_client_ids=client_id_param,
            key_param="client_id",
        ),
        ToolSpec(
            name="get_market_data",
            description="Preço de referência e contexto de mercado de uma commodity.",
            params_model=CommodityParams,
            resource_domain="market_data",
            kind="read",
            key_param="commodity",
        ),
        ToolSpec(
            name="get_available_documents",
            description="Documentos disponíveis do cliente do case (conteúdo é untrusted).",
            params_model=ClientIdParams,
            resource_domain="documents",
            kind="read",
            extract_client_ids=client_id_param,
            key_param="client_id",
        ),
        ToolSpec(
            name="search_policy",
            description="Busca por palavra-chave em políticas, playbooks, catálogo e glossário internos.",
            params_model=QueryParams,
            resource_domain="knowledge",
            kind="search",
            key_param="query",
        ),
        ToolSpec(
            name="get_product_catalog",
            description="Produtos de crédito disponíveis para a finalidade.",
            params_model=PurposeParams,
            resource_domain="product_catalog",
            kind="read",
            key_param="purpose",
        ),
        ToolSpec(
            name="calculate_credit_metrics",
            description="Cálculo determinístico de receita esperada, geração de caixa, alavancagem e cobertura.",
            params_model=CreditMetricsParams,
            resource_domain="calculations",
            kind="calc",
        ),
        ToolSpec(
            name="run_stress_scenarios",
            description="Reexecuta as métricas sob cenários de stress fixos definidos em policy.",
            params_model=StressParams,
            resource_domain="calculations",
            kind="calc",
        ),
        # P1 — registrada para congelar a interface; nenhum card P0 a inclui na allowlist
        ToolSpec(
            name="get_historical_cases",
            description="(P1) Casos históricos anonimizados comparáveis.",
            params_model=HistoricalFilters,
            resource_domain="historical_cases",
            kind="read",
        ),
    ]
}

P0_TOOLS: frozenset[str] = frozenset(TOOL_REGISTRY) - {"get_historical_cases"}


def register_handler(tool_name: str, handler: ToolHandler) -> None:
    spec = TOOL_REGISTRY[tool_name]
    TOOL_REGISTRY[tool_name] = spec.model_copy(update={"handler": handler})


def get_tool(tool_name: str) -> ToolSpec:
    return TOOL_REGISTRY[tool_name]


def validate_params(tool_name: str, params: dict[str, Any]) -> BaseModel:
    return TOOL_REGISTRY[tool_name].params_model(**params)
