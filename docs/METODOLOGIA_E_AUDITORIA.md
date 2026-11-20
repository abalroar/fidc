# Metodologia e Auditoria — Estudo da Indústria de FIDCs

Documento de defesa. Objetivo: que cada número do estudo seja **rastreável, reprodutível
e explicável em dois minutos** a um diretor executivo, sem inferência. Postura adversarial:
cada métrica só permanece se sobrevive às checagens de consistência (matemática, temporal,
metodológica, econômica e entre fontes).

Competência de referência: **mai/2026** (último mês completo do Informe Mensal FIDC).

---

## 0. Fontes primárias e por que foram escolhidas

| Fonte | O que fornece | Papel no estudo |
|---|---|---|
| **CVM — Informe Mensal Estruturado FIDC** (`dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL`) | PL, carteira, cedentes (%), cotistas por segmento, classes/subordinação — por fundo/classe, mensal | **Primária** para todos os números de estoque, estrutura e investidores |
| **CVM — Cadastro de Fundos** (`FI/CAD`: cad_fi, registro_fundo_classe) | Administrador, **gestor**, custodiante por CNPJ | Atribuição de gestor (não consta no Informe Mensal) |
| **Toma Conta FIDCs** (`data/industry_study/*`) | Séries mensais já consolidadas por dimensão (gestor/admin/custodiante/segmento/fic-fidc), snapshot por fundo, leituras de regulamento | Camada derivada — **materializa** as duas fontes CVM acima |
| **ANBIMA — Deliberação nº 72** | Definições oficiais das classes de FIDC | Referencial de classificação (texto) |
| **ANBIMA (imprensa/boletins)** | Números agregados de captação/crescimento | **Secundária** — validação de magnitude apenas |

**Por que CVM e não o dashboard ANBIMA:** o dashboard de FIDCs da ANBIMA é um relatório
Power BI *publish-to-web*; os números ficam presos no visual (querydata retorna 403 fora do
navegador — ver `docs/investigacao_dashboard_fidc_anbima.md`). A CVM é a fonte primária
regulatória — o mesmo insumo que a ANBIMA consome — e é 100% reprodutível.

**Por que gestor vem do Cadastro (e a ressalva):** o gestor não é reportado no Informe
Mensal. É atribuído pelo **cadastro vigente** e projetado para trás na série histórica.
→ *Limitação documentada:* a série de gestor assume o gestor atual em todos os períodos;
não capta "quem era o gestor à época". Direcional, não pontual. Administrador e custodiante
**constam no Informe Mensal** e não têm essa limitação.

---

## 1. Divergência de fontes no PL da indústria (documentada)

Há **três** números possíveis. Escolhemos um e explicamos os outros — nunca "porque parece melhor".

| Métrica | Valor (mai/26) | Como se obtém | Quando usar |
|---|--:|---|---|
| **PL bruto** | **R$ 959 bi** | Soma direta de `TAB_IV_A_VL_PL` de todas as classes (CVM cru) | Número "cheio" oficial CVM |
| **PL ex-FIC** (escolhido) | **R$ 880 bi** | Bruto − R$ 79 bi de FIC-FIDCs (fundos que só compram cotas de outros FIDCs) | **Padrão do estudo** — evita dupla contagem |
| PL "ANBIMA-like" | ~R$ 600 bi (abr/25 no deck Itaú) | Metodologia proprietária ANBIMA (dedup adicional master-feeder/classes) | Referência externa |

- **Checagem de reprodutibilidade:** a soma bruta do IME cru bate **exatamente** com a série
  do Toma Conta (R$ 959 bi). ✔
- **Risco de dupla contagem:** REAL e tratado. O bruto conta o mesmo real quando um FIDC
  investe em cotas de outro. O ex-FIC remove os 449 fundos marcados FIC-FIDC (−R$ 79 bi).
  Master-feeder e classes sênior/subordinada do mesmo fundo **ainda** podem inflar; por isso
  o número ANBIMA (com dedup adicional) é menor. **Documentado, não escondido.**
- **Recomendação de fala:** citar sempre "ex-FIC R$ 880 bi (bruto CVM R$ 959 bi)".

---

## 2. Auditoria métrica a métrica

Legenda de veredito: ✔ robusto · ⚠ robusto com limitação documentada · ▲ direcional/proxy.

