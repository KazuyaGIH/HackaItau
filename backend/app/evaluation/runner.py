"""python -m app.evaluation.runner --models app/evaluation/models.example.json

Cada arquitetura/modelo recebe a mesma base isolada. Persistimos inclusive falhas e
respostas antes das correções. Gabaritos e notas do avaliador nunca entram nos prompts.
"""

import argparse
import asyncio
import hashlib
import json
import random
import secrets
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import APP_DIR, REPO_ROOT, Settings
from app.container import build_container
from app.core.schemas.case import CaseStatus, DemoOptions
from app.core.schemas.outputs import InterpretedDemand
from app.evaluation.generalist import GeneralistOrchestrator
from app.evaluation.scoring import RUBRIC, automatic_checks, load_reviews, summarize
from app.llm.openai_compat import LLMError, OpenAICompatProvider

DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "evaluations"
CASES_PATH = Path(__file__).with_name("cases.json")


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    label: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_per_million: float | None = Field(default=None, ge=0)
    cached_input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float | None = Field(default=None, ge=0)
    price_source: str | None = None
    price_checked_on: str | None = None
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] | None = None
    timeout_seconds: float = Field(default=60, gt=0)

    @model_validator(mode="after")
    def rates(self):
        prices = (self.input_per_million, self.cached_input_per_million, self.output_per_million)
        if any(p is not None for p in prices) and not all(p is not None for p in prices):
            raise ValueError("informe todos os três preços, ou nenhum")
        if all(p is not None for p in prices) and not (self.price_source and self.price_checked_on):
            raise ValueError("preços precisam de fonte e data de consulta")
        return self


