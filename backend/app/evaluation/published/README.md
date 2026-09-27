# Resultado publicado da demonstração

`summary.json` é uma cópia integral do resumo de execuções reais consolidado em
`artifacts/evaluations/20260927T041859-743583Z-replay/summary.json`.
SHA-256: `535441c6f8e44605eccddbd410f8b80f3406b3b28f1b777e3a24c9f10e016e6b`.

Inclui todas as seis configurações avaliadas (48 execuções), inclusive falhas.
O painel destaca squad GPT-4.1 mini, generalista GPT-5.4 alto e generalista GPT-5.2 médio.
O replay reaplicou as verificações aos mesmos prompts e respostas gravados, sem novas
chamadas à API, após corrigir o reconhecimento de menções à alavancagem atual/líquida.
Os custos e tempos das execuções originais foram preservados.

Fontes locais do consolidado:
- `20260927T034541-521230Z`: GPT-4.1 mini e GPT-4.1, nas duas arquiteturas.
- `20260927T040126-518976Z`: generalista GPT-5.2 médio.
- `20260927T040523-624712Z`: generalista GPT-5.4 alto.

Sem resultados locais, a API usa esta cópia e a interface mostra “Benchmark publicado”
com a data. Havendo resultados locais válidos, o mais recente tem prioridade, inclusive
se parcial. Isso permite que outro clone mostre o resultado já medido sem refazer chamadas
pagas. O resumo não inclui prompts, respostas individuais nem credenciais.

São oito casos sintéticos por configuração, uma repetição por caso. O empate é nas
verificações automáticas; a avaliação humana de qualidade permanece pendente.
Metodologia e instruções de reprodução: [BENCHMARK.md](../../../../BENCHMARK.md).
