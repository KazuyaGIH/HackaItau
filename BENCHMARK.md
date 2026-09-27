# Como testar a hipótese de custo e qualidade

Para conferir os **valores apresentados na demo**, veja [a recontagem com fórmulas, registros e mapa do código](BENCHMARK_RECALCULO.md). Rode `make benchmark-audit` para conferir offline os 48 registros publicados.

O comparativo executa **squad e generalista com cada modelo configurado**. A hipótese é que a
especialização permita atingir uma qualidade exigida com menor custo. O resultado não é predeterminado:
o generalista barato também participa e pode vencer.

## Executar

Com as dependências instaladas e `LLM_API_KEY` configurada no `.env`:

```bash
make benchmark-plan                          # inspeciona; não chama a API
make benchmark                              # chama a API: 32 execuções nesta configuração
make benchmark ARGS="--cases soja-base,milho-coerente"  # piloto: 8 execuções
make benchmark ARGS="--repetitions 3"         # 96 execuções; mais consumo
```

São oito situações fictícias: soja, milho com fontes coerentes, cultura divergente, documento ausente,
mercado ausente, pedido acima do catálogo, alavancagem alta e documento com instrução maliciosa.
Os gabaritos e os critérios de avaliação ficam fora dos prompts. As variações são feitas em cópias
temporárias dos mocks; não modificam a demonstração nem os casos abertos no servidor.

O exemplo usa snapshots da mesma família para reduzir variação de versão:

| Papel no experimento | Modelo | Entrada USD/1M | Entrada em cache USD/1M | Saída USD/1M |
|---|---|---:|---:|---:|
| Barato | gpt-4.1-mini-2025-04-14 | 0,40 | 0,10 | 1,60 |
| Forte | gpt-4.1-2025-04-14 | 2,00 | 0,50 | 8,00 |

