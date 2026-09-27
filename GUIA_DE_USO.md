# Agent Squads — guia de funcionalidades e uso

O **Agent Squads** é uma aplicação demonstrativa para apoiar a análise inicial e a estruturação de crédito agro. O usuário descreve uma demanda em linguagem natural, acompanha o trabalho de quatro especialistas e recebe um relatório com riscos, cálculos, alternativas de operação e fontes consultáveis.

O projeto foi preparado para o Hackathon Itaú 2026. Clientes, documentos, produtos e políticas são fictícios. O resultado serve de apoio à avaliação humana: a aplicação não aprova crédito nem executa operações financeiras.

Este guia descreve o comportamento implementado no repositório, com foco em uso e demonstração.

## 1. Para que serve

O fluxo atende à preparação de uma análise por um analista de crédito ou gerente: reunir informações da operação, verificar pendências, avaliar a capacidade de pagamento e comparar possíveis estruturas antes de encaminhar o caso para uma próxima etapa.

| Necessidade do usuário | O que a aplicação entrega |
| --- | --- |
| Transformar um pedido em uma análise organizada | Identificação do cliente, valor, finalidade, cultura e safra; apresentação da sequência de especialistas. |
| Conferir se há informações suficientes | Verificação de elegibilidade e documentação, com solicitação de informações quando necessário. |
| Entender a capacidade de pagamento | Indicadores calculados por código e cenários de estresse. |
| Explorar formas de estruturar a operação | Duas ou três alternativas comparáveis, com prazo, amortização, garantias e condicionantes. |
| Questionar a qualidade da análise | Revisão de premissas, inconsistências, riscos ignorados e referências utilizadas. |
| Conferir de onde veio uma conclusão | Acesso às evidências citadas, aos cálculos e ao histórico de execução. |
| Pedir uma nova avaliação | Ajustes direcionados a um especialista, seguidos da atualização dos trabalhos dependentes e de nova revisão. |

A interface usa a identidade fictícia `analyst-001`. O fluxo atual é voltado a crédito agro, com um catálogo de produtos de custeio e um caso principal de soja.

## 2. Como rodar localmente

### Pré-requisitos

- Python 3.10 ou superior, com suporte a `venv` e `pip`.
- Node.js compatível com as dependências do frontend. O `package.json` declara `>=20.19`.
- npm, Make e Bash para os comandos abaixo.
- Chave e acesso a um modelo de um provedor compatível com a integração de Chat Completions e saída JSON usada pelo projeto.

Na raiz do repositório, execute:

```bash
make install
```

Esse comando instala as dependências do backend e do frontend e cria o `.env` a partir do `.env.example`, caso o arquivo ainda não exista.

Edite o `.env` e configure:

| Variável | Utilidade |
| --- | --- |
| `LLM_API_KEY` | Chave de acesso ao provedor. Necessária para executar os especialistas. |
| `LLM_BASE_URL` | Endereço da API compatível usada pelo provedor. |
| `LLM_MODEL` | Identificador de um modelo disponível na sua conta e compatível com a integração. |
| `LLM_TIMEOUT_SECONDS` | Tempo máximo de espera por uma chamada; o exemplo usa 60 segundos. |
| `LLM_MAX_RETRIES` | Limite de novas tentativas em erros transitórios do provedor; o exemplo usa 5. |
| `LLM_RETRY_BACKOFF_SECONDS` | Intervalo inicial das novas tentativas, aumentado progressivamente; o exemplo usa 2 segundos. |
| `DEMO_MODE` | Habilita opções de demonstração, incluindo o documento adversarial; mantenha `true` para o roteiro deste guia. |

O [arquivo de exemplo](.env.example) contém uma configuração de provedor e uma alternativa comentada. Ajuste o modelo ao que estiver disponível na sua conta. O modo de demonstração usa dados fictícios, mas a execução dos agentes faz chamadas reais ao provedor configurado.

Depois, execute:

```bash
make run
```

Abra **http://localhost:8000**. O comando gera o frontend e inicia o servidor que entrega a interface e a API.

Para desenvolver com recarregamento automático:

```bash
make dev
```

Nesse modo, a interface fica normalmente em **http://localhost:5173** e encaminha as chamadas da API ao backend na porta 8000. `Ctrl+C` encerra os dois processos.

Outros comandos úteis:

| Comando | Quando usar |
| --- | --- |
| `make run PORT=8001` | Executar a demonstração em outra porta. |
| `make dev PORT=8001` | Alterar a porta do backend no modo de desenvolvimento; o proxy acompanha a mudança. |
| `make build` | Gerar a versão compilada da interface. |
| `make test` | Rodar os testes e verificações de Python, além do build e lint do frontend. |

