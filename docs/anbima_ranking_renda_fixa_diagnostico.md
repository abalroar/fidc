# Ranking ANBIMA de Renda Fixa — de onde vem, como é apurado e qual é o share do Itaú BBA

Data-corte: **30/jun/2026**. Referência da publicação: **Junho/2026** (divulgada em 27/07/2026).
Todos os números deste documento são reproduzidos a partir das fontes oficiais pelo pipeline
`scripts/build_anbima_fixed_income_ranking.py`.

---

## 1. Resposta curta às três perguntas

| Pergunta | Resposta |
| --- | --- |
| Temos Coordenador Líder nas bases de emissões? | **Sim.** `services/industry_public_offers.py` já expõe `leader_name`, vindo de `Nome_Lider` (RCVM 160 automática) e de `Nome_Lider` do arquivo legado. Validado. |
| Dá para saber **todos** os coordenadores de cada oferta? | **Sim, mas não pela CVM.** O arquivo `oferta_distribuicao.zip` só publica o líder. Quem publica o sindicato completo é a própria ANBIMA, no **Anexo ao Ranking — Tabela de Encerramento**, com uma linha por (operação × coordenador) e o **percentual coordenado** de cada um. É público e gratuito. |
| O ranking só contabiliza o líder? | **Não.** Ele credita **todos os coordenadores e coordenadores contratados**, na proporção contratual (garantia firme) ou na proporção do fee (melhores esforços). O líder só tem o papel de **reportar** a operação à ANBIMA. |

---

## 2. De onde saiu o número do Valor

A matéria usa o **Ranking ANBIMA de Renda Fixa e Híbridos — Originação (Valor), Tipo 1: Renda
Fixa Consolidado, acumulado 2026**. Os valores batem ao centavo:

| # | Instituição | Valor 1S26 | Part. |
| --- | --- | ---: | ---: |
| 1 | BRADESCO BBI | R$ 62,033 bi | 27,79% |
| 2 | **ITAÚ BBA** | **R$ 51,047 bi** | **22,87%** |
| 3 | BTG PACTUAL | R$ 22,216 bi | 9,95% |

Universo do ranking no 1S26: **R$ 223,224 bi**.

**Fontes** (todas públicas, sem login):

- Página: <https://data.anbima.com.br/publicacoes/ranking-de-renda-fixa-e-hibridos>
- Ranking: `Ranking de Renda Fixa e Híbridos - Junho 2026.xlsx`
- Anexo deal-a-deal: `Anexo ao Ranking - Encerramento de Renda Fixa e Híbridos - Junho 2026.xlsx`
- Metodologia: `Metodologia_RF_Hib-2026-2.pdf`

Os arquivos são resolvidos programaticamente pela API da publicação
(`PUBLICATION_API` em `services/anbima_fixed_income_ranking.py`), então o pipeline acompanha
a competência corrente sem URL chumbada.

### Nuance de leitura: a liderança depende da janela

A manchete usa o acumulado do ano. Nas outras duas janelas publicadas na mesma planilha o
quadro muda — vale ter isso à mão antes de levar o tema para o presidente:

| Janela | 1º | 2º | Itaú BBA |
| --- | --- | --- | --- |
| Acumulado 2026 (jan–jun) | Bradesco BBI 27,79% | **Itaú BBA 22,87%** | 2º |
| Últimos 3 meses (abr–jun) | Bradesco BBI 36,63% | **Itaú BBA 20,31%** | 2º |
| Últimos 12 meses (jul/25–jun/26) | **Itaú BBA 25,02%** | Bradesco BBI 20,55% | **1º** |

Ou seja: o Itaú BBA **segue líder na janela de 12 meses** (R$ 140,863 bi, 25,02%). A perda de
liderança é um fenômeno do semestre, não do ciclo.

---

## 3. Como o ranking é feito (metodologia, cap. IV a VII)

