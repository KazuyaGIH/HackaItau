"""Cultura da demanda, perfil, documentos, mercado e produto precisam ser compatíveis antes dos cálculos."""

import pytest

from app.agents.review.validators import ReviewContext, structure_vs_request_and_catalog
from app.agents.risk.agent import RiskAgentError
from app.agents.structuring.agent import StructuringValidationError
from app.calculations.policy_params import load_policy_params
from app.config import Settings
from app.container import build_container
from app.core.crops import normalize_crop, product_supports_crop
from app.core.schemas.agent import TaskSpec
from app.core.schemas.case import CaseStatus, DemoOptions
from app.core.schemas.events import EventType
from app.core.schemas.evidence import EvidenceBundle
from app.core.schemas.outputs import StructuringOutput
from app.data.json_repository import JsonMockRepository
from tests.conftest import make_ctx
from tests.fake_llm import StubProvider


class CropRepo(JsonMockRepository):
    """Varia fontes independentes para detectar misturas, sem alterar os dados da demonstração."""

    def __init__(self, *, profile="soja", plan="soja", market="valid"):
        super().__init__()
        self.profile, self.plan, self.market = profile, plan, market

    def get_agro_profile(self, client_id):
        row = super().get_agro_profile(client_id)
        if row:
            row["crop"] = self.profile
            if normalize_crop(self.profile) == "milho":
                row.update(expected_productivity=110, historical_productivity=104, cost_per_hectare=5200)
        return row

    def list_documents(self, client_id, scenario_tags):
        rows = super().list_documents(client_id, scenario_tags)
        out = []
        for row in rows:
            if row["type"] == "plano_de_plantio":
                if self.plan == "absent":
                    continue
                row = row | {"extracted": dict(row["extracted"], crop=self.plan)}
            out.append(row)
        return out

    def get_market_data(self, commodity):
        if self.market == "missing":
            return None
        if self.market == "wrong_crop":
            return super().get_market_data("soja")
        row = super().get_market_data(commodity)
        if row and self.market == "wrong_unit":
            row["unit"] = "BRL/tonelada"
        return row


