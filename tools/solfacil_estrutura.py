# -*- coding: utf-8 -*-
"""Waterfall, subordinada, PDD, eventos e garantias."""

ND = "n/d"

# ============================================================ 06_Waterfall
WATERFALL_COLS = [
    "veiculo_id", "nome_contratual", "regime", "gatilho_de_mudanca_para_sequencial",
    "quem_recebe_juros_antes_de_principal", "super_senior_prioridade", "senior_prioridade",
    "mezanino_prioridade", "subordinado_prioridade", "subordinado_jr_prioridade",
    "cash_sweep", "reserva_de_despesas", "reserva_de_juros", "reserva_MTM",
    "reserva_para_resgate_antecipado", "condicionalidade", "fonte_id", "status",
]

WATERFALL = [
    ("CRI-II", "Ordem de Alocacao de Recursos (cl. 6.5 do Termo de Securitizacao)",
     "Pro rata condicionado por Razoes de Cobertura ate o mes 47; sequencial a partir do mes 48 ou por Evento de Desalavancagem",
     "Mes 48 (inclusive) ou ocorrencia de Evento de Desalavancagem",
     "Sim - em cada camada, Remuneracao e paga antes da Amortizacao da mesma camada",
     "1 (sem condicao de cobertura)", "2 (exige Razao de Cobertura Super Senior enquadrada)",
     "3 (exige Cobertura Super Senior e Senior)", "4 (exige Cobertura Super Senior, Senior e Mezanino)",
     "5 (exige as quatro Razoes de Cobertura e saldo acima do Target); recebe o Premio Final apos o resgate das quatro series publicas",
     "Sim - item (aa): amortizacao extraordinaria proporcional entre as series com Razao de Cobertura enquadrada",
     "Sim - item (b)", "Sim - Encargos Moratorios e Remuneracao vencida e nao paga tem prioridade sobre a amortizacao",
     ND, "Sim - constituida a partir de 98% amortizado, por serie",
     "Toda amortizacao e condicionada a 'caso exista disponibilidade' e ao limite do caixa disponivel",
     "ANX-TS2-K2", "Documentado"),

    ("CRI-I", "Ordem de Alocacao de Recursos (Termo de Securitizacao)",
     "Targets por camada (54/15/18/5/8 segundo o deck); sequencial em eventos", ND,
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, ND,
     "Amortizacao condicionada a disponibilidade e a Ordem de Alocacao de Recursos",
     "ANX-DECK; ANX-PRO-K1", "Documentado"),

    ("CRI-III", "Ordem de Alocacao de Recursos (Termo de Securitizacao)",
     "Pro rata condicionado ate o mes 47; sequencial a partir do mes 48", "Mes 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, "Sim - Resgate Antecipado Obrigatorio previsto",
     "Amortizacao condicionada a disponibilidade e a Ordem de Alocacao de Recursos; cronograma no Anexo I",
     "ANX-LAM-K3; ANX-DECK", "Documentado"),

    ("CRI-IV", "Ordem de Alocacao de Recursos (Termo de Securitizacao)",
     "Pro rata condicionado ate o mes 47; sequencial a partir do mes 48", "Mes 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, ND,
     "Amortizacao condicionada a disponibilidade e a Ordem de Alocacao de Recursos",
     "ANX-DECK", "Documentado"),

    ("CRI-V", "Ordem de Alocacao de Recursos (Termo de Securitizacao)",
     "Pro rata condicionado ate o mes 47; sequencial a partir do mes 48", "Mes 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND,
     "Sim - resgate compulsorio quando 98% do VNU amortizado e ha recursos suficientes",
     "'Ressalvadas as hipoteses de Resgate Antecipado Obrigatorio, caso exista disponibilidade, o saldo do Valor Nominal Unitario sera amortizado nas Datas de Pagamento indicadas no cronograma do Anexo I, observadas as regras da Ordem de Alocacao de Recursos' - redacao repetida para as cinco series",
     "ANX-LAM-V174", "Documentado"),

    ("CRI-VI", "Ordem de Alocacao de Recursos (Termo de Securitizacao)",
     "Pro rata condicionado ate o mes 47; sequencial a partir do mes 48", "Mes 48 ou eventos",
     ND, "1", "2", "3", "4", "5", ND, ND, ND, ND, ND,
     "Amortizacao condicionada a disponibilidade", "ANX-DECK", "Documentado"),

    ("FIDC-I", "Ordem de aplicacao de recursos do regulamento", "Hibrido por metas",
     "Liquidacao e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-II", "Ordem de aplicacao de recursos do regulamento", "Metas ate o mes 59",
     "Mes 60 e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-III", "Ordem de aplicacao de recursos do regulamento", "Pro rata ate o mes 47",
     "Mes 48 e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Ordem de aplicacao de recursos do regulamento", "Prioridade por classe",
     "Eventos e liquidacao", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Regra publica incompleta no acervo", "ANX-DECK", "Documentado"),
    ("FIDC-V", "Ordem de aplicacao de recursos do regulamento", "Metas por classe",
     "Eventos e liquidacao", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Ordem de aplicacao de recursos do regulamento", "Pro rata condicionado",
     "Eventos; 6 datas sequenciais aceleram ate aceleracao definitiva", ND,
     "1", "n/a", "2 (Mezz A) e 3 (Mezz B)", "n/a", "4", ND, ND, ND,
     "Sim - reserva de MTM prevista", ND,
     "Junior recebe apenas por amortizacao extraordinaria e sob testes", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Ordem de aplicacao de recursos do regulamento",
     "Revolvencia obrigatoria de 12 meses; pro rata condicionado depois",
     "Eventos; 6 datas sequenciais aceleram ate aceleracao definitiva", ND,
     "1", "n/a", "2 (Mezz A) e 3 (Mezz B)", "n/a", "4", ND, ND, ND,
     "Sim - reserva previa de MTM; venda vedada se o MTM superar a junior", ND,
     "Junior recebe apenas por amortizacao extraordinaria, sob testes e com trava de 3 meses apos Evento de Venda",
     "ANX-DECK", "Documentado"),
]

# Degraus literais da Ordem de Alocacao de Recursos de CRI-II (unica integralmente documentada)
WATERFALL_DEGRAUS_COLS = ["veiculo_id", "regime", "ordem", "item_contratual", "descricao", "fonte_id"]
WATERFALL_DEGRAUS = [
    ("CRI-II", "Pro rata", 1, "(a)", "Pagamento de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 2, "(b)", "Composicao da Reserva de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 3, "(c)-(d)", "Encargos moratorios e remuneracao vencida e nao paga da 1a serie (Super Senior)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 4, "(e)", "Remuneracao da 1a serie (Super Senior)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 5, "(f)", "Amortizacao da 1a serie: o maior entre o Anexo I e o necessario para atingir o Saldo Devedor Target; ou resgate se saldo <= 2%", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 6, "(g)", "Reserva para Resgate Antecipado da 1a serie, a partir de 98% amortizado", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 7, "(h)-(i)", "Encargos moratorios e remuneracao vencida e nao paga da 2a serie (Senior)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 8, "(j)", "Remuneracao da 2a serie, se a Razao de Cobertura Super Senior estiver enquadrada", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 9, "(k)", "Amortizacao da 2a serie ate o Target, se a Razao de Cobertura Super Senior estiver enquadrada", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 10, "(l)", "Reserva para Resgate Antecipado da 2a serie", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 11, "(m)-(n)", "Encargos moratorios e remuneracao vencida e nao paga da 3a serie (Mezanino)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 12, "(o)", "Remuneracao da 3a serie, se as Coberturas Super Senior e Senior estiverem enquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 13, "(p)", "Amortizacao da 3a serie ate o Target, sob as mesmas duas coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 14, "(q)", "Reserva para Resgate Antecipado da 3a serie", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 15, "(r)-(s)", "Encargos moratorios e remuneracao vencida e nao paga da 4a serie (Subordinado)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 16, "(t)", "Remuneracao da 4a serie, se as Coberturas Super Senior, Senior e Mezanino estiverem enquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 17, "(u)", "Amortizacao da 4a serie ate o Target, sob as mesmas tres coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 18, "(v)", "Reserva para Resgate Antecipado da 4a serie", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 19, "(w)-(x)", "Encargos moratorios e remuneracao vencida e nao paga da 5a serie (Subordinado Jr., privada)", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 20, "(y)", "Remuneracao da 5a serie, se as quatro Razoes de Cobertura estiverem enquadradas e o saldo estiver acima do Target", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 21, "(z)", "Amortizacao da 5a serie ate o Target, sob as mesmas quatro coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 22, "(aa)", "Amortizacao extraordinaria proporcional entre as series com cobertura enquadrada, excluidas as desenquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 23, "(bb)", "Premio Final: todo o valor remanescente do Patrimonio Separado vai a 5a serie, apos o resgate das quatro series publicas", "ANX-TS2-K2"),
    ("CRI-II", "Pro rata", 24, "(cc)", "Alocacao em Investimentos Permitidos", "ANX-TS2-K2"),

    ("CRI-II", "Sequencial", 1, "(a)-(b)", "Despesas e Reserva de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 2, "(c)-(e)", "Encargos, remuneracao vencida e remuneracao corrente da 1a serie", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 3, "(f)-(g)", "Amortizacao da 1a serie ate 98% do VNU e reserva de resgate - sem condicao de cobertura e sem Target", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 4, "(h)-(l)", "2a serie: encargos, remuneracao, amortizacao ate 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 5, "(m)-(q)", "3a serie: encargos, remuneracao, amortizacao ate 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 6, "(r)-(v)", "4a serie: encargos, remuneracao, amortizacao ate 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 7, "(w)-(y)", "5a serie: remuneracao vencida, remuneracao corrente e amortizacao", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 8, "(z)", "Premio Final a 5a serie apos o resgate das quatro series publicas", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 9, "(aa)", "Alocacao em Investimentos Permitidos", "ANX-TS2-K2"),
]

NOTA_WATERFALL = (
    "O regime chamado de pro rata nao paga as camadas em paralelo: cada camada so recebe se as Razoes "
    "de Cobertura de todas as camadas acima estiverem enquadradas, e recebe ate um Saldo Devedor Target, "
    "nao ate o cronograma. O cronograma do Anexo I e alvo, nao promessa - toda amortizacao esta "
    "condicionada a 'caso exista disponibilidade'."
)

# ============================================================ 07_Subordinada
SUBORDINADA_COLS = [
    "veiculo_id", "saque_permitido", "quem_solicita", "quem_autoriza", "quorum",
    "testes_exigidos", "pisos_de_subordinacao_pct", "indices_de_cobertura", "trava_temporal",
    "vedacoes_pos_evento", "principal_subordinado_ja_pago_Rmi", "primeira_ocorrencia",
    "ultima_ocorrencia", "subordinacao_antes_do_saque_pct", "subordinacao_depois_pct",
    "variacao_pp", "impacto_na_senior", "data_base", "fonte_id", "status",
]

SUBORDINADA = [
    ("FIDC-I", "Sim", "Cotista subordinado", "Administrador", ND,
     "Pisos, cobertura e ausencia de evento", "25", ND, "Limites do regulamento vigente", ND,
     "130.4", "2022-02-28", "2026-07-31", ND, ND, ND,
     "Attachment atual da senior: 39,3% da carteira (mezanino + junior sobre DC)", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-II", "Sim", "Cotista subordinado", "Administrador", ND,
     "Metas, indices e liquidez pro forma", "20", ND, "Antes do sequencial, se enquadrado", ND,
     "160.8", "2022-08-31", "2026-04-30", ND, ND, ND,
     "Attachment atual da senior: 24,9% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-III", "Sim", "Cotista subordinado", "Administrador", ND,
     "Subordinacao, cobertura e ausencia de evento", "25", ND, "Pro rata vigente", ND,
     "101.4", "2025-01-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da senior: 35,6% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Sim", ND, ND, ND, "Condicao detalhada n/d no acervo", "Sem piso", ND, ND, ND,
     "438.9", "2022-07-31", "2025-11-30", ND, ND, ND,
     "Attachment atual da senior: 0,0% - o fundo esta sem first loss", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-V", "Sim", "Cotista subordinado", "Administrador", ND,
     "Indices, caixa e ausencia de evento", "20", ND, "Limites do regulamento vigente", ND,
     "34.4", "2023-03-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da senior: 21,2% da carteira; folga de 0,9 p.p. ao piso", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Sim", "Titulares de 75% da junior", "Administrador", "75% da classe junior",
     "Subordinacao e cobertura pro forma; reserva de MTM; ausencia de eventos", "25",
     "Patamares de 136,0% / 113,3% / 106,3%", "Nao ha trava pos-venda equivalente a do VII", ND,
     "183.2", "2025-12-31", "2026-06-30", ND, ND, ND,
     "Attachment atual da senior: 48,1% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Sim", "Titulares de 75% da junior", "Administrador", "75% da classe junior",
     "Mesmos testes do VI: subordinacao e cobertura pro forma, reserva de MTM e ausencia de eventos", "25",
     "Patamares de 136,0% / 113,3% / 106,3%", "3 meses apos Evento de Venda",
     "Venda vedada se o MTM superar a junior", "7.7", "2026-07-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da senior: 36,1% da carteira; folga de 1,0 p.p. ao piso", "2026-07-31", "ANX-DECK", "Documentado"),

    ("CRI-II", "Sim, mas apenas ate o Saldo Devedor Target e sob as quatro Razoes de Cobertura",
     "n/a - nao ha pedido; e regra automatica da Ordem de Alocacao", "Emissora, na Data de Pagamento",
     "n/a", "Razoes de Cobertura Super Senior, Senior, Mezanino e Subordinada simultaneamente enquadradas, e saldo acima do Target",
     "n/a - a protecao e por Razao de Cobertura, nao por piso percentual",
     "Super Senior 159%; Senior 123%; Mezanino 110%; Subordinada 105%",
     "Carencia prevista no Anexo I: a 5a serie so comeca a receber no 13o pagamento (07/07/2025)",
     "No regime sequencial a 5a serie so recebe depois das quatro series publicas",
     "6.8", "2025-10-01", "2026-05-01", ND, ND, ND,
     "A 5a serie recebe o Premio Final - todo o remanescente do Patrimonio Separado - somente apos o resgate das quatro series publicas",
     "2026-05-01", "ANX-TS2-K2; ANX-DECK", "Documentado"),
    ("CRI-I", "Sim", "n/a - regra automatica", "Emissora", "n/a", ND, ND, ND, ND, ND,
     "22.5 (serie Subordinada publica); Subordinado Jr. n/d", "2025-07-01", "2026-06-01", ND, ND, ND,
     ND, "2026-06-01", "ANX-DECK", "Documentado"),
    ("CRI-III", "Sim", "n/a - regra automatica", "Emissora", "n/a", ND, ND, ND, ND, ND,
     "8.3 (serie Subordinada publica)", "2026-02-01", "2026-05-01", ND, ND, ND, ND,
     "2026-05-01", "ANX-DECK", "Documentado"),
    ("CRI-IV", ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, "2026-05-01", "ANX-DECK", "Documentado"),
    ("CRI-V", "Sim", "n/a - regra automatica", "Emissora", "n/a", ND, ND, ND, ND, ND,
     ND, ND, ND, ND, ND, ND, "Sem amortizacao observada ate a data-base", "2026-08-21", "ANX-DECK", "Documentado"),
    ("CRI-VI", ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND,
     "Sem informe mensal ate a data-base", "2026-08-21", "ANX-DECK", "Documentado"),
]

NOTA_SUBORDINADA = (
    "Nos sete FIDCs a subordinada ja recebeu principal - somam R$ 1,06 bi de mezanino e junior. "
    "Nos CRIs a saida da camada junior nao depende de pedido nem de quorum: e automatica, mas so "
    "ocorre se as quatro Razoes de Cobertura estiverem enquadradas na Data de Pagamento. "
    "A subordinacao antes e depois de cada saque exige o demonstrativo de cada competencia, que nao e publico."
)


# ============================================================ 08_PDD
PDD_COLS = [
    "veiculo_id", "metrica", "ate_15d", "d16_30", "d31_60", "d61_90", "d91_120",
    "d121_150", "d151_180", "acima_180d", "base_de_incidencia", "efeito_vagao",
    "tratamento_do_dia_181", "pdd_adicional_discricionaria", "pdd_observada_pct_carteira",
    "saldo_90d_pct_carteira", "razao_pdd_sobre_90d", "curva", "data_base", "fonte_id", "status",
]

_BASE_VP = ("Valor presente do Direito Creditorio (saldo remanescente da CCB), nao apenas a parcela vencida")
_VAGAO_SIM = ("Sim - definido em contrato como o arrasto da pior classificacao de atraso entre todas as "
              "CCBs de um mesmo devedor, esteja o titulo vencido ou a vencer")

PDD = [
    ("CRI-I", "PDD contabil por faixa de atraso", "0,00", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, _VAGAO_SIM,
     "Provisao integral acima de 180 dias", ND, ND, ND, ND, "Inicial", "2024-01-15",
     "ANX-PRO-K1", "Documentado"),
    ("CRI-II", "PDD contabil por faixa de atraso", "0,00", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, _VAGAO_SIM,
     "Provisao integral acima de 180 dias", ND, ND, ND, ND, "Inicial", "2024-06-25",
     "ANX-PRO-K2", "Documentado"),
    ("CRI-III", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisao integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2025-05-28", "ANX-DECK", "Documentado"),
    ("CRI-IV", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisao integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2025-09-28", "ANX-DECK", "Documentado"),
    ("CRI-V", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisao integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2026-05-20", "ANX-DECK", "Documentado"),
    ("CRI-VI", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisao integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2026-07-21", "ANX-DECK", "Documentado"),

    ("FIDC-I", "PDD contabil por faixa de atraso", ND, ND, ND, ND, ND, ND, ND, ND,
     "Tabela especifica nao publica", ND, ND, ND, "6,8", "1,3", "527", ND, "2026-07-31",
     "ANX-DECK", "Documentado"),
    ("FIDC-II", "PDD contabil por faixa de atraso", "0,00", "2,00", "6,00", "20,00", "100,00",
     "100,00", "100,00", "100,00", _BASE_VP, ND, "Provisao integral ja a partir de 91 dias",
     ND, "0,0", "2,1", "0", "Salto integral acima de 90 dias", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-III", "PDD contabil por faixa de atraso", ND, ND, ND, ND, ND, ND, ND, ND,
     "Tabela especifica nao publica", ND, ND, ND, "5,7", "1,2", "469", ND, "2026-07-31",
     "ANX-DECK", "Documentado"),
    ("FIDC-IV", "PDD contabil por faixa de atraso", "0,50", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, ND, "Provisao integral acima de 180 dias", ND,
     "69,9", "12,7", "550", "Inicial", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-V", "PDD contabil por faixa de atraso", "0,50", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, ND, "Provisao integral acima de 180 dias", ND,
     "9,3", "1,7", "546", "Inicial; lacunas na tabela publica", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, ND,
     "Lacuna literal no dia 181: a tabela salta de '151-180' para 'acima de 181'", ND,
     "48,8", "8,4", "581", "Posterior", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "PDD contabil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, ND,
     "Lacuna literal no dia 181, igual a do VI", ND,
     "0,2", "0,0", "3.725", "Posterior", "2026-07-31", "ANX-DECK", "Documentado"),

    # Metrica distinta: inadimplencia por safra (denominador diferente - nao misturar com a PDD contabil)
    ("CRI-III", "Inadimplencia por safra (perda bruta e liquida)", ND, ND, ND, ND, ND, ND, ND, ND,
     "Somatorio dos saldos devedores dos contratos com atraso > 90 dias dividido pelo total originado na safra",
     "n/a - metrica de safra, nao de provisao", "n/a", ND, ND, ND, ND,
     "Perda bruta e perda liquida; a diferenca entre as duas sao as recuperacoes (pagamentos e renegociacoes apos 90 dias)",
     "2025-04-22", "ANX-LAM-K3", "Documentado"),
    ("CRI-V", "Inadimplencia por safra (perda bruta e liquida)", ND, ND, ND, ND, ND, ND, ND, ND,
     "Somatorio dos saldos devedores dos contratos com atraso > 90 dias dividido pelo total originado na safra",
     "n/a - metrica de safra, nao de provisao", "n/a", ND, ND, ND, ND,
     "Perda bruta e perda liquida; o Prospecto traz a tabela de perda liquida consolidada de operacoes pre-fixadas",
     "2026-04-17", "ANX-LAM-V174", "Documentado"),
]

NOTA_PDD = (
    "A provisao incide sobre o valor presente do recebivel - o saldo que resta da CCB - e nao sobre a "
    "parcela vencida, e o contrato ainda determina o Efeito Vagao, que arrasta a pior faixa de atraso de "
    "um devedor para todas as CCBs dele. Sao esses dois mecanismos que explicam razoes PDD/>90d muito "
    "acima de 100%. A inadimplencia por safra tem outro denominador (o total originado na safra) e nao "
    "deve ser comparada com a PDD contabil."
)

# ============================================================ 09_Eventos
EVENTOS_COLS = [
    "veiculo_id", "tipo", "descricao_do_gatilho", "parametro_numerico",
    "consequencia_automatica", "quorum_de_dispensa", "prazo_de_cura",
    "ja_ocorreu", "data_da_ocorrencia", "fonte_id", "status",
]

EVENTOS = [
    ("CRI-II", "Desalavancagem", "Indice de Atraso de Estoque desenquadrado em 3 Datas de Verificacao consecutivas",
     "Indice de Atraso de Estoque nao pode superar 15%", "Regime muda de pro rata para Amortizacao Sequencial",
     "Assembleia Especial de Titulares de CRI", ND, "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Rebaixamento de rating dos CRI Super Senior e/ou Senior",
     "Queda de 2 niveis abaixo da classificacao originalmente atribuida", "Amortizacao Sequencial",
     "Assembleia Especial de Titulares de CRI", ND, "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Nao pagamento de remuneracao ou amortizacao da 1a serie prevista no Anexo I",
     "n/a", "Amortizacao Sequencial", ND, "5 Dias Uteis contados da Data de Pagamento, observada a carencia",
     "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Nao divulgacao do Relatorio da Emissao no prazo",
     "n/a", "Amortizacao Sequencial", ND, ND, "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Desenquadramento das Razoes de Cobertura",
     "2 Datas de Pagamento consecutivas ou 4 alternadas nos 12 meses anteriores", "Amortizacao Sequencial",
     ND, ND, "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Amortizacao Sequencial por prazo", "Alcance do mes 48 da operacao",
     "Mes 48 (inclusive)", "Amortizacao Sequencial permanente ate Evento de Realavancagem", ND, ND,
     "Nao", "Prevista para 2028", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Realavancagem", "Reenquadramento do Indice de Atraso de Estoque",
     "3 Datas de Verificacao consecutivas dentro do limite", "Retorno ao regime pro rata", ND, ND,
     "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Realavancagem", "Regularizacao do pagamento da 1a serie",
     "Pagamento regular em 3 Datas de Verificacao consecutivas; se o evento persistir por 6 meses consecutivos a operacao fica em sequencial permanente",
     "Retorno ao regime pro rata, salvo o caso de 6 meses", "Assembleia Especial para retomar o pro rata", ND,
     "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Resgate Antecipado Obrigatorio", "Saldo do VNU da serie igual ou inferior a 2% e recursos suficientes",
     "2% do Valor Nominal Unitario", "Resgate integral da serie", ND, ND, "Nao", "n/a",
     "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Substituicao do Agente de Cobranca",
     "Eventos Materiais Solfacil; impedimento de atuar; descumprimento do Contrato Operacional; resilicao; condenacao na Lei 12.846; crime contra a administracao publica",
     "n/a", "Emissora assume como Backup Servicer e convoca Assembleia Especial",
     "Assembleia Especial de Titulares de CRI", "Prazo de cura especifico do Contrato Operacional",
     "Nao", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Recompra Obrigatoria", "Hipoteses do Contrato de Cessao",
     "n/a", "Recompra ou compra dos Direitos Creditorios pelos Cedentes, Endossantes Iniciais, Solfacil ou Comprador Indicado",
     ND, ND, "n/d", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Vencimento Antecipado", "Nao aplicavel", "n/a", "n/a", "n/a", "n/a",
     "n/a", "n/a", "ANX-TS2-K2", "Documentado: nao aplicavel"),

    ("CRI-V", "Resgate Antecipado Compulsorio",
     "Cumulativamente: (i) 98% do VNU da serie amortizado e (ii) recursos suficientes para o resgate integral da serie",
     "98% do Valor Nominal Unitario", "Resgate integral da serie na Data de Pagamento", ND, ND,
     "Nao", "n/a", "ANX-LAM-V174", "Documentado"),
    ("CRI-V", "Recompra Obrigatoria",
     "Hipoteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfacil previstas no Contrato de Cessao",
     "n/a", "Recompra dos Direitos Creditorios Cedidos", ND, ND, "n/d", "n/a",
     "ANX-LAM-V174", "Documentado"),
    ("CRI-V", "Vencimento Antecipado", "Nao aplicavel - a lamina registra 'N/A' no campo",
     "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "ANX-LAM-V174", "Documentado: nao aplicavel"),

    ("CRI-III", "Resgate Antecipado Obrigatorio",
     "Na Data de Pagamento subsequente a Data de Verificacao Amortizacao e Pagamento, nos termos do Termo de Securitizacao",
     ND, "Resgate da serie", ND, ND, "Nao", "n/a", "ANX-LAM-K3", "Documentado"),
    ("CRI-III", "Recompra Obrigatoria",
     "Hipoteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfacil previstas no Contrato de Cessao",
     "n/a", "Recompra dos Direitos Creditorios Cedidos", ND, ND, "n/d", "n/a", "ANX-LAM-K3", "Documentado"),
    ("CRI-III", "Vencimento Antecipado", "Nao aplicavel - a lamina registra 'N/A' no campo",
     "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "ANX-LAM-K3", "Documentado: nao aplicavel"),

    ("CRI-I", "Recompra Obrigatoria",
     "Hipoteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfacil previstas no Contrato de Cessao",
     "n/a", "Recompra dos Direitos Creditorios Cedidos", ND, ND, "n/d", "n/a", "ANX-LAM-K1", "Documentado"),
    ("CRI-I", "Governanca", "Notificacoes formais registradas em 2026 pelo agente fiduciario, sem evidencia publica de cura",
     "n/a", ND, ND, ND, "Sim", "2026", "ANX-DECK", "Documentado"),

    ("FIDC-VI", "Desalavancagem", "Eventos de desalavancagem do regulamento; 6 datas sequenciais aceleram ate aceleracao definitiva",
     "6 datas", "Regime sequencial", ND, ND, "n/d", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Rating", "Rebaixamento da classificacao de risco", "Queda de 2 ou mais niveis",
     "Evento de desalavancagem", ND, ND, "Nao", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Desalavancagem", "Eventos de desalavancagem do regulamento; 6 datas sequenciais aceleram ate aceleracao definitiva",
     "6 datas", "Regime sequencial", ND, ND, "n/d", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Rating", "Rebaixamento da classificacao de risco", "Queda de 2 ou mais niveis",
     "Evento de desalavancagem", ND, ND, "Nao", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Desinvestimento", "Inicio do periodo de desinvestimento", "Mes 61 ou PL de R$ 100 mi, o que ocorrer primeiro",
     "Inicio do desinvestimento", ND, ND, "Nao", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Revolvencia", "Periodo de reinvestimento obrigatorio", "12 meses",
     "Principal suspenso e saldo reinvestido", ND, ND, "Sim - em curso", "2026-02-06", "ANX-DECK", "Documentado"),
]

# ============================================================ 09b_Garantias
GARANTIAS_COLS = ["veiculo_id", "garantia_no_ambito_do_veiculo", "garantia_sobre_os_direitos_creditorios",
                  "onde_e_contratada", "coobrigacao_do_cedente", "redacao_literal", "fonte_id", "status"]

GARANTIAS = [
    ("CRI-I", "Nao serao constituidas garantias no ambito dos CRI",
     "Alienacao fiduciaria dos Equipamentos (Sistema Solar)",
     "No ambito da respectiva CCB ou em Contrato de Alienacao Fiduciaria de Equipamentos apartado",
     "Cessao sem coobrigacao; o Patrimonio Separado nao conta com garantia ou coobrigacao da Emissora",
     "'Nao serao constituidas garantias no ambito dos CRI diretamente. Nao obstante, os Direitos Creditorios Imobiliarios sao garantidos por alienacao fiduciaria dos Equipamentos'",
     "ANX-LAM-K1", "Documentado"),
    ("CRI-III", "Nao serao constituidas garantias no ambito dos CRI",
     "Alienacao fiduciaria dos Equipamentos", "No ambito da respectiva CCB ou de forma apartada em contrato",
     "Cessao sem coobrigacao", "'Garantia 2: N/A.'", "ANX-LAM-K3", "Documentado"),
    ("CRI-V", "Nao serao constituidas garantias no ambito dos CRI",
     "Alienacao fiduciaria dos Equipamentos", "No ambito da respectiva CCB ou de forma apartada em contrato",
     "Cessao sem coobrigacao - o Contrato de Cessao e 'Sem Coobrigacao'",
     "'Nao serao constituidas garantias no ambito dos CRI diretamente. Nao obstante, os Direitos Creditorios Imobiliarios sao garantidos por alienacao fiduciaria dos Equipamentos, a ser contratada no ambito da respectiva CCB ou de forma apartada em contrato.'",
     "ANX-LAM-V174", "Documentado"),
    ("CRI-II", "Nao serao constituidas garantias no ambito dos CRI",
     "Alienacao fiduciaria dos Equipamentos", "No ambito da respectiva CCB ou de forma apartada",
     "Cessao sem coobrigacao", ND, "ANX-PRO-K2", "Documentado"),
    ("CRI-IV", ND, "Alienacao fiduciaria dos Equipamentos (padrao do programa)", ND, ND, ND,
     "ANX-DECK", "Inferido - padrao repetido em CRI-I, III e V; lamina da 4a emissao ausente do acervo"),
    ("CRI-VI", ND, "Alienacao fiduciaria dos Equipamentos (padrao do programa)", ND, ND, ND,
     "ANX-DECK", "Inferido - padrao repetido em CRI-I, III e V; lamina da 177a ausente do acervo"),
]

NOTA_GARANTIAS = (
    "Nenhum CRI tem garantia constituida no proprio titulo. A garantia real existe uma camada abaixo: "
    "os recebiveis sao garantidos por alienacao fiduciaria do equipamento solar, contratada na propria CCB. "
    "Para o investidor do CRI isso significa que a execucao depende de retomar equipamento instalado em "
    "telhado de terceiro, ativo de valor de revenda incerto - diferente de uma garantia no nivel do veiculo."
)
