# Cloudwalk - estimativas de custo financeiro

Período: 2025-01-01 a 2025-12-31. Snapshot: 2025-12-31.
CDI/DI proxy anual: 13.9936%. Fonte: manual --cdi-aa.

## Estimativas

1. `snapshot_pl_sem_amortizacao`: saldo remunerado na data snapshot vezes CDI+spread por todo o período.
2. `programado_bruto_com_amortizacao`: saldo por linha ajustado por captações e amortizações documentadas; a despesa bruta é a referência para gross-up da receita de antecipação.
3. `programado_liquido_caixa_lft`: mesma despesa bruta, menos rendimento CDI estimado sobre caixa/LFT. A base usa o maior valor entre caixa+títulos públicos reportados e a proxy `PL - recebíveis`, quando há recebíveis positivos.

## Leitura contábil/gerencial

A coluna `receita_antecipacao_gross_up_sugerida` repõe, em receita bruta gerencial, a mesma despesa financeira bruta explicitada. O rendimento de caixa/LFT fica separado para não misturar custo de funding com carry de liquidez.

## Lacunas

Linhas ativas sem spread CDI+ parseável: 0. Saldo snapshot afetado: R$ 0.0 mm.
Caixa/LFT usado na estimativa líquida: R$ 1,589.7 mm.

Quando você passar os spreads pendentes, preencha `config/cloudwalk_financial_cost_inputs.json` em `spreads_cdi_plus_aa` usando a chave `CNPJ|classe` listada em `cloudwalk_financial_cost_missing_inputs.csv`.

## Totais

| estimativa | descricao | despesa_financeira_bruta | receita_antecipacao_gross_up_sugerida | rendimento_caixa_lft | despesa_financeira_liquida | saldo_base | linhas_incluidas | linhas_sem_spread | saldo_snapshot_sem_spread | periodo_inicio | periodo_fim | snapshot_date | cdi_aa | cdi_source | cash_yield_cdi_factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1_snapshot_pl_sem_amortizacao | Saldo remunerado na data snapshot vezes CDI+spread por todo o ano; não reflete amortizações/captações intraperíodo. | 1745915589.35 | 1745915589.35 | 0.0 | 1745915589.35 | 11586594560.49 | 16 | 0 | 0 | 2025-01-01 | 2025-12-31 | 2025-12-31 | 0.1399364 | manual --cdi-aa | 1.0 |
| 2_programado_bruto_com_amortizacao | Custo bruto por linha com saldo diário aproximado, cronogramas de amortização e captações dentro do período. | 1221246229.51 | 1221246229.51 | 0.0 | 1221246229.51 | 8624140392.94 | 16 | 0 | 0 | 2025-01-01 | 2025-12-31 | 2025-12-31 | 0.1399364 | manual --cdi-aa | 1.0 |
| 3_programado_liquido_caixa_lft | Custo bruto programado menos rendimento CDI estimado sobre caixa/LFT: maior entre caixa+títulos reportados e proxy PL-recebíveis. | 1221246229.51 | 1221246229.51 | 220576990.07 | 1000669239.44 | 8624140392.94 | 16 | 0 | 0 | 2025-01-01 | 2025-12-31 | 2025-12-31 | 0.1399364 | manual --cdi-aa | 1.0 |
