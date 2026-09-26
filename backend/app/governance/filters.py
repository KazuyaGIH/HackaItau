"""Row-level e field-level filtering (ARCHITECTURE.md §10). Funções puras sobre listas de dicts."""

from collections.abc import Iterable, Sequence
from typing import Any

Record = dict[str, Any]


def apply_row_scope(records: Iterable[Record], scope: Sequence[str]) -> list[Record]:
    """Mantém registros sem `client_id` (mercado, catálogo, knowledge) ou com `client_id ∈ scope`."""
    kept = []
    for r in records:
        cid = r.get("client_id")
        if cid is None or cid in scope:
            kept.append(r)
    return kept


def apply_field_projection(record: Record, projection: list[str] | None, never: Sequence[str]) -> tuple[Record, int]:
    """`never` sempre removido; projection None = todos os restantes; [] = nada. Devolve (registro, fields_hidden)."""
    without_never = {k: v for k, v in record.items() if k not in never}
    if projection is None:
        kept = without_never
    else:
        allowed = set(projection)
        kept = {k: v for k, v in without_never.items() if k in allowed}
    return kept, len(record) - len(kept)


def project_records(
    records: Iterable[Record], projection: list[str] | None, never: Sequence[str]
) -> list[tuple[Record, int]]:
    return [apply_field_projection(r, projection, never) for r in records]
