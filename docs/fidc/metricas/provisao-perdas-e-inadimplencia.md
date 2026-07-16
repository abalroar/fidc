# Atraso, provisão, perda, recuperação e write-off

Essas medidas descrevem etapas diferentes. “Provisão/perda esperada” não é um único conceito.

## Atraso e inadimplência

Atraso é diferença entre vencimento e pagamento. Inadimplência é classificação de não pagamento segundo regra definida. A métrica precisa indicar se usa valor nominal, contábil, presente ou saldo devedor e se considera parcelas ou contratos.

`inadimplência da faixa = saldo vencido na faixa / base definida`

O denominador pode ser carteira total, carteira vencida, carteira elegível ou saldo da safra. A comparação só é válida com a mesma base.

## Aging completo do Informe Mensal

As faixas canônicas usadas pelo monitoramento são:

1. até 30 dias;
2. 31–60;
3. 61–90;
4. 91–120;
5. 121–150;
6. 151–180;
7. 181–360;
8. 361–720;
9. 721–1.080;
10. acima de 1.080 dias.

Não fundir 121–150 e 151–180 nem truncar acima de 360 quando a fonte oferece granularidade maior. Uma faixa ausente não deve ser preenchida como zero sem regra explícita.

## Inadimplência Over

`Over N = saldo com atraso superior a N dias / base definida`

É cumulativa, ao contrário do bucket de aging. Declare se “superior” inclui o dia N, quais saldos entram e qual denominador é usado.

## FPD, roll rate e cura

- **FPD:** convenção operacional para default na primeira obrigação segundo janela definida; requer coorte de originação e critério de default. Nenhuma definição contratual literal de FPD foi localizada nos regulamentos e relatórios de rating varridos, portanto o Glossário não atribui essa fórmula a um fundo nem a apresenta como padrão normativo.
- **Roll rate:** parcela que migra de uma faixa para outra entre datas.
- **Cura:** retorno de atraso para status adimplente segundo regra.

Renegociação pode produzir cura aparente; deve ser identificada separadamente quando possível.

## Provisão ou redução ao valor recuperável

É ajuste contábil reconhecido para refletir perda estimada/impairment conforme política e norma aplicável. O saldo é uma estimativa contábil; não é caixa reservado nem perda necessariamente realizada.

`índice de provisão = provisão ou redução acumulada / exposição bruta definida`

Registre sinal, conta contábil, tratamento de juros, garantias e recuperações.

## Perda esperada

É estimativa prospectiva. Em modelos de crédito, uma forma conceitual é:

`PE = PD × LGD × EAD`

mas o método efetivo pode ser por matriz de migração, fluxo descontado, modelo estatístico ou política contábil. Não inferir PD, LGD ou horizonte do saldo de provisão sem documentação.

## Perda realizada e write-off

Perda realizada é impacto econômico reconhecido conforme critério definido. **Write-off/baixa** retira ou reduz o ativo contabilmente quando atendidos os critérios; não significa necessariamente fim da cobrança. A queda do PL subordinado, isoladamente, não comprova write-off nem quantifica perda de crédito: despesas, amortizações e marcação também alteram o PL.

## Recuperação

`taxa de recuperação = caixa recuperado líquido / base de créditos em recuperação`

Defina coorte, custos, horizonte e desconto temporal. Recuperação bruta de carteiras NPL não é comparável à recuperação líquida de atraso recente.

## Cobertura de provisão

`cobertura = provisão acumulada / saldo vencido na base definida`

É proxy. Acima de 100% não prova conservadorismo; abaixo de 100% não prova insuficiência. Faixa de atraso, garantia, cura, recuperação e política contábil mudam a interpretação.

## Safras e denominadores

Análise de safra agrupa créditos por período de originação. Evita misturar carteira jovem com madura. Sempre mostre vintage, idade, exposição inicial, saldo atual, pré-pagamento, renegociação e recuperação.

## O que o Informe Mensal captura

O reporte oferece faixas de atraso e valores contábeis agregados úteis para séries históricas. Não entrega sozinho política contábil completa, PD/LGD/EAD, critério de baixa, coorte de FPD, roll rate, cura ou recuperação líquida.

## O que exige documento primário

Demonstrações financeiras e notas explicativas sustentam política e contas; regulamento e relatórios operacionais definem eventos e métricas; relatórios de cobrança e rating ajudam a entender safra, recuperação e pressupostos.

Fontes: ICVM 489 e orientações oficiais SIN/SNC; padrão XML mensal FIDC; demonstrações e documentos primários; metodologia analítica desta revisão para FPD, roll rate e cura. Verificação: **16/07/2026**.
