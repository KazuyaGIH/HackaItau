"""Interpretação da demanda (ARCHITECTURE.md §3). Saída é PROPOSTA: nada aqui vira permissão.

`heuristic_interpret` é determinístico e é a base; `interpret` pede ao LLM (sem tools) só para preencher campos
que a heurística não achou. O prompt do usuário entra como UNTRUSTED_DATA; falha do LLM → heurística.
"""

import re

from pydantic import ValidationError

from app.core.schemas.outputs import InterpretedDemand
from app.llm.openai_compat import LLMError
from app.llm.prompting import UNTRUSTED_RULES, extract_json, render_schema, wrap_untrusted
from app.llm.provider import LLMProvider, Message

_INTERPRET_SYSTEM = (
    "Você extrai campos estruturados de um pedido de análise de crédito agro. Não decide nada, não aprova, "
    "não infere permissões. Devolva apenas JSON.\n\n" + UNTRUSTED_RULES
)
_FILLABLE = ("client_ref", "requested_amount", "purpose", "crop", "cycle")

_CLIENT_ID_RE = re.compile(r"\bCLIENTE-\d{3,}\b", re.IGNORECASE)
# "cliente Fazenda Horizonte S.A. solicita" / "empresa X pede" / "para a Agro Delta Ltda."
_CLIENT_NAME_RE = re.compile(
    r"\b(?:cliente|empresa|produtor|grupo)\s+(?P<name>[A-ZÁ-Ú][\w&.\-]*(?:\s+[A-ZÁ-Úa-zá-ú][\w&.\-]*){0,5}?)"
    r"(?=\s+(?:solicita|pede|precisa|quer|deseja|busca|requer)|[,.;:]|\s*$)",
)
_AMOUNT_RE = re.compile(
    r"R?\$?\s*(?P<num>\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>milh(?:ão|ões|oes|ao)|mi\b|mm\b|m\b|bilh(?:ão|ões|oes|ao)|bi\b|mil\b|k\b)?",
    re.IGNORECASE,
)
_CYCLE_RE = re.compile(r"\b(20\d{2})\s*/\s*(20)?(\d{2})\b")
_PURPOSES = ("custeio", "investimento", "comercializacao", "comercialização", "industrializacao", "industrialização")
_CROPS = ("soja", "milho", "algodao", "algodão", "cana", "cafe", "café", "trigo", "arroz")


def _strip_accents(s: str) -> str:
    return s.replace("ã", "a").replace("ç", "c").replace("é", "e").replace("õ", "o")


def _to_number(raw: str) -> float:
    raw = raw.replace(" ", "")
    if "," in raw:  # 1.234,56 ou 1,5
        return float(raw.replace(".", "").replace(",", "."))
    if raw.count(".") == 1 and len(raw.split(".")[1]) != 3:  # 1.5 (decimal), não 50.000
        return float(raw)
    return float(raw.replace(".", ""))


def parse_amount(text: str, *, bare_number_ok: bool = False) -> float | None:
    """Valor em reais a partir de texto livre. Em prosa, número sem R$/unidade é ignorado (ano, área, sc/ha);
    `bare_number_ok` é para campos que só contêm o valor (ex.: resposta do formulário)."""
    best: float | None = None
    for m in _AMOUNT_RE.finditer(text):
        raw, unit = m.group("num"), (m.group("unit") or "").lower()
        has_currency = m.group(0).lstrip().startswith(("R$", "$"))
        if not unit and not has_currency and not bare_number_ok:
            continue
        mult = 1.0
        if unit.startswith("milh") or unit in ("mi", "mm", "m"):
            mult = 1e6
        elif unit.startswith("bilh") or unit == "bi":
            mult = 1e9
        elif unit in ("mil", "k"):
            mult = 1e3
        value = _to_number(raw) * mult
        if best is None or value > best:
            best = value
    return best


def heuristic_interpret(prompt: str) -> InterpretedDemand:
    text = prompt.strip()
    lower = _strip_accents(text.lower())

    client_ref: str | None = None
    if m := _CLIENT_ID_RE.search(text):
        client_ref = m.group(0).upper()
    elif m := _CLIENT_NAME_RE.search(text):
        client_ref = m.group("name").strip()

    purpose = next((p for p in _PURPOSES if p in lower), None)
    crop = next((c for c in _CROPS if re.search(rf"\b{c}\b", lower)), None)
    cycle = f"{m.group(1)}/{m.group(3)}" if (m := _CYCLE_RE.search(text)) else None

    return InterpretedDemand(
        intent="credito_agro",
        client_ref=client_ref,
        requested_amount=parse_amount(text),
        purpose=_strip_accents(purpose) if purpose else None,
        crop=_strip_accents(crop) if crop else None,
        cycle=cycle,
        notes="heuristic",
    )


async def interpret(prompt: str, provider: LLMProvider | None, model: str) -> InterpretedDemand:
    base = heuristic_interpret(prompt)
    base_fields = base.model_dump(include=set(_FILLABLE))
    if provider is None or all(v is not None for v in base_fields.values()):
        return base
    user = (
        "## Pedido do usuário\n"
        + wrap_untrusted("user_prompt", prompt)
        + "\n\n## Formato de saída\nJSON conforme:\n"
        + render_schema(InterpretedDemand)
        + '\nUse intent="credito_agro"; campos desconhecidos = null; purpose sem acento (ex.: custeio); '
        'requested_amount em reais, valor absoluto ("10 milhões"/"R$ 10M" → 10000000).'
    )
    try:
        resp = await provider.complete(
            model=model,
            messages=[Message(role="system", content=_INTERPRET_SYSTEM), Message(role="user", content=user)],
            response_schema=InterpretedDemand,
        )
        llm = InterpretedDemand.model_validate(extract_json(resp.content or ""))
    except (LLMError, ValueError, ValidationError):
        return base
    llm_fields = llm.model_dump(include=set(_FILLABLE))
    filled = {f: llm_fields[f] for f in _FILLABLE if base_fields[f] is None and llm_fields[f] is not None}
    if not filled:
        return base
    return base.model_copy(update=filled | {"notes": "heuristic+llm:" + ",".join(sorted(filled))})
