# Atena

**Uma squad de agentes especializados para a análise inicial e a estruturação de operações de crédito agro.**

O analista descreve a demanda em linguagem natural, por exemplo:

> O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2026/27.

A Atena interpreta o pedido, aciona quatro especialistas em sequência e devolve um relatório com capacidade de pagamento, cenários de estresse, alternativas de estrutura, riscos, incertezas e fontes que podem ser consultadas. A decisão fica com uma pessoa: o sistema **não aprova crédito** e **não executa operações**.

> **Ambiente demonstrativo.** Clientes, documentos, produtos, políticas e identidades são fictícios. As chamadas ao modelo de linguagem, porém, são reais e usam a chave configurada por você.

---

## Como funciona

```text
Demanda do analista
        │
        ▼
  Orquestrador ── identifica cliente, valor, finalidade, cultura e safra
        │
        ▼
  Elegibilidade ── há informação e documentação suficientes?  ──não──▶ pede o que falta
        │ sim
        ▼
  Risco ────────── geração de caixa, alavancagem e estresse (calculados por código)
        │
        ▼
  Estruturação ─── 2–3 alternativas do catálogo, lado a lado, sem uma preferida
        │
        ▼
  Revisor ──────── premissas frágeis, inconsistências, riscos sem tratamento
        │            └─▶ se necessário, reabre o especialista responsável (1 rodada)
        ▼
  Relatório ── Output Guard ── revisão humana
```

O princípio que organiza o projeto:

```text
LLM PROPÕE.  BACKEND AUTORIZA.  TOOL EXECUTA.  AUDIT REGISTRA.  HUMANO DECIDE.
```

A segurança não depende de o modelo obedecer ao prompt. Ela é garantida por código:

- **Escopo do caso:** cada caso fica vinculado a um cliente, e o acesso a qualquer outro é negado no backend antes de chegar ao modelo.
- **Permissões por agente:** o acesso efetivo é a interseção entre usuário, agente, caso, finalidade e política do recurso, com filtros por linha e por campo.
- **Dados não são instruções:** documentos e retornos de ferramentas entram como conteúdo não confiável. Uma tentativa de prompt injection pode ser sinalizada, mas não altera permissões.
- **Cálculos determinísticos:** indicadores e estresses são calculados por código. O modelo interpreta os números, mas não os produz.
- **Rastreabilidade:** cada fato e cada cálculo recebem um `source_id` ou `calculation_id` validado, e toda consulta, permitida ou negada, fica registrada na auditoria.
- **Output Guard:** antes de exibir o relatório, verifica secrets, IDs fora do escopo e linguagem de aprovação automática.

---

## Rodar localmente

### Pré-requisitos

- Python **3.10+** (com `venv` e `pip`)
- Node.js **20.19+** e npm
- Make e Bash
- Uma chave de API de um provedor compatível com **Chat Completions da OpenAI** e saída JSON

### 1. Instale as dependências

Na raiz do repositório:

```bash
make install
```

Esse comando cria o ambiente virtual em `backend/.venv`, instala o backend e o frontend e **cria o arquivo `.env` na raiz do repositório**, copiado de `.env.example` se ainda não existir.

### 2. Configure a chave da API

Abra o **`.env` na raiz do repositório**, ao lado de `.env.example` e do `Makefile`, e preencha a chave:

```dotenv
LLM_API_KEY=sua-chave-aqui
```

O `.env` está no `.gitignore` e não deve ser versionado. Só o backend lê esse arquivo, em [`backend/app/config.py`](backend/app/config.py). A chave nunca entra em prompts nem no bundle do frontend, e o Output Guard bloqueia qualquer saída que a contenha.

Variáveis disponíveis:

| Variável | Para que serve | Padrão |
| --- | --- | --- |
| `LLM_API_KEY` | Chave do provedor. **Obrigatória** para executar os agentes. | — |
| `LLM_BASE_URL` | Endpoint compatível com a API da OpenAI. | `https://api.openai.com/v1` |
| `LLM_MODEL` | Modelo disponível na sua conta. | `gpt-4o-mini` |
| `LLM_TIMEOUT_SECONDS` | Tempo máximo de cada chamada. | `60` |
| `LLM_MAX_RETRIES` | Novas tentativas em erros transitórios. | `5` |
| `LLM_RETRY_BACKOFF_SECONDS` | Intervalo inicial entre tentativas, que cresce a cada nova tentativa. | `2` |
| `DEMO_MODE` | Habilita as opções de demonstração, como o documento adversarial. | `true` |

O `.env.example` traz uma configuração de provedor pronta e uma alternativa comentada. Ajuste `LLM_MODEL` a um modelo disponível na sua conta.

### 3. Execute

```bash
make run
```

Abra **http://localhost:8000**. O comando gera o frontend e sobe o FastAPI, que serve a interface e a API na mesma porta. Para usar outra porta, rode `make run PORT=8001`.

Para desenvolver com hot reload:

```bash
make dev
```

A interface fica em **http://localhost:5173**, com proxy de `/api` para o backend na porta 8000. `Ctrl+C` encerra os dois processos.