1. **Quem pode entrar** (item 15): apenas instituições que atuaram como **Coordenador** em
   ofertas públicas registradas na CVM (ou dispensadas). Quem participou só do esforço de
   colocação sob outra denominação entra apenas no **Ranking de Distribuição**.
2. **Como o volume é rateado** — este é o ponto central:
   - **Garantia firme** (item 19): crédito conforme **a proporção da garantia definida em contrato**.
   - **Melhores esforços** (item 20): crédito conforme **a proporção do fee de coordenação/estruturação**.
   - Não é crédito integral para o líder, nem divisão igualitária. É contratual.
3. **Número de operações** (item 21): cada coordenador recebe **1 unidade** se teve qualquer
   crédito alocado no formulário-padrão — independentemente do tamanho da fatia.
4. **Mês de referência** (item 32): o mês em que se publica o **anúncio de encerramento** da
   distribuição (não a data de registro, nem a de emissão).
5. **Quem reporta** (itens 26–28): o **Coordenador Líder** envia o formulário-padrão e os
   contratos à ANBIMA, e deve identificar **todos** os coordenadores, mesmo os com crédito zero.
   Os demais coordenadores podem contestar (itens 34–35).
6. **Prazos** (itens 30–31): até o 7º dia corrido após o anúncio de encerramento. Fora do prazo,
   a operação escorrega para o ranking do trimestre seguinte. **O ranking é declaratório**: uma
   operação sem formulário enviado simplesmente não existe no ranking.
7. **Empresas ligadas** (itens 8, 10, 14): operações originadas por coordenador com ≥10% do
   capital da emissora/cedente/originadora vão para o **Tipo 3**, e **saem do Tipo 1**. Em
   securitização, se a operação não for simultânea (o cedente mantém os ativos na carteira),
   também é tratada como ligada.

### Perímetro do "Tipo 1 — Renda Fixa Consolidado"

| Sub-tipo | Instrumentos |
| --- | --- |
| 1.1 Curto prazo (≤366d) | Debêntures simples, notas promissórias, VM de agência multilateral, notas comerciais, **CPR-F** (novo em 2026) |
| 1.2 Longo prazo (>366d) | mesmos instrumentos |
| 1.3 Securitização | **1.3.1 FIDC** (cotas seniores e subordinadas, condomínio fechado), 1.3.2 CRI, 1.3.3 CRA, 1.3.4 CR |

FII, FIAGRO, FIP-IE, CEPAC e conversíveis ficam no **Tipo 2 (Híbridas)** e **não** entram no
número de renda fixa. Letras financeiras e CDCA ficam de fora de tudo.

---

## 4. Share do Itaú BBA — números para o presidente

Recorte **Originação — Valor, acumulado 2026 (jan–jun/26)**:

| Escopo | Volume Itaú BBA | Share | Posição | Universo | Nº ops Itaú |
| --- | ---: | ---: | :---: | ---: | ---: |
| **Renda fixa consolidado (Tipo 1)** | R$ 51,047 bi | **22,87%** | 2º | R$ 223,22 bi | 151 |
| Securitização (Tipo 1.3) | R$ 13,714 bi | **37,61%** | **1º** | R$ 36,47 bi | 33 |
| **FIDC (Tipo 1.3.1)** | **R$ 11,443 bi** | **45,66%** | **1º** | R$ 25,06 bi | **19** |
| CRI (Tipo 1.3.2) | R$ 1,647 bi | 26,66% | 1º | R$ 6,18 bi | 7 |
| CRA (Tipo 1.3.3) | R$ 0,625 bi | 12,38% | 3º | R$ 5,04 bi | 7 |

No **Ranking de Distribuição** (esforço efetivo de colocação), o Itaú BBA é **1º em renda fixa
consolidado (26,60%)** e **1º em FIDC (42,47%)**.

