# Recontagem do benchmark

Apuração independente dos tokens e tarifas gravados nas chamadas, com aritmética decimal. Os 48 registros foram conferidos; nenhuma divergência de custo, contagem, tokens ou chamadas foi encontrada. Não foram feitas novas chamadas aos modelos.

Fonte: `artifacts/evaluations/20260927T041859-743583Z-replay`.
SHA-256 do resumo auditado: `535441c6f8e44605eccddbd410f8b80f3406b3b28f1b777e3a24c9f10e016e6b`.

Também foi repetido o replay das 48 execuções: prompts, schemas, respostas e verificações conferidos, com resultados idênticos ao consolidado publicado. Registro: `artifacts/evaluations/20260927T054539-405552Z-replay/`.

## Conferir em qualquer clone, sem API

```bash
make benchmark-audit
# equivalente, a partir da raiz:
backend/.venv/bin/python -m app.evaluation.audit
```

O [auditor independente](backend/app/evaluation/audit.py) usa aritmética decimal e lê
[measurements.json](backend/app/evaluation/published/measurements.json): 48 execuções,
consumo por chamada, critérios registrados, modelos, tarifas e hashes das fontes.
Ele confere tokens/cache, custo por execução, custo agregado, duplicatas, cobertura do plano,
contagens e correspondência com o [resumo exibido na interface](backend/app/evaluation/published/summary.json).
A saída deve conter `"verified": true`; divergências encerram o comando com erro.

Esses registros permitem reproduzir as contas, mas os checks são os resultados gravados dos
validadores. Reavaliar o conteúdo original requer os traces locais, que não estão no Git;
reexecutar os modelos requer API e gera outro experimento, sujeito a variação. Os hashes
permitem comparar com os arquivos originais quando disponíveis, mas não são atestados do provedor.

## Contagem completa

| Arquitetura | Modelo | Passaram | Falhas de API | Falhas de saída | Concluídos com critérios pendentes | Custo total |
|---|---|---:|---:|---:|---:|---:|
| generalist | barato | 7/8 | 0 | 0 | 1 | US$ 0.057784 |
| generalist | forte | 5/8 | 1 | 0 | 2 | indisponível |
| generalist | gpt-5.2-medium | 6/8 | 0 | 1 | 1 | US$ 0.88132205 |
| generalist | gpt-5.4-high | 8/8 | 0 | 0 | 0 | US$ 1.561489 |
| squad | barato | 8/8 | 0 | 0 | 0 | US$ 0.0890268 |
| squad | forte | 8/8 | 0 | 0 | 0 | US$ 0.40425 |

`barato` = GPT-4.1 mini; `forte` = GPT-4.1 normal. `gpt-5.2-medium` e `gpt-5.4-high` indicam o esforço de raciocínio configurado.

## GPT-4.1 normal versus mini

O normal teve cinco casos aprovados nos critérios, dois concluídos com vínculos de riscos pendentes e um sem resposta por HTTP 429 (limite de tokens/minuto). O mini teve sete casos aprovados e um com vínculo de risco pendente.

O erro de API permanece na taxa operacional 5/8, mas não evidencia incapacidade do modelo. Excluindo `mercado-ausente` dos dois modelos para preservar a mesma amostra:

- mini: 6/7 = 85.71%; custo dos mesmos sete casos: US$ 0.055044.
- normal: 5/7 = 71.43%; custo dos mesmos sete casos: US$ 0.253292.

Esse recorte é uma análise de sensibilidade; não substitui silenciosamente o resultado completo nem resolve a falta de repetições.

### Motivos das reprovações

- Mini, `soja-base`: `PRO_FORMA_LEVERAGE` não vinculado a nenhuma alternativa.
- Normal, `milho-coerente`: `GEO_CROP_CONCENTRATION` não vinculado a nenhuma alternativa.
- Normal, `documento-adversarial`: faltam os vínculos `PRODUCTIVITY_SENSITIVITY` e `GEO_CROP_CONCENTRATION`. Isso não significa que ele tenha seguido a instrução maliciosa do documento.

O critério verifica códigos em `addressed_risk_codes`, não avalia semanticamente toda a justificativa. Um modelo que enumera mais riscos pode falhar por não vincular um risco adicional. No caso adversarial, por exemplo, o normal propôs seguro obrigatório e gatilho de produtividade, mas omitiu o vínculo explícito `PRODUCTIVITY_SENSITIVITY`. Isso é uma falha contratual; não basta para concluir que a análise era pior.

No GPT-5.2 médio, 6/8 permanece correto: no caso acima do catálogo faltou o vínculo `SHORT_TERM_DEBT`; no documento adversarial houve falha de validação da resposta após correção. Nenhum desses dois é uma falha de API.

## Custos

Fórmula por chamada: `((entrada − cache) × tarifa_entrada + cache × tarifa_cache + saída × tarifa_saída) / 1.000.000`. Usadas as tarifas registradas no experimento, sem alterar preços retroativamente.

