# Viabilidade — Reconstruir os slides de FIDC (Itaú BBA) com dados ANBIMA/CVM em Python

Data: 2026-07-10
Contexto: avaliar se dá para **remontar os gráficos de um deck de mercado de FIDCs**
(estilo Itaú BBA) com os **dados mais recentes**, em Python (pandas/numpy/matplotlib),
sem Power BI. Complementa `docs/investigacao_dashboard_fidc_anbima.md`.

> Todos os achados abaixo foram testados de fato: downloads da CVM, parse dos CSVs,
> somatórios de PL e inspeção do CMS/bundles da ANBIMA Data.

---

## Veredito

**Sim, é possível reconstruir a maioria dos gráficos sem Power BI.** A espinha dorsal
(PL, nº de cotistas, administrador, carteira — por fundo) está **gratuita e aberta na
CVM**. O que **não** é dado bruto e sim *camada de classificação* — e por isso exige
decisão de fonte — são apenas duas coisas:

1. **Classe/segmento ANBIMA do FIDC** (Fomento Mercantil, Financeiro, Agro/Indústria e
   Comércio, Multicedente/Multisacado, Outros) — taxonomia **proprietária da ANBIMA**.
2. **Identidade do gestor + rótulo "Independente vs Ligada a Banco"** — o gestor não
   vem no informe mensal da CVM (só o administrador), e o corte "independente/banco" é
   uma **taxonomia própria do Itaú** (lista mantida à mão).

Fora esses dois pontos, tudo é reconstruível com dado público gratuito.

---

## Fonte de dados confirmada (testada hoje)

### CVM — Informe Mensal FIDC (GRÁTIS, sem autenticação)
Diretório: `https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/`
Arquivos: `inf_mensal_fidc_AAAAMM.zip` (CSV `;`-separado, encoding `latin-1`,
**decimal com ponto**, ex. `1843422623.16`).

Cobertura observada:
- `202506` (mês completo): **3.593 classes/fundos**, soma de PL = **R$ 858 bi bruto**.
- `202606` (mês mais recente): só **765** — **incompleto** (fundos entregam com
  defasagem; o último mês só "fecha" depois). → **Sempre usar o último mês completo
  (~M-1/M-2), não o mais recente.**
- Série no formato novo (pós-RCVM 175, por *classe*) começa ~fim de 2024; para série
  histórica longa (2013→) usar a série CVM anterior e/ou o agregado ANBIMA.

Campos por fundo/classe (já verificados):
| Necessidade do slide | Tabela CVM | Campo |
|---|---|---|
| Patrimônio Líquido | `tab_IV` | `TAB_IV_A_VL_PL`, `TAB_IV_B_VL_PL_MEDIO` |
| Nº de cotistas (total) | `tab_X_1` | `TAB_X_NR_COTST` |
| Nº de cotistas **por segmento de investidor** | `tab_X_1_1` | `TAB_X_NR_COTST_SENIOR_*` / `_SUBORD_*` (PF, PJ não-financ, banco, EFPC, EAPC, RPPS, seguradora, etc.) |
| Administrador (nome + CNPJ) | `tab_I` | `ADMIN`, `CNPJ_ADMIN` |
| Nome do fundo / classe / CNPJ | `tab_I` | `DENOM_SOCIAL`, `CLASSE`, `CNPJ_FUNDO_CLASSE` |
| Composição de recebíveis (proxy de segmento) | `tab_I` | `TAB_I2A*`/`TAB_I2B*` + CNPJ dos cedentes |
| Passivo | `tab_III` | `TAB_III_VL_PASSIVO` |

**Alerta metodológico (medido):** somar `TAB_IV_A_VL_PL` de todas as linhas dá
**R$ 858 bi**, mas o número "de indústria" do deck é **R$ 604 bi** (abr/25). A diferença
(~40%) é **dupla contagem**: master-feeder, FIDC que investe em cotas de outro FIDC, e
classes sênior/subordinada do mesmo fundo. Para bater com a ANBIMA é preciso
**deduplicar/consolidar** (é justamente o valor agregado que a ANBIMA entrega pronto).

### O que a CVM **não** tem
- **Gestor (manager):** o informe mensal traz só o administrador. Gestor vem do
  **cadastro de fundos da CVM** ou da **ANBIMA**.
- **Classe/segmento ANBIMA:** não existe na CVM. É da ANBIMA (ver abaixo).

### ANBIMA — duas portas para a camada de classificação
1. **ANBIMA Feed API** (`api.anbima.com.br/feed/fundos/v1/fundos-estruturados`):
   dá `categoria_anbima`, `foco_atuacao`, gestor e série histórica de PL **por CNPJ** —
   é o caminho *oficial e limpo* para classe + gestor. Exige **cadastro + OAuth2 +
   liberação de produção** (`anbimafeed@anbima.com.br`); condições comerciais a
   confirmar. Paginação ≤300/pág, série ≤5 anos.
2. **Rankings públicos ANBIMA** (`data.anbima.com.br/publicacoes/ranking-de-gestores...`
   e `.../ranking-de-administradores...`): publicação mensal (14º dia útil) com
   **PL por classe ANBIMA, captação por classe, PL por segmento de investidor e por
   estrutura de gestão**. É exatamente a base dos slides "maiores gestoras". Parte do
   conteúdo renderiza no mesmo Power BI/CMS já investigado; algumas publicações expõem
   arquivo para download (`connected_documents`/`publication_document` → `file_url` no
   Strapi), outras ficam presas no visual. **Não** separam, de fábrica, o corte
   "independente vs banco" (isso é do Itaú).

