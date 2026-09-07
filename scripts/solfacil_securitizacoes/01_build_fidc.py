# -*- coding: utf-8 -*-
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = "outputs/solfacil/Solfacil_Securitizacoes_Comparativo.xlsx"

AR = "Arial"
NAVY = "1F3864"; BLUE = "2E5C8A"; LGREY = "F2F2F2"; BAND = "EAF0F6"; WHITE = "FFFFFF"
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = Workbook(); wb.remove(wb.active)

# ---------------------------------------------------------------- FIDC
# ordem cronologica de 1a emissao
F = ["I", "II", "IV", "V", "III", "VI", "VII"]
HDR = {
 "I":   "IS Green Solfácil I\nFIDC RL",
 "II":  "IS Green Solfácil II\nFIDC RL",
 "IV":  "Solfácil IV\nFIDC",
 "V":   "IS Green Solfácil V\nFIDC RL",
 "III": "IS Green Solfácil III\nFIDC RL",
 "VI":  "IS Green Solfácil VI\nFIDC RL",
 "VII": "IS Green Solfácil VII Financeiro\nFIDC RL",
}

D = {}
D["CNPJ"] = dict(I="36.771.685/0001-17", II="42.462.306/0001-00", IV="44.909.456/0001-44",
                 V="47.240.785/0001-33", III="49.920.525/0001-34", VI="57.028.406/0001-08",
                 VII="63.505.455/0001-89")
D["Registro CVM"] = dict(I="09/12/2020", II="17/09/2021", IV="04/05/2022", V="08/12/2022",
                         III="13/03/2023", VI="27/08/2024", VII="04/11/2025")
D["1ª emissão / início de operação"] = dict(
 I="dez/2020", II="out/2021", IV="jun/2022 (1ª emissão privada)\njan/2023 (1ª oferta pública, R$ 250 mm)",
 V="mar/2023", III="jul/2023 — 1ª integralização em 14/07/2023\n(oferta R$ 480 mm)",
 VI="nov/2024 — 1ª integralização em 29/11/2024\n(oferta R$ 896 mm)",
 VII="jan/2026 — anúncio de início 13/01/2026\n(oferta R$ 768 mm, encerrada 08/06/2026)")
D["Administrador"] = dict(I="Banco Daycoval", II="Banco Genial", IV="Banco Genial", V="Banco Daycoval",
                          III="Banco Daycoval", VI="Limine Trust DTVM", VII="Genial Investimentos CVM")
D["Gestor"] = dict(I="Angá Administração de Recursos", II="Angá Administração de Recursos",
                   IV="Genial Gestão", V="Angá Administração de Recursos", III="Régia Capital (originalmente JGP)",
                   VI="Régia Capital (originalmente JGP)", VII="Angá Administração de Recursos")
D["Coordenador líder da oferta"] = dict(I="Colocação privada", II="Colocação privada / Genial",
                                        IV="Banco Genial", V="Colocação privada",
                                        III="Itaú BBA", VI="Banco Modal", VII="Itaú BBA")
D["Rating (agência, data)"] = dict(
 I="SR Rating, out/2024\nSr brA+ · Mez brBBB+ · Jr brBB+",
 II="Austin, set/2025\nSr brAA(sf) · Mez brBBB+(sf) · Jr brBB+(sf)",
 IV="Austin, ago/2024 — ratings encerrados\nMez A1/A2/B1/B2 brBBB+(sf)",
 V="SR Rating, ago/2024\nSr brA+ · Mez brBBB+ · Jr brBB+",
 III="Fitch, nov/2025\nSr AA+sf(bra) persp. positiva · Mez A BBBsf(bra)",
 VI="Austin, nov/2025\nSr (1ª série) brAA(sf) estável",
 VII="Moody's (1ª série sênior), conforme registro CVM\nrelatório não publicado no Fundos.NET")
D["Prazo do fundo"] = dict(
 I="Indeterminado", II="Indeterminado", IV="Indeterminado", V="Indeterminado",
 III="Indeterminado (fundo)\nSéries com vencimento definido", VI="Indeterminado",
 VII="Indeterminado")