Sem chave, o backend pode iniciar e receber demandas, mas recusa a execução da squad com `llm_not_configured`. A interface exibe um aviso. Os testes automatizados usam respostas simuladas de modelo e não precisam de uma chave real.

## 3. Primeira análise, passo a passo

### Descreva a demanda

Clique em **Nova conversa** e informe cliente, valor, finalidade, cultura e safra. Exemplo alinhado aos dados fictícios atuais:

> O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2026/27.

Também é possível identificar o cliente como `CLIENTE-001`. Prefira o nome completo ou o identificador exato: a busca de clientes não funciona como uma pesquisa livre por nomes parciais.

**Observação sobre os atalhos:** as sugestões da tela inicial ainda usam `2025/26`, enquanto o perfil agro e o plano de plantio da base fictícia usam `2026/27`. Para uma apresentação consistente com a base, digite o exemplo acima.

### Confira o entendimento e inicie a squad

O Orquestrador apresenta a demanda interpretada e os especialistas selecionados. O caso fica vinculado ao cliente identificado. Clique em **Executar squad** para iniciar a análise.

Se o cliente não puder ser identificado, a aplicação pede o nome completo ou ID em um formulário. Outras pendências podem aparecer na etapa de elegibilidade. Preencha os campos solicitados e use a ação de execução apresentada após o envio.

Informações complementares não trocam o cliente de um caso já vinculado. Para analisar outro cliente, abra uma nova conversa.

### Acompanhe o trabalho

O bloco de atividade na conversa mostra o andamento de cada especialista, as consultas realizadas, ocorrências de segurança e eventuais reaberturas da análise.

| Especialista | Pergunta que ajuda a responder |
| --- | --- |
| **Elegibilidade** | Há informações, documentação e enquadramento suficientes para continuar? |
| **Risco de crédito agro** | Como a geração de caixa, o endividamento e os cenários de estresse afetam a operação? |
| **Estruturação** | Quais alternativas do catálogo podem atender à demanda e tratar os riscos identificados? |
| **Revisor** | As premissas e conclusões se sustentam? Há inconsistências ou riscos sem tratamento? |

Uma pendência bloqueante de elegibilidade interrompe o avanço para risco. Se o Revisor encontrar um problema com correção automática prevista, o fluxo pode refazer o trabalho do responsável e dos especialistas que dependem dele. Há uma rodada automática de retrabalho por execução inicial; questões remanescentes ficam expostas para avaliação humana.

A regra de produtividade é aplicada antes dos cálculos: quando a declaração supera o histórico e não há justificativa documental validada, o sistema usa o histórico já na primeira análise. Isso evita refazer Risco, Estruturação e Revisão apenas para corrigir uma premissa conhecida. A declaração original e a justificativa da escolha ficam disponíveis para conferência; a revisão independente continua obrigatória.

A cultura também é conferida antes do Risco: pedido, perfil agro, planos de plantio e referência de mercado precisam ser compatíveis. Um pedido de milho para um perfil de soja fica pendente, sem cálculos ou relatório. A tela explica a divergência. Se o pedido estava errado, responda, por exemplo, “a cultura correta é soja” e execute novamente. Se o pedido estava certo, as fontes precisam ser corrigidas na base autorizada; confirmar em texto não altera produtividade, custos ou cotação. Planos sem cultura identificada nos dados extraídos também ficam pendentes. Os cálculos atuais exigem cotação em BRL/saca e produtividade em sacas/ha.

### Leia o relatório e consulte as fontes

Ao final, a conversa apresenta o resultado. Use **Relatório**, no topo, para abrir a visão completa, e **Auditoria** para consultar a execução e a governança.

As referências junto às conclusões são clicáveis. Elas abrem as evidências disponíveis para aquele caso, já submetidas aos filtros de acesso.

### Solicite um ajuste ou registre a revisão

Enquanto o caso aguarda revisão humana, escreva um ajuste no campo de mensagem. Por exemplo:

> Explique melhor os impactos da queda de preço e produtividade sobre a cobertura da operação.

O campo sugere um especialista pelo assunto do texto. Confira a opção **Reabrir …** e altere o responsável se necessário. É possível selecionar Elegibilidade, Risco ou Estruturação; quem depende desse trabalho também executa novamente, e o Revisor confere o resultado.

O limite é de **três ajustes humanos com reexecução por caso**. O comentário orienta a revisão da análise; ele não edita a base fictícia nem altera permissões.

Quando terminar a avaliação, clique em **Aprovar para a próxima etapa** e depois em **Confirmar aprovação**. Um comentário de auditoria é opcional. Essa ação registra a revisão humana e encerra a etapa demonstrativa, sem aprovar ou liberar crédito.

