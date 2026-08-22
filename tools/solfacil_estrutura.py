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
    ("CRI-II", "Ordem de Alocação de Recursos (cl. 6.5 do Termo de Securitização)",
     "Pró-rata condicionado por Razões de Cobertura até o mês 47; sequencial a partir do mês 48 ou por Evento de Desalavancagem",
     "Mês 48 (inclusive) ou ocorrência de Evento de Desalavancagem",
     "Sim - em cada camada, Remuneração é paga antes da Amortização da mesma camada",
     "1 (sem condição de cobertura)", "2 (exige Razão de Cobertura Super Sênior enquadrada)",
     "3 (exige Cobertura Super Sênior e Sênior)", "4 (exige Cobertura Super Sênior, Sênior e Mezanino)",
     "5 (exige as quatro Razões de Cobertura e saldo acima do Target); recebe o Prêmio Final após o resgate das quatro séries públicas",
     "Sim - item (aa): amortização extraordinária proporcional entre as séries com Razão de Cobertura enquadrada",
     "Sim - item (b)", "Sim - Encargos Moratórios e Remuneração vencida e não paga tem prioridade sobre a amortização",
     ND, "Sim - constituída a partir de 98% amortizado, por série",
     "Toda amortização é condicionada a 'caso exista disponibilidade' e ao limite do caixa disponível",
     "ANX-TS2-K2", "Documentado"),

    ("CRI-I", "Ordem de Alocação de Recursos (Termo de Securitização)",
     "Targets por camada (54/15/18/5/8 segundo o deck); sequencial em eventos", ND,
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, ND,
     "Amortização condicionada a disponibilidade e a Ordem de Alocação de Recursos",
     "ANX-DECK; ANX-PRO-K1", "Documentado"),

    ("CRI-III", "Ordem de Alocação de Recursos (Termo de Securitização)",
     "Pró-rata condicionado até o mês 47; sequencial a partir do mês 48", "Mês 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, "Sim - Resgate Antecipado Obrigatório previsto",
     "Amortização condicionada a disponibilidade e a Ordem de Alocação de Recursos; cronograma no Anexo I",
     "ANX-LAM-K3; ANX-DECK", "Documentado"),

    ("CRI-IV", "Ordem de Alocação de Recursos (Termo de Securitização)",
     "Pró-rata condicionado até o mês 47; sequencial a partir do mês 48", "Mês 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND, ND,
     "Amortização condicionada a disponibilidade e a Ordem de Alocação de Recursos",
     "ANX-DECK", "Documentado"),

    ("CRI-V", "Ordem de Alocação de Recursos (Termo de Securitização)",
     "Pró-rata condicionado até o mês 47; sequencial a partir do mês 48", "Mês 48 ou eventos",
     "Sim", "1", "2", "3", "4", "5", ND, "Sim", ND, ND,
     "Sim - resgate compulsório quando 98% do VNU amortizado e ha recursos suficientes",
     "'Ressalvadas as hipóteses de Resgate Antecipado Obrigatório, caso exista disponibilidade, o saldo do Valor Nominal Unitário será amortizado nas Datas de Pagamento indicadas no cronograma do Anexo I, observadas as regras da Ordem de Alocação de Recursos' - redação repetida para as cinco séries",
     "ANX-LAM-V174", "Documentado"),

    ("CRI-VI", "Ordem de Alocação de Recursos (Termo de Securitização)",
     "Pró-rata condicionado até o mês 47; sequencial a partir do mês 48", "Mês 48 ou eventos",
     ND, "1", "2", "3", "4", "5", ND, ND, ND, ND, ND,
     "Amortização condicionada a disponibilidade", "ANX-DECK", "Documentado"),

    ("FIDC-I", "Ordem de aplicação de recursos do regulamento", "Hibrido por metas",
     "Liquidação e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-II", "Ordem de aplicação de recursos do regulamento", "Metas até o mês 59",
     "Mês 60 e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-III", "Ordem de aplicação de recursos do regulamento", "Pró-rata até o mês 47",
     "Mês 48 e eventos", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Ordem de aplicação de recursos do regulamento", "Prioridade por classe",
     "Eventos e liquidação", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Regra pública incompleta no acervo", "ANX-DECK", "Documentado"),
    ("FIDC-V", "Ordem de aplicação de recursos do regulamento", "Metas por classe",
     "Eventos e liquidação", ND, "1", "n/a", "2", "n/a", "3", ND, ND, ND, ND, ND,
     "Sujeito aos testes do regulamento vigente", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Ordem de aplicação de recursos do regulamento", "Pró-rata condicionado",
     "Eventos; 6 datas sequenciais aceleram até aceleração definitiva", ND,
     "1", "n/a", "2 (Mezz A) e 3 (Mezz B)", "n/a", "4", ND, ND, ND,
     "Sim - reserva de MTM prevista", ND,
     "Júnior recebe apenas por amortização extraordinária e sob testes", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Ordem de aplicação de recursos do regulamento",
     "Revolvência obrigatória de 12 meses; pró-rata condicionado depois",
     "Eventos; 6 datas sequenciais aceleram até aceleração definitiva", ND,
     "1", "n/a", "2 (Mezz A) e 3 (Mezz B)", "n/a", "4", ND, ND, ND,
     "Sim - reserva prévia de MTM; venda vedada se o MTM superar a júnior", ND,
     "Júnior recebe apenas por amortização extraordinária, sob testes e com trava de 3 meses após Evento de Venda",
     "ANX-DECK", "Documentado"),
]