D["Vencimento das séries"] = dict(
 I="Definido no Suplemento de cada série", II="Definido no Suplemento de cada série",
 IV="Definido no Apêndice de cada emissão (em branco no modelo)",
 V="Definido no Suplemento de cada série",
 III="Sênior ago/2031 (98 m)\nMez A ago/2033 (120 m)\nMez B fev/2036 (150 m)",
 VI="Data de Resgate de cada série (Suplemento)", VII="Data de Resgate de cada série (Suplemento)")

D["Subclasses"] = dict(
 I="Sênior · Mezanino Tipo A · Mezanino Tipo B · Júnior",
 II="Sênior (sér. 1 e 2) · Mezanino (sér. 1 e 2) · Júnior",
 IV="Sênior (subclasse única, exclusiva) · Mezanino A1/A2/B1/B2 · Júnior",
 V="Sênior · Mezanino · Júnior",
 III="Sênior · Mezanino A · Mezanino B · Júnior",
 VI="Sênior · Mezanino A · Mezanino B · Júnior",
 VII="Sênior · Mezanino A · Mezanino B · Júnior")
D["Volume da 1ª emissão por classe"] = dict(
 I="Não divulgado (colocação privada)", II="Não divulgado (colocação privada)",
 IV="R$ 250 mm registrados na 1ª oferta pública (jan/2023);\nreaberturas de R$ 10/50/250/260 mm",
 V="Não divulgado (colocação privada)",
 III="Sr R$ 319,3 mm · Mez A R$ 64,0 mm\nMez B R$ 18,7 mm · Sub R$ 20,0 mm",
 VI="Sr R$ 700 mm (78%) · Mez A R$ 140 mm (16%)\nMez B R$ 56 mm (6%) · Jr privada",
 VII="Sr R$ 600 mm (78%) · Mez A R$ 120 mm (16%)\nMez B R$ 48 mm (6%) · Jr privada")
D["Remuneração-alvo (benchmark)"] = dict(
 I="Sr IPCA + 6,75% a.a.\nMez A IPCA + 8,00% · Mez B IPCA (sem spread)",
 II="Sr sér.1: IPCA+11% (12 m) → +8% (13º) → +7% (50º)\nSr sér.2: IPCA+11% (6 m) → +8% (7º-13º) → +7% (44º)\nMez: IPCA+13% → +12,5% → +11,5%",
 IV="Mez A1 DI+6,65% · Mez A2 DI+7,3% → 8,30%\nMez B1 DI+6,2% → 7,20% · Mez B2 DI+7,3% → 8,30%\n(quebra em 23/06/2025)",
 V="Sr IPCA + 10,0% a.a.\nMez IPCA + 13,0% a.a.",
 III="Sr CDI + 3,50%\nMez A CDI + 5,75% · Mez B CDI + 6,75%",
 VI="Sr CDI + 3,50%",
 VII="Não divulgado em documento público (definido no Suplemento)")

D["Métrica de subordinação usada"] = dict(
 I="Razão de Garantia = PL / Cotas Seniores",
 II="Relação Mínima Sênior e Relação Mínima Mezanino\n(% do PL em cotas subordinadas)",
 IV="Não publicada no regulamento vigente\n(anexo de índices mínimos ausente)",
 V="Razão de Garantia = PL / Cotas Seniores",
 III="Índices de Subordinação (% do PL) por classe",
 VI="Índice de Subordinação (% do PL) + Razão de Cobertura\n(ativos / saldo das cotas)",
 VII="Índice de Subordinação (% do PL) + Razão de Cobertura\n(ativos / saldo das cotas)")
D["Subordinação mínima sob a Sênior"] = dict(
 I="25,0% do PL (Razão de Garantia ≥ 133%)",
 II="20,0% do PL",
 IV="Não divulgado; Austin reporta mín. de 10,0% do PL em Júnior",
 V="20,0% do PL (Razão de Garantia ≥ 125%)",
 III="25,0% do PL",
 VI="25,0% implícitos (Razão de Cobertura Sênior ≥ 133,3%)",
 VII="25,0% implícitos (Razão de Cobertura Sênior ≥ 133,33%)")
