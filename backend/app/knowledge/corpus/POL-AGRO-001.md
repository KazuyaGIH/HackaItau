# POL-AGRO-001 — Elegibilidade para crédito rural de custeio (mock)

Documento fictício para demonstração. Não representa política real.

## Critérios de elegibilidade
- Produtor rural ativo, pessoa jurídica ou física, com atividade agrícola comprovada.
- Área plantada comprovada por matrícula ou contrato de arrendamento vigente até o fim do ciclo.
- Ausência de restritivos relevantes no cadastro.
- Valor solicitado igual ou superior a R$ 1.000.000,00 (ticket mínimo das linhas de custeio do catálogo).

## Documentos obrigatórios para custeio
- Matrícula do imóvel ou contrato de arrendamento.
- Plano de plantio do ciclo com cultura, área e produtividade estimada.
- Demonstrações financeiras do último exercício.

## Divergências
Diferença entre área declarada no plano de plantio e área do perfil agro superior a 5% deve ser registrada como alerta (`DOC_AREA_MISMATCH`) e esclarecida antes da formalização.

## Consistência de cultura no custeio
- A cultura da demanda deve coincidir com o perfil agro e com a cultura identificada nos planos de plantio disponíveis.
- Um plano sem cultura identificada nos dados extraídos exige esclarecimento na base documental; texto livre não substitui essa identificação.
- É obrigatória uma referência de mercado para a mesma cultura. Na demonstração, a unidade da cotação é BRL/saca e a produtividade é medida em sacas/ha; outras unidades exigem adequação antes do cálculo.
- Divergência ou ausência dessas informações bloqueia a análise antes dos cálculos. Não combinar produtividade e custos de uma cultura com preço de outra.
- As culturas atendidas por cada produto são declaradas no catálogo (`supported_crops`); uma confirmação do usuário não altera essa restrição.
