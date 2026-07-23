# FIDCs — Leitura de mercado para o Comitê (Itaú BBA)

Competência-base: **mai/2026** (último mês completo). Fonte: Toma Conta FIDCs
(Informe Mensal FIDC + Cadastro da CVM), consolidado por conglomerado (de-para por CNPJ).
Base de PL **líquida (ex-FIC-FIDC)** salvo indicação. Números em R$ bilhões.

---

## 1. A tese em uma frase

O mercado de FIDC **dobrou em ~2,5 anos** (R$ 386 bi em dez/23 → **R$ 880 bi** em mai/26,
ex-FIC) e a captura desse boom foi feita por **plataformas de serviço fiduciário e por
independentes** — não pelos assets de banco de varejo. **A briga que importa para o BBA
não é gestão de crédito; é administração/custódia estruturada, e é justamente onde o
Itaú está fora do jogo.**

---

## 2. Quem cresceu, quem caiu

### Gestão (PL sob gestão, ex-FIC)
| Grupo | dez/23 | mai/26 | Δ | Leitura |
|---|--:|--:|--:|---|
| **Oliveira Trust** | 35,7 | **75,8** | +40,1 | Virou a maior gestora — trustee independente |
| **BTG Pactual** | 30,2 | **68,0** | +37,7 | 2ª; cresce em todas as pontas |
| Banco do Brasil | 37,7 | 60,9 | +23,2 | Grande, mas volátil (perdeu 2 posições) |
| **Solis** | 5,6 | 27,2 | +21,6 | Independente que mais subiu (crédito estruturado) |
| **Itaú** | 1,1 | 21,4 | +20,3 | Subiu **78 posições** — mas partindo do zero |
| Bradesco | 22,4 | 40,7 | +18,3 | — |
| CBSF | 4,8 | 21,0 | +16,1 | Fiduciário que escalou rápido |
| REAG | 5,1 | 18,9 | +13,8 | Consolidador (ativos judiciais/NPL) |

Caíram (raros): Jus Capital (−3,2), Acura, Eco Gestão, RB Asset — independentes pequenos
perdendo escala. **A indústria é de ganhadores; quase ninguém encolhe em termos absolutos.**

### Administração e Custódia — onde o Itaú apanha
| | Administração (mai/26) | Custódia (mai/26) | Δ custódia desde 2022 |
|---|--:|--:|--:|
| **BTG Pactual** | **145,3** | **145,7** | **+128** |
| **QI Tech** | 139,2 | 138,8 | +94 |
| **Oliveira Trust** | 97,7 | 116,5 | +82 |
| Daycoval | 57,7 | 63,7 | +50 |
| Bradesco | 51,4 | 49,9 | +26 |
| **Itaú (Intrag)** | **31,6** | ~baixo | — |

> **Itaú administra ~R$ 32 bi. BTG e QI Tech administram ~R$ 140 bi cada — 4 a 5x mais.**
> Em custódia estruturada o Itaú praticamente não aparece. Este é o gap para levar ao Presidente.

---

## 3. As três histórias que explicam o mercado

**Oliveira Trust — o vencedor improvável.** É "Independente Grande" (não é banco). Cresceu
simultaneamente como **gestora** (20→76), **administradora** (34→98) e **custodiante**
(34→117). Capturou o boom de FIDCs estruturados sendo o trustee neutro que bancos e
fintechs contratam. É o benchmark de "plataforma fiduciária".

**QI Tech — a fintech que virou infraestrutura.** Saiu de R$ 45 bi (2022) para **~R$ 139 bi**
em administração/custódia. Modelo *banking-as-a-service*/DTVM para as fintechs de crédito —
cada novo FIDC de fintech tende a nascer na QI. Cresce com a originação digital, não com balanço.

**BTG — domina o topo.** Lidera custódia (146) e administração (145) e é 2º gestor (68). Único
grande banco que joga forte na indústria estruturada — e é o principal cedente em pagamentos
(ver §5). É o competidor direto do BBA nessa arena.

---

## 4. Independentes x bancos (confirma a tese do deck)

PL sob gestão por tipo de controle: **Independente 65% (R$ 625 bi)**, Ligada a banco 26%
(R$ 251 bi), Independente Grande 8,5% (R$ 81 bi). Os independentes saíram de R$ 175 bi (2022)
para R$ 625 bi. **A gestão migrou para fora dos bancos; a administração/custódia concentrou
em poucas plataformas (BTG, QI, OT).**

## 5. Cedentes e sacados relevantes (leitura de regulamentos)

**Maiores cedentes (originadores)** — materialidade R$ bi:
Banco BTG Pactual **15,9** (pagamentos) · Multiplike 2,2 (risco sacado) · PagueVeloz 2,0 ·
Banco Bradesco 1,7 (pagamentos) · Banco BMG 1,5 · BRB 1,4 · UPL/Lavoro (agro) ~0,7–0,9.
Por setor, **Meios de Pagamento e Cartões lidera** (R$ 18 bi), seguido de Crédito PF (7,3).

**Maiores sacados (devedores)** — materialidade R$ bi:
**Mercado Pago 5,7** (o maior — ecossistema MELI) · Casas Bahia 0,8 · SafraPay 0,8 ·
Lavoro Agro 0,7 · PayJoy 0,5 · Banco Votorantim.

> Insight: os grandes sacados são **plataformas de pagamento e varejo** (Mercado Pago,
> Casas Bahia, SafraPay). O crédito estruturado está colado ao ecossistema de meios de
> pagamento — exatamente onde CloudWalk/PagSeguro/MELI aparecem no Top 25.

*Ressalva de dados:* a leitura de cedente/sacado vem de regex sobre regulamentos e cobre
~142 partes nomeadas; é a camada mais rala do dataset e o principal ponto a adensar (ver
brief do Codex).

## 6. Estrutura de cotistas

Entre os 863 fundos > R$ 200 mi (R$ 794 bi, ~90% da indústria), **273 têm até 2 cotistas
(R$ 251 bi)**: são veículos de crédito institucionais (cedente + banco/estruturador), não
distribuição pulverizada. Confirma que o crescimento é *funding atacadista*, não varejo.

---

## 7. Mensagens para o Presidente (3 slides de abertura sugeridos)

1. **"O mercado dobrou e nós não capturamos a camada que mais cresceu."** Indústria 386→880;
   Itaú administra 32 vs BTG/QI ~140. Gap de 4–5x em administração/custódia.
2. **"O jogo virou plataforma fiduciária."** Oliveira Trust e QI Tech — nenhum é banco de
   varejo — lideram; independentes já são 65% da gestão.
3. **"O crédito está colado a pagamentos."** Maiores sacados = Mercado Pago, SafraPay, Casas
   Bahia; maior cedente = BTG em pagamentos. É onde o BBA precisa de uma tese.

## 8. O que ainda falta para a versão final (gaps de dado honestos)

- **Cedente/sacado** é a camada mais fraca (142 partes) — precisa adensar via leitura de
  regulamentos dos Top 50–100 fundos.
- **Classe ANBIMA oficial** (Fomento/Financeiro/Agro) não é extraível do dashboard (Power BI);
  hoje usa-se a taxonomia de segmento do Toma Conta (análoga).
- **Série de gestor histórica** assume cadastro vigente projetado (gestor não consta no informe
  mensal); direcionalmente correta, mas não é gestor "à época".