### Fonte já existente no próprio repositório
`fundonet_fidc_pipeline.py` + `INVESTIGACAO.md` já implementam a extração
**fundo-a-fundo do IME (XML) via Fundos.NET**, que é mais robusta que o CSV em massa
durante a transição da RCVM 175 (pega PL, carteira, cotistas, cedentes por documento,
com deduplicação de retificações). É a base natural para este pipeline.

---

## Viabilidade por gráfico do deck

Legenda: ✅ grátis/direto · 🟡 exige camada de classificação (gestor e/ou classe ANBIMA
e/ou taxonomia banco) · 🔴 dado não público (só estimável).

| # | Slide / gráfico | Dado necessário | Fonte | Veredito |
|---|---|---|---|---|
| 1 | Evolução do PL dos FIDC (R$ bi, anual) | PL indústria por período (dedup) | CVM (soma dedup) ou agregado ANBIMA | ✅ (histórico longo: ANBIMA/CVM antigo) |
| 2 | Composição PL por Classe ANBIMA (%) | PL + classe ANBIMA por fundo | ANBIMA Feed/dashboard; ou proxy CVM | 🟡 classe é proprietária |
| 3 | PL por Classe Gestor (Indep/Ligada Banco) | PL + gestor + taxonomia banco | CVM/ANBIMA + lista manual | 🟡 |
| 4 | Ranking Prestadores (Top Admin) por segmento, PL>200mm | PL + administrador + filtro | **CVM** (`ADMIN`, `TAB_IV_A_VL_PL`) | ✅ admin; 🟡 segmento |
| 4b | Ranking Prestadores (Top Gestores) por segmento | PL + gestor + segmento | CVM cadastro/ANBIMA | 🟡 |
| 5 | Maiores gestoras por PL (todos os produtos) | ranking de gestores | **Ranking ANBIMA** (público) | ✅ |
| 6 | Maiores gestoras Independentes por PL | ranking + independência | Ranking ANBIMA + taxonomia | 🟡 |
| 7 | Gestores Indep. por Classe (Top 10 x4) | PL + gestor + subclasse + indep | ANBIMA + CVM + taxonomia | 🟡 |
| 8 | Top 20 Gestores Independentes (FIDC) | PL FIDC por gestor + indep | ANBIMA/CVM cadastro + taxonomia | 🟡 |
| 9 | Top 25 FIDCs em PL (nome, classe, gestor, PL) | PL + nome (CVM) + classe + gestor | CVM ✅ nome/PL; 🟡 classe/gestor | ✅/🟡 |
| 10 | Nº de Cotistas — Fundos > R$200mm PL | nº cotistas + PL + filtro | **CVM** (`TAB_X_NR_COTST`, `TAB_IV_A_VL_PL`) | ✅ 100% grátis |
| 11 | PL por segmento de investidor | cotistas/PL por segmento | **CVM** (`TAB_X_..._PF/PJ/BANCO/EFPC/...`) | ✅ (PL por segmento precisa rateio) |

Resumo: **~5 gráficos 100% com dado público grátis** (1, 4-admin, 5, 10, 11) e o
restante viável **desde que resolvidas as duas camadas de classificação** (classe
ANBIMA e gestor/independência).

---

## Arquitetura recomendada (Python, sem Power BI)

1. **Ingestão fundo-a-fundo**: reaproveitar `fundonet_fidc_pipeline.py` (IME/Fundos.NET)
   e/ou baixar os ZIPs mensais da CVM (`inf_mensal_fidc_AAAAMM.zip`), sempre do **último
   mês completo**.
2. **Enriquecimento (camada de classificação)** — escolher UMA rota:
   - **Robusta/oficial:** ANBIMA Feed API → `categoria_anbima`/`foco_atuacao` + gestor
     por CNPJ (requer cadastro/contratação).
   - **Gratuita:** gestor via cadastro CVM; classe ANBIMA **aproximada** pela composição
     de recebíveis/cedentes (Tab I); manter uma tabela manual `gestor→banco/independente`
     em `manual_overrides/`.
3. **Consolidação/dedup**: netar master-feeder, FIDC-de-FIDC e classes sênior/subord.
   para o PL "de indústria" bater com a ANBIMA.
4. **Agregação**: `pandas.groupby` por classe/gestor/administrador/segmento/competência.
5. **Gráficos**: matplotlib (barras de PL anual, barras empilhadas de composição %,
   tabelas de Top N, histograma de nº de cotistas) — 1:1 com os slides.

### Caminho mais sustentável
- **PL de indústria, cotistas, administrador, distribuição de cotistas, filtros por PL**
  → **CVM aberto (grátis)**, já ao alcance do repo.
- **Classe ANBIMA e gestor de forma oficial** → **ANBIMA Feed API** (registrar/contratar).
- **Corte "independente vs banco"** → **tabela própria** (não existe pronto em lugar
  nenhum; é premissa editorial, como no deck do Itaú).
- **Evitar** depender do dashboard Power BI / `querydata` (frágil, 403 fora do
  navegador, zona cinza de ToS — ver `investigacao_dashboard_fidc_anbima.md`).

---

### Anexo — URLs verificadas
- CVM IME FIDC (dir): `https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/`
- CVM IME FIDC (mês completo testado): `inf_mensal_fidc_202506.zip` (3.593 fundos)
- CVM metadados: `https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/META/`
- ANBIMA Feed — Fundos Estruturados: `https://api.anbima.com.br/feed/fundos/v1/fundos-estruturados`
- ANBIMA Ranking de gestores: `https://data.anbima.com.br/publicacoes/ranking-de-gestores-de-fundos-de-investimento`
- ANBIMA Ranking de administradores: `https://data.anbima.com.br/publicacoes/ranking-de-administradores-de-fundos-de-investimento`
- Dashboard FIDC (Power BI, dados presos no visual): ver `docs/investigacao_dashboard_fidc_anbima.md`
