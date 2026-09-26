"""KeywordKnowledgeRetriever: chunking por seção `##` + score por palavras-chave (sem embeddings, sem vector DB)."""

import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.governance.bootstrap_resolver import normalize

_STOPWORDS = frozenset(
    "a o as os de da do das dos e em um uma para por com no na nos nas que se ao aos à às ou como sobre é são".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalize(text)) if len(t) > 2 and t not in _STOPWORDS]


class KeywordKnowledgeRetriever:
    def __init__(self, corpus_dir: Path | None = None) -> None:
        self._dir = corpus_dir or get_settings().knowledge_corpus_dir
        self._chunks: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._chunks is None:
            chunks = []
            for path in sorted(self._dir.glob("*.md")):
                chunks.extend(self._chunk(path.stem, path.read_text(encoding="utf-8")))
            self._chunks = chunks
        return self._chunks

    @staticmethod
    def _chunk(doc_id: str, text: str) -> list[dict[str, Any]]:
        doc_title = ""
        sections: list[tuple[str, list[str]]] = []
        for line in text.splitlines():
            if line.startswith("# ") and not doc_title:
                doc_title = line[2:].strip()
            elif line.startswith("## "):
                sections.append((line[3:].strip(), []))
            elif sections:
                sections[-1][1].append(line)
        out = []
        for i, (title, body_lines) in enumerate(sections, start=1):
            body = "\n".join(body_lines).strip()
            if not body:
                continue
            out.append(
                {
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "title": f"{doc_title} — {title}" if doc_title else title,
                    "text": body,
                    "_tokens": set(tokenize(title + " " + body)),
                }
            )
        return out

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        q = set(tokenize(query))
        if not q:
            return []
        scored = []
        for c in self._load():
            hits = len(q & c["_tokens"])
            if hits:
                scored.append((hits / len(q), c))
        scored.sort(key=lambda s: (-s[0], s[1]["doc_id"], s[1]["chunk_index"]))
        return [{k: v for k, v in c.items() if k != "_tokens"} | {"score": round(score, 3)} for score, c in scored[:top_k]]
