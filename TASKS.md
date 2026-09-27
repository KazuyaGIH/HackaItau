# TASKS.md — P0

Decomposição do `Final P0 Scope` (ARCHITECTURE.md) em tarefas por stream. Referências `§n` apontam para ARCHITECTURE.md.

Regra de ordem: **T0 (kernel) merge primeiro**; depois S1–S5 em paralelo contra fixtures; T9 (integração) por último.

---

## Infra / stack (só o necessário)

| Item | Escolha | Observação |
|---|---|---|
| Backend | Python 3.10+ (`X \| None` ok; sem `Self`/`except*`), FastAPI, pydantic v2, pydantic-settings, httpx, uvicorn | `backend/pyproject.toml`; gerenciar com `pip`/`venv` (ou `uv` se disponível) |
| Testes backend | pytest, pytest-asyncio | sem cobertura, sem mutation, sem CI obrigatória |
| Frontend | Node 20 LTS, Vite + React + TypeScript | sem router, sem state manager, sem UI kit pesado (CSS simples) |
| LLM | 1 provider OpenAI-compatible via `httpx` (chat completions + `response_format=json_object`) | `.env`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `DEMO_MODE=true`. Nenhum SDK pesado |
| Dados / conhecimento | JSON em `backend/app/data/mock/`, markdown em `backend/app/knowledge/corpus/` | sem DB, sem vector store |
| Estado | dict em memória | sem Redis, sem fila |
| Execução local | `make install` → `make run` (demo: build + FastAPI servindo tudo em :8000) ou `make dev` (vite + uvicorn --reload, um terminal) | `Makefile` na raiz; `make test` roda pytest/ruff/build/lint |
| Lint/format | `ruff` (backend), `eslint`+`prettier` default do Vite (frontend) | opcional; não bloqueia merge |
| Deploy | **nenhum em P0** | P1: Dockerfile único + Render/Fly |
| Segredos | só `.env` local (gitignored) + `.env.example` commitado | `config.py` é o único leitor |

Não usar: Docker Compose, Postgres, Redis, Celery, LangChain/LangGraph, embeddings, SSE/WebSocket, OpenAPI codegen, Next.js.

Pré-requisitos na máquina de quem coda: Python 3.10+, Node 20, uma `LLM_API_KEY` válida (sem ela o backend sobe, `/api/health` reporta `llm_mode=unconfigured` e `POST /run` é recusado com 503 `llm_not_configured`; a UI mostra o aviso). Testes automatizados usam um provider stub em `tests/`.

---

## T0 — Kernel (congelar contratos; 1 PR, sem lógica) — §19

- [ ] T0.1 `backend/pyproject.toml`, `app/main.py` (FastAPI vazio + `/api/health`), `app/config.py`, `.env.example`, `.gitignore`
- [ ] T0.2 `core/schemas/context.py`: `UserIdentity`, `CaseScope(frozen)`, `ExecutionContext(frozen, case_scope obrigatório)`
- [ ] T0.3 `core/schemas/case.py`: `CaseStatus` (§4), `CaseState`
- [ ] T0.4 `core/schemas/events.py`: `EventType` (lista congelada §15), `Event`
- [ ] T0.5 `core/schemas/agent.py`: `AgentCard`, `ToolCallSpec{tool, params, params_from}`, `TaskSpec`, `ReworkInstruction{finding_ids, required_action, params, message}`, `Assumption{name, value, source_id, justification, origin}`, `AgentResult`, `LLMUsage`
- [ ] T0.6 `core/schemas/outputs.py`: `EligibilityOutput`, `RiskOutput` (campos `code_owned` vs `llm_owned`), `StructuringOutput` (`alternatives` 2–3, `Alternative` sem campo de preferência), `ReviewOutput`, `Finding`
- [ ] T0.7 `core/schemas/evidence.py`: `EvidenceItem`, `SourceRecord`, `CalculationRecord`, `EvidenceBundle`; formato de IDs `SRC-/KB-/CALC-/OUT-` (§12)
- [ ] T0.8 `core/schemas/tools.py`: `ToolSpec`, `ToolResult`, `Decision`; `core/schemas/report.py`: `Report` e views (§16)
- [ ] T0.9 `llm/provider.py` (`LLMProvider`, `LLMResponse`), `data/repository.py` (`DataRepository`), `agents/base.py` (`Agent` Protocol), `tools/registry.py` só com as 9 `ToolSpec` (handlers `NotImplemented`)
- [ ] T0.10 `governance/identities.json`, `purposes.json`, `resource_policies.json` (§10; `agro_structuring` ausente de `client_financials`/`agro_profile`), 4 `agents/cards/*.json`
- [ ] T0.11 Schema dos mocks com IDs finais (`CLIENTE-001`, `CLIENTE-999`, `POL-CRED-002`, …) e `tests/fixtures/` iniciais (ctx, cards, um output por agente, um `EvidenceBundle`)
- [ ] T0.12 `frontend/` scaffold Vite + `src/types.ts` espelhando os schemas

