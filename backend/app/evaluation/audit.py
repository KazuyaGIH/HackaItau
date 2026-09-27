"""Recalcula as medições publicadas com Decimal, sem rede nem uso do scorer de produção.

python -m app.evaluation.audit
python -m app.evaluation.audit --measurements caminho.json --summary resumo.json

Conferir checks gravados não equivale a reavaliar semanticamente as respostas.
Para executar novamente os validadores sobre as respostas originais, use evaluation.replay.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

PUBLISHED = Path(__file__).with_name("published")
D = Decimal


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_cost(actual, recorded):
    if actual is None or recorded is None:
        return actual is None and recorded is None
    return abs(actual - D(str(recorded))) < D("0.0000000001")


def recalculate(data):
    models = {m["label"]: m for m in data["models"]}
    groups = defaultdict(list)
    seen_ids, seen_runs = set(), set()
    for row in data["runs"]:
        identity = (row["case_id"], row["architecture"], row["model_label"], row["repetition"])
        require(row["blind_id"] not in seen_ids and identity not in seen_runs, "execução duplicada")
        seen_ids.add(row["blind_id"])
        seen_runs.add(identity)
        rates = models[row["model_label"]]
        require(row["model"] == rates["model"], "modelo divergente da tarifa")
        tokens = dict(tokens_in=0, tokens_out=0, tokens_cached=0)
        known = D(0)
        usage_complete = bool(row["calls_detail"])
        priced = all(
            rates.get(k) is not None for k in ("input_per_million", "cached_input_per_million", "output_per_million")
        )
        transport = False
        for call in row["calls_detail"]:
            if not call["ok"]:
                transport = True
                usage_complete = False
                continue
            usage = call["usage"]
            ti, to, cached = (usage.get(k, 0) for k in tokens)
            require(0 <= cached <= ti and to >= 0, "contagem inválida de tokens/cache")
            for key in tokens:
                tokens[key] += usage.get(key, 0)
            if not usage.get("usage_reported"):
                usage_complete = False
                continue
            if priced:
                known += (
                    (ti - cached) * D(str(rates["input_per_million"]))
                    + cached * D(str(rates["cached_input_per_million"]))
                    + to * D(str(rates["output_per_million"]))
                ) / D(1_000_000)
        cost = known if usage_complete and priced else None
        require(row["calls"] == len(row["calls_detail"]), "quantidade de chamadas divergente")
        require(all(row[k] == v for k, v in tokens.items()), "total de tokens divergente")
        require(row["usage_complete"] == usage_complete, "completude de usage divergente")
        require(same_cost(cost, row["cost_usd"]), "custo da execução divergente")
        require(bool(row["checks"]) and all(type(v) is bool for v in row["checks"].values()), "checks inválidos")
        passed = all(row["checks"].values())
        groups[row["architecture"], row["model_label"]].append(
            dict(row, passed=passed, transport=transport, computed_cost=cost, known_cost=known if priced else None)
        )
    require(seen_runs == {tuple(s) for s in data["schedule"]}, "execuções ausentes ou fora do plano")
    require(len(data["schedule"]) == len(seen_runs), "plano duplicado")
    result = []
    for (architecture, label), rows in sorted(groups.items()):
        total = sum((r["computed_cost"] for r in rows), D(0)) if all(r["computed_cost"] is not None for r in rows) else None
        subtotal = sum((r["known_cost"] for r in rows), D(0)) if all(r["known_cost"] is not None for r in rows) else None
        result.append(
            dict(
                architecture=architecture,
                model_label=label,
                runs=len(rows),
                automatic_passes=sum(r["passed"] for r in rows),
                errors=sum(r["status"] == "failed" for r in rows),
                transport_failures=sum(r["transport"] for r in rows),
                output_failures=sum(r["status"] == "failed" and not r["transport"] for r in rows),
                completed_with_pending_checks=sum(r["status"] != "failed" and not r["passed"] for r in rows),
                calls=sum(r["calls"] for r in rows),
                tokens_in=sum(r["tokens_in"] for r in rows),
                tokens_out=sum(r["tokens_out"] for r in rows),
                tokens_cached=sum(r["tokens_cached"] for r in rows),
                total_cost_usd=total,
                known_subtotal_usd=subtotal,
            )
        )
    return result


def verify_summary(groups, summary):
    indexed = {(g["architecture"], g["model_label"]): g for g in summary["groups"]}
    require(len(indexed) == len(groups) == len(summary["groups"]), "grupos divergentes")
    require(sum(g["runs"] for g in groups) == summary["completed_runs"], "total de execuções divergente")
    for group in groups:
        recorded = indexed[group["architecture"], group["model_label"]]
        for field in ("runs", "automatic_passes", "errors", "calls", "tokens_in", "tokens_out"):
            require(group[field] == recorded[field], f"resumo divergente: {field}")
        require(same_cost(group["total_cost_usd"], recorded["total_cost_usd"]), "custo do resumo divergente")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, default=PUBLISHED / "measurements.json")
    parser.add_argument("--summary", type=Path, default=PUBLISHED / "summary.json")
    args = parser.parse_args()
    data = json.loads(args.measurements.read_text())
    raw_summary = args.summary.read_bytes()
    require(hashlib.sha256(raw_summary).hexdigest() == data["source_summary_sha256"], "hash do resumo divergente")
    groups = recalculate(data)
    verify_summary(groups, json.loads(raw_summary))
    print(
        json.dumps(
            {"verified": True, "source_run": data["source_run"], "groups": groups}, ensure_ascii=False, indent=2, default=str
        )
    )


if __name__ == "__main__":
    main()