Preços padrão consultados em 27/09/2026: [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
e [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1). São referências de API, não uma
garantia de tarifa da sua conta ou de outro provedor compatível.

Para trocar modelos ou preços, copie `backend/app/evaluation/models.example.json` e use
`make benchmark ARGS="--models /caminho/modelos.json"`. O mesmo endpoint e credencial do `.env` atendem
aos dois modelos. Preços desconhecidos devem ser omitidos: o relatório deixa o custo indisponível.
Não atribua tarifa alta ao generalista usando o mesmo modelo da squad.

Para testar apenas o generalista com outro modelo, sem repetir as quatro configurações anteriores:

```bash
make benchmark ARGS="--models backend/app/evaluation/models.reasoning.json --architectures generalist --pause-seconds 10"
```

Esse arquivo configura `gpt-5.2-2025-12-11` com `reasoning_effort=medium` e timeout de 180 segundos.
Os preços de referência são USD 1,75/1M na entrada, 0,175/1M em cache e 14/1M na saída,
conforme a [documentação do GPT-5.2](https://developers.openai.com/api/docs/models/gpt-5.2), consultada em 27/09/2026.
Tokens de raciocínio já integram `completion_tokens` reportados pela API; não são somados novamente.
Com raciocínio ativo, o provider omite `temperature`, seguindo a compatibilidade da API.
O intervalo entre casos reduz pressão sobre o rate limit e fica fora da latência individual da análise.
Cada tentativa cria um relatório novo: não sobrescreve nem elimina os resultados dos modelos anteriores.
Um empate em oito verificações automáticas é um resultado exploratório, não equivalência de qualidade comprovada.

`models.reasoning-high.json` testa `gpt-5.4-2026-03-05` com raciocínio alto e timeout de 300 segundos.
Use o mesmo comando trocando apenas o arquivo de modelos. A tabela configurada é USD 2,50/1M na
entrada, 0,25/1M em cache e 15/1M na saída, conforme a
[documentação do GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4), consultada em 27/09/2026.
Esses preços valem para a faixa de contexto usada pela suíte (abaixo de 272 mil tokens de entrada).

## O que é comparado

- **Squad:** executa o orquestrador real da aplicação, com quatro especialistas, projeções de contexto,
  validações e eventual retrabalho.
- **Generalista:** um agente produz elegibilidade, risco, alternativas e autorrevisão em uma resposta.
  Recebe a união das fontes filtradas e os mesmos cálculos. Não recebe as respostas da squad.
  O prompt adapta as responsabilidades dos especialistas para seções de uma única análise.
- Ambos usam os mesmos schemas por seção, validadores, cálculo de baseline, catálogo, revisão
  determinística, consolidação, proteção de saída e decisão humana. O agente único também pode
  corrigir JSON, receber feedback de validação e refazer uma rodada após revisão.
- Antes de calcular, o generalista verifica por código se há dados obrigatórios para a análise;
  quando não há, coleta só o necessário para elegibilidade. A squad interrompe no mesmo gate.
- As demandas estruturadas são idênticas. A interpretação inicial do chat, uploads, ajustes humanos
  e qualidade de extração de PDF ficam **fora** deste experimento.

O generalista tem todas as evidências autorizadas em um contexto; a squad distribui essas evidências
por responsabilidade. Esse é o tratamento experimental, não a remoção artificial de ferramentas de
um dos lados. Este baseline é de análise em uma resposta com correções, não representa todas as
arquiteturas possíveis de agente único com planejamento e busca dinâmica.

## Resultados e auditoria

Cada execução cria `artifacts/evaluations/<data>/`. Os arquivos sobrevivem a reinícios e são ignorados
pelo Git. O painel **Desempenho dos agentes** lê o resumo mais recente, inclusive enquanto parcial,
por `GET /api/benchmarks/latest`; atualizar a página não inicia chamadas pagas.

Sem resultados locais, a API usa o [resumo publicado](backend/app/evaluation/published/README.md)
versionado no repositório. A tela identifica esse resultado como **Benchmark publicado**, com data.
Assim, outros clones preservam o comparativo já executado sem chamadas pagas. Novas execuções locais
válidas têm prioridade; os traces individuais continuam fora do Git.

| Arquivo | Conteúdo |
|---|---|
| `REPORT.md` | Tabela de consumo, restrições atendidas e avaliação |
| `summary.json` | Resumo usado pelo painel |
| `manifest.json` | Casos, modelos, tarifas, ordem aleatória reproduzível, limites e hash dos arquivos da aplicação |
| `runs.jsonl` | Uma linha por execução, incluindo falhas |
| `traces/<id>.json` | Prompts filtrados, respostas brutas antes das correções, consumo, eventos e relatório |
| `review_blind.json` | Conteúdo e evidências sem rótulo de arquitetura/modelo, para revisão |
| `reviews.template.json` | Formulário de notas a preencher |

Não envie os traces ao avaliador antes das notas: eles revelam o modelo. Referências a seções/agentes
nos textos podem dar pistas da arquitetura; a ocultação dos rótulos reduz viés, mas não garante cegamento perfeito.

O custo é calculado por chamada:

```text
((entrada - entrada_em_cache) × preço_entrada
 + entrada_em_cache × preço_cache
 + saída × preço_saída) / 1.000.000
```

Todas as chamadas entram, inclusive respostas inválidas e correções. Falta de `usage`, falha de
transporte ou preço incompleto deixa o custo total **indisponível**, não zero. Os tokens conhecidos
continuam visíveis. Retries HTTP estão desativados neste experimento para não esconder tentativas;
429/timeout ficam registrados como falhas operacionais, não evidência de incapacidade intelectual
do modelo. Cada execução tem limite de 16 chamadas por padrão (`--max-calls`).

A ordem de casos e configurações é sorteada com seed registrada. Cache pode variar com essa ordem;
o desconto só é aplicado aos tokens que o provedor declara em cache. Não é uma fatura, nem inclui
infraestrutura, ferramentas externas ou tempo humano. Evite comparar totais enquanto o relatório
estiver parcial, pois os grupos ainda podem ter recebido casos diferentes.

## Avaliar qualidade

As verificações automáticas medem restrições específicas: bloqueio esperado, premissa numérica,
limites de produtos, existência de referências e cobertura dos códigos de risco. Essas verificações
incluem trabalho do backend; **não são uma medida de acurácia factual do modelo**. Correções de
grounding, validação, proteção de saída e retrabalho são registradas separadamente.

Um avaliador de domínio deve ler `review_blind.json` e preencher uma cópia de
`reviews.template.json`, com nome e justificativa, nas quatro dimensões:

1. Fundamentação: fatos e afirmações sustentados pelas evidências.
2. Risco: identificação e explicação dos riscos materiais, divergências e incertezas.
3. Estrutura: alternativas viáveis e condicionadas aos riscos; em bloqueios, solicitação correta de dados.
4. Clareza: informação útil, neutra e sem decisão automática de crédito.

Escala: **0** ausente/incorreto; **1** falha material; **2** adequado; **3** completo.
Cada caso é aceito se atender às restrições automáticas, receber pelo menos 2 em cada dimensão
e não apresentar erro crítico. Falhas operacionais permanecem no denominador de entrega e devem
ser examinadas separadamente da qualidade das respostas produzidas.

```bash
backend/.venv/bin/python -m app.evaluation.runner \
  --score artifacts/evaluations/SEU_DIRETORIO \
  --reviews /caminho/reviews.preenchido.json
```

Esse comando recalcula o relatório sem chamar o LLM. Notas ausentes não viram acertos. O custo por
análise aceita é o gasto de **todo o grupo**, incluindo falhas, dividido pelos casos aceitos. Se ainda
faltam revisões, esse indicador fica indisponível. Os intervalos de Wilson no JSON são descritivos;
repetições dos mesmos casos não podem ser tratadas como casos independentes.

## O que permite defender a tese

A configuração barata da squad precisa atingir o nível de qualidade exigido com custo menor.
Também é necessário verificar se o generalista barato já atinge esse nível: comparar apenas squad
barata com generalista caro não demonstra que a arquitetura permitiu economizar.

Esta suíte pequena e conhecida é exploratória. Antes de afirmar superioridade ou equivalência,
reserve casos novos, defina a margem aceitável de qualidade antes de ver as respostas, repita o
experimento e revise com especialistas. Não ajuste gabaritos após observar qual arquitetura ganhou.
Uma execução concluída, uma barra menor ou preço por token menor, isoladamente, não provam a tese.

## Reavaliar uma correção de medição sem gastar com a API

O comando abaixo reproduz as respostas já gravadas, conferindo a igualdade dos prompts, modelos,
schemas e quantidade de chamadas. Se houver divergência, ele rejeita a reavaliação: é preciso rodar
um experimento novo. Custos e latências são os originais, não o tempo do replay local.

```bash
backend/.venv/bin/python -m app.evaluation.replay \
  artifacts/evaluations/DIRETORIO_ORIGINAL \
  artifacts/evaluations/DIRETORIO_OUTRO_MODELO
```

A revisão `current_leverage_synonyms_v2` corrige um falso positivo do validador: reconhecer
“alavancagem atual/líquida” como descrição da alavancagem existente, além de “dívida” ou “EBITDA”.
Mencionar só alavancagem pró-forma não satisfaz essa verificação. A correção vale para todas as
arquiteturas e modelos. Os traces originais permanecem intactos; os reavaliados guardam
`original_automatic`, os critérios atualizados e o caminho da origem. O manifest registra os hashes
originais e o código da reavaliação. A revisão qualitativa continua pendente.