D["Subordinação mínima sob o Mezanino"] = dict(
 I="Mez B + Júnior ≥ 15,0% do PL",
 II="n/a (única faixa mezanino)",
 IV="Não divulgado",
 V="n/a (única faixa mezanino)",
 III="Mez A ≥ 10,0% (Mez B + Jr) · Mez B ≥ 4,0% (Jr)",
 VI="Mez A ≥ 5,0% · Mez B ≥ 2,5% (Índice de Subordinação)\nCobertura: Mez A ≥ 111,1% · Mez B ≥ 104,2%",
 VII="Mez A ≥ 5,0% · Mez B ≥ 2,5% (Índice de Subordinação)\nCobertura: Mez A ≥ 111,11% · Mez B ≥ 104,17%")
D["Subordinação mínima do Júnior"] = dict(
 I="Incluída nos 15% de Mez B + Júnior", II="4,5% do PL (3,0% pro forma na integralização)",
 IV="10,0% do PL (fonte: Austin)", V="7,0% do PL", III="4,0% do PL",
 VI="2,0% do PL", VII="2,0% do PL")
D["Trava para amortizar o Júnior"] = dict(
 I="Pro forma: subordinadas ≥ 26,5% e Mez B + Jr ≥ 16,5% do PL;\nRazão de Garantia de Cotas Públicas ≥ 110%",
 II="Índices de atraso enquadrados, relações mínimas mantidas\ne rentabilidade da Júnior positiva nos últimos 3 meses",
 IV="Não divulgado",
 V="Pro forma: subordinadas ≥ 22% e Júnior ≥ 9% do PL;\nÍndice de Garantia de Cotas Públicas ≥ 105%",
 III="Índices de Subordinação enquadrados e alvo de 12% do PL",
 VI="Solicitação de 75% das Júnior; cobertura acima do Patamar de\nLiberação de Amortização Extraordinária (136,0/113,3/106,3%)",
 VII="Solicitação de 75% das Júnior; cobertura acima do Patamar de\nLiberação (136,0/113,3/106,3%); Pro Rata em curso")

D["Tipo de amortização (como funciona)"] = dict(
 I="Programada linear. A Reserva de Amortização é constituída todo mês\ncomo PL da classe ÷ nº de meses restantes, paga a Sênior e depois o\nMezanino A. Não há regimes pro rata / sequencial nomeados.",
 II="Alvo de composição (pro rata). Em cada Data de Pagamento o caixa\nleva cada classe de volta ao seu alvo de % do PL — Sr 80%, Mez 16%,\nJr 10%. A partir do 60º mês vira sequencial pura.",
 IV="Definida em cada Apêndice de emissão; o regulamento vigente não\ntraz cronograma nem regimes nomeados. Fundo em run-off.",
 V="Programada linear, mesma mecânica do FIDC I (Reserva de\nAmortização mensal sobre o prazo remanescente da série).",
 III="Alvo de composição (pro rata) até o 47º mês — Sr 67%, Mez A 15%,\nMez B 6%, Jr 12% do PL. Do 48º mês em diante, cascata sequencial.",
 VI="Bullet. Meta de Amortização de Principal = 0% durante todo o Período\nde Carência; o principal só sai no Período de Desinvestimento\n(6 meses antes do resgate), em Evento de Venda, por call do Júnior\nou sob Amortização Sequencial.",
 VII="Revolvente 12 meses (só juros) e depois alvo de composição\n(pro rata) — Sr 73%, Mez A 15%, Mez B 6%, Jr 6% do PL.")
D["Carência de principal"] = dict(
 I="Período de Carência definido no Suplemento da série;\nnenhuma cota amortiza durante ele",
 II="Período de Carência definido no Suplemento;\nrecursos reinvestidos em novos direitos creditórios",
 IV="Definida no Apêndice",
 V="Período de Carência definido no Suplemento\n(Júnior pode amortizar extraordinariamente)",
 III="Zero — todas as séries amortizam desde o 1º mês (fonte: Fitch)",
 VI="Integral: da 1ª integralização até o mês anterior ao\nPeríodo de Desinvestimento",
 VII="12 meses (Período de Revolvência)")
