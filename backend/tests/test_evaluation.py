import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.core.schemas.agent import LLMUsage
from app.evaluation.replay import ReplayProvider
from app.evaluation.runner import (
    ModelSpec,
    RecordingProvider,
    consumption,
    load_cases,
    prepare_fixture,
    run_one,
)
from app.evaluation.scoring import HumanReview, load_reviews, summarize
from app.llm.openai_compat import LLMError, OpenAICompatProvider
from app.llm.prompting import extract_json
from app.llm.provider import LLMResponse, Message
from tests.fake_llm import StubProvider, _ai_review, _eligibility, _Evidence, _risk, _structuring


class BothProvider(StubProvider):
    """Exercita o encanamento; não é avaliação de qualidade nem benchmark de modelos."""

    def __init__(self, break_first=False):
        super().__init__()
        self.break_first = break_first

    async def complete(self, **kwargs):
        if kwargs["response_schema"].__name__ != "GeneralistOutput":
            response = await super().complete(**kwargs)
            response.usage.usage_reported = True
            return response
        self.calls.append(kwargs["messages"])
        text = "\n".join(m.content for m in kwargs["messages"] if m.role == "user")
        ev = _Evidence(text.replace("label=demanda", "label=task_inputs"))
        out = {"eligibility": _eligibility(ev)}
        if ev.calcs:
            out["risk"] = _risk(ev)
            ev.inputs["risk"] = out["risk"]
            out["structuring"] = _structuring(ev)
            out["review"] = _ai_review(ev)
            if self.break_first and len(self.calls) == 1:
                for alternative in out["structuring"]["alternatives"]:
                    alternative["product_id"] = "PROD-INVENTADO"
        return LLMResponse(
            content=json.dumps(out),
            usage=LLMUsage(
                model=kwargs["model"],
                tokens_in=100,
                tokens_out=50,
                usage_reported=True,
            ),
        )


def spec():
    return ModelSpec(
        label="test",
        model="test-model",
        input_per_million=2,
        cached_input_per_million=0.5,
        output_per_million=8,
        price_source="test",
        price_checked_on="2026-09-27",
    )


@pytest.mark.parametrize("architecture", ["squad", "generalist"])
async def test_replay_preserves_responses_and_rejects_changed_prompt(tmp_path, architecture):
    settings = Settings(llm_api_key="", _env_file=None)
    case = load_cases("soja-base")[0]
    prepare_fixture(settings.mock_data_dir, tmp_path / "mock", case)
    original = await run_one(settings, tmp_path / "mock", case, architecture, spec(), 1, provider=BothProvider())
    provider = ReplayProvider(original["trace"])
    repeated = await run_one(settings, tmp_path / "mock", case, architecture, spec(), 1, provider=provider)
    assert repeated["automatic"] == original["automatic"] and repeated["outputs"] == original["outputs"]
    assert provider.index == len(original["trace"]) and provider.mismatch is None
    original["trace"][0]["messages"][0]["content"] += " changed"
    provider = ReplayProvider(original["trace"])
    repeated = await run_one(settings, tmp_path / "mock", case, architecture, spec(), 1, provider=provider)
    assert provider.mismatch and repeated["status"] == "failed"


@pytest.mark.parametrize(
    "case_id", ["soja-base", "milho-coerente", "cultura-divergente", "documento-ausente", "mercado-ausente"]
)
async def test_same_fixtures_calculations_and_gate_for_both_architectures(tmp_path, case_id):
    settings = Settings(llm_api_key="", _env_file=None)
    case = load_cases(case_id)[0]
    fixture = tmp_path / "mock"
    prepare_fixture(settings.mock_data_dir, fixture, case)
    runs = []
    for architecture in ("squad", "generalist"):
        result = await run_one(settings, fixture, case, architecture, spec(), 1, provider=BothProvider())
        assert result["status"] == case["expected_status"], result["error"]
        assert result["automatic"]["passed"], result["automatic"]
        assert result["usage_complete"] and result["cost_usd"] > 0
        assert "MOCK-NEVER" not in json.dumps(result["trace"])
        assert case["focus"] not in json.dumps(result["trace"])
        runs.append(result)
    assert [c["outputs"] for c in runs[0]["calculations"]] == [c["outputs"] for c in runs[1]["calculations"]]
    if case["expected_status"] == "human_review_required":
        assert runs[0]["calls"] == 4 and runs[1]["calls"] == 1


async def test_generalist_gets_validation_feedback_and_all_calls_are_charged(tmp_path):
    settings = Settings(llm_api_key="", _env_file=None)
    case = load_cases("soja-base")[0]
    prepare_fixture(settings.mock_data_dir, tmp_path / "mock", case)
    result = await run_one(settings, tmp_path / "mock", case, "generalist", spec(), 1, provider=BothProvider(True))
    assert result["status"] == "human_review_required", result["error"]
    assert result["calls"] == 2 and result["tokens_in"] == 200
    assert result["automatic"]["interventions"]["output_rejections"] == 1
    raw_first = extract_json(result["trace"][0]["response"])
    assert raw_first["structuring"]["alternatives"][0]["product_id"] == "PROD-INVENTADO"
    assert "PROD-INVENTADO" in result["trace"][1]["messages"][-1]["content"]