Critério: `pytest` roda (mesmo que só import), `npm run build` passa, ninguém mais edita `core/schemas/*` sem PR dedicado.

---

## S1 — Governance + Gateway + Data + API — §7 §8 §9 §10 §11

- [ ] S1.1 `governance/policy_engine.py`: `authorize()` — allowlist, user, agent, purpose, scope por `client_id`, projeção de campos; deny sem detalhes
- [ ] S1.2 `governance/filters.py`: `apply_row_scope`, `apply_field_projection` (`never` sempre; sem entrada para o agente = vazio; conta `fields_hidden`)
- [ ] S1.3 `governance/bootstrap_resolver.py`: `BootstrapClientResolver.resolve()` — só permissão do usuário, match exato/normalizado, `MIN_NAME_LEN`, `not_found | ambiguous(count) | ok(ClientRef)`, evento `BOOTSTRAP_RESOLVED`
- [ ] S1.4 `governance/injection_guard.py`: padrões heurísticos + IDs fora do scope → `flagged`, `SECURITY_EVENT`; **scope probe** (`authorize` sem handler → `PERMISSION_DENIED{probe:true}`)
- [ ] S1.5 `core/events.py` (`EventLog` append-only, `list_after`), `core/evidence.py` (`EvidenceRegistry`, IDs determinísticos), `core/store.py` (`CaseStore` em memória)
- [ ] S1.6 `tools/gateway.py`: `Toolbox.call()` na ordem de §8 (validação params → authorize → eventos → handler → row → field → injection → register → `TOOL_CALLED`)
- [ ] S1.7 `data/json_repository.py` (`JsonMockRepository`, valida `_meta.mock=true`) + `tools/data_tools.py` (handlers das 7 tools read/search)
- [ ] S1.8 `knowledge/retriever.py`: chunking por seção markdown + keyword score → `KB-<DOC>-c<n>`; `tools/knowledge_tools.py`
- [ ] S1.9 `api/routes.py`: os 7 endpoints P0 de §19.9 (`/api/agents` fora); `main.py` serve `frontend/dist`
- [ ] S1.10 Testes: `test_policy_engine.py` (no-union, user/agent/purpose deny, `CLIENTE-999` deny com `security`, structuring ∌ financials), `test_bootstrap_resolver.py` (sem permissão → deny; nome curto → not_found; 2 matches → ambiguous sem candidatos; saída só `client_id,name`), `test_gateway_filters.py` (row, field, `never`, injection flag, probe)

---

## S2 — Agentes especialistas + cálculos + LLM — §5 §6.1–6.3 §13