D["Carência de juros"] = dict(
 I="Não prevista", II="Não prevista", IV="Definida no Apêndice", V="Não prevista",
 III="Não prevista", VI="Não prevista", VII="3 meses iniciais")
D["Datas de pagamento"] = dict(
 I="Mensais, conforme Suplemento da série", II="Mensais, conforme Suplemento da série",
 IV="Conforme Apêndice", V="Mensais, conforme Suplemento da série",
 III="Mensais", VI="Mensais (Data de Referência da Classe)", VII="Mensais (Data de Referência da Classe)")
D["Regime pro rata × sequencial"] = dict(
 I="Não existe. A cascata é fixa: encargos → Reserva de Caixa →\nReserva de Amortização Sênior → Mezanino A → demais",
 II="Pro rata por alvo até o 59º mês; sequencial a partir do 60º mês\n(Sênior integral → Mezanino integral → Júnior)",
 IV="Não previsto no regulamento vigente",
 V="Não existe. Cascata fixa, como no FIDC I",
 III="Pro rata por alvo até o 47º mês; sequencial do 48º mês em diante\nou sob Amortização Sequencial",
 VI="Pro Rata até Evento de Desalavancagem; Sequencial depois dele,\nvoltando a Pro Rata com Evento de Realavancagem",
 VII="Pro Rata desde a 1ª integralização de Sênior; Sequencial após\nEvento de Desalavancagem; retorna com Realavancagem")
D["Gatilhos que disparam a amortização sequencial"] = dict(
 I="Não aplicável. Desenquadramento da Razão de Garantia suspende\naquisições e obriga aporte dos subordinados em até 2 dias úteis",
 II="Passagem do 60º mês (por prazo). Desenquadramento das Relações\nMínimas bloqueia amortização de Júnior",
 IV="Não aplicável",
 V="Não aplicável. Mesma mecânica de reenquadramento do FIDC I",
 III="Passagem do 48º mês (por prazo) ou desenquadramento dos\nÍndices de Subordinação / Índices de Atraso",
 VI="Evento de Desalavancagem: (i) cobertura < Patamar 1 em 2 datas\nconsecutivas ou 4 alternadas em 12 m, ou < Patamar 2 em qualquer\ndata; (ii) não pagamento da Meta Sênior em 3 dias úteis;\n(iii) Índice de Atraso 90 > 15%; (iv) Evento de Liquidação Antecipada",
 VII="Idênticos ao VI. Encerram automaticamente a revolvência.")
D["Gatilho de retorno ao pro rata"] = dict(
 I="n/a", II="n/a (mudança é por prazo)", IV="n/a", V="n/a",
 III="Reenquadramento dos índices (a troca do 48º mês é definitiva)",
 VI="Evento de Realavancagem: cobertura ≥ Patamar de Liberação\n(136,0 / 113,3 / 106,3%) e Índice de Atraso 90 < 14%",
 VII="Evento de Realavancagem, mesmos patamares do VI")
D["Aceleração de vencimento"] = dict(
 I="Eventos de Avaliação e de Liquidação (assembleia decide)",
 II="Eventos de Avaliação e de Liquidação (assembleia decide)",
 IV="Anexo VII: Eventos de Avaliação e de Liquidação",
 V="Eventos de Avaliação e de Liquidação (assembleia decide)",
 III="Eventos de Avaliação e de Liquidação (assembleia decide)",
 VI="6 Datas de Pagamento consecutivas em Amortização Sequencial;\nmudança definitiva, sem deliberação de assembleia",
 VII="6 Datas de Pagamento consecutivas em Amortização Sequencial;\nmudança definitiva, sem deliberação de assembleia")
D["Call / amortização antecipada"] = dict(
 I="Amortização extraordinária de Mez B e Júnior sujeita às travas acima",
 II="Evento de Venda com prêmio ao Júnior (10% do excedente sobre\nIPCA+11,5% e 1,5% do valor dos direitos vendidos)",
 IV="Não previsto no regulamento vigente", V="Amortização extraordinária de Júnior",
 III="Amortização extraordinária sujeita aos Índices de Subordinação",
 VI="A partir do 18º mês, 75% das Júnior podem solicitar amortização\nantecipada das Cotas Públicas (3 a 8 dias úteis)",
 VII="A partir do 24º mês, mesma mecânica, com Premiação por\nAmortização Antecipada paga junto à amortização")

