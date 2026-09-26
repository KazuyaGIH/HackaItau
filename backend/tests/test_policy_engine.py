"""Policy Engine: user ∩ agent ∩ case_scope ∩ purpose ∩ resource_policy — nunca união."""

from app.core.schemas.context import CaseScope
from app.governance import policy_engine as pe
from app.governance.filters import apply_field_projection, apply_row_scope
from app.governance.loader import load_resource_policies
from app.tools.registry import TOOL_REGISTRY
from tests.conftest import PURPOSE, make_ctx


def test_allow_returns_projection_and_never(analyst, cards, scope_001):
    ctx = make_ctx(analyst, "agro_credit_risk", scope_001)
    d = pe.authorize(ctx, cards["agro_credit_risk"], TOOL_REGISTRY["get_client_financials"], {"client_id": "CLIENTE-001"})
    assert d.allowed and d.row_scope == ("CLIENTE-001",)
    assert d.field_projection and "revenue" in d.field_projection
    assert "tax_id" in d.never_fields


def test_user_without_permission_is_denied_even_if_agent_has_it(manager, cards, scope_001):
    ctx = make_ctx(manager, "agro_credit_risk", scope_001)
    d = pe.authorize(ctx, cards["agro_credit_risk"], TOOL_REGISTRY["get_client_financials"], {"client_id": "CLIENTE-001"})
    assert not d.allowed and d.reason == pe.REASON_USER and not d.security


def test_agent_without_tool_is_denied_even_if_user_has_it(analyst, cards, scope_001):
    ctx = make_ctx(analyst, "agro_structuring", scope_001)
    d = pe.authorize(ctx, cards["agro_structuring"], TOOL_REGISTRY["get_client_financials"], {"client_id": "CLIENTE-001"})
    assert not d.allowed and d.reason == pe.REASON_TOOL_NOT_ALLOWED


def test_structuring_never_gets_financials_agro_or_documents(analyst, cards, scope_001):
    card = cards["agro_structuring"]
    assert not {"client_financials", "agro_profile", "documents"} & set(card.allowed_data_domains)
    assert not {"get_client_financials", "get_agro_profile", "get_available_documents"} & set(card.tools)
    policies = load_resource_policies()
    for domain in ("client_financials", "agro_profile", "documents"):
        assert policies[domain].fields_for("agro_structuring") is None


def test_purpose_denies_domain_not_in_purpose(analyst, cards, scope_001):
    purposes = {PURPOSE: pe.PurposeSpec(description="x", allowed_data_domains=["client_profile"])}
    ctx = make_ctx(analyst, "agro_credit_risk", scope_001)
    d = pe.authorize(
        ctx,
        cards["agro_credit_risk"],
        TOOL_REGISTRY["get_client_financials"],
        {"client_id": "CLIENTE-001"},
        purposes=purposes,
    )
    assert not d.allowed and d.reason == pe.REASON_PURPOSE


def test_purpose_mismatch_between_ctx_and_scope(analyst, cards, scope_001):
    ctx = make_ctx(analyst, "agro_eligibility", scope_001, purpose="outro_purpose")
    d = pe.authorize(ctx, cards["agro_eligibility"], TOOL_REGISTRY["get_client_profile"], {"client_id": "CLIENTE-001"})
    assert not d.allowed and d.reason == pe.REASON_PURPOSE_MISMATCH


def test_out_of_scope_client_is_denied_with_security_flag(analyst, cards, scope_001):
    ctx = make_ctx(analyst, "agro_eligibility", scope_001)
    d = pe.authorize(ctx, cards["agro_eligibility"], TOOL_REGISTRY["get_client_profile"], {"client_id": "CLIENTE-999"})
    assert not d.allowed and d.reason == pe.REASON_SCOPE and d.security is True


def test_scope_with_other_client_allows_that_client_only(analyst, cards):
    scope = CaseScope(client_ids=("CLIENTE-002",), purpose=PURPOSE)
    ctx = make_ctx(analyst, "agro_eligibility", scope)
    ok = pe.authorize(ctx, cards["agro_eligibility"], TOOL_REGISTRY["get_client_profile"], {"client_id": "CLIENTE-002"})
    no = pe.authorize(ctx, cards["agro_eligibility"], TOOL_REGISTRY["get_client_profile"], {"client_id": "CLIENTE-001"})
    assert ok.allowed and not no.allowed


def test_missing_resource_policy_denies(analyst, cards, scope_001):
    ctx = make_ctx(analyst, "agro_eligibility", scope_001)
    d = pe.authorize(
        ctx, cards["agro_eligibility"], TOOL_REGISTRY["get_client_profile"], {"client_id": "CLIENTE-001"}, policies={}
    )
    assert not d.allowed and d.reason == pe.REASON_NO_POLICY


def test_deny_reason_does_not_leak_policy_details(manager, cards, scope_001):
    ctx = make_ctx(manager, "agro_credit_risk", scope_001)
    d = pe.authorize(ctx, cards["agro_credit_risk"], TOOL_REGISTRY["get_client_financials"], {"client_id": "CLIENTE-001"})
    assert d.field_projection is None and d.never_fields == [] and d.row_scope == ()


def test_row_scope_filters_other_clients_and_keeps_global_records():
    rows = [{"client_id": "CLIENTE-001", "a": 1}, {"client_id": "CLIENTE-999", "a": 2}, {"commodity": "soja"}]
    kept = apply_row_scope(rows, ("CLIENTE-001",))
    assert [r.get("client_id", "global") for r in kept] == ["CLIENTE-001", "global"]


def test_field_projection_and_never():
    rec = {"client_id": "C", "revenue": 1, "tax_id": "x", "internal_notes": "n", "ebitda": 2}
    projected, hidden = apply_field_projection(rec, ["client_id", "revenue", "tax_id"], ["tax_id", "internal_notes"])
    assert projected == {"client_id": "C", "revenue": 1}
    assert hidden == 3
    all_but_never, hidden2 = apply_field_projection(rec, None, ["tax_id"])
    assert "tax_id" not in all_but_never and hidden2 == 1
    nothing, hidden3 = apply_field_projection(rec, [], [])
    assert nothing == {} and hidden3 == 5