**A mensagem central para o presidente**: a perda de liderança do semestre foi em renda fixa
corporativa (debêntures/notas). **Em FIDC o Itaú BBA não só lidera como tem quase metade do
mercado apurado — 45,66%, mais que o dobro do 2º colocado (Bradesco BBI, 20,65%).** E na janela
de 12 meses o share em FIDC é 36,89%, também 1º lugar.

### Ressalva de entidade jurídica

O ranking ANBIMA consolida o conglomerado sob o rótulo único **"ITAU BBA"**. Ele **não** separa
`Itaú BBA Assessoria Financeira S.A.` de `Banco Itaú BBA S.A.`. Na base CVM do 1S26, todas as
ofertas primárias encerradas lideradas pelo grupo aparecem sob **`ITAU BBA ASSESSORIA
FINANCEIRA S.A`** (169 ofertas e R$ 88,9 bi de valor registrado considerando todos os
instrumentos; R$ 64,4 bi restringindo ao perímetro de renda fixa) — o Banco Itaú BBA S.A. não
figura como líder em nenhuma oferta encerrada no período. Então, para a pergunta como foi feita
("share do Itaú BBA Assessoria Financeira"), o número do ranking é atribuível a essa entidade,
mas a **atribuição é nossa, não da ANBIMA** — a planilha oficial não permite essa segregação.

---

## 5. Por que a nossa base CVM dá um número diferente (e qual usar)

Existem **três universos distintos**, e confundi-los é o erro clássico:

| Universo | Renda fixa 1S26 | FIDC 1S26 | Métrica |
| --- | ---: | ---: | --- |
| **CVM** — ofertas primárias encerradas | R$ 312,44 bi (1.510 ofertas) | R$ 65,49 bi (771 ofertas) | Valor **registrado** |
| **ANBIMA Boletim** — mercado | R$ 288,8 bi | R$ 53,1 bi (559 operações) | Valor **encerrado** |
| **ANBIMA Ranking** — Tipo 1 | R$ 223,22 bi (418 ops) | R$ 25,06 bi (43 ops) | Valor **originado creditado** |

O ranking cobre **71,4% do universo CVM em renda fixa** e apenas **38,3% em FIDC**. As causas,
em ordem de materialidade:

1. **Operações de empresas ligadas saem do Tipo 1.** O Tipo 3 soma R$ 23,53 bi, dos quais
   R$ 3,30 bi são FIDC. Em FIDC isso pesa muito: é comum o coordenador ser ligado ao
   cedente/originador.
2. **Ofertas sem formulário enviado não entram.** Boa parte do mercado de FIDC é liderada por
   administradores/DTVMs que não disputam ranking. Na base CVM do 1S26, os líderes de FIDC
   incluem Singulare (R$ 6,99 bi), Vórtx (R$ 2,95 bi), Hemera (R$ 2,75 bi), Oliveira Trust
   (R$ 2,56 bi), BRL Trust (R$ 1,75 bi) — volume que praticamente não aparece no ranking.
3. **Métrica diferente**: a CVM mede valor registrado; a ANBIMA mede valor efetivamente
   encerrado/colocado.
4. **Data de referência diferente**: CVM usa data de encerramento da oferta; ANBIMA usa o mês do
   anúncio de encerramento.

**Consequência prática — o share muda de patamar conforme a base:**

| Recorte | Share Itaú BBA pela **CVM (só líder)** | Share pelo **ranking ANBIMA** |
| --- | ---: | ---: |
| Renda fixa | 20,60% | **22,87%** |
| **FIDC** | **15,38%** | **45,66%** |

A diferença de 30 p.p. em FIDC **não é erro de cálculo** — são perguntas diferentes. A leitura
CVM responde "que fatia de tudo que se registrou o Itaú liderou". O ranking responde "que fatia
do mercado endereçável e disputado o Itaú originou". **Para falar com o presidente e para
qualquer comparação com concorrente ou com a imprensa, use o ranking ANBIMA** — é o número
oficial e o que sai no Valor. A leitura CVM serve como visão de mercado total e para
granularidade que a ANBIMA não dá (cedente, sacado, taxonomia).