D["Ativo-lastro"] = dict(
 I="CCB de financiamento solar originada na Plataforma Solfácil",
 II="CCB de financiamento solar (pré e pós-fixadas)",
 IV="CCB de financiamento solar",
 V="CCB de financiamento solar + CPR-Financeira (agro)",
 III="CCB de financiamento solar pré-fixadas",
 VI="CCB de financiamento solar pré-fixadas, aderentes à categoria\n'Energia Renovável' (Green Bond Principles)",
 VII="CCB de financiamento solar pré-fixadas (título verde)")
D["Prazo máximo do recebível"] = dict(
 I="126 meses (3.836 dias), já incluída a carência",
 II="Pré-fixado 2.340 dias (78 m) · Pós-fixado 4.500 dias (150 m)",
 IV="3.870 dias (≈127 meses)",
 V="4.760 dias (≈156 meses), já incluída a carência",
 III="3.845 dias (≈126 meses)",
 VI="126 meses",
 VII="126 meses")
D["Prazo médio ponderado máximo da carteira"] = dict(
 I="70 meses (2.135 dias)", II="80 meses (2.400 dias)", IV="6,5 anos (78 meses)",
 V="Não fixado", III="66 meses (2.000 dias)", VI="80 meses (2.400 dias)", VII="80 meses (2.400 dias)")
D["Carência máxima do recebível"] = dict(
 I="Sem teto autônomo (o limite de 126 meses já inclui a carência)",
 II="180 dias", IV="185 dias",
 V="185 dias (CCB) · 366 dias (CPR-Financeira)",
 III="185 dias", VI="185 dias", VII="185 dias")
D["Teto por devedor — Pessoa Física"] = dict(
 I="R$ 201.000 (preço de aquisição da CCB)", II="R$ 300.000 (valor nominal)",
 IV="R$ 300.000", V="R$ 500.000 (preço de aquisição)", III="R$ 350.000 (valor nominal)",
 VI="R$ 350.000", VII="R$ 350.000 (por CCB e por devedor)")
D["Teto por devedor — Pessoa Jurídica"] = dict(
 I="R$ 502.000", II="R$ 500.000", IV="R$ 500.000", V="R$ 700.000",
 III="R$ 600.000", VI="R$ 700.000", VII="R$ 700.000 (por CCB e por devedor)")
D["Limite de PJ na carteira"] = dict(
 I="Sem limite explícito", II="Sem limite explícito",
 IV="Máx. 35% dos direitos creditórios adquiridos",
 V="Sem limite explícito (tetos nominais por devedor)",
 III="Sem limite explícito", VI="Sem limite explícito",
 VII="Sem limite explícito")
D["Requisitos do devedor PJ"] = dict(
 I="Não especificado", II="Constituída há ≥ 2 anos", IV="Não especificado",
 V="Não especificado", III="Constituída há ≥ 2 anos",
 VI="Constituída há ≥ 2 anos + coobrigação de sócio (≤ 71 anos)",
 VII="Constituída há ≥ 2 anos + coobrigação de sócio (≤ 71 anos)")
D["Idade máxima do devedor PF"] = dict(
 I="Não especificada", II="70 anos", IV="Não especificada", V="Não especificada",
 III="71 anos", VI="71 anos", VII="71 anos")
D["Concentração por devedor"] = dict(
 I="2% do PL por devedor · 10% nos 10 maiores (acima de PL R$ 50 mm)",
 II="2% do PL por devedor · 10% nos 10 maiores (acima de R$ 50 mm)",
 IV="Top 5 integradores ≤ 30% · estado principal ≤ 20%\n4 maiores estados ≤ 40% · score < 300 ≤ 8%\nprazo > 7,5 anos ≤ 17,5% · refinanciados ≤ 5%",
 V="2% do PL por devedor · 10% nos 10 maiores\nmaior integrador ≤ 10% · top 5 integradores ≤ 30%\nCCB PF > R$ 350 mil ≤ 1% do PL · PJ > R$ 550 mil ≤ 1% do PL",
 III="0,10% do PL por devedor · 1% nos 10 maiores",
 VI="Sem limite específico por devedor além dos tetos nominais",
 VII="20% do PL por devedor/grupo econômico (regra geral)\nalém dos tetos nominais")