## 4. O que observar no relatório

O relatório separa os elementos necessários para entender e conferir a análise:

- **Resumo:** cliente, valor solicitado, finalidade, elegibilidade, quantidade de alternativas e retrabalhos.
- **Capacidade de pagamento e estresse:** geração de caixa, cobertura e classificações por cenário.
- **Fórmulas e entradas:** parâmetros, resultados e referências das políticas usadas nos cálculos.
- **Riscos e fatores favoráveis:** interpretação qualitativa com evidências citadas.
- **Estruturas alternativas:** produtos comparados por valor, prazo, amortização, garantias, condicionantes, vantagens e riscos.
- **Pendências e incertezas:** o que ainda precisa ser esclarecido.
- **Fatos e premissas:** origem das informações e mudanças de premissas durante o retrabalho.
- **Revisão:** achados abertos e resolvidos, gravidade e responsável.
- **Contribuição da squad e fontes:** participação dos especialistas e referências consultáveis.

As alternativas aparecem lado a lado, sem uma opção preferida pelo sistema. O catálogo fictício contém **Custeio Agro Safra**, **CPR Financeira Soja** e **Custeio em Tranches com Gatilhos**. As propostas podem variar entre execuções, respeitando as validações implementadas.

O catálogo declara as culturas aceitas por produto: Custeio Agro Safra e Tranches atendem soja e milho; CPR Financeira Soja atende apenas soja. A seleção e a validação das alternativas usam essa informação, sem deduzir compatibilidade pelo nome do produto.

Os principais indicadores seguem as fórmulas simplificadas da demonstração:

| Indicador | Como é calculado no projeto |
| --- | --- |
| Receita esperada | Área plantada × produtividade × preço da commodity. |
| Custo da safra | Área plantada × custo por hectare. |
| Geração de caixa esperada | Receita esperada − custo da safra. |
| Cobertura | Geração de caixa esperada ÷ valor solicitado. |
| Dívida líquida / EBITDA | Dívida líquida ÷ EBITDA. |
| Alavancagem pró-forma | (Dívida líquida + valor solicitado) ÷ EBITDA. |

A política fictícia prevê estresse de **queda de 15% no preço**, **queda de 10% na produtividade** e **combinação dos dois choques**. Números e classificações são calculados por código; o modelo produz a interpretação textual. Essas regras pertencem à demonstração e não representam políticas reais do banco.

## 5. Roteiro de demonstração

### Cenário A — análise completa com revisão de premissa

1. Envie o pedido de R$ 50 milhões para custeio de soja da Fazenda Horizonte.
2. Confira o cliente identificado e clique em **Executar squad**.
3. Acompanhe Elegibilidade, Risco, Estruturação e Revisão.
4. Observe a escolha preventiva da produtividade: a base informa **61 sacas/ha esperadas**, contra **58 sacas/ha históricas**. Sem justificativa documental validada para superar o histórico, o sistema já calcula com **58** na primeira rodada e explica a escolha na premissa do relatório. Essa diferença, por si só, não deve provocar retrabalho.
5. Abra o relatório e confira premissas, cenários, alternativas e evidências.
6. Peça um ajuste e observe a nova execução dos especialistas envolvidos.
7. Registre a revisão humana pela ação de aprovação para a próxima etapa.

Esse cenário mostra como a aplicação organiza uma demanda, previne uma premissa otimista sem respaldo e mantém a revisão independente. Retrabalhos continuam possíveis se forem encontrados outros problemas.

### Cenário B — documento malicioso

1. Abra uma nova conversa.
2. Ative **Teste de segurança** antes de enviar a demanda, ou escolha a sugestão **O mesmo caso com um documento malicioso**.
3. Execute a squad e consulte os avisos e a auditoria.

O cenário inclui um anexo fictício que tenta instruir o sistema a consultar `CLIENTE-999` e aprovar crédito imediatamente. O conteúdo suspeito é sinalizado. Uma verificação de acesso ao cliente fora do escopo é registrada como negada, sem consultar seus dados.

A detecção do texto malicioso é heurística e sinaliza o documento; o bloqueio de acesso é responsabilidade das regras de autorização do backend. O caso continua sujeito à revisão humana.

### Cenário C — informação insuficiente

Escolha **Demanda sem cliente identificado** ou envie:

> Preciso de uma análise de R$ 20 milhões para custeio de milho safrinha.

A aplicação deve pedir a identificação do cliente. Esse atalho demonstra a coleta da informação ausente; não garante uma análise completa de milho, pois a base principal foi preparada para soja. Para demonstrar o fluxo completo, use o cenário A.

## 6. Conversas, versões e recuperação de falhas

