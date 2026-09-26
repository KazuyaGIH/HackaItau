"""Interpretação da demanda (ARCHITECTURE.md §3). Saída é PROPOSTA: nada aqui vira permissão.

`heuristic_interpret` é determinístico e serve de contingência quando o LLM não está configurado
(S3.4 adiciona `interpret_with_llm`, que cai aqui em caso de falha).
"""

import re

from app.core.schemas.outputs import InterpretedDemand

_CLIENT_ID_RE = re.compile(r"\bCLIENTE-\d{3,}\b", re.IGNORECASE)
# "cliente Fazenda Horizonte S.A. solicita" / "empresa X pede" / "para a Agro Delta Ltda."
_CLIENT_NAME_RE = re.compile(
    r"\b(?:cliente|empresa|produtor|grupo)\s+(?P<name>[A-ZÁ-Ú][\w&.\-]*(?:\s+[A-ZÁ-Úa-zá-ú][\w&.\-]*){0,5}?)"
    r"(?=\s+(?:solicita|pede|precisa|quer|deseja|busca|requer)|[,.;:]|\s*$)",
)
_AMOUNT_RE = re.compile(
    r"R?\$?\s*(?P<num>\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(?P<unit>milh(?:ão|ões|oes|ao)|mi\b|mm\b|bilh(?:ão|ões|oes|ao)|bi\b|mil\b)?",
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


def _parse_amount(text: str) -> float | None:
    best: float | None = None
    for m in _AMOUNT_RE.finditer(text):
        raw, unit = m.group("num"), (m.group("unit") or "").lower()
        has_currency = m.group(0).lstrip().startswith(("R$", "$"))
        if not unit and not has_currency:
            continue  # número solto (ano, área, sc/ha) não é valor
        mult = 1.0
        if unit.startswith("milh") or unit in ("mi", "mm"):
            mult = 1e6
        elif unit.startswith("bilh") or unit == "bi":
            mult = 1e9
        elif unit == "mil":
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
        requested_amount=_parse_amount(text),
        purpose=_strip_accents(purpose) if purpose else None,
        crop=_strip_accents(crop) if crop else None,
        cycle=cycle,
        notes="heuristic",
    )