D["Taxa mínima da carteira"] = dict(
 I="15,75% a.a. (pré) ou IPCA + 11,5% a.a.", II="16,50% a.a. (pré) · 11,75% a.a. (pós)",
 IV="20,50% a.a.", V="Definida por faixa no regulamento", III="23,00% a.a.",
 VI="Taxa Mínima de Transferência (não numérica no regulamento)",
 VII="Taxa Mínima de Transferência (não numérica no regulamento)")
D["Preço de aquisição máximo"] = dict(
 I="100,4% do valor nominal da CCB", II="Não especificado", IV="Não especificado",
 V="Não especificado", III="Não especificado",
 VI="101,0% do saldo contábil da CCB", VII="104,0% do saldo contábil da CCB")
D["Índices de atraso (limite)"] = dict(
 I="Atraso Estoque > 15% ou Atraso Parcelas > 15% → evento",
 II="Atraso Estoque ≤ 12% · Média de Rolagem 90 mensal ≤ 0,9%",
 IV="Não divulgado",
 V="Atraso Estoque > 15% ou Atraso de Arrecadação > 10% → evento",
 III="Atraso Estoque ≤ 12% · Atraso Parcelas ≤ 8,5%",
 VI="Índice de Atraso 90 > 15% → desalavancagem; < 14% → realavancagem\nAvaliação de rolagens: 1,6%",
 VII="Índice de Atraso 90 > 15% → desalavancagem; < 14% → realavancagem\nAvaliação de rolagens: 1,6%")
D["Derivativos"] = dict(I="Não previsto", II="Não previsto", IV="Não previsto", V="Não previsto",
 III="Swap de fluxo de caixa (posição em jul/26: R$ 179 mil)",
 VI="Swap de fluxo de caixa com Reserva de MtM",
 VII="Swap de fluxo de caixa com Reserva de MtM;\naporte obrigatório do Júnior quando o MtM excede 1% do PL")
D["Observações de crédito"] = dict(
 I="Fundo maduro, em amortização. Mezanino B remunerado só por IPCA\nfunciona como camada de absorção de perdas.",
 II="Único da família que admite recebíveis pós-fixados (mínimo de 22%\nda carteira acima de PL de R$ 50 mm).",
 IV="Em run-off: PL caiu para R$ 17,5 mm, só cotas sêniores em circulação,\nratings encerrados e regulamento vigente com referências quebradas.",
 V="Único que admite CPR-Financeira (até 15% do PL) — exposição agro\ndentro de um fundo solar.",
 III="Primeira operação com rating internacional e distribuição pública ampla.\nAmortiza desde o 1º mês, sem carência.",
 VI="Estrutura bullet: nenhuma amortização programada até o fim.\nEm mai/2026 a carteira foi cedida ao CRI 174ª da Vert — PL caiu de\nR$ 895,8 mm (set/25) para R$ 211,1 mm (jul/26).",
 VII="Maior e mais recente. Estrutura de covenants mais completa da família\n(revolvência, razões de cobertura em dois patamares, reserva de MtM).")

# composicao atual (R$ mm, jul/2026 — IME CVM)
COMP = {  # senior, mezanino, junior
 "I":   (53.2, 27.2, 3.3),
 "II":  (68.5, 14.0, 11.5),
 "IV":  (17.5, 0.0, 0.0),
 "V":   (53.4, 9.1, 5.0),
 "III": (94.3, 29.6, 17.2),
 "VI":  (140.1, 39.4, 31.5),
 "VII": (458.5, 128.8, 32.4),
}

ws = wb.create_sheet("FIDC")

