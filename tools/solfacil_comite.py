# -*- coding: utf-8 -*-
"""Tabelas analíticas para o comitê de crédito.

Cobre os nove pontos pedidos: timeline, de-para FIDC->CRI, ranking de risco,
waterfall por estrutura e consolidado, resgate da subordinada, preço de aquisição,
mismatch de prazo, prazo sugerido de exposição e histórico de saques.
"""

ND = "n/d"
NAO_DISP = "não disponível nos documentos"

# ============================================================ 26_Timeline consolidada
TIMELINE_COLS = ["ordem", "data_evento", "veiculo_id", "instrumento", "evento",
                 "montante_Rmi", "data_vencimento_final", "prazo_meses", "situacao", "fonte_id"]
TIMELINE = [
    ("1", "2020-12-09", "FIDC-I", "FIDC", "Registro da 1ª emissão de cotas", "425.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("2", "2021-09-24", "FIDC-II", "FIDC", "Registro da cota subordinada júnior", "25.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("3", "2021-10-07", "FIDC-II", "FIDC", "Registro da 1ª emissão de cotas", "600.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("4", "2021-11-05", "FIDC-I", "FIDC", "2ª oferta de cota subordinada júnior", "50.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("5", "2021-12-21", "FIDC-I", "FIDC", "3ª oferta de cota subordinada júnior", ND, ND, ND, "Em funcionamento", "ANX-DECK"),
    ("6", "2022-02-18", "DEB-I", "Debênture", "Escritura da 1ª emissão de debêntures", "60.0", "2035-08-18", "162", "Em amortização", "ANX-ESC-DEB"),
    ("7", "2022-04-25", "FIDC-II", "FIDC", "2ª emissão de cotas", "96.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("8", "2022-06-20", "FIDC-I", "FIDC", "Emissão da cota mezanino B", "58.6", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("9", "2022-06-23", "FIDC-IV", "FIDC", "Registro da 1ª emissão de cotas", "500.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("10", "2022-12-08", "FIDC-V", "FIDC", "Registro da 1ª emissão de cotas", "356.3", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("11", "2023-01-13", "FIDC-IV", "FIDC", "Emissão das cotas sênior B e mezanino A-2, B-1 e B-2", "317.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("12", "2023-07-10", "FIDC-III", "FIDC", "Registro da 1ª emissão de cotas", "480.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("13", "2023-09-30", "FIDC-III", "FIDC", "Cota subordinada júnior privada", "20.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("14", "2023-12-05", "FIDC-IV", "FIDC", "Emissão da cota sênior C", "260.0", ND, ND, "Em funcionamento", "ANX-DECK"),
    ("15", "2024-01-15", "CRI-I", "CRI", "Emissão da 1ª emissão Kanastra", "603.0", "2036-01-15", "144", "Ativa / adimplente", "ANX-ENC-K1"),
    ("16", "2024-06-25", "CRI-II", "CRI", "Emissão da 2ª emissão Kanastra", "750.0", "2036-06-06", "144", "Ativa / adimplente", "ANX-CM-K2"),
    ("17", "2024-11-06", "FIDC-VI", "FIDC", "Registro da 1ª emissão de cotas", "896.0", ND, ND, "Em runoff pós take-out", "ANX-DECK"),
    ("18", "2025-05-28", "CRI-III", "CRI", "Emissão da 3ª emissão Kanastra", "750.0", "2037-05-08", "144", "Ativa / adimplente", "ANX-PRO-K3"),
    ("19", "2025-09-28", "CRI-IV", "CRI", "Emissão da 4ª emissão Kanastra", "450.0", "2037-09-22", "144", "Ativa / adimplente", "ANX-INI-K4"),
    ("20", "2026-01-13", "FIDC-VII", "FIDC", "Registro da 1ª emissão de cotas", "768.0", ND, ND, "Em revolvência obrigatória", "ANX-DECK"),
    ("21", "2026-05-20", "CRI-V", "CRI", "Emissão da 174ª emissão VERT", "470.6", "2038-05-20", "144", "Ativa / adimplente", "ANX-PRO-V174"),
    ("22", "2026-07-21", "CRI-VI", "CRI", "Emissão da 177ª emissão VERT", "647.1", "2038-07-20", "144", "Ativa / sem informe", "ANX-TS-V177"),
]

# Vencimentos programados por ano, somando todas as séries de CRI e a debênture.
# Base: data_vencimento e montante por série de 02_Series. FIDC não entra: cotas
# de fundo fechado não têm data de vencimento publicada nos documentos do acervo.
NOTA_TIMELINE = (
    "A linha do tempo mistura dois eixos: à esquerda, quando cada veículo foi constituído; "
    "à direita, até quando ele vive. Os FIDCs não aparecem na metade direita porque os "
    "documentos do acervo não publicam data de vencimento das cotas - o que existe é o "
    "período de desinvestimento do FIDC VII (mês 61 ou PL de R$ 100 mi, o que vier primeiro)."
)

# ============================================================ 27_De-para FIDC -> CRI
DEPARA_COLS = ["cri", "cri_nome", "data_emissao", "cedentes_documentados", "cessao_direta_solfacil",
               "situacao_do_cri", "qualidade_da_evidencia", "fonte_id"]
DEPARA = [
    ("CRI-I", "Kanastra 1ª", "2024-01-15", "FIDC II e FIDC IV", "Não",
     "Ativa / adimplente", "Documento primário: Prospecto Definitivo nomeia os dois fundos como representantes de mais de 10% dos direitos creditórios cedidos",
     "ANX-PRO-K1"),
    ("CRI-II", "Kanastra 2ª", "2024-06-25", "FIDC II e FIDC IV", "Não",
     "Ativa / adimplente", "Documento primário: a definição de 'Cedentes' do Prospecto é o FIDC II e o FIDC IV em conjunto",
     "ANX-PRO-K2"),
    ("CRI-III", "Kanastra 3ª", "2025-05-28", "FIDC II, FIDC IV e FIDC VI", "Não",
     "Ativa / adimplente", "Análise de crédito; a lâmina não nomeia fundo e remete ao Termo de Securitização, que não está no acervo",
     "ANX-DECK"),
    ("CRI-IV", "Kanastra 4ª", "2025-09-28", "FIDC II, FIDC IV e FIDC VI", "Sim - parcial",
     "Ativa / adimplente", "Análise de crédito; Termo de Securitização da 4ª emissão não está no acervo",
     "ANX-DECK"),
    ("CRI-V", "VERT 174ª", "2026-05-20", "FIDC VI", "Sim - parcial",
     "Ativa / adimplente", "Análise de crédito. A lâmina confirma que existe um 'Cedente Fundo' com Gestora e custodiante próprios, mas não o nomeia",
     "ANX-DECK; ANX-LAM-V174"),
    ("CRI-VI", "VERT 177ª", "2026-07-21", "FIDC VI e FIDC VII", "Sim",
     "Ativa / sem informe mensal", "Documento primário: o Termo define 'Cedentes' como a Solfácil e os Cedentes Fundos, e 'Cedentes Fundos' como o FIDC Solfácil VI e o FIDC Solfácil VII",
     "ANX-TS-V177"),
]

FIDC_STATUS_COLS = ["fidc", "nome_oficial", "cnpj", "cedeu_para", "situacao_hoje", "pl_Rmi", "carteira_Rmi", "fonte_id"]
FIDC_STATUS = [
    ("FIDC-I", ND, "36.771.685/0001-17", "Nenhum CRI documentado", "Em funcionamento", "83.7", "77.6", "ANX-DECK"),
    ("FIDC-II", "GREEN SOLFÁCIL II FIDC", "42.462.306/0001-00", "CRI-I, CRI-II, CRI-III, CRI-IV", "Em funcionamento", "94.1", "102.5", "ANX-PRO-K1; ANX-DECK"),
    ("FIDC-III", ND, "49.920.525/0001-34", "Nenhum CRI documentado", "Em funcionamento", "141.1", "131.5", "ANX-DECK"),
    ("FIDC-IV", "GREEN SOLFÁCIL IV FIDC", "44.909.456/0001-44", "CRI-I, CRI-II, CRI-III, CRI-IV", "Em funcionamento; sem first loss corrente", "17.5", "14.6", "ANX-PRO-K1; ANX-DECK"),
    ("FIDC-V", ND, "47.240.785/0001-33", "Nenhum CRI documentado", "Em funcionamento", "67.5", "66.7", "ANX-DECK"),
    ("FIDC-VI", "IS GREEN SOLFÁCIL VI FIDC RESPONSABILIDADE LIMITADA", "57.028.406/0001-08",
     "CRI-III, CRI-IV, CRI-V, CRI-VI", "Em runoff após o take-out de julho de 2026", "211.1", "147.7", "ANX-TS-V177; ANX-DECK"),
    ("FIDC-VII", "SOLFÁCIL CRÉDITO PESSOAL VII FIDC RESPONSABILIDADE LIMITADA", "63.505.455/0001-89",
     "CRI-VI", "Em revolvência obrigatória de 12 meses", "619.6", "446.1", "ANX-TS-V177; ANX-DECK"),
]

NOTA_DEPARA = (
    "Dois dos sete fundos nunca aparecem como cedentes em nenhum documento do acervo: o FIDC I e o "
    "FIDC III. O FIDC II e o FIDC IV alimentaram as quatro emissões Kanastra; o FIDC VI atravessa "
    "quatro operações e hoje está em runoff; o FIDC VII entrou apenas na 177ª e segue em revolvência. "
    "Só CRI-I, CRI-II e CRI-VI têm o cedente nomeado em documento primário."
)


# ============================================================ 28_Ranking de permissividade
# Método: cada veículo recebe nota de 0 a 100 em quatro eixos documentados, em que
# 0 = mandato mais restritivo e 100 = mais permissivo. A nota final é a média simples
# dos eixos com dado disponível; eixos n/d não entram e o número de eixos usados fica
# declarado na coluna eixos_avaliados. É agregação de parâmetros documentados, não
# opinião: cada insumo rastreia para 03_Elegibilidade e 04_Concentracao.
RANKING_COLS = ["posicao", "veiculo_id", "instrumento", "cap_individual_pct", "wam_max_dias",
                "prazo_max_dias", "ticket_max_PJ_R", "nota_concentracao", "nota_prazo_wam",
                "nota_prazo_ativo", "nota_ticket", "indice_permissividade", "eixos_avaliados",
                "leitura", "fonte_id", "status"]

# (veiculo, instrumento, cap%, wam, prazo, ticketPJ)
_INSUMOS = [
    ("CRI-V", "CRI", 0.07, 2000, 3845, 700000),
    ("CRI-I", "CRI", 0.10, 2000, 3845, 600000),
    ("CRI-II", "CRI", 0.10, 2000, 3845, None),
    ("CRI-III", "CRI", 0.10, 2000, 3845, 700000),
    ("FIDC-III", "FIDC", 0.10, 2000, 3845, 600000),
    ("CRI-VI", "CRI", 0.11, 2000, 3845, None),
    ("CRI-IV", "CRI", 0.17, 2000, 3845, None),
    ("FIDC-I", "FIDC", 2.00, 2135, 3836, 502000),
    ("FIDC-V", "FIDC", 2.00, None, 4760, 700000),
    ("FIDC-II", "FIDC", 2.00, 2400, 4500, 500000),
    ("FIDC-VI", "FIDC", None, 2400, 3836, 700000),
    ("FIDC-VII", "FIDC", None, 2400, 3836, 700000),
    ("FIDC-IV", "FIDC", 20.00, None, None, None),
]

_LEITURAS = {
    "CRI-V": "Mandato mais restritivo do programa quando o pool amadurece: 0,07% por devedor e vedação expressa a parcela balão.",
    "CRI-I": "Único CRI com teto para os dez maiores devedores (1% do patrimônio separado); ticket PJ é o menor entre os CRIs.",
    "CRI-II": "Mesmo recorte de CRI-I sem o teto de grupo; quatro Razões de Cobertura protegendo a cascata (159/123/110/105%).",
    "CRI-III": "Igual a CRI-II em concentração; ticket PJ sobe de R$ 600 mil para R$ 700 mil.",
    "FIDC-III": "O warehouse com o mandato mais próximo de um CRI: 0,10% por devedor, WAM de 2.000 dias e teto de 1% para os dez maiores.",
    "CRI-VI": "Três Razões de Cobertura (120,48/109,89/105,26%), menos camadas de trava que CRI-II, e o hedge cambial de taxa recai sobre a série retida.",
    "CRI-IV": "Cap individual mais folgado entre os CRIs, escalonado de 0,25% para 0,17%.",
    "FIDC-I": "Adimplência na cessão não é explícita na lista de critérios - a redação é menos protetiva que a dos demais.",
    "FIDC-V": "Único veículo que admite CPR-F além de CCB, com prazo por recebível de até 4.760 dias e ticket PF de R$ 500 mil.",
    "FIDC-II": "Prazo por recebível de até 4.500 dias na modalidade pós-fixada, o dobro do teto de WAM dos CRIs.",
    "FIDC-VI": "Preço máximo de aquisição de 101% do saldo contábil; cap individual não divulgado no acervo.",
    "FIDC-VII": "Preço máximo sobe para 104% do saldo contábil e a elegibilidade passa a ser atestada por endossantes e originador, não pela gestora.",
    "FIDC-IV": "Mandato mais permissivo do programa: 20% por devedor, sem piso de subordinação e sem first loss corrente.",
}


def _nota(valor, minimo, maximo, log=False):
    """0 = extremo restritivo, 100 = extremo permissivo, dentro do universo observado.

    O eixo de concentração usa escala logarítmica: o cap por devedor vai de 0,07% a 20%,
    uma diferença de 285 vezes, e em escala linear todos os CRIs colapsariam em zero.
    Os demais eixos têm amplitude estreita e usam escala linear.
    """
    if valor is None:
        return None
    if log:
        import math
        valor, minimo, maximo = math.log10(valor), math.log10(minimo), math.log10(maximo)
    return round(100.0 * (valor - minimo) / (maximo - minimo), 1)


def _monta_ranking():
    caps = [x[2] for x in _INSUMOS if x[2] is not None]
    wams = [x[3] for x in _INSUMOS if x[3] is not None]
    prazos = [x[4] for x in _INSUMOS if x[4] is not None]
    tickets = [x[5] for x in _INSUMOS if x[5] is not None]
    linhas = []
    for vid, inst, cap, wam, prz, tic in _INSUMOS:
        notas = [_nota(cap, min(caps), max(caps), log=True), _nota(wam, min(wams), max(wams)),
                 _nota(prz, min(prazos), max(prazos)), _nota(tic, min(tickets), max(tickets))]
        validas = [n for n in notas if n is not None]
        indice = round(sum(validas) / len(validas), 1) if validas else None
        linhas.append([vid, inst,
                       f"{cap:.2f}" if cap is not None else ND,
                       str(wam) if wam else ND,
                       str(prz) if prz else ND,
                       str(tic) if tic else ND,
                       *[f"{n:.1f}" if n is not None else ND for n in notas],
                       f"{indice:.1f}" if indice is not None else ND,
                       str(len(validas)),
                       _LEITURAS[vid],
                       "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-TS-V177; ANX-DECK",
                       "Inferido - agregação dos parâmetros documentados; fórmula em 18_Metodologia"])
    linhas.sort(key=lambda r: float(r[10]) if r[10] != ND else 999)
    return [[str(i)] + r for i, r in enumerate(linhas, 1)]


RANKING = _monta_ranking()

NOTA_RANKING = (
    "O índice ordena mandatos, não desempenho: mede o quanto cada documento permite, e não o que "
    "a carteira de fato tem. O FIDC IV é o extremo permissivo em qualquer leitura - 20% por devedor, "
    "sem piso de subordinação e sem first loss corrente. Os seis CRIs ocupam a metade restritiva, "
    "e o FIDC III é o único warehouse que se posiciona junto deles. Os FIDCs VI e VII têm índice "
    "parcial porque o cap por devedor não é divulgado."
)

# ============================================================ 29_Waterfall comparado e consolidado
WATERFALL_CMP_COLS = ["degrau", "ordem", "CRI-II (2ª Kanastra)", "CRI-VI (177ª VERT)", "divergencia"]
WATERFALL_CMP = [
    ("Despesas e reserva de despesas", "1", "Sim - itens (a) e (b)", "Sim - itens (a) e (b)", "Igual"),
    ("Ajustes de contratos de derivativos", "2", "Não previsto", "Sim - item (c), antes da remuneração sênior",
     "CRI-VI paga o swap antes de qualquer investidor"),
    ("Remuneração da camada sênior", "3", "1ª série, sem condição de cobertura",
     "1ª e 2ª séries em conjunto, sem condição de cobertura", "CRI-VI tem duas séries sênior pari passu"),
    ("Amortização da camada sênior", "4", "Maior entre o Anexo I e o Saldo Devedor Target",
     "Até 98% do valor nominal, mantendo a razão base entre as duas séries sênior",
     "CRI-VI trava a proporção entre Sênior A e B (cl. 7.5.3)"),
    ("Camadas intermediárias", "5", "Sênior, Mezanino e Subordinado, cada uma travada pelas coberturas acima",
     "Terceira e Quarta séries (Mezanino I e II), travadas pelas coberturas acima", "Mesma lógica, menos camadas"),
    ("Reserva de caixa de derivativos", "6", "Não previsto", "Sim - item (p), antes da série retida",
     "CRI-VI protege o swap com reserva de até 1% do valor presente"),
    ("Série retida pelo originador", "7", "5ª série, exige as quatro Razões de Cobertura e saldo acima do Target",
     "5ª série, exige as três Razões de Cobertura e saldo acima do Target", "Mesma mecânica"),
    ("Amortização extraordinária proporcional", "8", "Sim - item (aa), só séries enquadradas",
     "Sim - item (t), só séries enquadradas", "Igual"),
    ("Prêmio Final à série retida", "9", "Sim - item (bb), após resgate das quatro séries públicas",
     "Sim - item (u), após resgate das quatro séries públicas", "Igual"),
    ("Alocação em investimentos permitidos", "10", "Sim - item (cc)", "Sim - item (v)", "Igual"),
]

COBERTURAS_COLS = ["veiculo_id", "camada", "razao_de_cobertura_minima_pct", "fonte_id"]
COBERTURAS = [
    ("CRI-II", "Super Sênior", "159,00", "ANX-TS2-K2"),
    ("CRI-II", "Sênior", "123,00", "ANX-TS2-K2"),
    ("CRI-II", "Mezanino", "110,00", "ANX-TS2-K2"),
    ("CRI-II", "Subordinado", "105,00", "ANX-TS2-K2"),
    ("CRI-VI", "Sênior (A e B)", "120,48", "ANX-TS-V177"),
    ("CRI-VI", "Mezanino I", "109,89", "ANX-TS-V177"),
    ("CRI-VI", "Mezanino II", "105,26", "ANX-TS-V177"),
]

NOTA_WATERFALL_CMP = (
    "As duas cascatas integralmente documentadas têm o mesmo esqueleto: despesas, depois cada camada "
    "de cima para baixo travada pelas Razões de Cobertura das camadas acima, e no fim o Prêmio Final "
    "à série retida pelo originador. A diferença material está no derivativo: em CRI-VI o ajuste do "
    "swap é pago antes de qualquer investidor e ainda constitui reserva própria, e o diferencial de "
    "taxa - positivo ou negativo - recai sobre a remuneração da 5ª série, que é a série retida."
)


# ============================================================ 30_Resgate da subordinada
SUBORD_REGRA_COLS = ["veiculo_id", "instrumento", "como_a_subordinada_recebe", "gatilho_ou_teste",
                     "quorum", "trava_temporal", "pode_ser_fonte_de_caixa_do_originador",
                     "evidencia_documental", "fonte_id", "status"]
SUBORD_REGRA = [
    ("CRI-II", "CRI",
     "Automático na Data de Pagamento, até o Saldo Devedor Target; e Prêmio Final ao fim",
     "As quatro Razões de Cobertura enquadradas (159/123/110/105%) e saldo acima do Target",
     "Não há - não depende de deliberação",
     "Carência do Anexo I: a 5ª série só começa a receber no 13º pagamento (07/07/2025)",
     "Sim - a série é subscrita integralmente pela Solfácil e recebe caixa antes do vencimento das séries públicas, desde que as coberturas estejam enquadradas",
     "Cl. 6.5.1, itens (y), (z) e (bb) do Termo consolidado", "ANX-TS2-K2", "Documentado"),

    ("CRI-VI", "CRI",
     "Automático na Data de Pagamento, até o Saldo Devedor Target; e Prêmio Final ao fim",
     "As três Razões de Cobertura enquadradas (120,48/109,89/105,26%) e saldo acima do Target",
     "Não há - não depende de deliberação",
     "Reserva de Caixa Derivativo é constituída antes do pagamento à 5ª série",
     "Sim - mesma mecânica de CRI-II, com a diferença de que o diferencial do swap, positivo ou negativo, impacta a remuneração da própria 5ª série",
     "Cl. 7.5.1, itens (r), (s) e (u); cl. 15.14.6 item 7 e cl. 15.14.8 item 3", "ANX-TS-V177", "Documentado"),

    ("CRI-I", "CRI", "Automático, por targets por camada", "Targets do Termo de Securitização",
     "Não há", ND, "Sim - estrutura equivalente à das demais emissões Kanastra",
     "Termo de Securitização da 1ª emissão não está no acervo; estrutura de targets descrita na análise de crédito",
     "ANX-DECK", "Inferido - Termo ausente"),
    ("CRI-III", "CRI", "Automático, pró-rata condicionado até o mês 47", "Razões de Cobertura",
     "Não há", ND, "Sim - estrutura equivalente", "Termo de Securitização da 3ª emissão não está no acervo",
     "ANX-DECK", "Inferido - Termo ausente"),
    ("CRI-IV", "CRI", "Automático, pró-rata condicionado até o mês 47", "Razões de Cobertura",
     "Não há", ND, "Sim - estrutura equivalente", "Termo de Securitização da 4ª emissão não está no acervo",
     "ANX-DECK", "Inferido - Termo ausente"),
    ("CRI-V", "CRI", "Automático, pró-rata condicionado até o mês 47", "Razões de Cobertura",
     "Não há", ND, "Sim - estrutura equivalente", "Termo de Securitização da 174ª emissão não está no acervo",
     "ANX-DECK; ANX-LAM-V174", "Inferido - Termo ausente"),

    ("FIDC-VI", "FIDC",
     "Amortização extraordinária, mediante pedido dos cotistas da classe júnior",
     "Subordinação e cobertura pro forma, reserva de MTM constituída e ausência de eventos; patamares de 136,0% / 113,3% / 106,3%",
     "75% dos titulares da classe júnior", "Não há trava pós-venda",
     "Sim - R$ 183,2 mi de principal júnior e mezanino já saíram do fundo",
     "Regulamento vigente, conforme a análise de crédito de 21/08/2026",
     "ANX-DECK", "Documentado - regulamento não está no acervo"),
    ("FIDC-VII", "FIDC",
     "Amortização extraordinária, mediante pedido dos cotistas da classe júnior",
     "Mesmos testes do FIDC VI", "75% dos titulares da classe júnior",
     "Bloqueio de 3 meses após Evento de Venda; venda vedada se o MTM superar a júnior",
     "Sim - R$ 7,7 mi já saíram em julho de 2026, no primeiro mês de operação com take-out",
     "Regulamento vigente, conforme a análise de crédito de 21/08/2026",
     "ANX-DECK", "Documentado - regulamento não está no acervo"),
    ("FIDC-I", "FIDC", "Amortização extraordinária sob testes do regulamento",
     "Pisos de subordinação, cobertura e ausência de evento; piso total de 25%", ND,
     "Limites do regulamento vigente", "Sim - R$ 130,4 mi já saíram",
     "Regulamento não está no acervo", "ANX-DECK", "Documentado - regulamento não está no acervo"),
    ("FIDC-II", "FIDC", "Amortização extraordinária sob testes do regulamento",
     "Metas, índices e liquidez pro forma; piso total de 20%", ND,
     "Antes do regime sequencial, se enquadrado", "Sim - R$ 160,8 mi já saíram",
     "Regulamento não está no acervo", "ANX-DECK", "Documentado - regulamento não está no acervo"),
    ("FIDC-III", "FIDC", "Amortização extraordinária sob testes do regulamento",
     "Subordinação, cobertura e ausência de evento; piso total de 25%", ND, "Pró-rata vigente",
     "Sim - R$ 101,4 mi já saíram", "Regulamento não está no acervo", "ANX-DECK",
     "Documentado - regulamento não está no acervo"),
    ("FIDC-IV", "FIDC", "Regra pública incompleta", NAO_DISP, ND, ND,
     "Sim - R$ 438,9 mi já saíram, o maior volume do programa, e o fundo ficou sem first loss",
     "Regulamento não está no acervo e a análise de crédito registra a regra como incompleta",
     "ANX-DECK", "não disponível"),
    ("FIDC-V", "FIDC", "Amortização extraordinária sob testes do regulamento",
     "Índices, caixa e ausência de evento; piso total de 20%", ND, "Limites do regulamento vigente",
     "Sim - R$ 34,4 mi já saíram", "Regulamento não está no acervo", "ANX-DECK",
     "Documentado - regulamento não está no acervo"),
    ("DEB-I", "Debênture",
     "A 2ª série é subordinada à 1ª no recebimento de todos e quaisquer valores",
     "Subordinação contratual integral; a 2ª série não recebe antes da 1ª", "Não há", ND,
     "Não antes da 1ª série - em 31/07/2026 o total distribuído aos investidores da 2ª série é R$ 0,00",
     "Cl. 3.3.2 e 3.3.3 da escritura; tabela de dados das séries do relatório mensal",
     "ANX-ESC-DEB; ANX-RMA-DEB", "Documentado"),
]

NOTA_SUBORDINADA_CAIXA = (
    "A resposta à pergunta é sim, e por dois caminhos distintos. Nos FIDCs a saída depende de pedido "
    "dos cotistas da classe júnior e de testes - nos fundos VI e VII o quórum é de 75% da própria "
    "classe, que é da originadora, de modo que quem pede e quem se beneficia são a mesma parte. "
    "Nos CRIs não há pedido nem quórum: a série retida recebe automaticamente em cada Data de "
    "Pagamento, desde que as Razões de Cobertura estejam enquadradas, e ao final recebe todo o "
    "remanescente do patrimônio separado a título de Prêmio Final. A trava é a cobertura, não a "
    "governança. A exceção documentada é a debênture, em que a 2ª série é integralmente subordinada "
    "à 1ª e não recebeu nada até julho de 2026."
)

# ============================================================ 31_Preço de aquisição
PRECO_COLS = ["veiculo_id", "instrumento", "mecanismo_de_preco", "teto_contratual",
              "preco_efetivamente_praticado", "quem_define", "fonte_id", "status"]
PRECO = [
    ("CRI-VI", "CRI",
     "Valor presente das parcelas vincendas, descontadas pela Taxa de Retorno em base 252 dias úteis, "
     "conforme fórmula do Termo de Securitização",
     "O valor bruto da fórmula é o máximo; a elegibilidade exige Taxa de Retorno igual ou superior à "
     "Taxa Média Mínima de Retorno, o que fixa o preço máximo por baixo da taxa mínima",
     NAO_DISP + " - o preço de cada cessão é evidenciado em cada Termo de Cessão, que não é público",
     "Emissora, evidenciado em cada Termo de Cessão", "ANX-TS-V177", "Documentado - mecanismo; preço realizado não disponível"),
    ("CRI-I", "CRI", "Preço de Aquisição definido no Contrato de Cessão",
     "Taxa Média Mínima de Retorno de 21,5% a.a. como piso da taxa de desconto",
     NAO_DISP, "Emissora", "ANX-PRO-K1", "Documentado - piso de taxa; preço realizado não disponível"),
    ("CRI-II", "CRI", "Preço de Aquisição definido no Contrato de Cessão",
     "Taxa Média Mínima de Retorno de 21,0% a.a. como piso da taxa de desconto",
     NAO_DISP, "Emissora", "ANX-PRO-K2", "Documentado - piso de taxa; preço realizado não disponível"),
    ("CRI-III", "CRI", "Preço de Aquisição definido no Contrato de Cessão",
     "Elegibilidade exige Taxa de Retorno igual ou superior à Taxa Média Mínima de Retorno; o percentual não consta da lâmina",
     NAO_DISP, "Emissora", "ANX-LAM-K3", "Documentado - regra; parâmetro e preço não disponíveis"),
    ("CRI-IV", "CRI", NAO_DISP, NAO_DISP, NAO_DISP, ND, "ANX-DECK", "não disponível"),
    ("CRI-V", "CRI", "Preço de Aquisição definido no Contrato de Cessão",
     "Elegibilidade exige Taxa de Retorno igual ou superior à Taxa Média Mínima de Retorno, medida sobre o valor presente da cessão",
     NAO_DISP, "Emissora", "ANX-LAM-V174", "Documentado - regra; parâmetro e preço não disponíveis"),
    ("FIDC-VI", "FIDC", "Percentual do saldo contábil do direito creditório", "Máximo de 101% do saldo contábil",
     NAO_DISP, "Gestora, que testa a elegibilidade", "ANX-DECK", "Documentado - teto; preço realizado não disponível"),
    ("FIDC-VII", "FIDC", "Percentual do saldo contábil do direito creditório", "Máximo de 104% do saldo contábil",
     NAO_DISP, "Endossantes e originador atestam a condição", "ANX-DECK", "Documentado - teto; preço realizado não disponível"),
    ("FIDC-I", "FIDC", "Percentual do saldo contábil", "Máximo de 100,4% do saldo contábil", NAO_DISP, "Gestor",
     "ANX-DECK", "Documentado - teto; preço realizado não disponível"),
    ("FIDC-II", "FIDC", "Percentual do saldo contábil", "Máximo de 100,5% do saldo contábil", NAO_DISP, "Gestor",
     "ANX-DECK", "Documentado - teto; preço realizado não disponível"),
    ("FIDC-V", "FIDC", "Percentual do saldo contábil", "Máximo de 100,5% do saldo contábil", NAO_DISP, "Gestor",
     "ANX-DECK", "Documentado - teto; preço realizado não disponível"),
    ("DEB-I", "Debênture", "Aquisição de CCBs com os recursos da emissão", NAO_DISP,
     "Valor de aquisição acumulado de R$ 17.212.382,98 para 499 créditos, igual ao valor nominal total adquirido - ou seja, aquisição ao par",
     "Emissora", "ANX-RMA-DEB", "Documentado"),
]

NOTA_PRECO = (
    "Os dois lados do programa precificam de formas diferentes. O FIDC compra por percentual do saldo "
    "contábil, com teto que subiu de 100,4% no fundo I para 104% no fundo VII. O CRI compra por valor "
    "presente descontado a uma taxa, e o que o contrato limita não é o percentual, e sim a taxa mínima "
    "de desconto - quanto maior a taxa exigida, menor o preço pago. O preço efetivamente praticado em "
    "cada cessão é evidenciado no respectivo Termo de Cessão, que não é público em nenhuma das seis "
    "operações. A única aquisição com preço observável é a da debênture, ao par."
)


# ============================================================ 32_Mismatch e prazo sugerido
MISMATCH_COLS = ["veiculo_id", "camada_senior", "duration_dias", "duration_meses",
                 "vencimento_legal", "prazo_legal_meses", "wam_max_pool_meses",
                 "prazo_max_recebivel_meses", "gap_ativo_vs_duration_meses",
                 "regime_muda_em", "prazo_sugerido_de_exposicao", "racional", "fonte_id", "status"]

_MM = [
    ("CRI-I", "Super Sênior (1ª série)", 1246, "2031-01-15", 84),
    ("CRI-III", "Super Sênior A (1ª série)", 1806, "2030-05-08", 60),
    ("CRI-V", "Super Sênior A (1ª série)", 659, "2031-05-20", 60),
]
MISMATCH = []
for vid, camada, dur, venc, legal in _MM:
    dm = dur / 30.4375
    MISMATCH.append([
        vid, camada, str(dur), f"{dm:.1f}", venc, str(legal), "65,7", "126,3",
        f"{126.3 - dm:.1f}", "Mês 48 - regime passa a sequencial",
        f"{legal} meses, até {venc}",
        "A duration é cenário-base, não teto: a lâmina só admite que ela encurte por amortização "
        "extraordinária, mas a amortização de toda série é condicionada a 'caso exista disponibilidade' "
        "e ao Saldo Devedor Target, de modo que um pool com performance abaixo do previsto alonga o "
        "recebimento. O prazo de aprovação deve cobrir o vencimento legal.",
        "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-TS2-K2", "Inferido - método declarado em 18_Metodologia"])

NOTA_MISMATCH = (
    "Há descasamento em três níveis e ele não é uniforme. O ativo individual pode ir a 126 meses e a "
    "média ponderada do pool a 66; a série sênior tem vencimento legal de 60 a 84 meses e duration "
    "de 22 a 59 meses. O gap entre o prazo máximo do recebível e a duration da sênior vai de 67 a "
    "104 meses conforme a operação. Quem absorve esse gap é a estrutura: o recebível longo continua "
    "no patrimônio separado depois que a sênior foi resgatada, e o que sustenta o resgate no prazo é "
    "a amortização do pool, não o vencimento dele."
)

PRAZO_SUGERIDO_NOTA = (
    "Recomendação de prazo de aprovação para exposição à cota sênior: dimensionar pelo vencimento "
    "legal da série, não pela duration. A duration divulgada é estimativa de cenário-base e as "
    "lâminas só a qualificam para baixo; o risco de extensão, porém, existe e está no próprio "
    "contrato - toda amortização é condicionada à disponibilidade de caixa e ao Saldo Devedor Target, "
    "e no mês 48 o regime vira sequencial. Um limite aprovado pela duration ficaria vencido antes do "
    "papel em qualquer cenário de performance abaixo do previsto. Esta é uma leitura de estrutura "
    "para o comitê, não recomendação de investimento."
)

# ============================================================ 33_Histórico de saques da subordinada
HISTORICO_COLS = ["veiculo_id", "instrumento", "camada", "primeira_ocorrencia", "ultima_ocorrencia",
                  "meses_com_pagamento", "total_amortizado_Rmi", "maximo_mensal_Rmi",
                  "respeitou_o_regulamento", "fonte_id"]
_VERIF = "não disponível - exige o demonstrativo dos testes na data de cada amortização"
HISTORICO = [
    ("FIDC-I", "FIDC", "Subordinado Jr.", "2022-02-28", "2026-07-31", "41", "45.3", "2.1", _VERIF, "ANX-DECK"),
    ("FIDC-I", "FIDC", "Mezanino", "2024-01-31", "2026-07-31", "28", "85.1", "7.4", _VERIF, "ANX-DECK"),
    ("FIDC-II", "FIDC", "Subordinado Jr.", "2022-08-31", "2026-02-28", "20", "118.8", "13.8", _VERIF, "ANX-DECK"),
    ("FIDC-II", "FIDC", "Mezanino", "2023-12-31", "2026-04-30", "19", "42.0", "19.1", _VERIF, "ANX-DECK"),
    ("FIDC-III", "FIDC", "Subordinado Jr.", "2025-01-31", "2026-07-31", "18", "26.0", "3.2", _VERIF, "ANX-DECK"),
    ("FIDC-III", "FIDC", "Mezanino", "2024-04-30", "2026-07-31", "25", "75.4", "5.2", _VERIF, "ANX-DECK"),
    ("FIDC-IV", "FIDC", "Subordinado Jr.", "2022-07-31", "2025-11-30", "21", "159.4", "86.7",
     "não disponível - a regra de saque do fundo IV está registrada como incompleta no acervo público", "ANX-DECK"),
    ("FIDC-IV", "FIDC", "Mezanino", "2023-12-31", "2025-08-31", "12", "279.5", "151.4",
     "não disponível - a regra de saque do fundo IV está registrada como incompleta no acervo público", "ANX-DECK"),
    ("FIDC-V", "FIDC", "Subordinado Jr.", "2023-03-31", "2026-02-28", "6", "11.6", "3.4", _VERIF, "ANX-DECK"),
    ("FIDC-V", "FIDC", "Mezanino", "2023-12-31", "2026-07-31", "26", "22.8", "6.0", _VERIF, "ANX-DECK"),
    ("FIDC-VI", "FIDC", "Subordinado Jr.", "2025-12-31", "2026-06-30", "2", "35.2", "29.0", _VERIF, "ANX-DECK"),
    ("FIDC-VI", "FIDC", "Mezanino", "2025-03-31", "2026-06-30", "15", "148.1", "111.4", _VERIF, "ANX-DECK"),
    ("FIDC-VII", "FIDC", "Subordinado Jr.", "2026-07-31", "2026-07-31", "1", "7.7", "7.7", _VERIF, "ANX-DECK"),
    ("CRI-I", "CRI", "Subordinado", "2025-07-01", "2026-06-01", "12", "22.5", "7.4", _VERIF, "ANX-DECK"),
    ("CRI-II", "CRI", "Subordinado", "2025-09-01", "2026-05-01", "9", "7.8", "2.6", _VERIF, "ANX-DECK"),
    ("CRI-II", "CRI", "Subordinado Jr.", "2025-10-01", "2026-05-01", "8", "6.8", "1.4", _VERIF, "ANX-DECK"),
    ("CRI-III", "CRI", "Subordinado", "2026-02-01", "2026-05-01", "4", "8.3", "3.2", _VERIF, "ANX-DECK"),
    ("DEB-I", "Debênture", "2ª série subordinada", "n/a", "n/a", "0", "0.0", "0.0",
     "Sim - o relatório mensal registra R$ 0,00 distribuídos aos investidores da 2ª série em 31/07/2026, consistente com a subordinação integral da cl. 3.3.2",
     "ANX-RMA-DEB; ANX-ESC-DEB"),
]

NOTA_HISTORICO = (
    "Já ocorreu em todos os sete FIDCs e em três das seis operações de CRI. O maior volume é o do "
    "FIDC IV - R$ 438,9 mi somando mezanino e júnior, com um único mês de R$ 151,4 mi - e é também "
    "o fundo que hoje está sem first loss. Se cada saída respeitou o regulamento é a pergunta que os "
    "documentos do acervo não respondem: o informe mensal comprova o pagamento, mas o teste de "
    "subordinação e de cobertura na data de cada amortização não é publicado. É o item de diligência "
    "com maior assimetria entre o que se observa e o que se pode afirmar."
)

# ============================================================ 34_Pontos em aberto
ABERTO_COLS = ["prioridade", "pergunta_do_comite", "o_que_falta", "onde_obter", "impacto_na_decisao"]
ABERTO = [
    ("1", "Qual o preço efetivamente pago em cada cessão?",
     "Termos de Cessão de todas as operações; o mecanismo é documentado, o preço realizado não",
     "Solfácil, securitizadoras e gestoras dos FIDCs",
     "Sem ele não há como medir ágio, deságio nem o ganho econômico do take-out"),
    ("2", "As saídas de subordinada respeitaram os testes em cada competência?",
     "Demonstrativos de subordinação, cobertura e reservas na data de cada amortização",
     "Administradores dos FIDCs e emissoras dos CRIs",
     "R$ 1,06 bi já saíram dos fundos; a aderência contratual não é verificável com o informe mensal"),
    ("3", "Quais os termos das quatro operações de CRI sem Termo de Securitização no acervo?",
     "Termos de Securitização da 1ª, 3ª e 4ª Kanastra e da 174ª VERT",
     "CVM Fundos.NET; documentos.kanastra.com.br; data.vert-capital.app",
     "Cascata, gatilhos numéricos e regra da subordinada de quatro das seis operações são inferidos"),
    ("4", "Quais os critérios literais de elegibilidade de cada FIDC?",
     "Regulamentos vigentes dos sete fundos e suplementos de classe", "CVM Fundos.NET",
     "O ranking de permissividade usa parâmetros da análise de crédito, não a redação dos regulamentos"),
    ("5", "Qual o WAM observado e a performance por safra de cada pool?",
     "Tape de CCBs com originação, score, parcelas, pré-pagamento e recuperação",
     "Solfácil, como originadora e agente de cobrança",
     "Só existe o teto contratual de WAM; o descasamento observado não é mensurável"),
    ("6", "O FIDC IV pode voltar a ter first loss?",
     "Regulamento do FIDC IV e memória das amortizações de R$ 438,9 mi",
     "Administrador do fundo (Banco Genial)",
     "É o veículo mais permissivo do programa e hoje está sem camada de absorção de perda"),
    ("7", "Qual o custo all-in de cada estrutura na mesma régua?",
     "Curva DI futura da B3 e inflação implícita das NTN-B em cada data-base de emissão",
     "B3 e ANBIMA",
     "Quatro das seis operações têm séries pré-fixadas; sem a curva não há comparação entre famílias"),
    ("8", "Qual a exposição corrente por titular?",
     "Posição de titulares por ISIN", "B3 e Oliveira Trust, como escriturador",
     "A distribuição inicial é conhecida; a concentração de hoje não"),
    ("9", "Quanto da queda de PL do FIDC VI em julho de 2026 foi cessão?",
     "Memória contábil da competência", "Administrador do FIDC VI",
     "O PL caiu R$ 226,3 mi sem decomposição entre cessão, ajuste de valor e distribuição"),
    ("10", "Existem outras operações de debênture além da Amazônia Solar?",
     "Escritura e relatórios das debêntures SFCL11, SFCL21, SFCL31 e SFCL41",
     "Solfácil, agente fiduciário e B3",
     "A análise de crédito as dimensiona em R$ 150 mi, mas não há documento no acervo"),
]
