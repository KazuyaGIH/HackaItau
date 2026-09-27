"""O auditor usa os registros publicados e aritmética independente do runner."""

import json
from decimal import Decimal

import pytest

from app.evaluation.audit import PUBLISHED, recalculate, verify_summary


def published():
    return json.loads((PUBLISHED / "measurements.json").read_text())


def test_published_measurements_reproduce_summary_and_separate_transport():
    groups = recalculate(published())
    verify_summary(groups, json.loads((PUBLISHED / "summary.json").read_text()))
    indexed = {(g["architecture"], g["model_label"]): g for g in groups}
    assert sum(g["runs"] for g in groups) == 48
    squad = indexed["squad", "barato"]
    high = indexed["generalist", "gpt-5.4-high"]
    normal = indexed["generalist", "forte"]
    assert squad["total_cost_usd"] == Decimal("0.0890268")
    assert high["total_cost_usd"] == Decimal("1.561489")
    assert normal["automatic_passes"] == 5
    assert normal["transport_failures"] == 1
    assert normal["completed_with_pending_checks"] == 2
    assert normal["total_cost_usd"] is None
    assert normal["known_subtotal_usd"] == Decimal("0.253292")


def test_cache_uses_discounted_rate_without_double_counting():
    data = published()
    row = next(r for r in data["runs"] if r["model_label"] == "barato")
    usage = dict(tokens_in=100, tokens_cached=60, tokens_out=10, usage_reported=True)
    row.update({k: v for k, v in usage.items() if k != "usage_reported"})
    # 40 * 0.4 + 60 * 0.1 + 10 * 1.6 = 38 millionths of a dollar.
    row.update(calls=1, calls_detail=[dict(ok=True, usage=usage)], usage_complete=True, cost_usd=0.000038)
    data["runs"] = [row]
    data["schedule"] = [[row[k] for k in ("case_id", "architecture", "model_label", "repetition")]]
    assert recalculate(data)[0]["total_cost_usd"] == Decimal("0.000038")


@pytest.mark.parametrize("field", ["cost_usd", "tokens_in", "calls"])
def test_rejects_altered_recorded_totals(field):
    data = published()
    data["runs"][0][field] += 1
    with pytest.raises(ValueError, match="divergente"):
        recalculate(data)


def test_rejects_duplicate_runs():
    data = published()
    data["runs"].append(data["runs"][0])
    with pytest.raises(ValueError, match="duplicada"):
        recalculate(data)


def test_rejects_cache_larger_than_input():
    data = published()
    usage = data["runs"][0]["calls_detail"][0]["usage"]
    usage["tokens_cached"] = usage["tokens_in"] + 1
    with pytest.raises(ValueError, match="tokens/cache"):
        recalculate(data)


def test_rejects_missing_planned_run():
    data = published()
    data["runs"].pop()
    with pytest.raises(ValueError, match="ausentes"):
        recalculate(data)
