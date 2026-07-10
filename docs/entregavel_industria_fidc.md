# Entregável — Panorama executivo da Indústria de FIDCs (Excel + PPT)

Reconstrução independente dos gráficos de mercado de FIDCs (estilo deck Itaú BBA),
**sem Power BI e sem dado proprietário**, com gráficos **nativos do Office** (editáveis).

## Como gerar / atualizar

```bash
python scripts/build_industria_fidc_deck.py
# saídas:
#   outputs/Industria_FIDC_<competencia>.xlsx
#   outputs/Industria_FIDC_<competencia>.pptx
```

O builder lê as bases já materializadas em `data/industry_study/`
(`industry_fund_snapshot.csv.gz`, `admin_monthly.csv`, `cotistas_tipo_monthly.csv`),
que são derivadas do **CVM Dados Abertos — Informe Mensal FIDC + Cadastro de fundos**.
A competência de referência é o último mês completo disponível no snapshot.

Para trazer um mês mais novo, primeiro rode o pipeline de indústria do projeto
(que atualiza o snapshot a partir da CVM) e depois este builder.

## O que sai

**PowerPoint executivo** (`.pptx`, 9 slides, gráficos nativos com workbook Excel
embutido — dá "Editar Dados" no PowerPoint):
1. Capa
2. Evolução do PL da indústria (série anual, R$ bi)
3. Composição do PL por segmento de atuação
4. Ranking de Administradores por PL (Top 10)
5. Ranking de Gestores por PL (Top 10)
6. Top 25 FIDCs por PL (tabela)
7. Número de cotistas — fundos > R$ 200 mi (distribuição)
8. Nº de cotistas por segmento de investidor
9. PL por tipo de gestor (Independente vs Ligada a banco — heurístico)

**Excel** (`.xlsx`, 9 abas, gráficos nativos do Office): uma aba por tema (com o
gráfico + a tabela-fonte) e uma aba "Fonte e Metodologia".

## Fidelidade aos slides de referência

| Slide de referência | Cobertura neste entregável |
|---|---|
| Evolução do PL (R$ bi, anual) | ✅ direto |
| Nº de cotistas por faixa (>R$200mm) | ✅ direto |
| Ranking de Administradores | ✅ direto |
| Ranking de Gestores / Top FIDCs | ✅ direto (gestor via cadastro CVM) |
| Composição por classe ANBIMA | 🟡 usa `segmento_principal` (taxonomia interna, análoga — **não** as classes oficiais ANBIMA) |
| Independente vs Ligada a banco | 🟡 heurística por palavra-chave no nome do gestor |
| PL por segmento de investidor | ✅ nº de cotistas por segmento (PL por segmento exige rateio) |

## Metodologia e ressalvas (resumo)

- **Fonte:** CVM Dados Abertos (Informe Mensal FIDC + Cadastro). Sem Power BI, sem API paga.
- **PL:** soma de `TAB_IV_A_VL_PL` por fundo/classe. A série de indústria descarta o
  último mês se estiver incompleto (defasagem de entrega).
- **Dupla contagem:** a soma bruta contém master-feeder / FIC-FIDC / classes
  sênior-subordinada; por isso o total bruto (~R$ 950 bi em 2026-05) fica acima do
  "PL líquido de indústria" que casas divulgam. Netar essas camadas é trabalho de
  metodologia (a base traz o flag `is_fic_fidc` para começar).
- **Classe ANBIMA oficial** e **corte independente/banco** são as duas camadas que
  exigiriam, para fidelidade total, a ANBIMA Feed API (paga) ou uma tabela editorial
  mantida à mão. Ver `docs/viabilidade_reconstrucao_slides_fidc.md`.