# Degraus literais da Ordem de Alocacao de Recursos de CRI-II (unica integralmente documentada)
WATERFALL_DEGRAUS_COLS = ["veiculo_id", "regime", "ordem", "item_contratual", "descricao", "fonte_id"]
WATERFALL_DEGRAUS = [
    ("CRI-II", "Pró-rata", 1, "(a)", "Pagamento de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 2, "(b)", "Composição da Reserva de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 3, "(c)-(d)", "Encargos moratórios e remuneração vencida e não paga da 1ª série (Super Sênior)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 4, "(e)", "Remuneração da 1ª série (Super Sênior)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 5, "(f)", "Amortização da 1ª série: o maior entre o Anexo I e o necessário para atingir o Saldo Devedor Target; ou resgate se saldo <= 2%", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 6, "(g)", "Reserva para Resgate Antecipado da 1ª série, a partir de 98% amortizado", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 7, "(h)-(i)", "Encargos moratórios e remuneração vencida e não paga da 2ª série (Sênior)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 8, "(j)", "Remuneração da 2ª série, se a Razão de Cobertura Super Sênior estiver enquadrada", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 9, "(k)", "Amortização da 2ª série até o Target, se a Razão de Cobertura Super Sênior estiver enquadrada", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 10, "(l)", "Reserva para Resgate Antecipado da 2ª série", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 11, "(m)-(n)", "Encargos moratórios e remuneração vencida e não paga da 3ª série (Mezanino)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 12, "(o)", "Remuneração da 3ª série, se as Coberturas Super Sênior e Sênior estiverem enquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 13, "(p)", "Amortização da 3ª série até o Target, sob as mesmas duas coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 14, "(q)", "Reserva para Resgate Antecipado da 3ª série", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 15, "(r)-(s)", "Encargos moratórios e remuneração vencida e não paga da 4ª série (Subordinado)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 16, "(t)", "Remuneração da 4ª série, se as Coberturas Super Sênior, Sênior e Mezanino estiverem enquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 17, "(u)", "Amortização da 4ª série até o Target, sob as mesmas três coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 18, "(v)", "Reserva para Resgate Antecipado da 4ª série", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 19, "(w)-(x)", "Encargos moratórios e remuneração vencida e não paga da 5ª série (Subordinado Jr., privada)", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 20, "(y)", "Remuneração da 5ª série, se as quatro Razões de Cobertura estiverem enquadradas é o saldo estiver acima do Target", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 21, "(z)", "Amortização da 5ª série até o Target, sob as mesmas quatro coberturas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 22, "(aa)", "Amortização extraordinária proporcional entre as séries com cobertura enquadrada, excluídas as desenquadradas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 23, "(bb)", "Prêmio Final: todo o valor remanescente do Patrimônio Separado vai a 5ª série, após o resgate das quatro séries públicas", "ANX-TS2-K2"),
    ("CRI-II", "Pró-rata", 24, "(cc)", "Alocação em Investimentos Permitidos", "ANX-TS2-K2"),

    ("CRI-II", "Sequencial", 1, "(a)-(b)", "Despesas e Reserva de Despesas", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 2, "(c)-(e)", "Encargos, remuneração vencida e remuneração corrente da 1ª série", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 3, "(f)-(g)", "Amortização da 1ª série até 98% do VNU e reserva de resgate - sem condição de cobertura e sem Target", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 4, "(h)-(l)", "2ª série: encargos, remuneração, amortização até 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 5, "(m)-(q)", "3ª série: encargos, remuneração, amortização até 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 6, "(r)-(v)", "4ª série: encargos, remuneração, amortização até 98% e reserva de resgate", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 7, "(w)-(y)", "5ª série: remuneração vencida, remuneração corrente e amortização", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 8, "(z)", "Prêmio Final a 5ª série após o resgate das quatro séries públicas", "ANX-TS2-K2"),
    ("CRI-II", "Sequencial", 9, "(aa)", "Alocação em Investimentos Permitidos", "ANX-TS2-K2"),
]

NOTA_WATERFALL = (
    "O regime chamado de pró-rata não paga as camadas em paralelo: cada camada só recebe se as Razões "
    "de Cobertura de todas as camadas acima estiverem enquadradas, e recebe até um Saldo Devedor Target, "
    "não até o cronograma. O cronograma do Anexo I é alvo, não promessa - toda amortização está "
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
     "Pisos, cobertura e ausência de evento", "25", ND, "Limites do regulamento vigente", ND,
     "130.4", "2022-02-28", "2026-07-31", ND, ND, ND,
     "Attachment atual da sênior: 39,3% da carteira (mezanino + júnior sobre DC)", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-II", "Sim", "Cotista subordinado", "Administrador", ND,
     "Metas, índices e liquidez pro forma", "20", ND, "Antes do sequencial, se enquadrado", ND,
     "160.8", "2022-08-31", "2026-04-30", ND, ND, ND,
     "Attachment atual da sênior: 24,9% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-III", "Sim", "Cotista subordinado", "Administrador", ND,
     "Subordinação, cobertura e ausência de evento", "25", ND, "Pró-rata vigente", ND,
     "101.4", "2025-01-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da sênior: 35,6% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Sim", ND, ND, ND, "Condição detalhada n/d no acervo", "Sem piso", ND, ND, ND,
     "438.9", "2022-07-31", "2025-11-30", ND, ND, ND,
     "Attachment atual da sênior: 0,0% - o fundo esta sem first loss", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-V", "Sim", "Cotista subordinado", "Administrador", ND,
     "Índices, caixa e ausência de evento", "20", ND, "Limites do regulamento vigente", ND,
     "34.4", "2023-03-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da sênior: 21,2% da carteira; folga de 0,9 p.p. ao piso", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Sim", "Titulares de 75% da júnior", "Administrador", "75% da classe júnior",
     "Subordinação e cobertura pro forma; reserva de MTM; ausência de eventos", "25",
     "Patamares de 136,0% / 113,3% / 106,3%", "Não há trava pos-venda equivalente a do VII", ND,
     "183.2", "2025-12-31", "2026-06-30", ND, ND, ND,
     "Attachment atual da sênior: 48,1% da carteira", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Sim", "Titulares de 75% da júnior", "Administrador", "75% da classe júnior",
     "Mesmos testes do VI: subordinação e cobertura pro forma, reserva de MTM e ausência de eventos", "25",
     "Patamares de 136,0% / 113,3% / 106,3%", "3 meses após Evento de Venda",
     "Venda vedada se o MTM superar a júnior", "7.7", "2026-07-31", "2026-07-31", ND, ND, ND,
     "Attachment atual da sênior: 36,1% da carteira; folga de 1,0 p.p. ao piso", "2026-07-31", "ANX-DECK", "Documentado"),

    ("CRI-II", "Sim, mas apenas até o Saldo Devedor Target e sob as quatro Razões de Cobertura",
     "n/a - não há pedido; é regra automática da Ordem de Alocação", "Emissora, na Data de Pagamento",
     "n/a", "Razões de Cobertura Super Sênior, Sênior, Mezanino e Subordinada simultaneamente enquadradas, e saldo acima do Target",
     "n/a - a proteção e por Razão de Cobertura, não por piso percentual",
     "Super Sênior 159%; Sênior 123%; Mezanino 110%; Subordinada 105%",
     "Carência prevista no Anexo I: a 5ª série só começa a receber no 13o pagamento (07/07/2025)",
     "No regime sequencial a 5ª série só recebe depois das quatro séries públicas",
     "6.8", "2025-10-01", "2026-05-01", ND, ND, ND,
     "A 5ª série recebe o Prêmio Final - todo o remanescente do Patrimônio Separado - somente após o resgate das quatro séries públicas",
     "2026-05-01", "ANX-TS2-K2; ANX-DECK", "Documentado"),
    ("CRI-I", "Sim", "n/a - regra automática", "Emissora", "n/a", ND, ND, ND, ND, ND,
     "22.5 (série Subordinada pública); Subordinado Jr. n/d", "2025-07-01", "2026-06-01", ND, ND, ND,
     ND, "2026-06-01", "ANX-DECK", "Documentado"),
    ("CRI-III", "Sim", "n/a - regra automática", "Emissora", "n/a", ND, ND, ND, ND, ND,
     "8.3 (série Subordinada pública)", "2026-02-01", "2026-05-01", ND, ND, ND, ND,
     "2026-05-01", "ANX-DECK", "Documentado"),
    ("CRI-IV", ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, "2026-05-01", "ANX-DECK", "Documentado"),
    ("CRI-V", "Sim", "n/a - regra automática", "Emissora", "n/a", ND, ND, ND, ND, ND,
     ND, ND, ND, ND, ND, ND, "Sem amortização observada até a data-base", "2026-08-21", "ANX-DECK", "Documentado"),
    ("CRI-VI", ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND, ND,
     "Sem informe mensal até a data-base", "2026-08-21", "ANX-DECK", "Documentado"),
]

