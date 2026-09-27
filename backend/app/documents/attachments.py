"""Documentos anexados pelo analista na conversa (UNTRUSTED DATA).

Viram documentos do case e chegam aos agentes pela mesma tool (`get_available_documents`) dos documentos do
cliente: passam pelo filtro de campos, pelo Injection Guard e pela auditoria do Gateway. O texto nunca vira
instrução; o tipo é inferido por palavras-chave para a Elegibilidade reconhecer documentos obrigatórios.
"""

import io
import json
import re
import unicodedata

MAX_BYTES = 2_000_000
MAX_CHARS = 12_000  # o que vai para o prompt; o resto é cortado e marcado como truncado
MAX_PER_CASE = 10
SUPPORTED = (".pdf", ".txt", ".md", ".csv", ".json")

# tipo → padrões (nome do arquivo + texto, sem acento)
_TYPES: tuple[tuple[str, str], ...] = (
    ("demonstracoes_financeiras", r"demonstra\w*\s+financeir|balanco|\bdre\b|\bebitda\b|demonstrativo"),
    ("plano_de_plantio", r"plano\s+de\s+plantio|plantio|produtividade\s+estimada"),
    ("matricula_ou_arrendamento", r"matricula|arrendamento|\bccir\b|\bcar\b|escritura"),
)


class AttachmentError(ValueError):
    pass


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def extract_text(filename: str, data: bytes) -> tuple[str, bool]:
    """Texto do arquivo e se foi truncado. Erros viram AttachmentError com mensagem para o analista."""
    name = filename.lower()
    if not name.endswith(SUPPORTED):
        raise AttachmentError(f"Formato não suportado. Use {', '.join(SUPPORTED)}.")
    if len(data) > MAX_BYTES:
        raise AttachmentError(f"Arquivo maior que {MAX_BYTES // 1_000_000} MB.")
    if name.endswith(".pdf"):
        text = _pdf_text(data)
    else:
        text = data.decode("utf-8", errors="replace")
        if name.endswith(".json"):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
            except ValueError:
                pass
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        raise AttachmentError("Não encontrei texto no arquivo (PDF escaneado ou vazio).")
    return (text[:MAX_CHARS], True) if len(text) > MAX_CHARS else (text, False)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # import local: só quem anexa PDF precisa

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:50])
    except Exception as exc:  # noqa: BLE001 — PDF corrompido/criptografado vira erro legível
        raise AttachmentError("Não consegui ler o PDF (corrompido ou protegido por senha).") from exc


def infer_type(filename: str, text: str) -> str:
    haystack = _plain(f"{filename} {text[:4000]}")
    return next((t for t, pat in _TYPES if re.search(pat, haystack)), "documento_complementar")