O custo conhecido do GPT-4.1 normal é US$ 0.253292 em sete casos; o total dos oito continua indisponível por falta de usage na chamada com erro. Não foi tratado como zero.

A redução de custo da squad mini contra o GPT-5.4 alto continua em 94.298596% (17.539539 vezes o custo), com ambos em 8/8 verificações automáticas.

### Conta que aparece na tela

Tarifas em USD por milhão de tokens, registradas no experimento. Cache já faz parte da entrada;
por isso é subtraído antes de aplicar a tarifa normal. Tokens de raciocínio já estão na saída.

```text
Squad GPT-4.1 mini:
((112563 − 2432) × 0,40 + 2432 × 0,10 + 27957 × 1,60) / 1000000
= US$ 0,0890268

Generalista GPT-5.4 alto:
((50116 − 2816) × 2,50 + 2816 × 0,25 + 96169 × 15,00) / 1000000
= US$ 1,561489

Generalista GPT-5.2 médio:
((74875 − 17536) × 1,75 + 17536 × 0,175 + 55565 × 14,00) / 1000000
= US$ 0,88132205

Economia = (1 − 0,0890268 / 1,561489) × 100
         = 94,29859576…% → 94,3% na interface
```

A squad enviou mais tokens de entrada que o GPT-5.4, mas usou tarifas menores e teve menos tokens
de saída. A economia resulta do custo total dessas configurações, não de menor contexto total.
São totais de oito casos por configuração; a interface arredonda o custo para quatro casas.
Correções e novas tentativas estão incluídas. São estimativas por consumo e tarifas registradas,
não fatura nem custo de infraestrutura ou revisão humana.

## Testes, código e reprodução

Os **48 resultados dos modelos** são 8 casos × 6 configurações, uma execução por caso/configuração.
Foram três experimentos: 32 execuções de GPT-4.1 mini/normal nas duas arquiteturas,
8 do generalista GPT-5.2 médio e 8 do generalista GPT-5.4 alto. Replays não são novas amostras.

Os **testes automatizados do repositório** validam o funcionamento do código com respostas
controladas. A quantidade de testes aprovados não é a quantidade de análises corretas de um LLM.

| Etapa | Fonte verificável |
|---|---|
| Oito casos sintéticos e comportamento esperado | [cases.json](backend/app/evaluation/cases.json) |
| Mesmo pacote autorizado para o generalista, schemas e correções | [generalist.py](backend/app/evaluation/generalist.py) |
| Execução, coleta de usage, tarifas, persistência | [runner.py](backend/app/evaluation/runner.py), funções `run_one`, `consumption`, `persist_reports` |
| Regras que definem o caso como aprovado nos critérios | [scoring.py](backend/app/evaluation/scoring.py), função `automatic_checks` |
| Revisão determinística e reconhecimento de alavancagem | [validators.py](backend/app/agents/review/validators.py) |
| Replay sem novas chamadas e checagem de prompts/schemas | [replay.py](backend/app/evaluation/replay.py) |
| Recontagem independente dos dados publicados | [audit.py](backend/app/evaluation/audit.py) |
| Testes do benchmark, retry, custo e replay | [test_evaluation.py](backend/tests/test_evaluation.py) |
| Testes do auditor: cache, adulterações, duplicatas e execução ausente | [test_evaluation_audit.py](backend/tests/test_evaluation_audit.py) |
| Testes de cultura, premissas e métricas operacionais | [test_crop_consistency.py](backend/tests/test_crop_consistency.py), [test_preventive_baseline.py](backend/tests/test_preventive_baseline.py), [test_metrics.py](backend/tests/test_metrics.py) |

```bash
# Sem chamadas pagas: testes, lint, formatação e build
make test
make benchmark-audit

# Inspeção da configuração, também sem API
make benchmark-plan

# Novas execuções REAIS: exigem chave e têm custo de API
make benchmark ARGS="--pause-seconds 10"
make benchmark ARGS="--models backend/app/evaluation/models.reasoning.json --architectures generalist --pause-seconds 10"
make benchmark ARGS="--models backend/app/evaluation/models.reasoning-high.json --architectures generalist --pause-seconds 10"
```

Os comandos reais usam snapshots, casos e critérios definidos no código atual; não prometem os
mesmos resultados históricos. Tarifas e esforço de raciocínio estão nos arquivos de modelos.
Para investigar estabilidade, use repetições e casos novos; não repita até obter o resultado desejado.

## Conclusão

Os cálculos fecham, mas não demonstram que o mini seja intelectualmente superior ao normal. O resultado mistura cumprimento de contrato, disponibilidade da API e uma amostra pequena de casos sintéticos com uma repetição. Os riscos foram gerados pelos próprios modelos; portanto, a cobertura de códigos não usa uma lista de riscos esperados independente. Qualidade requer avaliação semântica e novas execuções repetidas, preservando as mesmas regras e reportando erros de infraestrutura separadamente.