| Indicador | Fonte exata | Fórmula | Universo | Dupla contagem | Reprodutível | Veredito |
|---|---|---|---|---|---|---|
| Evolução do PL | IME Tab IV (via dim `fic_fidc`) | Σ PL ex-FIC, dez de cada ano | Todos FIDCs | Tratada (ex-FIC) | Sim | ✔ |
| Composição por segmento | Toma Conta dim `segmento` | Σ PL por segmento / total | Todos c/ segmento | N/A | Sim | ⚠ segmento é taxonomia interna, ≈ANBIMA |
| Ranking gestor | dim `gestor` + cadastro | Σ PL por grupo (de-para CNPJ) | Todos | N/A (1 gestor/fundo) | Sim | ⚠ gestor = cadastro vigente |
| Ranking adm/custódia | dim `admin`/`custodiante` | Σ PL por grupo | Todos | N/A | Sim | ✔ |
| Market share por papel | idem | PL grupo / PL total do papel | Todos | N/A | Sim | ✔ / ⚠ (gestor) |
| Δ share / Δ rank | idem, 2023→mai/26 | share(t1)−share(t0); rank(t0)−rank(t1) | Todos | N/A | Sim | ✔ |
| Tipo de controle | dim `gestor` + taxonomia | Σ PL por Independente/Banco/Indep. Grande | Todos | N/A | Sim | ⚠ taxonomia = def. rodapé Itaú BBA |
| Originação (novos FIDCs) | snapshot `first_offer_year` | Σ PL de fundos com 1ª oferta no ano | **1.407 de 4.219** c/ 1ª oferta datada | N/A | Sim | ⚠ cobertura 33% (ver §4) |
| Emissões (variação de PL) | dim `fic_fidc` | ΔPL anual (ex-FIC) | Todos | Tratada | Sim | ✔ |
| Captação líquida | IME (dim `segmento`) | Σ (captações − resgates)/ano | Todos | N/A | Sim | ✔ |
| Cotistas (distribuição) | IME Tab X_1 | Σ `NR_COTST` por fundo | Todos | N/A (posições) | Sim | ⚠ conta posições, não CPFs únicos |
| Cotistas por investidor | IME Tab X_1_1 | Σ por categoria (16 tipos) | Todos | N/A | Sim | ⚠ 24% "Outros" (ver §6) |
| Top 25 detalhe | IME Tabs I/VII/X + regulamento | ver `top25_fidc_dossie` | 25 maiores por PL | N/A | Sim | ⚠ cedente/sacado esparsos |
| Cedentes/sacados nomeados | regulamentos (regex) | contagem/materialidade | **569 fundos** (ver §4) | N/A | Sim | ▲ amostra enviesada |
| Itaú por papel | IME + cadastro + de-para | Σ PL por papel | Todos | Não somar papéis | Sim | ✔ (ver `crosscheck_itau.md`) |

---

## 3. Market share — o que existe e como ler

Para **gestores, administradores e custodiantes**, o estudo entrega (abas + slides):
- **share % em 2023, 2024, 2025 e mai/26** (trajetória, não só pontas);
- **Δ share (pp)** = share final − share inicial;
- **Δ PL (R$ bi)** = PL final − inicial;
- **Δ nº de fundos** (dim `funds_unique`; ex.: Oliveira Trust 24→50, BTG 33→77 como gestor);
- **ranking inicial e final** e **Δ rank**;
- **maiores vencedores/perdedores** destacados por papel.

**Interpretação (exemplos defensáveis):**
- *Administração/custódia:* **BTG** é o maior vencedor (+9,1 pp de share, rank 3→1). **Banco
  do Brasil** é o maior perdedor (−10 pp, um único ciclo de 2024 que reverteu). QI Tech e
  Oliveira Trust cederam share relativo por crescerem menos que o BTG, mas ganharam PL.
- *Gestão:* **Itaú** salta 78 posições — mas partindo de share 0,3%; é crescimento de base
  pequena, não liderança. **Solis** é o independente que mais ganha share orgânico.
- *Deltas explicados por fundo único:* sinalizados quando um movimento vem de 1 fundo (ex.:
  a volatilidade do BB em 2024 concentra-se em poucos veículos grandes) — por isso mostramos
  a trajetória trimestral, que expõe o "pulo e volta".

---

## 4. Cedentes — universo explícito (o ponto que estava obscuro)

**Universo:** leituras de regulamento por regex. Não são todos os FIDCs.

- Regulamentos disponíveis no inventário: **736 fundos**.
- Fundos com extração estruturada de cedente/sacado bem-sucedida: **569 fundos**.
- Partes com **nome real** (não só CNPJ): **141**; o resto fica como CNPJ.
- **Viés de amostra (crítico):** os regulamentos existem sobretudo para a safra **2024–2026**
  (era RCVM 175, quando o regulamento é público e padronizado). Distribuição por ano de 1ª
  oferta dos fundos lidos: 2024→277, 2025→206, 2026→62. → **A base de cedentes representa os
  FIDCs NOVOS e independentes, e sub-representa os megafundos cativos antigos** (Petrobras,
  TAPSO, consignados de banco), que não têm regulamento parseado.
- **Como ler:** os cedentes/sacados são uma **fotografia da nova safra estruturada**, não do
  estoque inteiro. Nunca apresentar como "os cedentes de toda a indústria".
- **Achados (dentro desse universo):** por materialidade, maior cedente = **Banco BTG**
  (pagamentos, R$ 15,9 bi); setores predominantes = Crédito PF (46), Crédito PJ (41),
  Imobiliário (16), Agro (16), Pagamentos (13). Concentração alta em poucos originadores
  ligados a pagamentos/varejo.
- **Limitação de reprodutibilidade:** extração por regex tem falso-negativo (nomes não
  capturados). Por isso a contagem é **piso**, não total.

