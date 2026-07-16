# Cloudwalk FIDCs - Run-off do PL atual

Data de geração: 2026-06-18
PL oficial reconciliado: R$ 18,15 bi
PL alocado no waterfall: R$ 18,15 bi

## Metodologia

1. Universo: carteira Cloudwalk cadastrada em `portfolios.json`.
2. PL atual: último Informe Mensal Estruturado disponível no cache CVM/Fundos.NET para cada CNPJ.
3. PL por classe/cota: classes do IME foram normalizadas para chaves comparáveis aos regulamentos, como `senior_1`, `senior_2` e mezaninos específicos.
4. Reconciliação: a soma bruta das classes foi escalada dentro de cada fundo para bater exatamente no PL total oficial do IME; o fator fica em `runoff_allocation_long.csv`.
5. Situação cadastral: cadastro aberto CVM `registro_fundo_classe.zip`.
6. Cronogramas: campo curado `Amortização principal` em `data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv`, com fonte documental por regulamento/ata/anexo.
7. Alocação: cada classe foi distribuída pelos anos conforme seu cronograma documental remanescente após a competência-base do IME.
8. Fallback: classes sem cronograma próprio parseável, principalmente subordinadas, foram alocadas pela curva documental remanescente do respectivo fundo; isso soma R$ 0,55 bi.
9. Buckets: 2026, 2027, 2028 e 2029+.

## Resumo por ano

| Ano | PL alocado | % total |
|---|---:|---:|
| 2026 | R$ 1,06 bi | 5.8% |
| 2027 | R$ 3,86 bi | 21.2% |
| 2028 | R$ 0,00 bi | 0.0% |
| 2029+ | R$ 13,24 bi | 72.9% |

## Limitações explícitas

- O gráfico não é uma projeção de rentabilidade ou recompra antecipada; é um run-off contratual de principal.
- Quando o regulamento lista datas sem percentuais, a curadoria usa distribuição linear entre as datas documentadas, com aviso no `schedule_audit.csv`.
- Quando o documento informa apenas intervalo de amortização, a curadoria usa parcelas mensais lineares no intervalo documentado.
- Subordinadas sem calendário fixo próprio não são tratadas como vencimento contratual independente; entram pelo fallback de curva do fundo e ficam marcadas em `method_note`.
- Kick Ass II aparece com PL atual zero e situação CVM cancelada; fica fora do run-off futuro.
- Fundos em liquidação podem ter última competência anterior a maio/2026 se o Fundos.NET não publicou IME posterior ou se a consulta pública falhou.

## Arquivos gerados

- `cloudwalk_pl_runoff_waterfall.png`
- `cloudwalk_pl_runoff_waterfall.svg`
- `cloudwalk_pl_runoff_waterfall.xlsx`
- `current_pl_snapshot.csv`
- `current_class_pl_snapshot.csv`
- `runoff_allocation_long.csv`
- `runoff_by_year_fund.csv`
- `documentary_schedule_long.csv`
- `schedule_audit.csv`

## Linhas documentais não usadas no cronograma

- Kick Ass I: Cotas subordinadas - Amortização não mapeada no campo de curadoria.
- Kick Ass II: 1ª série sênior - Série sem dívida futura ativa para o waterfall.
- Kick Ass II: Cotas subordinadas - Amortização não mapeada no campo de curadoria.
- Kick Ass II: 1ª série sênior - alteração - Volume ausente/zero.
- Kick Ass II: 1ª série sênior - rerratificação - Série sem dívida futura ativa para o waterfall.
- Akira II: 1ª série sênior - Série sem dívida futura ativa para o waterfall.
- Akira II: 1ª série sênior - rerratificação 2023 - Volume ausente/zero.
- Akira II: 1ª série sênior - rerratificação 2024 - Volume ausente/zero.