def dump(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class RecordingProvider:
    def __init__(self, provider, *, max_calls=16, secret_values=()):
        self.provider, self.max_calls, self.secrets = provider, max_calls, secret_values
        self.trace = []

    def clean(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return json.loads(text)

    async def complete(self, **kwargs):
        if len(self.trace) >= self.max_calls:
            raise LLMError("evaluation_call_limit")
        call = {
            "requested_model": kwargs["model"],
            "schema": kwargs["response_schema"].__name__,
            "messages": [m.model_dump() for m in kwargs["messages"]],
        }
        self.trace.append(call)
        start = time.monotonic()
        try:
            response = await self.provider.complete(**kwargs)
            call.update(ok=True, response=response.content, usage=response.usage.model_dump())
            return response
        except Exception as exc:
            # Não registrar o corpo da resposta HTTP: pode conter dados da conta ou credenciais.
            call.update(ok=False, error_type=type(exc).__name__)
            raise
        finally:
            call["latency_seconds"] = time.monotonic() - start


def consumption(trace, spec):
    usages = [c["usage"] for c in trace if c.get("ok")]
    complete = bool(trace) and all(c.get("ok") and c["usage"].get("usage_reported") for c in trace)
    ti = sum(u["tokens_in"] for u in usages)
    to = sum(u["tokens_out"] for u in usages)
    cached = sum(u.get("tokens_cached", 0) for u in usages)
    valid_counts = all(0 <= u.get("tokens_cached", 0) <= u["tokens_in"] and u["tokens_out"] >= 0 for u in usages)
    complete = complete and valid_counts
    cost = None
    if complete and spec.input_per_million is not None:
        cost = (
            (ti - cached) * spec.input_per_million + cached * spec.cached_input_per_million + to * spec.output_per_million
        ) / 1_000_000
    return {
        "calls": len(trace),
        "tokens_in": ti,
        "tokens_out": to,
        "tokens_cached": cached,
        "usage_complete": complete,
        "cost_usd": cost,
    }


def prepare_fixture(source: Path, destination: Path, case: dict):
    shutil.copytree(source, destination)
    for filename, updates in (("agro_profiles", case.get("profile", {})), ("financials", case.get("financials", {}))):
        path = destination / f"{filename}.json"
        data = json.loads(path.read_text())
        for row in data["records"]:
            if row["client_id"] == "CLIENTE-001":
                row.update(updates)
                if filename == "agro_profiles" and "historical_productivity" in updates:
                    row["historical_productivity_series"] = [
                        {"cycle": cycle, "productivity": updates["historical_productivity"] + delta}
                        for cycle, delta in (("2022/23", -1), ("2023/24", 1), ("2024/25", 0))
                    ]
        dump(path, data)
    path = destination / "documents.json"
    data = json.loads(path.read_text())
    data["records"] = [
        r for r in data["records"] if not (r["client_id"] == "CLIENTE-001" and r["type"] == case.get("remove_document"))
    ]
    for row in data["records"]:
        if row["client_id"] == "CLIENTE-001" and row["type"] == "plano_de_plantio" and "plan_crop" in case:
            crop = case["plan_crop"]
            row["extracted"]["crop"] = crop
            row["extracted"]["expected_productivity"] = case.get("profile", {}).get("expected_productivity", 61)
            row["title"] = f"Plano de plantio {crop} 2026/27 (fictício)"
            row["content"] = f"Plano fictício de {crop}. Dados extraídos: " + json.dumps(
                row["extracted"], ensure_ascii=False
            )
    dump(path, data)


async def run_one(settings, fixture, case, architecture, spec, repetition, provider=None, max_calls=16):
    configured = settings.model_copy(
        update={
            "mock_data_dir": fixture,
            "llm_model": spec.model,
            "llm_max_retries": 0,
            "llm_timeout_seconds": spec.timeout_seconds,
        }
    )
    c = build_container(configured)
    if provider is None and spec.reasoning_effort is not None:
        provider = OpenAICompatProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout_seconds=spec.timeout_seconds,
            secret_values=settings.secret_values(),
            max_retries=0,
            reasoning_effort=spec.reasoning_effort,
        )
    recorder = RecordingProvider(provider or c.runtime.provider, max_calls=max_calls, secret_values=settings.secret_values())
    c.runtime.provider = recorder
    if architecture == "generalist":
        c.orchestrator = GeneralistOrchestrator(
            c.store,
            c.resolver,
            configured,
            agents=c.agents,
            runtime=c.runtime,
            repo=c.repo,
            knowledge=c.knowledge,
            llm_mode="real",
        )
    # Benchmark do raciocínio: demanda estruturada idêntica, sem confundir interpretação com arquitetura.
    demand = InterpretedDemand(
        intent="credito_agro",
        client_ref="CLIENTE-001",
        requested_amount=case["amount"],
        purpose="custeio",
        crop=case["crop"],
        cycle="2026/27",
    )
    rec = c.store.create(
        user_id="analyst-001",
        prompt="Demanda estruturada do benchmark",
        llm_mode="real",
        demo_options=DemoOptions(adversarial_document=case.get("adversarial", False)),
    )
    rec.state.interpreted = demand
    c.orchestrator._bootstrap(rec, c.orchestrator._user("analyst-001"), "CLIENTE-001")
    start = time.monotonic()
    await c.orchestrator.run(rec.state.case_id)
    duration = time.monotonic() - start
    result = {
        "blind_id": secrets.token_hex(8),
        "case_id": case["id"],
        "repetition": repetition,
        "architecture": architecture,
        "model_label": spec.label,
        "model": spec.model,
        "reasoning_effort": spec.reasoning_effort,
        "status": rec.state.status.value,
        # Falha continua no denominador; o detalhe fica nos eventos sanitizados.
        "error": rec.state.error if rec.state.status == CaseStatus.failed else None,
        "latency_seconds": duration,
        **consumption(recorder.trace, spec),
        "automatic": automatic_checks(rec, case),
        "demand": demand.model_dump(),
        "focus": case["focus"],
        "report": rec.state.report.model_dump(mode="json") if rec.state.report else None,
        "missing_info": rec.state.missing_info.model_dump() if rec.state.missing_info else None,
        "outputs": {a: r.output for a, r in rec.results.items()},
        "evidence": [s.model_dump() for s in rec.evidence.sources()],
        "calculations": [s.model_dump() for s in rec.evidence.calculations()],
        "trace": recorder.trace,
        "events": [e.model_dump(mode="json") for e in rec.events.list_after(0)],
    }
    return recorder.clean(result)


def persist_reports(output, manifest, runs, reviews=None):
    summary = {
        "version": 1,
        "run_id": output.name,
        "created_at": manifest["created_at"],
        "status": "complete" if len(runs) == manifest["planned_runs"] else "partial",
        "planned_runs": manifest["planned_runs"],
        "completed_runs": len(runs),
        "quality_status": "reviewed" if reviews and len(reviews) == len(runs) else "pending_human_review",
        "groups": summarize(runs, reviews),
        "conclusion": "Resultados descritivos. Sem conclusão automática de superioridade ou equivalência.",
    }
    dump(output / "summary.json", summary)
    lines = [
        "# Comparativo executado: squad × generalista",
        "",
        f"Execuções: {len(runs)}/{manifest['planned_runs']}. Qualidade: {summary['quality_status']}.",
        "",
        "Custos em USD calculados com tokens reportados e tabela configurada; não são uma fatura.",
        "Falhas e correções entram no consumo. Sem usage ou preço completo, custo fica indisponível.",
        "",
        "| Arquitetura | Modelo | Restrições atendidas | Revisados | Aceitos | Custo USD | Custo/aceito | Tempo médio |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in summary["groups"]:
        fmt = lambda value: "—" if value is None else f"{value:.4f}"  # noqa: E731
        model_description = g["model"] + (f" ({g['reasoning_effort']})" if g.get("reasoning_effort") else "")
        lines.append(
            f"| {g['architecture']} | {model_description} | {g['automatic_passes']}/{g['runs']} | {g['reviewed']} | "
            f"{g['accepted'] if g['accepted'] is not None else 'pendente'} | {fmt(g['total_cost_usd'])} | "
            f"{fmt(g['cost_per_accepted_usd'])} | {g['mean_latency_seconds']:.1f}s |"
        )
    lines += [
        "",
        "As restrições automáticas incluem trabalho do backend; não medem acurácia factual do LLM.",
        "A revisão cega avalia fundamentação, riscos, alternativas e clareza (0–3 cada). Aceitação exige ≥2 em",
        "cada dimensão, nenhum erro crítico e todas as restrições automáticas atendidas.",
        "O custo por aceito inclui o gasto de TODAS as tentativas do grupo, inclusive falhas.",
        "Intervalos de Wilson no JSON são descritivos: repetições do mesmo caso não são amostras independentes.",
        "A suíte sintética é pequena e conhecida. Use casos reservados e revisão de domínio antes de afirmar equivalência.",
        "",
        "Consulte manifest.json, runs.jsonl e traces/ para reproduzir e auditar cada execução.",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def blind_packet(run):
    # Só o conteúdo a julgar: remover arquitetura, modelo, custo, latência, agentes, contadores e IDs do case.
    report = run["report"]
    content = {
        k: v
        for k, v in (report or {}).items()
        if k
        in (
            "facts",
            "calculations",
            "favorable_factors",
            "risk_factors",
            "uncertainties",
            "alternatives",
            "executive_summary",
            "assumptions",
            "stress_scenarios",
            "missing_data",
            "policy_limits",
        )
    }
    return {
        "blind_id": run["blind_id"],
        "case_id": run["case_id"],
        "status": run["status"],
        "eligibility": run["automatic"]["eligibility"],
        "demand": run["demand"],
        "focus": run["focus"],
        "content": content,
        "outputs": run["outputs"],
        "missing_info": run["missing_info"],
        "evidence": [{k: v for k, v in s.items() if k != "accessed_by_agent"} for s in run["evidence"]],
        "calculations": [{k: v for k, v in s.items() if k != "computed_by_agent"} for s in run["calculations"]],
    }


def load_cases(selected=None):
    cases = json.loads(CASES_PATH.read_text())["cases"]
    if selected:
        wanted = set(selected.split(","))
        unknown = wanted - {c["id"] for c in cases}
        if unknown:
            raise ValueError(f"Casos desconhecidos: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in wanted]
    return cases


async def execute(args):
    settings = Settings()
    specs = [ModelSpec.model_validate(m) for m in json.loads(args.models.read_text())["models"]]
    if (
        not specs
        or len({s.label for s in specs}) != len(specs)
        or len({(s.model, s.reasoning_effort) for s in specs}) != len(specs)
    ):
        raise ValueError("configurações de modelo/raciocínio e labels devem ser únicos; configure pelo menos um modelo")
    cases = load_cases(args.cases)
    schedule = [
        (case, architecture, spec, rep)
        for rep in range(1, args.repetitions + 1)
        for case in cases
        for spec in specs
        for architecture in args.architectures
    ]
    random.Random(args.seed).shuffle(schedule)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "cases": [c["id"] for c in cases],
                    "models": [s.model for s in specs],
                    "planned_runs": len(schedule),
                    "max_calls_per_run": args.max_calls,
                },
                indent=2,
            )
        )
        return
    if not settings.llm_configured:
        raise ValueError("LLM_API_KEY ausente; nenhum resultado real foi produzido")
    output = args.output or DEFAULT_OUTPUT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    output.mkdir(parents=True, exist_ok=False)
    (output / "traces").mkdir()
    digest = hashlib.sha256()
    for path in sorted(APP_DIR.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".md", ".json"):
            digest.update(str(path.relative_to(APP_DIR)).encode() + path.read_bytes())
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "planned_runs": len(schedule),
        "app_sha256": digest.hexdigest(),
        "cases": cases,
        "models": [s.model_dump() for s in specs],
        "seed": args.seed,
        "repetitions": args.repetitions,
        "max_calls_per_run": args.max_calls,
        "rubric": RUBRIC,
        "acceptance": "all automatic checks; each human dimension >=2/3; no critical error",
        "transport_retries": 0,
        "architectures": args.architectures,
        "pause_seconds": args.pause_seconds,
        "schedule": [[c["id"], a, s.label, r] for c, a, s, r in schedule],
    }
    dump(output / "manifest.json", manifest)
    runs = []
    persist_reports(output, manifest, runs)
    with tempfile.TemporaryDirectory(prefix="agro-eval-") as tmp:
        for case in cases:
            prepare_fixture(settings.mock_data_dir, Path(tmp) / case["id"], case)
        for case, architecture, spec, rep in schedule:
            print(f"[{len(runs) + 1}/{len(schedule)}] {case['id']} {architecture} {spec.label}", flush=True)
            run = await run_one(settings, Path(tmp) / case["id"], case, architecture, spec, rep, max_calls=args.max_calls)
            dump(output / "traces" / f"{run['blind_id']}.json", run)
            row = {
                k: v for k, v in run.items() if k not in ("trace", "events", "outputs", "evidence", "calculations", "report")
            }
            with (output / "runs.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            runs.append(row)
            persist_reports(output, manifest, runs)
            print(
                f"  {run['status']} | checks={run['automatic']['passed']} | calls={run['calls']} | "
                f"cost={run['cost_usd']} USD",
                flush=True,
            )
            if args.pause_seconds and len(runs) < len(schedule):
                await asyncio.sleep(args.pause_seconds)
    packets = [blind_packet(json.loads(path.read_text())) for path in sorted((output / "traces").glob("*.json"))]
    random.Random(args.seed + 1).shuffle(packets)
    dump(
        output / "review_blind.json",
        {"rubric": RUBRIC, "scale": "0 ausente/incorreto, 1 falha material, 2 adequado, 3 completo", "items": packets},
    )
    dump(
        output / "reviews.template.json",
        [
            {"blind_id": p["blind_id"], "reviewer": "", **dict.fromkeys(RUBRIC), "critical_error": None, "rationale": ""}
            for p in packets
        ],
    )
    print(f"Relatório: {output / 'REPORT.md'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path(__file__).with_name("models.example.json"))
    parser.add_argument("--cases", help="IDs separados por vírgula; padrão: todos")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--architectures", nargs="+", choices=("squad", "generalist"), default=["squad", "generalist"])
    parser.add_argument("--pause-seconds", type=float, default=0, help="Intervalo entre casos para respeitar limites da API")
    parser.add_argument("--max-calls", type=int, default=16)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score", type=Path, help="Diretório de uma execução existente; não chama o LLM")
    parser.add_argument("--reviews", type=Path)
    args = parser.parse_args()
    try:
        if args.repetitions < 1 or args.max_calls < 1:
            raise ValueError("repetitions e max-calls precisam ser positivos")
        if not 0 <= args.pause_seconds <= 3600 or len(set(args.architectures)) != len(args.architectures):
            raise ValueError("pause-seconds deve ficar entre 0 e 3600; arquiteturas devem ser únicas")
        if args.score:
            if not args.reviews:
                raise ValueError("--score exige --reviews com avaliações preenchidas")
            manifest = json.loads((args.score / "manifest.json").read_text())
            runs = [json.loads(line) for line in (args.score / "runs.jsonl").read_text().splitlines()]
            reviews = load_reviews(args.reviews, {r["blind_id"] for r in runs})
            dump(args.score / "reviews.json", [r.model_dump() for r in reviews.values()])
            persist_reports(args.score, manifest, runs, reviews)
        else:
            asyncio.run(execute(args))
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