Com o servidor no ar, também ficam disponíveis:

- `GET http://localhost:8000/api/health`: verificação rápida do backend
- **http://localhost:8000/docs**: documentação interativa da API

<details>
<summary>Sem Make</summary>

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
cp .env.example .env            # e preencha LLM_API_KEY
(cd frontend && npm install && npm run build)
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
```

</details>

### Com Docker

O [Dockerfile](Dockerfile) gera uma imagem única com o frontend compilado e o FastAPI. No container, a chave é passada por variável de ambiente e não entra na imagem:

```bash
docker build -t atena .
docker run -p 8000:8000 -e LLM_API_KEY=sua-chave-aqui -e LLM_MODEL=... atena
```

Para publicar no Render, use o [render.yaml](render.yaml) (New + › Blueprint) e preencha as variáveis no painel. Os detalhes estão no [Guia de uso](GUIA_DE_USO.md#publicar-com-um-link-docker).

### Sem chave?

O servidor sobe e a interface funciona, mas a execução da squad é recusada com `llm_not_configured` e a tela mostra um aviso. Os testes automatizados usam um modelo simulado e **não precisam de chave**.

---

## Primeira análise

1. Clique em **Nova conversa** e envie o pedido do início deste README. Você também pode identificar o cliente como `CLIENTE-001`.
2. Confira a demanda interpretada e clique em **Executar squad**.
3. Acompanhe os especialistas, as consultas e os eventos de segurança na conversa.
4. Abra o **Relatório** e a **Auditoria**. As referências ao lado das conclusões são clicáveis.
5. Peça um ajuste em texto livre (até três por caso) ou registre a revisão humana.

Para ver a governança em ação, ative **Teste de segurança** antes de enviar. O caso passa a incluir um documento que tenta fazer o sistema consultar `CLIENTE-999`, e a tentativa aparece como negada na auditoria.

O [Guia de uso](GUIA_DE_USO.md) traz o roteiro completo, os cenários de demonstração e a solução de problemas comuns.

---

## Testes e benchmark

```bash
make test              # pytest + ruff + build e lint do frontend (sem API)
make benchmark-audit   # confere offline os 48 registros publicados e seus custos
make benchmark-plan    # mostra casos e modelos do comparativo, sem chamar a API
make benchmark         # executa o comparativo real (chamadas pagas à API)
```

O benchmark compara a squad com um agente generalista em oito casos fictícios, entre eles cultura divergente, documento ausente, alavancagem alta e documento malicioso. No resultado publicado, a squad com GPT-4.1 mini passou nos 8 casos por **US$ 0,089** no total. O generalista só chegou a 8/8 com GPT-5.4 e raciocínio alto, por **US$ 1,56**. A amostra é pequena, com uma repetição por caso. Os detalhes e as ressalvas estão em [BENCHMARK.md](BENCHMARK.md) e [BENCHMARK_RECALCULO.md](BENCHMARK_RECALCULO.md).

---

## Estrutura do repositório

```text
.
├── backend/                  FastAPI + Pydantic
│   ├── app/
│   │   ├── agents/           especialistas, playbooks e agent cards
│   │   ├── orchestration/    orquestrador, retrabalho e consolidação do relatório
│   │   ├── governance/       policy engine, filtros, Output Guard
│   │   ├── tools/            gateway de ferramentas e dados
│   │   ├── calculations/     indicadores e cenários de estresse
│   │   ├── llm/              cliente compatível com a API da OpenAI
│   │   ├── data/mock/        clientes, financeiros, perfis agro, mercado, produtos, políticas
│   │   ├── knowledge/corpus/ políticas, catálogo, roteiro de risco e glossário
│   │   ├── evaluation/       benchmark squad × generalista e resultados publicados
│   │   └── api/              rotas REST
│   └── tests/
├── frontend/                 React + TypeScript + Vite
├── Dockerfile, render.yaml   imagem única e deploy no Render
├── Makefile                  instalação, execução, testes e benchmark
└── .env.example              modelo de configuração (copie para .env)
```

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [GUIA_DE_USO.md](GUIA_DE_USO.md) | Funcionalidades, roteiro de demonstração e problemas comuns. |
| [ESPECIFICACAO.md](ESPECIFICACAO.md) | Especificação funcional: objetivos, agentes, guardrails e invariantes de segurança. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura técnica, contratos e decisões de simplificação. |
| [BENCHMARK.md](BENCHMARK.md) | Protocolo do comparativo de custo e qualidade. |
| [BENCHMARK_RECALCULO.md](BENCHMARK_RECALCULO.md) | Recontagem independente dos resultados publicados. |
| [TASKS.md](TASKS.md) | Decomposição do trabalho de implementação. |

## Limitações atuais

- Casos, evidências e eventos ficam **em memória**: reiniciar o backend apaga esses dados. O histórico de conversas fica no navegador.
- As identidades são fictícias (`analyst-001`) e não há autenticação corporativa.
- Os documentos já vêm cadastrados na base local, sem upload pela interface. As cotações de mercado também são fixas, não vêm de uma fonte em tempo real.
- O fluxo foi preparado para crédito agro, com um caso principal de soja.