def test_cost_accounts_for_output_and_cached_input_and_unknown_usage():
    trace = [{"ok": True, "usage": {"tokens_in": 1000, "tokens_out": 500, "tokens_cached": 400, "usage_reported": True}}]
    assert consumption(trace, spec())["cost_usd"] == pytest.approx(0.0054)
    assert consumption(trace + [{"ok": False}], spec())["cost_usd"] is None
    trace[0]["usage"]["usage_reported"] = False
    assert consumption(trace, spec())["cost_usd"] is None
    trace[0]["usage"]["usage_reported"] = True
    assert consumption(trace, ModelSpec(label="x", model="x"))["cost_usd"] is None


async def test_recording_retains_failure_and_enforces_call_limit():
    class Failing:
        async def complete(self, **kwargs):
            raise LLMError("sensitive-detail")

    recorder = RecordingProvider(Failing(), max_calls=1)
    params = dict(model="test", messages=[], response_schema=HumanReview)
    with pytest.raises(LLMError):
        await recorder.complete(**params)
    with pytest.raises(LLMError, match="call_limit"):
        await recorder.complete(**params)
    assert len(recorder.trace) == 1 and recorder.trace[0]["ok"] is False
    assert "sensitive-detail" not in json.dumps(recorder.trace)


def test_summary_requires_human_review_and_counts_failed_costs():
    row = {
        "architecture": "squad",
        "model_label": "cheap",
        "model": "test",
        "blind_id": "a",
        "calls": 1,
        "automatic": {"passed": True},
        "status": "human_review_required",
        "tokens_in": 10,
        "tokens_out": 10,
        "usage_complete": True,
        "cost_usd": 1.0,
        "latency_seconds": 1,
    }
    failed = row | {"blind_id": "b", "status": "failed", "automatic": {"passed": False}, "cost_usd": 2.0}
    assert summarize([row, failed])[0]["accepted"] is None
    review = HumanReview(
        blind_id="a",
        reviewer="Analista",
        grounding=2,
        risk=2,
        structure=2,
        clarity=3,
        critical_error=False,
        rationale="Conferido contra as fontes.",
    )
    reviews = {"a": review, "b": review.model_copy(update={"blind_id": "b"})}
    result = summarize([row, failed], reviews)[0]
    assert result["accepted"] == 1 and result["cost_per_accepted_usd"] == 3.0
    assert result["accepted_rate"] == 0.5 and result["errors"] == 1


def test_invalid_reviewer_scores_duplicates_unknown_ids_and_prices_rejected(tmp_path):
    with pytest.raises(ValidationError):
        HumanReview(
            blind_id="a", reviewer="", grounding=True, risk=4, structure=2, clarity=3, critical_error=False, rationale=""
        )
    with pytest.raises(ValidationError):
        ModelSpec(label="cheap", model="x", input_per_million=-1)
    with pytest.raises(ValidationError):
        ModelSpec(label="cheap", model="x", input_per_million=1)
    review = {
        "blind_id": "a",
        "reviewer": "Analista",
        "grounding": 2,
        "risk": 2,
        "structure": 2,
        "clarity": 2,
        "critical_error": False,
        "rationale": "Conferido contra as fontes.",
    }
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps([review, review]))
    with pytest.raises(ValueError, match="duplicado"):
        load_reviews(path, {"a"})
    path.write_text(json.dumps([review]))
    with pytest.raises(ValueError, match="desconhecido"):
        load_reviews(path, {"b"})


@pytest.mark.parametrize("report_usage", [True, False])
async def test_provider_marks_missing_usage_and_reads_cache(report_usage):
    async def handler(request):
        response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "prompt_tokens_details": {"cached_tokens": 60},
                },
            },
        )
        if not report_usage:
            data = response.json()
            del data["usage"]
            return httpx.Response(200, json=data)
        return response

    provider = OpenAICompatProvider("https://test.invalid", "test-secret", 1, [], transport=httpx.MockTransport(handler))
    response = await provider.complete(model="test", messages=[Message(role="user", content="JSON")])
    assert response.usage.usage_reported == report_usage
    assert response.usage.tokens_cached == (60 if report_usage else 0)


async def test_schema_retry_and_failed_run_are_retained(tmp_path):
    class InvalidProvider(BothProvider):
        async def complete(self, **kwargs):
            result = await super().complete(**kwargs)
            result.content = "{}"
            return result

    settings = Settings(llm_api_key="", _env_file=None)
    case = load_cases("soja-base")[0]
    prepare_fixture(settings.mock_data_dir, tmp_path / "mock", case)
    run = await run_one(settings, tmp_path / "mock", case, "generalist", spec(), 1, provider=InvalidProvider())
    assert run["status"] == "failed" and not run["automatic"]["passed"]
    assert run["calls"] == 2 and run["cost_usd"] > 0
    assert len(run["trace"]) == 2 and all(c["response"] == "{}" for c in run["trace"])


def test_latest_benchmark_endpoint_is_read_only_and_handles_empty_or_invalid_files(tmp_path):
    from fastapi.testclient import TestClient

    from app.container import build_container, get_container
    from app.main import app

    c = build_container(Settings(llm_api_key="", benchmark_results_dir=tmp_path, _env_file=None))
    app.dependency_overrides[get_container] = lambda: c
    try:
        with TestClient(app) as client:
            assert client.get("/api/benchmarks/latest").json() == {"benchmark": None}
            older = tmp_path / "20260101"
            older.mkdir()
            summary = {"version": 1, "groups": [], "status": "partial"}
            (older / "summary.json").write_text(json.dumps(summary))
            newer = tmp_path / "20260201"
            newer.mkdir()
            (newer / "summary.json").write_text("[")
            assert client.get("/api/benchmarks/latest").json() == {"benchmark": summary}
            assert len(c.store) == 0
    finally:
        app.dependency_overrides.clear()