- [ ] S2.1 `llm/openai_compat.py`: `complete()` com json mode, timeout, checagem de secret nas mensagens, `LLMUsage`; `llm/prompting.py` (`wrap_untrusted`, `render_schema`, retry 1× com erro de validação)
- [ ] S2.2 `agents/runtime.py`: `gather (código) → reason (1 chamada, sem tools) → validate`; grounding (IDs existem **e** foram fornecidos ao agente); `GROUNDING_REJECTED`; registra `OUT-<agent>-R<n>`; `AGENT_STARTED/COMPLETED`, `LLM_CALLED`; sem provider/erro de provider/schema inválido após retry → `AgentExecutionError` (auditável)
- [ ] S2.3 `agents/registry.py` + carregamento dos cards; `gather` default executa `card.required_data` com `params_from` (`scope.client_id`, `task.inputs.crop`, …)
- [ ] S2.4 `calculations/credit_metrics.py`, `calculations/stress.py` (puras; classificação por thresholds passados como parâmetro); `tools/calc_tools.py` registra `CALC-*` com inputs/fontes/thresholds `KB-*`
- [ ] S2.5 `agents/eligibility/`: playbook, `validate` com lista de obrigatórios da policy → `blocked` por código; gate
- [ ] S2.6 `agents/risk/baseline.py`: `AssumptionSet` por código (`baseline_policy ∈ {declared, historical}`), `origin="code"`, `justification` só com fonte; `agents/risk/agent.py`: gather = dados + baseline + 2 calcs; `validate` copia números/categorias dos `CALC-*`, marca divergência textual como `warning`
- [ ] S2.7 `agents/structuring/`: domínios `product_catalog`+`knowledge`; gather catálogo + policy; `validate` (amount ≤ pedido, produto no catálogo, tenor no intervalo, 2–3 alternativas, sem linguagem de preferência)
- [ ] S2.8 Playbooks (`## Papel / ## Passos / ## Regras / ## Formato de saída`) dos 3 agentes; regra de untrusted data em todos
- [ ] S2.9 Testes: `test_calculations.py` (valores conhecidos; cenários; classificação), testes de `validate` de cada agente com fixtures, `test_runtime_grounding.py`

---

## S3 — Review + Output Guard + Orchestrator + Report — §4 §6.4 §14 §16

- [ ] S3.1 `agents/review/validators.py`: os 9 códigos de §6.4-A como funções independentes sobre `(outputs, evidence_registry, event_log, policies)`
- [ ] S3.2 `agents/review/remediations.py`: `code → (required_action, params)`; `agents/review/ai_review.py` (1 chamada, findings com `evidence_ids` obrigatórios; sem ID → descartado); merge → `ReviewOutput`, `reexecution_required` só com remediação conhecida
- [ ] S3.3 `governance/output_guard.py`: 6 checks de §14 sobre `Report` (e modo leve sobre `AgentResult`); findings `GUARD_*`; força `decision_status`
- [ ] S3.4 `orchestration/interpreter.py` (LLM → `{intent, client_ref, amount, purpose, crop}`), `orchestration/plans.py` (template `credito_agro`, `depends_on`, `input_projection` exata de §6.3)
- [ ] S3.5 `orchestration/orchestrator.py`: state machine §4; bootstrap → `SCOPE_FROZEN`; `waiting_input` (resolver/gate); execução em `asyncio.Task`; rework 1× (owner + dependentes); `EXECUTION_FAILED`
- [ ] S3.6 `orchestration/consolidator.py`: `Report` por template; números só de `CALC-*`; `governance` view (domínios por agente, denials, security events, `fields_hidden`); `human_gate`
- [ ] S3.7 Human gate: `approve_next_step` → `CASE_COMPLETED` (`completed_demo`); `request_adjustment` → registra comentário no relatório
- [x] S5 Ajuste humano reexecuta o agente escolhido (`target_agent`) + dependentes; `POST /cases/{id}/retry` retoma execução que falhou (checkpoints por agente/rodada) — `tests/test_s5_adjust_retry.py`
- [x] S6 Conversa: leitura ampla da demanda + perguntas de volta em texto livre (`/reply`), anexos (`/attachments`, `pypdf`), assistente de entrada (`/assist`) e métricas de desempenho (`/metrics`) — `tests/test_s6_conversation.py`
- [ ] S3.8 Testes: `test_validators.py` (61 vs 58 → `ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED`; `CALC_INCONSISTENT`; `EVIDENCE_NOT_FOUND`; `RISK_IGNORED_BY_STRUCTURE`), `test_output_guard.py`, `test_orchestrator.py` com provider stub de teste (gate bloqueia Risk; rework 1× e para; case não conclui sem `approve_next_step`; scope imutável)