---

## 6. O que o anexo destrava que a CVM não dá

O anexo é o único lugar público com o **sindicato completo**. No 1S26, em FIDC:

- 38 das 43 operações (88%) tiveram **coordenador único**;
- 5 operações foram sindicalizadas, sendo a maior o **CloudWalk Bela FIDC** (R$ 5,50 bi,
  **6 coordenadores**: Bradesco BBI, BTG Pactual, Itaú BBA, Safra, UBS BB, Votorantim — Itaú com
  25,0%), seguido de **Agibank II** (R$ 2,50 bi, Bradesco/Itaú 50/50) e **Driver Brasil Six**
  (R$ 2,00 bi, Bradesco/Itaú 50/50).

Regime de colocação em FIDC: 21 operações em garantia firme (R$ 14,38 bi), 28 em melhores
esforços (R$ 7,66 bi), 4 mistas (R$ 3,02 bi).

O anexo traz `Registro CVM`, o que permite **casar operação a operação com a nossa base CVM** e
enriquecer o ranking com cedente, sacado e taxonomia de carteira já existentes no repositório.

---

## 7. O que foi construído

| Artefato | Conteúdo |
| --- | --- |
| `services/anbima_fixed_income_ranking.py` | Parser do ranking e do anexo; conversão de R$ mil → BRL; agregações por escopo |
| `scripts/build_anbima_fixed_income_ranking.py` | Pipeline: resolve os arquivos na API da ANBIMA, baixa, parseia, reconcilia e materializa |
| `data/industry_study/anbima_rf_ranking_official.csv` | Ranking publicado, tidy (medida × tipo × janela × participante) |
| `data/industry_study/anbima_rf_ranking_annex.csv.gz` | **Anexo deal-a-deal: uma linha por operação × coordenador, com percentual** |
| `data/industry_study/anbima_rf_ranking_participant_share.csv` | Share por participante e escopo (originação e distribuição) |
| `data/industry_study/anbima_rf_ranking_reconciliation.csv` | Prova anexo × ranking publicado + comparação contra CVM líder |
| `data/industry_study/anbima_rf_ranking_syndication.csv` | Distribuição de operações por nº de coordenadores |
| `data/industry_study/anbima_rf_ranking_manifest.json` | Proveniência: URLs, SHA-256 dos arquivos, contagens, limitações |

Reexecutar:

```bash
python scripts/build_anbima_fixed_income_ranking.py
```

### Qualidade da reprodução

Somar o anexo reproduz o ranking publicado **ao centavo** em todos os escopos e nas duas
medidas (originação e distribuição): maior divergência absoluta observada de
**R$ 0,0000076** (ruído de ponto flutuante), e divergência máxima de participação de 5×10⁻¹².

**Limitação conhecida**: a contagem de **número de operações** do bloco consolidado (Tipo 1) tem
resíduo de até 3 operações por participante (Itaú BBA: 151 calculadas × 154 publicadas). O anexo
não expõe o identificador interno de operação da ANBIMA, então o agrupamento usa
`CNPJ do emissor + data de encerramento`. **No recorte FIDC a contagem bate exatamente**
(19 para o Itaú BBA, 43 no total), que é o recorte que interessa aqui. Os **valores** batem em
todos os escopos.

---

## 8. Momento 2 — integração ao contrato de slides

Fora do escopo desta entrega, conforme combinado. Quando for a hora, o caminho natural é:

- adicionar o share ANBIMA ao `services/industry_ppt_export.py`, com as três janelas;
- casar `registro_cvm` do anexo com `offer_id` da base CVM para trazer cedente/sacado/taxonomia
  para os slides de FIDC;
- fixar a competência no manifesto para que o deck declare a data-corte e o SHA-256 da fonte,
  no mesmo padrão dos demais pacotes do repositório.
