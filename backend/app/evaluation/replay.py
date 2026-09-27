"""Reavalia respostas salvas sem rede. Rejeita replay se qualquer prompt ou schema divergir.

Uso: python -m app.evaluation.replay <diretório1> <diretório2>
Resultados originais são preservados. Tokens, custos e latências continuam sendo os da API original.
"""

import argparse
import asyncio
import hashlib
import json
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import APP_DIR, Settings
from app.core.schemas.agent import LLMUsage
from app.evaluation.runner import DEFAULT_OUTPUT, ModelSpec, blind_packet, dump, persist_reports, prepare_fixture, run_one
from app.evaluation.scoring import RUBRIC
from app.llm.openai_compat import LLMError
from app.llm.provider import LLMResponse


class ReplayProvider:
    def __init__(self, trace):
        self.trace = trace
        self.index = 0
        self.mismatch = None

    async def complete(self, **kwargs):
        if self.index >= len(self.trace):
            self.mismatch = "a nova execução exige chamadas adicionais"
            raise LLMError(self.mismatch)
        old = self.trace[self.index]
        self.index += 1
        if (
            old["messages"] != [m.model_dump() for m in kwargs["messages"]]
            or old["schema"] != kwargs["response_schema"].__name__
            or old["requested_model"] != kwargs["model"]
        ):
            self.mismatch = f"prompt, modelo ou schema divergente na chamada {self.index}"
            raise LLMError(self.mismatch)
        if not old.get("ok"):
            raise LLMError("falha de transporte registrada na execução original")
        return LLMResponse(content=old["response"], usage=LLMUsage.model_validate(old["usage"]))


async def replay(directories):
    settings = Settings(llm_api_key="", _env_file=None)  # impossibilita chamadas à API
    output = DEFAULT_OUTPUT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ") + "-replay")
    inputs = [json.loads((directory / "manifest.json").read_text()) for directory in directories]
    first = inputs[0]
    if any(
        m["cases"] != first["cases"] or m["rubric"] != first["rubric"] or m["acceptance"] != first["acceptance"]
        for m in inputs
    ):
        raise ValueError("casos ou rubricas diferentes; não combinar")
    digest = hashlib.sha256()
    for path in sorted(APP_DIR.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".md", ".json"):
            digest.update(str(path.relative_to(APP_DIR)).encode() + path.read_bytes())
    manifest = dict(
        first,
        created_at=datetime.now(timezone.utc).isoformat(),
        planned_runs=sum(m["planned_runs"] for m in inputs),
        source_runs=[str(p.resolve()) for p in directories],
        source_app_hashes=[m["app_sha256"] for m in inputs],
        app_sha256=digest.hexdigest(),
        mode="offline_replay",
        measurement_revision="current_leverage_synonyms_v2",
        models=[s for m in inputs for s in m["models"]],
        schedule=[s for m in inputs for s in m["schedule"]],
    )
    output.mkdir(parents=True)
    (output / "traces").mkdir()
    dump(output / "manifest.json", manifest)
    runs, packets = [], []
    with tempfile.TemporaryDirectory(prefix="agro-replay-") as tmp:
        for case in first["cases"]:
            prepare_fixture(settings.mock_data_dir, Path(tmp) / case["id"], case)
        for directory, original_manifest in zip(directories, inputs, strict=True):
            cases = {c["id"]: c for c in original_manifest["cases"]}
            models = {m["label"]: ModelSpec.model_validate(m) for m in original_manifest["models"]}
            for path in sorted((directory / "traces").glob("*.json")):
                old = json.loads(path.read_text())
                provider = ReplayProvider(old["trace"])
                result = await run_one(
                    settings,
                    Path(tmp) / old["case_id"],
                    cases[old["case_id"]],
                    old["architecture"],
                    models[old["model_label"]],
                    old["repetition"],
                    provider=provider,
                    max_calls=original_manifest["max_calls_per_run"],
                )
                if provider.mismatch or provider.index != len(provider.trace):
                    raise ValueError(f"{path}: replay inválido: {provider.mismatch or 'número de chamadas divergente'}")
                # Uma correção de medição nunca pode transformar erro de execução em sucesso, ou vice-versa.
                if result["status"] != old["status"]:
                    raise ValueError(f"{path}: status divergente; necessário novo experimento com API")
                revised = dict(
                    old,
                    automatic=result["automatic"],
                    report=result["report"],
                    original_automatic=old["automatic"],
                    source_trace=str(path.resolve()),
                    measurement_revision=manifest["measurement_revision"],
                )
                dump(output / "traces" / path.name, revised)
                row = {
                    k: v
                    for k, v in revised.items()
                    if k not in ("trace", "events", "outputs", "evidence", "calculations", "report")
                }
                runs.append(row)
                packets.append(blind_packet(revised))
                if revised["automatic"]["passed"] != old["automatic"]["passed"]:
                    print(
                        old["architecture"],
                        old["model_label"],
                        old["case_id"],
                        old["automatic"]["passed"],
                        "->",
                        revised["automatic"]["passed"],
                        flush=True,
                    )
    if len({r["blind_id"] for r in runs}) != len(runs):
        raise ValueError("resultados duplicados; não combinar os mesmos traces duas vezes")
    (output / "runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in runs))
    persist_reports(output, manifest, runs)
    random.Random(43).shuffle(packets)
    dump(output / "review_blind.json", {"rubric": RUBRIC, "items": packets})
    dump(
        output / "reviews.template.json",
        [
            dict(blind_id=p["blind_id"], reviewer="", **dict.fromkeys(RUBRIC), critical_error=None, rationale="")
            for p in packets
        ],
    )
    with (output / "REPORT.md").open("a") as f:
        f.write(
            "\nReavaliação offline: sinônimos de alavancagem atual/líquida corrigidos para todas as arquiteturas. "
            "Prompts, schemas e quantidade de chamadas conferidos contra os originais. "
            "Custos e latências preservados; nenhuma chamada nova à API. Veja source_runs no manifest.\n"
        )
    print(f"Relatório reavaliado: {output / 'REPORT.md'}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    asyncio.run(replay(args.directories))


if __name__ == "__main__":
    main()
