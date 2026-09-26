"""Smoke tests do kernel: contratos congelados (ARCHITECTURE.md §19) e invariantes estruturais."""

import pytest
from pydantic import ValidationError

from app.core.schemas import (
    CaseScope,
    EvidenceBundle,
    ExecutionContext,
    StructuringOutput,
    UserIdentity,
)
from app.core.schemas.evidence import EVIDENCE_ID_RE, calculation_id, knowledge_id, output_id, source_id
from app.core.schemas.outputs import OUTPUT_SCHEMAS
from app.governance.loader import load_agent_cards, load_identities, load_purposes, load_resource_policies
from app.tools.registry import P0_TOOLS, TOOL_REGISTRY

USER = UserIdentity(user_id="u", name="n", role="r", permissions_read=("client_profile",))


def test_case_scope_is_frozen_and_requires_client():
    scope = CaseScope(client_ids=("CLIENTE-001",), purpose="credit_analysis_agro")
    with pytest.raises(ValidationError):
        scope.client_ids = ("CLIENTE-999",)  # type: ignore[misc]
    with pytest.raises(ValidationError):
        CaseScope(client_ids=(), purpose="credit_analysis_agro")


def test_execution_context_requires_scope():
    with pytest.raises(ValidationError):
        ExecutionContext(user=USER, case_id="c", task_id="t", agent_id="a", purpose="p")  # type: ignore[call-arg]


def test_evidence_id_helpers_match_regex():
    for eid in (
        source_id("agro_profile", "CLIENTE-001"),
        knowledge_id("POL-CRED-002", 1),
        calculation_id("credit_metrics", 1),
        output_id("agro_credit_risk", 2),
    ):
        assert EVIDENCE_ID_RE.match(eid), eid
    assert not EVIDENCE_ID_RE.match("FAKE-123")
    assert EvidenceBundle().allowed_ids() == set()


ALT = {
    "id": "ALT-1",
    "name": "x",
    "product_id": "PROD-CUSTEIO-01",
    "amount": 1.0,
    "tenor_months": 12,
    "amortization": "bullet_post_harvest",
    "guarantees": [],
    "conditions": [],
    "rationale": "r",
    "when_it_fits": "w",
    "advantages": [],
    "risks": [],
    "trade_offs": [],
}


def test_structuring_requires_2_to_3_alternatives_and_no_preference():
    StructuringOutput(alternatives=[ALT, {**ALT, "id": "ALT-2"}])
    with pytest.raises(ValidationError):
        StructuringOutput(alternatives=[ALT])
    with pytest.raises(ValidationError):
        StructuringOutput(alternatives=[{**ALT, "id": f"ALT-{i}"} for i in range(4)])
    with pytest.raises(ValidationError):
        StructuringOutput(alternatives=[{**ALT, "preferred_for_discussion": True}, {**ALT, "id": "ALT-2"}])
    with pytest.raises(ValidationError):
        StructuringOutput(alternatives=[ALT, {**ALT, "id": "ALT-2"}], preferred_for_discussion="ALT-1")


def test_registry_has_exactly_p0_tools_and_no_resolve_client():
    assert P0_TOOLS == {
        "get_client_profile",
        "get_client_financials",
        "get_agro_profile",
        "get_market_data",
        "get_available_documents",
        "search_policy",
        "get_product_catalog",
        "calculate_credit_metrics",
        "run_stress_scenarios",
    }
    assert "resolve_client" not in TOOL_REGISTRY


def test_agent_cards_are_consistent_with_registry_policies_and_schemas():
    cards = load_agent_cards()
    policies = load_resource_policies()
    assert set(cards) == {"agro_eligibility", "agro_credit_risk", "agro_structuring", "credit_review"}
    for card in cards.values():
        assert set(card.tools) <= P0_TOOLS, card.agent_id
        assert set(card.allowed_data_domains) <= set(policies), card.agent_id
        assert card.output_schema in OUTPUT_SCHEMAS, card.agent_id
        for spec in card.required_data:
            assert spec.tool in card.tools, (card.agent_id, spec.tool)
            assert TOOL_REGISTRY[spec.tool].resource_domain in card.allowed_data_domains, (card.agent_id, spec.tool)
        for tool in card.tools:
            domain = TOOL_REGISTRY[tool].resource_domain
            assert domain in card.allowed_data_domains, (card.agent_id, tool)
            assert policies[domain].fields_for(card.agent_id) is not None, (card.agent_id, domain)


def test_structuring_card_has_least_privilege():
    card = load_agent_cards()["agro_structuring"]
    assert card.allowed_data_domains == ["product_catalog", "knowledge"]
    for domain in ("client_financials", "agro_profile", "documents"):
        assert domain not in card.allowed_data_domains
        assert load_resource_policies()[domain].fields_for("agro_structuring") is None


def test_governance_json_loads():
    assert "analyst-001" in load_identities()
    assert "credit_analysis_agro" in load_purposes()
    for name, policy in load_resource_policies().items():
        assert policy.row_scope in {"case_client", "none"}, name


def test_mock_data_is_flagged_and_has_demo_values(mock_data, golden_case):
    for name, payload in mock_data.items():
        assert payload["_meta"]["mock"] is True, name
    agro = {r["client_id"]: r for r in mock_data["agro_profiles"]["records"]}
    exp = golden_case["expected"]["agro"]
    assert agro["CLIENTE-001"]["expected_productivity"] == exp["expected_productivity"] == 61
    assert agro["CLIENTE-001"]["historical_productivity"] == exp["historical_productivity"] == 58
    assert agro["CLIENTE-001"]["cost_per_hectare"] == exp["cost_per_hectare"]
    assert "CLIENTE-999" in agro and "CLIENTE-999" in {r["client_id"] for r in mock_data["clients"]["records"]}
    docs = {d["doc_id"]: d for d in mock_data["documents"]["records"]}
    assert "adversarial" in docs["DOC-ADV-001"]["scenario_tags"]
    assert "CLIENTE-999" in docs["DOC-ADV-001"]["content"]


def test_mock_records_contain_never_fields_for_filter_tests(mock_data):
    policies = load_resource_policies()
    domain_to_file = {
        "client_profile": "clients",
        "client_financials": "financials",
        "agro_profile": "agro_profiles",
        "market_data": "market_data",
        "documents": "documents",
        "product_catalog": "products",
    }
    for domain, file in domain_to_file.items():
        record = mock_data[file]["records"][0]
        for never in policies[domain].never:
            assert never in record, (domain, never)