SEC = "§"
rows = [
 (SEC, "IDENTIFICAÇÃO"),
 ("row", "CNPJ"), ("row", "Registro CVM"), ("row", "1ª emissão / início de operação"),
 ("row", "Administrador"), ("row", "Gestor"), ("row", "Coordenador líder da oferta"),
 ("row", "Rating (agência, data)"), ("row", "Prazo do fundo"), ("row", "Vencimento das séries"),
 (SEC, "ESTRUTURA DE CAPITAL"),
 ("row", "Subclasses"), ("row", "Volume da 1ª emissão por classe"), ("row", "Remuneração-alvo (benchmark)"),
 (SEC, "SUBORDINAÇÃO MÍNIMA"),
 ("row", "Métrica de subordinação usada"), ("row", "Subordinação mínima sob a Sênior"),
 ("row", "Subordinação mínima sob o Mezanino"), ("row", "Subordinação mínima do Júnior"),
 ("row", "Trava para amortizar o Júnior"),
 (SEC, "AMORTIZAÇÃO"),
 ("row", "Tipo de amortização (como funciona)"), ("row", "Carência de principal"), ("row", "Carência de juros"),
 ("row", "Datas de pagamento"), ("row", "Regime pro rata × sequencial"),
 ("row", "Gatilhos que disparam a amortização sequencial"), ("row", "Gatilho de retorno ao pro rata"),
 ("row", "Aceleração de vencimento"), ("row", "Call / amortização antecipada"),
 (SEC, "CRITÉRIOS DE ELEGIBILIDADE"),
 ("row", "Ativo-lastro"), ("row", "Prazo máximo do recebível"),
 ("row", "Prazo médio ponderado máximo da carteira"), ("row", "Carência máxima do recebível"),
 ("row", "Teto por devedor — Pessoa Física"), ("row", "Teto por devedor — Pessoa Jurídica"),
 ("row", "Limite de PJ na carteira"), ("row", "Requisitos do devedor PJ"),
 ("row", "Idade máxima do devedor PF"), ("row", "Concentração por devedor"),
 ("row", "Taxa mínima da carteira"), ("row", "Preço de aquisição máximo"),
 (SEC, "MONITORAMENTO"),
 ("row", "Índices de atraso (limite)"), ("row", "Derivativos"),
 (SEC, "POSIÇÃO EM JUL/2026 (Informe Mensal CVM)"),
 ("num", "Cotas sêniores (R$ mm)"), ("num", "Cotas mezanino (R$ mm)"), ("num", "Cotas júnior (R$ mm)"),
 ("fml", "Total de cotas (R$ mm)"), ("pct", "Sênior (% do total)"), ("pct", "Mezanino (% do total)"),
 ("pct", "Júnior (% do total)"), ("pct", "Subordinação atual (% do total)"),
 (SEC, "LEITURA DE CRÉDITO"),
 ("row", "Observações de crédito"),
]

def style_sheet(ws, cols, title, subtitle):
    ws["A1"] = title
    ws["A1"].font = Font(name=AR, size=14, bold=True, color=NAVY)
    ws["A2"] = subtitle
    ws["A2"].font = Font(name=AR, size=9, italic=True, color="595959")
    ws.row_dimensions[1].height = 20
    ws.row_dimensions[2].height = 26

ncols = len(F)
style_sheet(ws, ncols, "Securitizações Solfácil — FIDCs",
            "Comparativo estrutural das 7 classes de FIDC. Fontes: regulamentos e relatórios de rating no Fundos.NET (CVM), "
            "cadastro e informe mensal FIDC em dados.cvm.gov.br. Colunas em ordem cronológica de 1ª emissão. Posição patrimonial: jul/2026.")

HR = 4
ws.cell(row=HR, column=1, value="Atributo")
for j, k in enumerate(F, start=2):
    ws.cell(row=HR, column=j, value=HDR[k])
for j in range(1, ncols + 2):
    c = ws.cell(row=HR, column=j)
    c.font = Font(name=AR, size=10, bold=True, color=WHITE)
    c.fill = PatternFill("solid", fgColor=NAVY)
    c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    c.border = BOX
ws.row_dimensions[HR].height = 34

