"""Leitura de resumos persistidos. A API não inicia chamadas pagas nem expõe prompts."""

import json
from pathlib import Path


def latest_summary(directory: Path):
    if not directory.exists():
        return None
    # O arquivo é publicado atomicamente pelo runner. Não aceita caminhos vindos do browser.
    paths = sorted(directory.glob("*/summary.json"), key=lambda p: p.parent.name, reverse=True)
    for path in paths:
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(summary, dict) and summary.get("version") == 1 and isinstance(summary.get("groups"), list):
                return summary
        except (OSError, ValueError):
            continue
    return None
