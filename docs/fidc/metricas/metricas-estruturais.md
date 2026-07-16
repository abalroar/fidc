# Métricas estruturais e de liquidez

Toda métrica precisa de nome, fórmula, nível, data, unidade e fonte. O mesmo rótulo pode representar cálculos contratuais diferentes.

## Patrimônio líquido

`PL = ativos reconhecidos − passivos reconhecidos`

Unidade: moeda. Identifique se é PL da classe, valor atribuído a subclasse/série ou agregado analítico do fundo. Somar classes serve ao ranking de `cnpj_fundo`, mas não cria fungibilidade entre patrimônios segregados.

## Alocação em direitos creditórios

Convenção simples:

`alocação = direitos creditórios computáveis / PL da classe`

A regra regulatória do art. 44 usa critério e prazo próprios; uma meta contratual pode usar direitos elegíveis, valor presente ou excluir parcelas. Regra normativa, meta de aquisição e gatilho de evento são registros separados.

## Subordinação reportada

Proxy do painel:

`subordinação reportada = (PL mezanino + PL subordinado residual) / PL total reportado`

Unidade: %. Não é automaticamente o índice contratual do art. 2º, XV, que se refere à subclasse e ao PL da classe conforme o regulamento.

## Índice de cobertura

Forma ilustrativa:

`cobertura = ativos elegíveis ajustados / obrigações protegidas`

Numerador, haircuts, reservas, passivos, juros acumulados e threshold variam. Nunca compare “1,20x” de dois fundos sem reconciliar as fórmulas.

## Concentração

`concentração_i = exposição computável ao fator i / base contratual`

O fator pode ser devedor, grupo, cedente, originador, garantidor, setor ou prazo. A participação dominante da Tabela II é outra métrica:

`maior segmento / total reportado na Tabela II`

Ela não mede concentração individual.

## Reserva

`cobertura da reserva = saldo de ativos da reserva / necessidade-alvo`

Defina tipo de reserva, ativos admitidos, necessidade-alvo, data, saque e recomposição. Caixa total não é numerador válido sem vínculo contratual.

## Excesso de spread

Uma aproximação econômica por período:

`receita da carteira − perdas − despesas − custo das cotas protegidas − outros encargos`

Pode ser expresso em moeda ou taxa. Precisa refletir pré-pagamento, atraso, recuperação e calendário. “Taxa média da carteira menos benchmark” é proxy incompleto.

## Liquidez e descasamento

### Caixa disponível

`caixa disponível / saídas previstas na janela`

Defina janela, ativos líquidos e saídas. Reserva restrita pode não estar disponível.

### WAL

`WAL = Σ(principal esperado_t × tempo_t) / Σ principal esperado_t`

Unidade: dias, meses ou anos. Use fluxo esperado e declare premissas de atraso, pré-pagamento e recuperação.

### Gap de prazo

`WAL dos ativos − prazo médio ponderado das obrigações`

É indicador simplificado, não simulação de caixa. Gaps de taxa, índice e moeda devem ser medidos separadamente.

## Fluxos do Informe Mensal

Aquisições, alienações, liquidações, pré-pagamentos, amortizações e resgates devem ser tratados como fluxos da competência, não saldos. Compare com PL ou carteira média apenas com denominador temporal coerente.

## Guardrails contratuais

FPD, DCV, índice de refinanciamento, diluição, cobertura, concentração e alocação podem ter definições próprias. FPD é convenção operacional no Glossário, não cláusula atribuída ao corpus. Para cada métrica, capture:

1. numerador e denominador;
2. janela/coorte;
3. data de observação e frequência;
4. exclusões e cura;
5. threshold e consequência;
6. fonte e versão.

Um limite de um fundo é exemplo, não definição universal. Prática recorrente no corpus só é tratada como tal com evidência em pelo menos duas famílias econômicas independentes.

## O que o Informe Mensal captura

PL, composição, faixas, fluxos e cotas permitem várias métricas reportadas ou proxies. Índice contratual, ativos elegíveis ajustados, reservas, cash waterfall, WAL projetado e gatilhos exigem regulamento e base operacional.

Fontes: RCVM 175; padrão XML mensal; documentos primários do corpus; metodologia analítica da revisão. Verificação: **16/07/2026**.