## 5. Sacados — o que dá e o que não dá

Mesmo universo e mesma extração dos cedentes (regulamentos, 569 fundos).
- **Dá para identificar:** maiores sacados por materialidade (ex.: **Mercado Pago R$ 5,7 bi**,
  Casas Bahia, SafraPay, Lavoro Agro), setor e recorrência **dentro da amostra 2024–26**.
- **Não dá para identificar de forma completa:** a lista exaustiva de sacados por fundo, nem a
  concentração real, porque (i) regulamentos citam sacados de forma textual e parcial; (ii) os
  megafundos do Top 25 não têm nomes extraídos. O IME traz o **perfil de risco do devedor
  (SCR AA–H)** por fundo — usamos isso como proxy estruturado de qualidade de sacado.
- **Veredito:** sacado nominal = ▲ proxy/amostra; qualidade de sacado (SCR) = ⚠ estruturado.

## 6. Investidores (cotistas) — até onde chega a identificação

**Fonte:** IME Tab X_1_1 — cotistas **por categoria** (sênior + subordinada), 16 tipos.

- **Identificação NOMINAL não é possível** — a CVM divulga cotistas por **categoria**, nunca
  por nome (sigilo). Isto é uma **limitação regulatória**, não do estudo.
- **Identificação por CATEGORIA (mai/26, indústria):** Outros fundos **44%**, Outros 24%,
  Pessoa física 22%, Corretora/distribuidora 8%, PJ não financeira 1,3%, Banco 0,4%,
  institucionais diretos (EFPC/RPPS/seguradora/EAPC/capitalização) **< 0,1% somados**.
  - *Insight defensável:* FIDC é produto **atacadista/veículo de fundo**, não de investidor
    institucional final direto nem de varejo pulverizado.
  - *Limitação:* "Outros fundos" e "Outros" (68% juntos) são categorias amplas do próprio
    formulário CVM; e a contagem é de **posições de cotista**, não de investidores únicos
    (um investidor em 2 classes conta 2×).
- **Distribuição de nº de cotistas por fundo (todos):** mediana **4**, média **106**,
  p90 = 64, p95 = 158, p99 = 3.059, máx 23.847; **40% dos fundos têm ≤ 2 cotistas**.
  Cauda pesada: a maioria são veículos concentrados; poucos (fintechs/varejo) têm milhares.
- **Entregável:** histograma + percentis por fundo, com recorte adicional para a safra
  2024–2026 (fundos novos), onde a base documental é mais rica.

## 7. Mercado secundário — verdito de disponibilidade

**Não há base pública granular gratuita.** Investigado:
- **ANBIMA Feed** `precos-indices/v1/fidc/mercado-secundario`: taxas de compra/venda/indicativa
  e PU por FIDC — **exige credencial paga** (OAuth2, contratação).
- **B3 DataWise+**: volume negociado por investidor, série desde 2012 — **solução comercial**.
- **ANBIMA Data / Boletins**: só **agregados** periódicos (PDF), sem granularidade por fundo.
- **CVM**: o Informe Mensal traz negociação de **direitos creditórios** (o fundo comprando/
  vendendo recebíveis), que **não é** o mercado secundário de **cotas** — não confundir.

**Conclusão:** uma análise robusta de liquidez do secundário **exige fonte paga** (ANBIMA Feed
ou B3). Proxies gratuitos possíveis, com ressalva explícita de fraqueza:
- rotatividade de cotistas mês a mês (Tab X) — proxy fraco de liquidez;
- volume de novas emissões vs. resgates (primário, não secundário).
→ **Recomendação:** não apresentar número de secundário sem a fonte paga; declarar a lacuna.
Nunca inventar indicador de liquidez.

## 8. Checagens adversariais executadas

- **Matemática:** soma de shares = 100% por papel/competência. ✔
- **Temporal:** séries mensais contínuas 2013→2026; último mês incompleto descartado. ✔
- **Entre fontes:** PL bruto Toma Conta = PL bruto CVM cru (R$ 959 bi). ✔
- **Econômica:** ordem de grandeza do crescimento (≈ dobrou em 2,5a) coerente com ANBIMA
  (FIDCs entre líderes de captação 2024–25). ✔
- **De-para:** varredura de todas as entidades por keyword; Itaúna excluída; Itaú completo. ✔
- **Falha conhecida (não resolvida):** classe ANBIMA oficial exata e liquidez do secundário —
  exigem fonte paga; permanecem como lacunas declaradas.

## 9. O que NÃO afirmamos (para não ser derrubado no comitê)

- Não afirmamos a classe ANBIMA oficial de cada fundo (usamos segmento interno, análogo).
- Não afirmamos cedentes/sacados de "toda a indústria" (amostra 569 fundos, safra 2024–26).
- Não afirmamos identidade nominal de investidores (sigilo CVM; só categoria).
- Não afirmamos liquidez/volume de secundário (sem fonte paga).
- Não somamos PL de papéis diferentes do mesmo grupo (gestor ≠ adm ≠ custódia).