r = HR + 1
numrow = {}
for kind, label in rows:
    if kind == SEC:
        ws.cell(row=r, column=1, value=label)
        for j in range(1, ncols + 2):
            c = ws.cell(row=r, column=j)
            c.fill = PatternFill("solid", fgColor=BLUE)
            c.font = Font(name=AR, size=10, bold=True, color=WHITE)
            c.border = BOX
        ws.row_dimensions[r].height = 18
        r += 1
        continue
    ws.cell(row=r, column=1, value=label).font = Font(name=AR, size=10, bold=True, color=NAVY)
    ws.cell(row=r, column=1).alignment = Alignment(vertical="top", wrap_text=True)
    ws.cell(row=r, column=1).border = BOX
    for j, k in enumerate(F, start=2):
        c = ws.cell(row=r, column=j)
        if kind == "row":
            c.value = D[label][k]
            c.font = Font(name=AR, size=9)
        elif kind == "num":
            idx = {"Cotas sêniores (R$ mm)": 0, "Cotas mezanino (R$ mm)": 1, "Cotas júnior (R$ mm)": 2}[label]
            c.value = COMP[k][idx]
            c.number_format = '#,##0.0;(#,##0.0);-'
            c.font = Font(name=AR, size=9, color="0000FF")
        c.alignment = Alignment(vertical="top", wrap_text=True)
        c.border = BOX
    numrow[label] = r
    r += 1

# formulas
sr = numrow["Cotas sêniores (R$ mm)"]; mz = numrow["Cotas mezanino (R$ mm)"]; jr = numrow["Cotas júnior (R$ mm)"]
tt = numrow["Total de cotas (R$ mm)"]
for name, f in [("Total de cotas (R$ mm)", "=SUM({c}%d:{c}%d)" % (sr, jr)),
                ("Sênior (% do total)", "=IF({c}%d=0,0,{c}%d/{c}%d)" % (tt, sr, tt)),
                ("Mezanino (% do total)", "=IF({c}%d=0,0,{c}%d/{c}%d)" % (tt, mz, tt)),
                ("Júnior (% do total)", "=IF({c}%d=0,0,{c}%d/{c}%d)" % (tt, jr, tt)),
                ("Subordinação atual (% do total)", "=IF({c}%d=0,0,({c}%d+{c}%d)/{c}%d)" % (tt, mz, jr, tt))]:
    rr = numrow[name]
    for j in range(2, ncols + 2):
        col = get_column_letter(j)
        c = ws.cell(row=rr, column=j, value=f.replace("{c}", col))
        c.number_format = '#,##0.0;(#,##0.0);-' if "R$" in name else '0.0%;(0.0%);-'
        c.font = Font(name=AR, size=9, bold=("Subordinação" in name or "Total" in name))
        c.alignment = Alignment(vertical="top", horizontal="right")
        c.border = BOX

ws.column_dimensions["A"].width = 34
for j in range(2, ncols + 2):
    ws.column_dimensions[get_column_letter(j)].width = 34
ws.freeze_panes = "B5"
ws.sheet_view.showGridLines = False

foot = r + 1
ws.cell(row=foot, column=1, value=(
 "Notas: (1) valores em R$ mm apurados a partir do Informe Mensal FIDC de jul/2026 (dados.cvm.gov.br), quantidade × valor da cota por subclasse — células em azul são entradas. "
 "(2) 'Não divulgado' significa que a informação não consta dos documentos públicos consultados (regulamento vigente, relatórios de rating e documentos de oferta). "
 "(3) O Solfácil IV é o único cujo regulamento vigente não publica índices mínimos de subordinação; o número de 10% vem do relatório da Austin Rating de ago/2024."))
ws.cell(row=foot, column=1).font = Font(name=AR, size=8, italic=True, color="595959")
ws.cell(row=foot, column=1).alignment = Alignment(wrap_text=True, vertical="top")
ws.merge_cells(start_row=foot, start_column=1, end_row=foot, end_column=ncols + 1)
ws.row_dimensions[foot].height = 46

wb.save(OUT)
print("FIDC ok ->", OUT)
