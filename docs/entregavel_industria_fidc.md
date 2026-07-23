# Entregável — Panorama executivo da Indústria de FIDCs (Excel + PPT)

Deck e planilha executivos sobre a **evolução da indústria de FIDCs**, com gráficos
**nativos do Office**, consolidação por conglomerado e **fonte declarada em cada gráfico**.

## Como gerar / atualizar

```bash
python scripts/build_industria_fidc_deck.py
# saídas:
#   outputs/Industria_FIDC_<competencia>.xlsx
#   outputs/Industria_FIDC_<competencia>.pptx
```

Lê as bases já materializadas do **Toma Conta FIDcs** em `data/industry_study/`
(`industry_fund_snapshot.csv.gz`, `industry_dimension_monthly.csv.gz`,
`cotistas_tipo_monthly.csv`), derivadas do **Informe Mensal FIDC + Cadastro da CVM**.
Competência de referência = último mês completo do snapshot.

## Conteúdo (15 slides / 14 abas)

1. Evolução do PL da indústria (base líquida, ex-FIC-FIDC)
2. Composição do PL por segmento (% ao longo do tempo)
3. **Definições ANBIMA das classes** (Fomento Mercantil, Financeiro, Agro/Ind/Comércio, Outros, Multicedente/Multissacado)
4. Ranking de Gestores — **consolidado por conglomerado**
5. **Evolução dos Gestores** (2022→2026): PL por período, Δ PL e Δ ranking
6. Ranking de Administradores — consolidado
7. **Evolução dos Administradores**
8. **PL por tipo de controle** (Independente / Ligada a banco / Independente Grande) — evolução
9. **De-para de conglomerados** (auditável)
10. Top 25 FIDCs por PL — com tipo de recebível, gestor consolidado, subordinação mínima, última leitura e cedente
11. Número de cotistas — fundos > R$ 200 mi
12. Nº de cotistas por segmento de investidor
13. **Emissões** — variação anual de PL (ex-FIC)
14. Fonte exata por gráfico

## Consolidação por conglomerado (de-para)

Config auditável: `config/conglomerados_fidc.json`; lógica: `services/conglomerados.py`.
**Chave = CNPJ (14 dígitos)** — evita falsos positivos por nome (ex.: *Itaúna Capital*
**não** entra no Itaú). Grupos consolidados:

- **Ligada a banco:** Itaú (Itaú Asset + Itaú Unibanco + Kinea + Intrag), BTG Pactual
  (Banco + Asset + Serviços Financeiros + Gestão/Consultoria + Alternativos), XP
  (CCTVM + Vista + Allocation + Serviços), Bradesco (Banco + BEM), Banco do Brasil
  (BB Gestão + Banco), Caixa, Santander (Banco + S3 CACEIS¹ + DTVM), Genial (Banco +
  Investimentos + Gestão), Daycoval (Banco + Asset), Plural, Safra, Banco Master, Inter.
- **Independente Grande:** Oliveira Trust (DTVM + Servicer), BRL Trust.
- **Independente:** QI Tech, Vórtx, REAG, CBSF, Finaxis, JIVE, e demais gestores.

Critério de controle segue o rodapé do deck Itaú BBA ("Ligada a banco: vinculado a
banco; Independente Grande: Oliveira Trust, BRL Trust, BR Trust; Independente: demais").
¹ S3 CACEIS é JV Santander/CACEIS, mapeada a Santander com ressalva.

## Emissões (metodologia)

- Métrica: **variação anual de PL (ex-FIC)** — como na aba Indústria do Toma Conta.
  **Não** é o campo "emissões encerradas" (status ANBIMA), considerado menos confiável.
- Anos completos (jan–dez); 2026 é parcial. Eixo em ano (não texto solto).
- Validação de magnitude: a ANBIMA reportou os FIDCs entre as categorias que mais
  cresceram em 2024, consistente com a variação de +R$ 241 bi apurada aqui.

## Fonte por gráfico (resumo)

| Gráfico | Fonte |
|---|---|
| Evolução PL, emissões | Toma Conta (dimensão mensal, ex-FIC) ← Informe Mensal FIDC/CVM. **Não usa o Power BI/dashboard ANBIMA** (dados presos no visual). |
| Composição por segmento | Toma Conta (dimensão segmento). Taxonomia interna alinhada às classes ANBIMA. |
| Definições de classe | ANBIMA — Deliberação nº 72. |
| Rankings e evoluções (gestor/admin) | Toma Conta (dimensões gestor/admin) consolidado por CNPJ. Gestor ← Cadastro CVM. |
| Tipo de controle | Idem + taxonomia de controle (rodapé Itaú BBA). |
| Top 25 detalhado | Snapshot por fundo + leituras regulatórias do Toma Conta (quando há regulamento parseado). |
| Cotistas / segmento de investidor | Informe Mensal FIDC/CVM (Tabela X). |

Ressalvas honestas: a **classe ANBIMA oficial exata** (Fomento Mercantil etc.) não é
extraível do dashboard (Power BI); usa-se a taxonomia de segmento do Toma Conta,
análoga. As **leituras de regulamento** (cedente/sacado/subordinação) são ricas para
fundos com regulamento parseado e esparsas para megafundos de banco/cativos.
