"""Assistente de entrada do Orquestrador: lê cada mensagem do analista e decide o que ela é.

- demanda de crédito agro → abre um case (squad);
- dúvida sobre política, documentação ou produtos → responde pela base interna, citando as fontes (KB-*);
- pergunta sobre o case aberto → responde a partir do relatório já consolidado (nenhum dado novo é consultado);
- resposta/ajuste para o case aberto → o frontend encaminha para /reply ou /human-review;
- saudação ou "o que você faz" → explica as capacidades; fora de crédito agro → diz o escopo.

Determinístico (sem LLM): a classificação não autoriza nada e a resposta só usa a base de conhecimento, que o
perfil do usuário precisa poder ler, ou o relatório que ele já recebeu.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.schemas.case import CaseState, CaseStatus
from app.core.schemas.context import UserIdentity
from app.core.schemas.report import Report
from app.data.repository import KnowledgeRetriever
from app.orchestration.interpreter import heuristic_interpret

AssistKind = Literal[
    "credit_demand", "case_reply", "adjustment", "case_question", "policy_answer", "capabilities", "out_of_scope", "clarify"
]


class Citation(BaseModel):
    id: str
    title: str
    excerpt: str


class AssistRequest(BaseModel):
    user_id: str
    text: str
    case_id: str | None = None


class AssistReply(BaseModel):
    kind: AssistKind
    message: str = ""
    bullets: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


_GREETING = re.compile(r"^\s*(oi|ol[aá]|bom dia|boa tarde|boa noite|e a[ií]|hello|hi)\b", re.IGNORECASE)
_CAPABILITIES = re.compile(
    r"o que (voc[eê] )?(consegue|pode|sabe|faz)|como (voc[eê] )?funciona|quem [eé] voc[eê]|capacidade|"
    r"em que (voc[eê] )?pode|como (voc[eê] )?(me )?ajuda",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^\s*(qual|quais|como|quando|quanto|quantos|quantas|o que|por que|porque|existe|h[aá] |onde|precisa|preciso de qu)",
    re.IGNORECASE,
)
_REQUEST_START = re.compile(r"^\s*(pode|poderia|daria|d[aá] (pra|para)|consegue|voc[eê] pode)", re.IGNORECASE)
_IMPERATIVE = re.compile(r"^\s*(analis|avali|estrutur|mont|fa[cç]a|rode|execut|simul|compar)", re.IGNORECASE)
_AGRO_CREDIT = re.compile(
    r"cr[eé]dito|custeio|investimento|comercializa|safra|soja|milho|algod|caf[eé]|trigo|cana|arroz|produtor|fazenda|"
    r"rural|agro|financiament|garantia|penhor|aval|\bcpr\b|pol[ií]tica|document|elegib|alavancag|cobertura|estresse|"
    r"limite|ticket|taxa|prazo|amortiza|cat[aá]logo|produto|arrendamento|matr[ií]cula|plantio|demonstra|cliente|risco",
    re.IGNORECASE,
)
_DEMAND = re.compile(
    r"solicit|pede|pedido|quer |deseja|analis|avali|estrutur|financi|opera[cç]|precisa de r\$", re.IGNORECASE
)

CAPABILITIES = [
    "Analisar uma operação de crédito agro (custeio, investimento ou comercialização): monto uma squad que checa "
    "elegibilidade e documentação, calcula capacidade de pagamento e cenários de estresse, propõe estruturas e revisa "
    "o resultado.",
    "Responder dúvidas sobre políticas, documentos exigidos e produtos, citando a base interna.",
    "Conferir documentos que você anexar (plano de plantio, matrícula ou arrendamento, demonstrações financeiras) e "
    "apontar o que falta.",
    "Refazer partes da análise com os seus ajustes (garantias, prazo, leitura de riscos) e comparar as versões.",
    "Explicar o relatório: riscos, cenários de estresse, alternativas, pendências e o que a revisão encontrou.",
]

EXAMPLES = [
    "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26.",
    "Quais documentos são obrigatórios para custeio?",
    "Qual é o limite de alavancagem da política de crédito?",
]


def assist(text: str, user: UserIdentity, state: CaseState | None, knowledge: KnowledgeRetriever) -> AssistReply:
    t = text.strip()
    if (_GREETING.search(t) and len(t) < 40) or _CAPABILITIES.search(t):
        return AssistReply(
            kind="capabilities",
            message="Sou o Orquestrador das squads de crédito agro. Posso:",
            bullets=CAPABILITIES,
            suggestions=EXAMPLES,
        )

    h = heuristic_interpret(t)
    agro = bool(_AGRO_CREDIT.search(t))
    question = (t.endswith("?") or bool(_QUESTION_START.search(t))) and not _IMPERATIVE.search(t)
    has_case_data = h.client_ref is not None or h.requested_amount is not None

    if state is not None:
        # na revisão humana, "pode incluir aval?" é um pedido de ajuste, não uma dúvida
        if state.status == CaseStatus.human_review_required and _REQUEST_START.search(t):
            question = False
        return _with_case(t, question, has_case_data, user, state, knowledge)

    if question and agro and not has_case_data:
        return _policy_answer(t, user, knowledge)
    signals = sum([has_case_data, h.purpose is not None and h.crop is not None, bool(_DEMAND.search(t))])
    if agro and signals >= 1:
        return AssistReply(kind="credit_demand")
    if agro:
        return _clarify()
    return AssistReply(
        kind="out_of_scope",
        message="Isso fica fora do que eu faço. Meu escopo é crédito agro: análise de operações, políticas, documentos e "
        "produtos. Posso ajudar com algo assim?",
        suggestions=EXAMPLES,
    )


def _with_case(
    t: str, question: bool, has_case_data: bool, user: UserIdentity, state: CaseState, knowledge: KnowledgeRetriever
) -> AssistReply:
    status = state.status
    if question and not has_case_data:
        if state.report is not None and (reply := _case_answer(t, state.report)) is not None:
            return reply
        if status == CaseStatus.waiting_input and state.missing_info is not None:
            return AssistReply(
                kind="clarify",
                message="Preciso dessa informação porque a análise não fecha sem ela. " + state.missing_info.message,
            )
        policy = _policy_answer(t, user, knowledge)
        if policy.kind == "policy_answer":
            return policy
    if status == CaseStatus.human_review_required:
        return AssistReply(kind="adjustment")
    return AssistReply(kind="case_reply")


def _policy_answer(t: str, user: UserIdentity, knowledge: KnowledgeRetriever) -> AssistReply:
    if "knowledge" not in user.permissions_read:
        return AssistReply(kind="clarify", message="Seu perfil não tem acesso à base de políticas internas.")
    chunks = [c for c in knowledge.search(t, top_k=3) if c.get("score", 0) >= 0.25]
    if not chunks:
        return _clarify("Não encontrei isso nas políticas internas.")
    return AssistReply(
        kind="policy_answer",
        message="Encontrei isto nas políticas internas (dados de demonstração):",
        bullets=[f"{_short_title(c['title'])}: {_gist(c['text'])}" for c in chunks],
        citations=[
            Citation(id=f"KB-{c['doc_id']}-c{c['chunk_index']}", title=c["title"], excerpt=c["text"][:900]) for c in chunks
        ],
        suggestions=["Analisar uma operação com base nisso", "Quais documentos são obrigatórios para custeio?"],
    )


def _clarify(lead: str = "") -> AssistReply:
    return AssistReply(
        kind="clarify",
        message=(lead + " " if lead else "")
        + "Posso seguir de dois jeitos: analisar uma operação de um cliente (me diga quem é, o valor e a finalidade) "
        "ou responder uma dúvida sobre políticas, documentos e produtos. O que você prefere?",
        suggestions=EXAMPLES,
    )


_CLASSIFICATION = {
    "comfortable": "confortável",
    "reduced_buffer": "folga reduzida",
    "attention_required": "requer atenção",
    "insufficient": "insuficiente",
}


def _case_answer(t: str, r: Report) -> AssistReply | None:
    low = t.lower()
    if re.search(r"risco|estresse|cobertura|pagamento|caixa|cen[aá]rio", low):
        bullets = [
            f"{s.label}: cobertura de {s.coverage:.2f}x".replace(".", ",")
            + f" ({_CLASSIFICATION.get(s.classification, s.classification)})"
            for s in r.stress_scenarios
        ] + [f.text for f in r.risk_factors[:3]]
        return AssistReply(kind="case_question", message="Sobre risco e capacidade de pagamento:", bullets=bullets)
    if re.search(r"alternativ|estrutura|garantia|prazo|amortiza", low):
        bullets = [
            f"{a.name}: {a.tenor_months} meses, {a.amortization.replace('_', ' ')}, garantias {', '.join(a.guarantees)}"
            for a in r.alternatives
        ]
        return AssistReply(
            kind="case_question",
            message="As estruturas comparáveis que a squad propôs (sem preferência do sistema):",
            bullets=bullets,
        )
    if re.search(r"pend[eê]nc|document|falta|incerte", low):
        items = [i.text for i in r.missing_data + r.uncertainties]
        return AssistReply(
            kind="case_question",
            message="Pendências e incertezas registradas:" if items else "O relatório não registrou pendências.",
            bullets=items,
        )
    if re.search(r"revis|achado|problema|erro|corrig", low):
        bullets = [f"{f.message} ({'resolvido' if f.status == 'resolved' else f.status})" for f in r.review.findings]
        return AssistReply(kind="case_question", message="O que a revisão encontrou:", bullets=bullets)
    return None


def _short_title(title: str) -> str:
    return title.split(" — ")[-1]


def _gist(text: str) -> str:
    lines = [ln.strip("- ").strip().rstrip(".;") for ln in text.splitlines() if ln.strip()]
    gist = "; ".join(lines[:3]) + "."
    return gist if len(gist) <= 260 else gist[:257].rstrip() + "…"