NOTA_SUBORDINADA = (
    "Nos sete FIDCs a subordinada já recebeu principal - somam R$ 1,06 bi de mezanino e júnior. "
    "Nos CRIs a saída da camada júnior não depende de pedido nem de quórum: é automática, mas só "
    "ocorre se as quatro Razões de Cobertura estiverem enquadradas na Data de Pagamento. "
    "A subordinação antes e depois de cada saque exige o demonstrativo de cada competência, que não é público."
)


# ============================================================ 08_PDD
PDD_COLS = [
    "veiculo_id", "metrica", "ate_15d", "d16_30", "d31_60", "d61_90", "d91_120",
    "d121_150", "d151_180", "acima_180d", "base_de_incidencia", "efeito_vagao",
    "tratamento_do_dia_181", "pdd_adicional_discricionaria", "pdd_observada_pct_carteira",
    "saldo_90d_pct_carteira", "razao_pdd_sobre_90d", "curva", "data_base", "fonte_id", "status",
]

_BASE_VP = ("Valor presente do Direito Creditorio (saldo remanescente da CCB), não apenas a parcela vencida")
_VAGAO_SIM = ("Sim - definido em contrato como o arrasto da pior classificação de atraso entre todas as "
              "CCBs de um mesmo devedor, esteja o título vencido ou a vencer")

