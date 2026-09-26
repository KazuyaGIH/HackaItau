"""Tool Gateway: única porta de dados; row/field/never; injection guard marca mas não autoriza nada."""

from app.core.schemas.context import CaseScope
from app.core.schemas.events import EventType, SecurityEventKind
from app.governance import policy_engine as pe
from app.tools.registry import P0_TOOLS, TOOL_REGISTRY
from tests.conftest import PURPOSE


def _events(tb, type_):
    return tb.events.of_type(type_)


async def test_row_scope_never_returns_other_client(toolbox_factory):
    tb = toolbox_factory("agro_eligibility")
    res = await tb.call("get_client_profile", client_id="CLIENTE-001")
    assert res.ok and [s.data["client_id"] for s in res.sources] == ["CLIENTE-001"]
    assert res.sources[0].id == "SRC-CLIENT-PROFILE-CLIENTE-001"

    denied = await tb.call("get_client_profile", client_id="CLIENTE-999")
    assert not denied.ok and denied.reason == pe.REASON_SCOPE and denied.sources == []
    sec = _events(tb, EventType.SECURITY_EVENT)
    assert sec and sec[-1].payload["kind"] == SecurityEventKind.SCOPE_VIOLATION_BLOCKED.value
    assert sec[-1].payload["permissions_changed"] is False
    assert _events(tb, EventType.PERMISSION_DENIED)


async def test_field_projection_and_never_fields_applied(toolbox_factory, mock_data):
    tb = toolbox_factory("agro_credit_risk")
    res = await tb.call("get_client_financials", client_id="CLIENTE-001")
    assert res.ok and len(res.sources) == 1
    data = res.sources[0].data
    assert "revenue" in data and "tax_id" not in data and "internal_notes" not in data
    raw = next(r for r in mock_data["financials"]["records"] if r["client_id"] == "CLIENTE-001")
    assert res.sources[0].fields_hidden == len(raw) - len(data) > 0
    called = _events(tb, EventType.TOOL_CALLED)
    assert called[-1].payload["fields_hidden"] == res.sources[0].fields_hidden


async def test_eligibility_never_sees_financial_numbers_in_agro_profile(toolbox_factory):
    tb = toolbox_factory("agro_eligibility")
    res = await tb.call("get_agro_profile", client_id="CLIENTE-001")
    data = res.sources[0].data
    assert "planted_area_hectares" in data
    assert not {"expected_productivity_sc_ha", "cost_per_hectare", "field_notes"} & set(data)


async def test_structuring_cannot_pull_financials_through_gateway(toolbox_factory):
    tb = toolbox_factory("agro_structuring")
    res = await tb.call("get_client_financials", client_id="CLIENTE-001")
    assert not res.ok and res.reason == pe.REASON_TOOL_NOT_ALLOWED and res.sources == []
    assert tb.evidence.ids() == set()
    ok = await tb.call("get_product_catalog", purpose="custeio")
    assert ok.ok and all("internal_margin_target" not in s.data for s in ok.sources)


async def test_manager_without_financials_permission_is_denied(toolbox_factory, manager):
    tb = toolbox_factory("agro_credit_risk", user=manager)
    res = await tb.call("get_client_financials", client_id="CLIENTE-001")
    assert not res.ok and res.reason == pe.REASON_USER


async def test_adversarial_document_is_flagged_and_probe_denied(toolbox_factory):
    tb = toolbox_factory("agro_eligibility", adversarial=True)
    res = await tb.call("get_available_documents", client_id="CLIENTE-001")
    assert res.ok
    adv = next(s for s in res.sources if s.id == "SRC-DOCUMENTS-DOC-ADV-001")
    assert adv.flagged and adv.out_of_scope_refs == ["CLIENTE-999"]
    assert all(s.data["client_id"] == "CLIENTE-001" for s in res.sources)

    kinds = [e.payload["kind"] for e in _events(tb, EventType.SECURITY_EVENT)]
    assert SecurityEventKind.INJECTION_SUSPECTED.value in kinds
    assert SecurityEventKind.SCOPE_VIOLATION_BLOCKED.value in kinds
    probe = [e for e in _events(tb, EventType.PERMISSION_DENIED) if e.payload.get("probe")]
    assert probe and probe[0].payload["resource_key"] == "CLIENTE-999"
    assert probe[0].payload["reason"] == pe.REASON_SCOPE
    # nenhum dado do CLIENTE-999 entrou no registro de evidências
    assert all("CLIENTE-999" not in i for i in tb.evidence.ids())


async def test_without_adversarial_tag_document_is_absent(toolbox_factory):
    tb = toolbox_factory("agro_eligibility")
    res = await tb.call("get_available_documents", client_id="CLIENTE-001")
    assert res.ok and all(s.id != "SRC-DOCUMENTS-DOC-ADV-001" for s in res.sources)
    assert not _events(tb, EventType.SECURITY_EVENT)


async def test_probe_is_audited_even_without_injection(toolbox_factory):
    tb = toolbox_factory("agro_credit_risk")
    d = tb.probe("CLIENTE-999")
    assert not d.allowed and d.security
    assert _events(tb, EventType.PERMISSION_DENIED)[-1].payload["probe"] is True


async def test_knowledge_chunks_have_kb_ids(toolbox_factory):
    tb = toolbox_factory("credit_review")
    res = await tb.call("search_policy", query="produtividade histórica premissa")
    assert res.ok and res.sources
    assert all(s.id.startswith("KB-") and s.kind == "knowledge" for s in res.sources)
    assert tb.evidence.get(res.sources[0].id) is not None


async def test_invalid_params_and_unknown_tool_are_denied(toolbox_factory):
    tb = toolbox_factory("agro_eligibility")
    assert (await tb.call("get_client_profile")).reason == "invalid_params"
    assert (await tb.call("run_sql", q="select 1")).reason == "unknown_tool"
    assert "resolve_client" not in TOOL_REGISTRY and "get_historical_cases" not in P0_TOOLS


async def test_scope_purpose_mismatch_blocks_everything(toolbox_factory):
    other = CaseScope(client_ids=("CLIENTE-001",), purpose="outro")
    tb = toolbox_factory("agro_eligibility", scope=other)
    res = await tb.call("get_client_profile", client_id="CLIENTE-001")
    assert not res.ok and res.reason == pe.REASON_PURPOSE_MISMATCH
    assert tb.ctx.purpose == PURPOSE
