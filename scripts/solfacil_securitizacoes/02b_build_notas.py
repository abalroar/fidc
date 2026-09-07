# -*- coding: utf-8 -*-
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT = "outputs/solfacil/Solfacil_Securitizacoes_Comparativo.xlsx"
AR = "Arial"; NAVY = "1F3864"; BLUE = "2E5C8A"; WHITE = "FFFFFF"
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
wb = load_workbook(OUT)
ws = wb.create_sheet("Como ler")

ws["A1"] = "Como ler o comparativo"
ws["A1"].font = Font(name=AR, size=14, bold=True, color=NAVY)
ws.row_dimensions[1].height = 20

BLOCKS = [
 ("§", "OS QUATRO DESENHOS DE AMORTIZAÇÃO DA FAMÍLIA SOLFÁCIL", ""),
 ("t", "1. Programada linear  —  FIDC I e V",
  "Todo mês o administrador constitui uma Reserva de Amortização igual ao PL da classe dividido pelo número de meses "
  "que faltam até o vencimento da série. O caixa paga primeiro a Sênior, depois o Mezanino A. É o desenho mais previsível "
  "e o mais rígido: a amortização não reage à performance da carteira, só ao calendário. Não existe regime pro rata nem "
  "sequencial; o que protege a Sênior é a Razão de Garantia (PL ÷ cotas sêniores), cujo desenquadramento suspende a "
  "compra de novos recebíveis e obriga o cotista subordinado a aportar em até dois dias úteis."),
 ("t", "2. Alvo de composição, ou pro rata  —  FIDC II, III e VII",
  "Em cada data de pagamento o administrador calcula quanto cada classe deveria representar do PL (o 'target') e devolve "
  "caixa a quem estiver acima do alvo. Enquanto todas as classes estão no alvo, todo mundo amortiza junto, na proporção do "
  "desenho original. Os alvos são: FIDC II — Sr 80% / Mez 16% / Jr 10%; FIDC III — Sr 67% / Mez A 15% / Mez B 6% / Jr 12%; "
  "FIDC VII — Sr 73% / Mez A 15% / Mez B 6% / Jr 6%. O regime tem prazo de validade: no FIDC II ele acaba no 60º mês e no "
  "FIDC III no 48º, quando a cascata vira sequencial por decurso de prazo, independentemente de performance."),
 ("t", "3. Sequencial  —  o modo de estresse",
  "A cascata paga remuneração e principal da Sênior até o resgate integral, só então passa ao Mezanino A, depois ao "
  "Mezanino B e por último ao Júnior. Nos FIDC VI e VII o sequencial é acionado por gatilho de performance (Evento de "
  "Desalavancagem) e pode ser revertido por um Evento de Realavancagem; nos FIDC II e III ele chega por prazo e é "
  "definitivo. Seis datas de pagamento seguidas em sequencial nos FIDC VI e VII configuram Evento de Aceleração de "
  "Vencimento — mudança definitiva, sem assembleia."),
 ("t", "4. Bullet  —  FIDC VI",
  "A Meta de Amortização de Principal é zero durante todo o Período de Carência, que vai da primeira integralização até o "
  "mês anterior ao Período de Desinvestimento (os 6 meses que antecedem a data de resgate). O principal só sai por quatro "
  "caminhos: o Período de Desinvestimento, um Evento de Venda da carteira, uma solicitação de 75% das cotas Júnior a "
  "partir do 18º mês, ou a Amortização Sequencial após um gatilho. Na prática o caminho usado foi o Evento de Venda: a "
  "carteira foi cedida ao CRI 174ª da Vert em maio de 2026."),
 ("§", "O QUE MUDA ENTRE AS GERAÇÕES", ""),
 ("t", "Da geração Daycoval/Angá (I, V) para a geração Itaú BBA/Fitch (III)",
  "Sai a amortização por calendário e entra o alvo de composição, com índices de subordinação nomeados por classe "
  "(25% / 10% / 4%) e limites de concentração muito mais apertados — 0,10% do PL por devedor no III contra 2% no I e no V. "
  "A remuneração deixa de ser indexada ao IPCA e passa ao CDI."),
 ("t", "Da geração III para VI e VII",
  "Entram as Razões de Cobertura em dois patamares (desalavancagem 1 e 2) e um terceiro patamar para liberar amortização "
  "extraordinária, mais o Índice de Atraso 90 como gatilho autônomo em 15%. O regime deixa de trocar por calendário e passa "
  "a trocar por performance, com caminho de volta. O VII acrescenta um período de revolvência de 12 meses, carência inicial "
  "de 3 meses nos juros e uma Reserva de MtM para os derivativos, com aporte obrigatório do Júnior quando o MtM excede 1% do PL."),
 ("t", "Do FIDC para o CRI",
  "A 174ª emissão da Vert repete a lógica dos FIDC VI e VII — pro rata até o 47º mês, sequencial depois, gatilhos de "
  "desalavancagem por cobertura e por atraso — mas separa a dívida sênior em duas camadas (Super Sênior A pré-fixada e "
  "Super Sênior B em CDI) e dá a elas o único cronograma de amortização contratado da estrutura. As demais séries vivem "
  "de varredura de caixa. Também muda o investidor: 2.505 pessoas físicas na 174ª, contra dezenas de cotistas "
  "profissionais nos FIDCs."),
 ("§", "TERMOS QUE APARECEM NAS TABELAS", ""),
 ("t", "Razão de Garantia / Razão de Cobertura",
  "Ativos divididos por passivo de uma faixa de cotas. Uma razão de 133% sob a Sênior equivale a 25% de subordinação "
  "(1 − 1 ÷ 1,333). Nos FIDC I e V a razão é calculada sobre o PL; nos VI, VII e no CRI é calculada sobre o valor presente "
  "dos direitos creditórios líquido de PDD mais as disponibilidades."),
 ("t", "Índice de Subordinação",
  "Percentual do PL representado pelas cotas de prioridade igual ou inferior à faixa em questão. É a leitura direta de "
  "quanto capital está abaixo de cada tranche."),
 ("t", "Evento de Desalavancagem / Realavancagem",
  "Gatilho que troca o regime de amortização de pro rata para sequencial, e o gatilho inverso que devolve a estrutura ao "
  "pro rata. Existem apenas nos FIDC VI e VII e no CRI 174ª."),
 ("t", "Período de Desinvestimento",
  "Janela final em que o fundo para de reinvestir e devolve caixa. No FIDC VI são os 6 meses anteriores à data de resgate; "
  "no VII começa no 61º mês ou quando o PL cai a R$ 100 mm."),
 ("t", "Amortização Extraordinária",
  "Pagamento de principal fora do cronograma, alimentado pelo caixa que sobra na cascata. É o único mecanismo de "
  "amortização das séries Sênior, Mezanino e Subordinado do CRI 174ª, e depende de as razões de cobertura estarem acima "
  "do patamar de liberação."),
 ("§", "FONTES", ""),
 ("t", "Documentos consultados",
  "Regulamentos vigentes das 7 classes e relatórios de rating (Austin, Fitch, SR Rating), obtidos no Fundos.NET da B3/CVM. "
  "Cadastro de fundos, classes e subclasses (registro_fundo_classe) e Informe Mensal FIDC de julho de 2026, em dados.cvm.gov.br. "
  "Base de ofertas públicas encerradas sob a Resolução CVM 160. Lâmina e prospecto definitivo da 174ª emissão e anúncio de "
  "início da 177ª emissão, no Sistema de Registro de Ofertas da CVM. Consulta realizada em setembro de 2026."),
 ("t", "Escopo",
  "Foram identificadas 7 classes de FIDC com o nome Solfácil no cadastro da CVM e 2 emissões de CRI cujo lastro é "
  "declaradamente originado na Plataforma Solfácil. O FIDC Solfarma, apesar do nome parecido, é de outra companhia e "
  "não integra este comparativo."),
]

r = 3
for kind, title, body in BLOCKS:
    if kind == "§":
        ws.cell(row=r, column=1, value=title)
        for j in (1, 2):
            c = ws.cell(row=r, column=j)
            c.fill = PatternFill("solid", fgColor=BLUE)
            c.font = Font(name=AR, size=10, bold=True, color=WHITE)
            c.border = BOX
        ws.row_dimensions[r].height = 18
        r += 2
        continue
    ws.cell(row=r, column=1, value=title).font = Font(name=AR, size=10, bold=True, color=NAVY)
    ws.cell(row=r, column=1).alignment = Alignment(vertical="top", wrap_text=True)
    c = ws.cell(row=r, column=2, value=body)
    c.font = Font(name=AR, size=9)
    c.alignment = Alignment(vertical="top", wrap_text=True)
    r += 1

ws.column_dimensions["A"].width = 44
ws.column_dimensions["B"].width = 116
ws.sheet_view.showGridLines = False
ws.freeze_panes = "A3"

wb.move_sheet("Como ler", offset=-2)
wb.save(OUT)
print("notas ok", wb.sheetnames)