É possível manter várias conversas na barra lateral e acompanhar casos em andamento. Editar a demanda original ou usar **Gerar de novo** cria uma nova versão vinculada a um novo caso. A interface permite alternar entre essas versões.

Isso difere de pedir um ajuste: o ajuste reabre especialistas no caso existente. Também difere de retomar uma falha: quando uma execução falha e há trabalho recuperável, a ação de nova tentativa retoma o processamento aproveitando as etapas já concluídas.

O histórico de conversas é guardado no navegador, mas os casos, evidências e eventos do servidor ficam **em memória**. Reiniciar o backend perde esses dados. Nessa situação, uma conversa antiga pode continuar na barra lateral, acompanhada do aviso de que o caso não existe mais; abra uma nova conversa.

## 7. Governança visível para o usuário

Cada caso tem um cliente definido, e cada especialista recebe apenas os recursos permitidos para seu papel. Por exemplo, Estruturação trabalha com o catálogo, o conhecimento disponível e resumos das análises anteriores, sem acesso direto aos dados financeiros brutos.

A aplicação registra consultas, recusas de acesso, campos ocultados, chamadas ao modelo e eventos de segurança. Documentos e respostas de ferramentas são tratados como dados a analisar, sem autoridade para mudar permissões. Referências produzidas pelos agentes também passam por validação, e o relatório recebe verificações antes de ser apresentado.

Esses mecanismos permitem demonstrar controle e rastreabilidade. O repositório ainda usa identidades fictícias e não implementa autenticação corporativa real.

## 8. Problemas comuns

| Situação | O que fazer |
| --- | --- |
| Aviso de modelo não configurado ou erro `llm_not_configured` | Preencha `LLM_API_KEY`, confira provedor e modelo e reinicie o backend. |
| A aplicação informa `llm_mode=real`, mas as chamadas falham | Esse estado indica que há uma chave configurada, sem validar sua autenticidade ou o acesso ao modelo. Confira as configurações do provedor. |
| Cliente não identificado | Use `CLIENTE-001` ou o nome completo `Fazenda Horizonte S.A.`. |
| Campo de mensagem desabilitado durante uma pendência | Responda no formulário de informações solicitado na conversa. |
| Squad falhou durante o processamento | Confira a mensagem de erro e use a ação de nova tentativa quando disponível. Erros transitórios do provedor também recebem tentativas automáticas. |
| Caso antigo desapareceu do servidor | Abra uma nova conversa; o backend perdeu o estado ao reiniciar. |
| Interface não aparece na porta 8000 | Inicie com `make run`, que gera o frontend antes de subir o servidor. |
| Limite de ajustes atingido | Crie uma nova versão da demanda ou uma nova conversa para continuar a exploração. |

Para verificar se o backend responde:

```bash
curl http://localhost:8000/api/health
```

## 9. Limites atuais e organização do projeto

O MVP não oferece conexão com sistemas bancários, upload de documentos pela interface, cotação de mercado em tempo real, exportação dedicada para PDF ou persistência dos casos em banco de dados. Os documentos já vêm cadastrados na base local, e o chat conduz um fluxo específico de análise e ajustes, sem funcionar como um assistente geral.

A qualidade dos textos e o tempo de execução dependem do provedor configurado. Ter um relatório pronto significa que ele está disponível para revisão humana; não significa que todas as pendências foram resolvidas.

A organização técnica pode ser resumida em três partes: uma interface React para interação e consulta, um backend FastAPI que coordena os especialistas e aplica regras, e arquivos locais com dados e conhecimento fictícios.

| Onde consultar | Conteúdo |
| --- | --- |
| [README.md](README.md) | Objetivos, regras funcionais e escopo proposto para o MVP. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Descrição técnica detalhada. |
| [TASKS.md](TASKS.md) | Decomposição de trabalho; as marcações não substituem a conferência do código implementado. |
| [Makefile](Makefile) | Comandos de instalação, execução e verificação. |
| [BENCHMARK.md](BENCHMARK.md) | Comparação real de squad e generalista, modelos, custos e avaliação de qualidade. |
| [Dados fictícios](backend/app/data/mock/) | Clientes, informações financeiras e agro, documentos, mercado, produtos e políticas. |
| [Base de conhecimento](backend/app/knowledge/corpus/) | Políticas, catálogo, roteiro de risco e glossário usados pela análise. |
| [Testes do backend](backend/tests/) | Cenários de cálculo, permissões, revisão, retrabalho, ajustes e recuperação de falhas. |

Para integrações locais, a API também permite criar casos, enviar informações, iniciar ou retomar análises, consultar eventos, relatório e evidências e registrar a revisão humana. A documentação interativa fica em **http://localhost:8000/docs** com o servidor em execução.