PDD = [
    ("CRI-I", "PDD contábil por faixa de atraso", "0,00", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, _VAGAO_SIM,
     "Provisão integral acima de 180 dias", ND, ND, ND, ND, "Inicial", "2024-01-15",
     "ANX-PRO-K1", "Documentado"),
    ("CRI-II", "PDD contábil por faixa de atraso", "0,00", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, _VAGAO_SIM,
     "Provisão integral acima de 180 dias", ND, ND, ND, ND, "Inicial", "2024-06-25",
     "ANX-PRO-K2", "Documentado"),
    ("CRI-III", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisão integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2025-05-28", "ANX-DECK", "Documentado"),
    ("CRI-IV", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisão integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2025-09-28", "ANX-DECK", "Documentado"),
    ("CRI-V", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisão integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2026-05-20", "ANX-DECK", "Documentado"),
    ("CRI-VI", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, _VAGAO_SIM, "Provisão integral acima de 180 dias",
     ND, ND, ND, ND, "Posterior", "2026-07-21", "ANX-DECK", "Documentado"),

    ("FIDC-I", "PDD contábil por faixa de atraso", ND, ND, ND, ND, ND, ND, ND, ND,
     "Tabela específica não pública", ND, ND, ND, "6,8", "1,3", "527", ND, "2026-07-31",
     "ANX-DECK", "Documentado"),
    ("FIDC-II", "PDD contábil por faixa de atraso", "0,00", "2,00", "6,00", "20,00", "100,00",
     "100,00", "100,00", "100,00", _BASE_VP, ND, "Provisão integral já a partir de 91 dias",
     ND, "0,0", "2,1", "0", "Salto integral acima de 90 dias", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-III", "PDD contábil por faixa de atraso", ND, ND, ND, ND, ND, ND, ND, ND,
     "Tabela específica não pública", ND, ND, ND, "5,7", "1,2", "469", ND, "2026-07-31",
     "ANX-DECK", "Documentado"),
    ("FIDC-IV", "PDD contábil por faixa de atraso", "0,50", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, ND, "Provisão integral acima de 180 dias", ND,
     "69,9", "12,7", "550", "Inicial", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-V", "PDD contábil por faixa de atraso", "0,50", "1,00", "3,00", "10,00", "30,00",
     "50,00", "70,00", "100,00", _BASE_VP, ND, "Provisão integral acima de 180 dias", ND,
     "9,3", "1,7", "546", "Inicial; lacunas na tabela pública", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, ND,
     "Lacuna literal no dia 181: a tabela salta de '151-180' para 'acima de 181'", ND,
     "48,8", "8,4", "581", "Posterior", "2026-07-31", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "PDD contábil por faixa de atraso", "0,00", "1,50", "5,00", "10,00", "37,00",
     "58,00", "78,00", "100,00", _BASE_VP, ND,
     "Lacuna literal no dia 181, igual a do VI", ND,
     "0,2", "0,0", "3.725", "Posterior", "2026-07-31", "ANX-DECK", "Documentado"),

    # Metrica distinta: inadimplencia por safra (denominador diferente - nao misturar com a PDD contabil)
    ("CRI-III", "Inadimplência por safra (perda bruta e líquida)", ND, ND, ND, ND, ND, ND, ND, ND,
     "Somatorio dos saldos devedores dos contratos com atraso > 90 dias dividido pelo total originado na safra",
     "n/a - métrica de safra, não de provisão", "n/a", ND, ND, ND, ND,
     "Perda bruta e perda líquida; a diferença entre as duas são as recuperações (pagamentos e renegociações após 90 dias)",
     "2025-04-22", "ANX-LAM-K3", "Documentado"),
    ("CRI-V", "Inadimplência por safra (perda bruta e líquida)", ND, ND, ND, ND, ND, ND, ND, ND,
     "Somatorio dos saldos devedores dos contratos com atraso > 90 dias dividido pelo total originado na safra",
     "n/a - métrica de safra, não de provisão", "n/a", ND, ND, ND, ND,
     "Perda bruta e perda líquida; o Prospecto traz a tabela de perda líquida consolidada de operações pré-fixadas",
     "2026-04-17", "ANX-LAM-V174", "Documentado"),
]

NOTA_PDD = (
    "A provisão incide sobre o valor presente do recebível - o saldo que resta da CCB - e não sobre a "
    "parcela vencida, e o contrato ainda determina o Efeito Vagão, que arrasta a pior faixa de atraso de "
    "um devedor para todas as CCBs dele. São esses dois mecanismos que explicam razões PDD/>90d muito "
    "acima de 100%. A inadimplência por safra tem outro denominador (o total originado na safra) e não "
    "deve ser comparada com a PDD contábil."
)

# ============================================================ 09_Eventos
EVENTOS_COLS = [
    "veiculo_id", "tipo", "descricao_do_gatilho", "parametro_numerico",
    "consequencia_automatica", "quorum_de_dispensa", "prazo_de_cura",
    "ja_ocorreu", "data_da_ocorrencia", "fonte_id", "status",
]

EVENTOS = [
    ("CRI-II", "Desalavancagem", "Índice de Atraso de Estoque desenquadrado em 3 Datas de Verificação consecutivas",
     "Índice de Atraso de Estoque não pode superar 15%", "Regime muda de pró-rata para Amortização Sequencial",
     "Assembleia Especial de Titulares de CRI", ND, "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Rebaixamento de rating dos CRI Super Sênior e/ou Sênior",
     "Queda de 2 níveis abaixo da classificação originalmente atribuída", "Amortização Sequencial",
     "Assembleia Especial de Titulares de CRI", ND, "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Não pagamento de remuneração ou amortização da 1ª série prevista no Anexo I",
     "n/a", "Amortização Sequencial", ND, "5 Dias Uteis contados da Data de Pagamento, observada a carência",
     "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Não divulgação do Relatorio da Emissão no prazo",
     "n/a", "Amortização Sequencial", ND, ND, "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Desalavancagem", "Desenquadramento das Razões de Cobertura",
     "2 Datas de Pagamento consecutivas ou 4 alternadas nos 12 meses anteriores", "Amortização Sequencial",
     ND, ND, "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Amortização Sequencial por prazo", "Alcance do mês 48 da operação",
     "Mês 48 (inclusive)", "Amortização Sequencial permanente até Evento de Realavancagem", ND, ND,
     "Não", "Prevista para 2028", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Realavancagem", "Reenquadramento do Índice de Atraso de Estoque",
     "3 Datas de Verificação consecutivas dentro do limite", "Retorno ao regime pró-rata", ND, ND,
     "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Realavancagem", "Regularizacao do pagamento da 1ª série",
     "Pagamento regular em 3 Datas de Verificação consecutivas; se o evento persistir por 6 meses consecutivos a operação fica em sequencial permanente",
     "Retorno ao regime pró-rata, salvo o caso de 6 meses", "Assembleia Especial para retomar o pró-rata", ND,
     "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Resgate Antecipado Obrigatório", "Saldo do VNU da série igual ou inferior a 2% e recursos suficientes",
     "2% do Valor Nominal Unitário", "Resgate integral da série", ND, ND, "Não", "n/a",
     "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Substituição do Agente de Cobrança",
     "Eventos Materiais Solfácil; impedimento de atuar; descumprimento do Contrato Operacional; resilição; condenação na Lei 12.846; crime contra a administração pública",
     "n/a", "Emissora assume como Backup Servicer e convoca Assembleia Especial",
     "Assembleia Especial de Titulares de CRI", "Prazo de cura específico do Contrato Operacional",
     "Não", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Recompra Obrigatória", "Hipóteses do Contrato de Cessão",
     "n/a", "Recompra ou compra dos Direitos Creditórios pelos Cedentes, Endossantes Iniciais, Solfácil ou Comprador Indicado",
     ND, ND, "n/d", "n/a", "ANX-TS2-K2", "Documentado"),
    ("CRI-II", "Vencimento Antecipado", "Não aplicável", "n/a", "n/a", "n/a", "n/a",
     "n/a", "n/a", "ANX-TS2-K2", "Documentado: não aplicável"),

    ("CRI-V", "Resgate Antecipado Compulsório",
     "Cumulativamente: (i) 98% do VNU da série amortizado e (ii) recursos suficientes para o resgate integral da série",
     "98% do Valor Nominal Unitário", "Resgate integral da série na Data de Pagamento", ND, ND,
     "Não", "n/a", "ANX-LAM-V174", "Documentado"),
    ("CRI-V", "Recompra Obrigatória",
     "Hipóteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfácil previstas no Contrato de Cessão",
     "n/a", "Recompra dos Direitos Creditórios Cedidos", ND, ND, "n/d", "n/a",
     "ANX-LAM-V174", "Documentado"),
    ("CRI-V", "Vencimento Antecipado", "Não aplicável - a lâmina registra 'N/A' no campo",
     "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "ANX-LAM-V174", "Documentado: não aplicável"),

    ("CRI-III", "Resgate Antecipado Obrigatório",
     "Na Data de Pagamento subsequente a Data de Verificação Amortização e Pagamento, nos termos do Termo de Securitização",
     ND, "Resgate da série", ND, ND, "Não", "n/a", "ANX-LAM-K3", "Documentado"),
    ("CRI-III", "Recompra Obrigatória",
     "Hipóteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfácil previstas no Contrato de Cessão",
     "n/a", "Recompra dos Direitos Creditórios Cedidos", ND, ND, "n/d", "n/a", "ANX-LAM-K3", "Documentado"),
    ("CRI-III", "Vencimento Antecipado", "Não aplicável - a lâmina registra 'N/A' no campo",
     "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "ANX-LAM-K3", "Documentado: não aplicável"),

    ("CRI-I", "Recompra Obrigatória",
     "Hipóteses de recompra das Cedentes e/ou Endossante Inicial e/ou Solfácil previstas no Contrato de Cessão",
     "n/a", "Recompra dos Direitos Creditórios Cedidos", ND, ND, "n/d", "n/a", "ANX-LAM-K1", "Documentado"),
    ("CRI-I", "Governança", "Notificacoes formais registradas em 2026 pelo agente fiduciário, sem evidência pública de cura",
     "n/a", ND, ND, ND, "Sim", "2026", "ANX-DECK", "Documentado"),

    ("FIDC-VI", "Desalavancagem", "Eventos de desalavancagem do regulamento; 6 datas sequenciais aceleram até aceleração definitiva",
     "6 datas", "Regime sequencial", ND, ND, "n/d", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Rating", "Rebaixamento da classificação de risco", "Queda de 2 ou mais níveis",
     "Evento de desalavancagem", ND, ND, "Não", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Desalavancagem", "Eventos de desalavancagem do regulamento; 6 datas sequenciais aceleram até aceleração definitiva",
     "6 datas", "Regime sequencial", ND, ND, "n/d", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Rating", "Rebaixamento da classificação de risco", "Queda de 2 ou mais níveis",
     "Evento de desalavancagem", ND, ND, "Não", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Desinvestimento", "Início do período de desinvestimento", "Mês 61 ou PL de R$ 100 mi, o que ocorrer primeiro",
     "Início do desinvestimento", ND, ND, "Não", "n/a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Revolvência", "Período de reinvestimento obrigatório", "12 meses",
     "Principal suspenso e saldo reinvestido", ND, ND, "Sim - em curso", "2026-02-06", "ANX-DECK", "Documentado"),
]

# ============================================================ 09b_Garantias
GARANTIAS_COLS = ["veiculo_id", "garantia_no_ambito_do_veiculo", "garantia_sobre_os_direitos_creditorios",
                  "onde_e_contratada", "coobrigacao_do_cedente", "redacao_literal", "fonte_id", "status"]

GARANTIAS = [
    ("CRI-I", "Não serão constituídas garantias no âmbito dos CRI",
     "Alienação fiduciária dos Equipamentos (Sistema Solar)",
     "No âmbito da respectiva CCB ou em Contrato de Alienação Fiduciária de Equipamentos apartado",
     "Cessão sem coobrigação; o Patrimônio Separado não conta com garantia ou coobrigação da Emissora",
     "'Não serão constituídas garantias no âmbito dos CRI diretamente. Não obstante, os Direitos Creditórios Imobiliarios são garantidos por alienação fiduciária dos Equipamentos'",
     "ANX-LAM-K1", "Documentado"),
    ("CRI-III", "Não serão constituídas garantias no âmbito dos CRI",
     "Alienação fiduciária dos Equipamentos", "No âmbito da respectiva CCB ou de forma apartada em contrato",
     "Cessão sem coobrigação", "'Garantia 2: N/A.'", "ANX-LAM-K3", "Documentado"),
    ("CRI-V", "Não serão constituídas garantias no âmbito dos CRI",
     "Alienação fiduciária dos Equipamentos", "No âmbito da respectiva CCB ou de forma apartada em contrato",
     "Cessão sem coobrigação - o Contrato de Cessão e 'Sem Coobrigação'",
     "'Não serão constituídas garantias no âmbito dos CRI diretamente. Não obstante, os Direitos Creditórios Imobiliarios são garantidos por alienação fiduciária dos Equipamentos, a ser contratada no âmbito da respectiva CCB ou de forma apartada em contrato.'",
     "ANX-LAM-V174", "Documentado"),
    ("CRI-II", "Não serão constituídas garantias no âmbito dos CRI",
     "Alienação fiduciária dos Equipamentos", "No âmbito da respectiva CCB ou de forma apartada",
     "Cessão sem coobrigação", ND, "ANX-PRO-K2", "Documentado"),
    ("CRI-IV", ND, "Alienação fiduciária dos Equipamentos (padrão do programa)", ND, ND, ND,
     "ANX-DECK", "Inferido - padrão repetido em CRI-I, III e V; lâmina da 4ª emissão ausente do acervo"),
    ("CRI-VI", ND, "Alienação fiduciária dos Equipamentos (padrão do programa)", ND, ND, ND,
     "ANX-DECK", "Inferido - padrão repetido em CRI-I, III e V; lâmina da 177a ausente do acervo"),
]

NOTA_GARANTIAS = (
    "Nenhum CRI tem garantia constituída no próprio título. A garantia real existe uma camada abaixo: "
    "os recebíveis são garantidos por alienação fiduciária do equipamento solar, contratada na própria CCB. "
    "Para o investidor do CRI isso significa que a execução depende de retomar equipamento instalado em "
    "telhado de terceiro, ativo de valor de revenda incerto - diferente de uma garantia no nível do veículo."
)