---

## S4 — Frontend — §17

- [ ] S4.1 `api.ts` (7 endpoints) + polling 1,5 s (`GET /cases/{id}`, `GET /events?after=seq`)
- [ ] S4.2 `CaseInput`: textarea pré-preenchida, toggle "documento adversarial", banner "dados fictícios"
- [ ] S4.3 `SquadBoard`: `AgentCard` (status, domínios acessados, contagens), `Timeline`, `GovernancePanel` (✓/✗ por agente×domínio, security events em destaque, `fields_hidden`, badges "permissões inalteradas" / "LLM sem capability de acesso"), `MissingInfoForm`, indicação de rework (Review → owner reaberto)
- [ ] S4.4 `ReportView`: seções do `Report`, `AlternativesGrid` (colunas comparáveis, sem destaque), `SourceChip` (abre payload da evidência), findings; aviso "LLM não configurado" quando `/api/health` reporta `unconfigured`
- [ ] S4.5 `HumanGate`: "Solicitar ajuste" / "Aprovar para próxima etapa" + texto de responsabilidade humana; estado `completed_demo`
- [ ] S4.6 Desenvolver contra `tests/fixtures/*.json` servidos estaticamente até S1/S3 estarem prontos

---

## S5 — Dados mock + conhecimento + roteiro — §10 §12 §18

- [ ] S5.1 `data/mock/clients.json` (CLIENTE-001 Fazenda Horizonte, CLIENTE-999 e 1–2 outros; campos `never`: `tax_id`, `internal_rating_notes`, `relationship_manager_phone`)
- [ ] S5.2 `financials.json` (revenue, ebitda, cash, gross/net debt; valores que dão alavancagem pró-forma perto do limite), `agro_profiles.json` (`expected_productivity=61`, `historical_productivity=58`, `cost_per_hectare`, `planted_area_hectares`, `region`, `field_agent_notes`), `market_data.json` (soja), `products.json` (3 produtos custeio com tenor/garantias), `documents.json` (incl. doc com área divergente e doc adversarial com `scenario_tags:["adversarial"]`)
- [ ] S5.3 `knowledge/corpus/`: POL-AGRO-001 (elegibilidade + obrigatórios), POL-CRED-002 (thresholds de coverage/alavancagem, 3 cenários de stress, classificação), PLAYBOOK-RISK-001, CATALOG-AGRO-001, GLOSSARY-001 — curtos, com seções `##` para chunking
- [ ] S5.4 `governance/purposes.json` e revisão de `resource_policies.json` contra os campos reais dos mocks
- [ ] S5.5 `docs/demo-script.md`: roteiro de 5 min (caso normal → rework 61/58 → adversarial → human gate)

---

## T9 — Integração e demo (após S1–S5)

- [ ] T9.1 `tests/test_demo_case.py`: golden run end-to-end com provider stub de teste (status final `human_review_required`, 1 rework, findings esperados, 2 security events no modo adversarial, zero `CLIENTE-999` no relatório)
- [ ] T9.2 Rodar end-to-end com LLM real; ajustar playbooks/schemas até 3 runs seguidos passarem no Output Guard sem `GUARD_UNGROUNDED` em massa
- [ ] T9.3 `npm run build` + servir pelo FastAPI; README seção "Rodar localmente" (`.env`, dois comandos)
- [ ] T9.4 Checklist do Final P0 Scope (20 itens) marcado; abrir P1 só depois

---

## Dependências entre streams

```text
T0 ──► S1 ──┐
      S2 ──┼──► T9
      S3 ──┤   (S3 precisa de S1.5/S1.6 para rodar; até lá usa fixtures)
      S4 ──┤   (S4 usa fixtures; troca para API real em T9)
      S5 ──┘   (S5 entrega cedo: S1/S2 testam contra mocks reais)
```