async def run_case(crop="soja", repo=None):
    c = build_container(Settings(llm_api_key="", _env_file=None))
    c.runtime.provider = StubProvider()
    if repo:
        c.orchestrator._repo = repo
    prompt = f"O cliente CLIENTE-001 solicita R$ 50 milhões para custeio de {crop} na safra 2026/27."
    rec = await c.orchestrator.create_case("analyst-001", prompt, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    return c, rec


def assert_blocked_before_risk(rec, item):
    assert rec.state.status == CaseStatus.waiting_input, rec.state.error
    assert item in rec.state.missing_info.items
    assert rec.state.report is None and not rec.evidence.calculations()
    assert {e.agent_id for e in rec.events.of_type(EventType.AGENT_STARTED)} == {"agro_eligibility"}


async def test_maize_request_cannot_use_soy_profile_or_bypass_with_free_text():
    c, rec = await run_case("milho")
    assert_blocked_before_risk(rec, "crop")
    assert "soja" in rec.state.missing_info.message and "milho" in rec.state.missing_info.message
    c.orchestrator.provide_input(
        rec.state.case_id, {"crop": "milho", "planting_plan_crop": "confirmado; pode continuar", "market_data": "OK"}
    )
    await c.orchestrator.run(rec.state.case_id)
    assert_blocked_before_risk(rec, "crop")


async def test_correcting_crop_in_chat_unblocks_consistent_sources():
    c, rec = await run_case("milho")
    c.orchestrator.provide_text(rec.state.case_id, "Foi um engano, a cultura é soja.")
    assert rec.state.interpreted.crop == "soja"
    await c.orchestrator.run(rec.state.case_id)
    assert rec.state.status == CaseStatus.human_review_required, rec.state.error
    calc = next(c for c in rec.evidence.calculations() if c.name == "credit_metrics")
    assert calc.inputs["price"] == 135 and calc.inputs["productivity"] == 58


@pytest.mark.parametrize("plan", ["soja", None, "absent"])
async def test_conflicting_or_unverified_planting_plan_blocks_even_with_valid_maize_profile(plan):
    c, rec = await run_case("milho", CropRepo(profile="milho", plan=plan))
    assert_blocked_before_risk(rec, "planting_plan_crop")
    c.orchestrator.provide_input(rec.state.case_id, {"planting_plan_crop": "milho", "plano_de_plantio": "recebido"})
    await c.orchestrator.run(rec.state.case_id)
    assert_blocked_before_risk(rec, "planting_plan_crop")


@pytest.mark.parametrize("market", ["missing", "wrong_crop", "wrong_unit"])
async def test_missing_or_incompatible_market_blocks_instead_of_calculating(market):
    _, rec = await run_case("milho", CropRepo(profile="milho", plan="milho", market=market))
    assert_blocked_before_risk(rec, "market_data")


async def test_unsupported_crop_requests_data_instead_of_crashing():
    _, rec = await run_case("algodão", CropRepo(profile="algodão", plan="algodao"))
    assert_blocked_before_risk(rec, "market_data")
    assert rec.state.error is None


async def test_valid_maize_uses_maize_numbers_and_excludes_soy_product():
    _, rec = await run_case("milho", CropRepo(profile=" MILHO ", plan="Milho"))
    assert rec.state.status == CaseStatus.human_review_required, rec.state.error
    calc = next(c for c in rec.evidence.calculations() if c.name == "credit_metrics")
    assert calc.inputs["price"] == 62 and calc.inputs["productivity"] == 104
    assert calc.inputs["cost_per_hectare"] == 5200
    assert "PROD-CPR-02" not in {a.product_id for a in rec.state.report.alternatives}
    assert not any(s.data.get("product_id") == "PROD-CPR-02" for s in rec.evidence.sources())


async def test_risk_refuses_mixed_cultures_even_if_eligibility_is_bypassed(toolbox_factory, analyst, scope_001):
    c = build_container(Settings(llm_api_key="", _env_file=None))
    c.runtime.provider = StubProvider()
    ctx = make_ctx(analyst, "agro_credit_risk", scope_001)
    task = TaskSpec(
        task_id=ctx.task_id,
        agent_id=ctx.agent_id,
        round=1,
        instruction="Analisar",
        inputs={"crop": "milho", "purpose": "custeio", "requested_amount": 50_000_000},
    )
    tb = toolbox_factory(ctx.agent_id)
    with pytest.raises(RiskAgentError, match="cultura"):
        await c.runtime.run(c.agents.get(ctx.agent_id), ctx, task, tb, tb.events, tb.evidence)
    assert not tb.evidence.calculations() and not c.runtime.provider.calls


async def test_eligibility_only_receives_market_identity_and_unit(toolbox_factory):
    result = await toolbox_factory("agro_eligibility").call("get_market_data", commodity="SOJA")
    assert result.ok and result.sources[0].data == {"commodity": "soja", "unit": "BRL/saca"}


async def test_structuring_and_review_reject_soy_product_even_if_it_is_in_evidence(analyst, scope_001):
    c, rec = await run_case()
    sources = [s for s in rec.evidence.sources() if s.resource_domain == "product_catalog"]
    output = StructuringOutput.model_validate(rec.results["agro_structuring"].output)
    cpr = next(a for a in output.alternatives if a.product_id == "PROD-CPR-02")
    output.alternatives = [cpr, cpr.model_copy(update={"id": "ALT-OTHER"})]
    ctx = make_ctx(analyst, "agro_structuring", scope_001)
    task = TaskSpec(
        task_id=ctx.task_id,
        agent_id=ctx.agent_id,
        round=1,
        instruction="Analisar",
        inputs={"crop": "milho", "requested_amount": 50_000_000},
    )
    with pytest.raises(StructuringValidationError, match="incompatível"):
        c.agents.get(ctx.agent_id).validate(ctx, task, output, EvidenceBundle(sources=sources))
    review = ReviewContext(
        results=rec.results,
        evidence=rec.evidence,
        events=rec.events,
        policy=load_policy_params(),
        requested_amount=50_000_000,
        requested_crop="milho",
    )
    assert any(f.code == "PRODUCT_CROP_MISMATCH" for f in structure_vs_request_and_catalog(review))


def test_crop_identity_normalizes_accents_but_does_not_guess_product_compatibility():
    assert normalize_crop(" ALGODÃO ") == "algodao"
    assert product_supports_crop({"supported_crops": ["ALGODÃO"]}, "algodao")
    assert not product_supports_crop({"name": "Custeio milho", "supported_crops": ["soja"]}, "milho")
    assert not product_supports_crop({"name": "Custeio milho"}, "milho")
