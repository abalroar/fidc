# -*- coding: utf-8 -*-
"""Conflitos, metodologia, glossário, veredito FIDC x CRI e lacunas."""

ND = "n/d"

# ============================================================ 16_Conflitos
CONFLITOS_COLS = ["id", "campo_em_conflito", "valor_fonte_A", "fonte_A", "data_base_A",
                  "valor_fonte_B", "fonte_B", "data_base_B", "decisao_adotada",
                  "justificativa", "conflito"]

CONFLITOS = [
    ("C1", "Total de séries do programa de CRI",
     "34 séries em seis operações", "ANX-DECK (sl.9 e sl.20)", "2026-08-21",
     "27 séries se CRI-I e CRI-II forem contados como 4 séries cada, conforme os anúncios de oferta",
     "ANX-ENC-K1 ('de 4 (quatro) séries'); ANX-INI-K4 ('de 6 (seis) séries')", "2024-02-23 e 2025-09-29",
     "34 séries - o deck esta correto e não há divergência real",
     "Os anúncios de oferta contam apenas as séries de distribuição pública. A lâmina de CRI-I diz "
     "textualmente '1ª Emissão, em 5 (cinco) séries, sendo 1 para colocação privada e 4 para colocação "
     "pública', e o título do Termo de Securitização de CRI-IV diz 'em 7 (Sete) Séries, sendo 1 (Uma) "
     "Série para Colocação Privada e 6 (Seis) Séries para Distribuição Pública'. Somando a série privada "
     "de cada operação: 5+5+6+7+6+5 = 34. A hipótese de que a VERT 177ª precisaria ter 7 séries para "
     "fechar a conta esta descartada - ela tem 5.", "não"),

    ("C2", "Número de séries e volume da 4ª emissão Kanastra (CRI-IV)",
     "7 séries e R$ 450,0 mi", "ANX-DECK (sl.9)", "2026-08-21",
     "6 séries públicas e R$ 436,5 mi", "ANX-INI-K4", "2025-09-29",
     "7 séries e R$ 450,0 mi no total, dos quais 6 séries e R$ 436,5 mi públicos e 1 série e R$ 13,5 mi privados",
     "Não é divergência, é perímetro. O próprio Anúncio de Início cita o Termo de Securitização 'em 7 "
     "(Sete) Séries, sendo 1 (Uma) Série para Colocação Privada'. R$ 436,5 mi + R$ 13,5 mi = R$ 450,0 mi. "
     "As duas colunas ficam separadas em 02_Series.", "não"),

    ("C3", "Datas da 2ª emissão Kanastra (CRI-II)",
     "Bookbuilding em 20/06/2024", "ANX-CM-K2", "2024-06-20",
     "Data de emissão em 25/06/2024", "ANX-DECK (sl.9); ANX-PRO-K2", "2024-06-25",
     "As duas datas são mantidas em colunas separadas: data_bookbuilding e data_inicio_ou_emissao",
     "São eventos distintos do mesmo processo - a apuração de taxas e quantidades precede a emissão em "
     "cinco dias. Nenhuma das duas é erro da outra.", "não"),

    ("C4", "Volume da 3ª emissão Kanastra (CRI-III)",
     "Até 582.000 CRI / R$ 582,0 mi de lote base, com lote adicional de até 25% (R$ 145,5 mi)",
     "ANX-LAM-K3", "2025-04-22",
     "R$ 727,5 mi públicos e R$ 750,0 mi no total", "ANX-DECK (sl.20)", "2026-08-21",
     "Lote base de R$ 582,0 mi e volume reportado de R$ 727,5 mi ficam em colunas distintas; o lote "
     "adicional de 25% foi integralmente exercido",
     "582.000 x 1,25 = 727.500 exatamente, o que confirma o exercício integral do lote adicional. Como "
     "o Anúncio de Encerramento da 3ª emissão não está no acervo, a coluna montante_subscrito permanece "
     "n/d e o valor do deck fica na coluna montante_reportado_deck.", "sim"),

    ("C5", "Volume da 174ª emissão VERT (CRI-V)",
     "Até 727.500 CRI / R$ 727,5 mi de lote base, sem lote suplementar nem adicional",
     "ANX-LAM-V174", "2026-04-17",
     "R$ 456,5 mi públicos e R$ 470,6 mi no total", "ANX-DECK (sl.20 e sl.33)", "2026-08-21",
     "Lote base de R$ 727,5 mi e volume reportado de R$ 470,6 mi ficam em colunas distintas",
     "Ao contrario de CRI-III, aqui a operação colocou bem menos que o teto: R$ 456,5 mi de séries "
     "públicas contra um lote base de R$ 727,5 mi, ou 62,7%. Sem Anúncio de Encerramento no acervo, "
     "montante_subscrito permanece n/d.", "sim"),

    ("C6", "Cap de concentração por devedor",
     "0,10% do Patrimônio Separado (CRI-III); 0,15% caindo a 0,07% (CRI-V)",
     "ANX-LAM-K3; ANX-LAM-V174", "2025-04-22 e 2026-04-17",
     "Máximo de 20% dos créditos por um único devedor", "ANX-CM-K2 (classificação ANBIMA)", "2024-06-20",
     "Os três números são tabulados lado a lado, sem conciliação",
     "Medem coisas diferentes: o cap contratual limita a exposição a um devedor dentro do Patrimônio "
     "Separado; o limite ANBIMA é critério de classificação de mercado para chamar a operação de "
     "'Pulverizada'. Estão a duas ordens de grandeza de distância e o que morde é o contratual.", "não"),

    ("C7", "Número de séries da 1ª emissão Kanastra (CRI-I)",
     "4 séries", "ANX-ENC-K1 (título e item 2)", "2024-02-23",
     "5 séries, sendo 1 privada e 4 públicas", "ANX-LAM-K1 (item a.1)", "2024-01-15",
     "5 séries, das quais 4 públicas",
     "A lâmina descreve a emissão completa; o anúncio de encerramento só encerra a oferta pública. A "
     "5ª série e subscrita integralmente pela Solfácil e/ou partes relacionadas, sem esforço de venda, "
     "e por isso não entra no registro da oferta.", "sim"),

    ("C8", "Prazo de referência usado no descasamento",
     "Duration de 659 a 713 dias corridos (CRI-V)", "ANX-LAM-V174", "2026-04-17",
     "Duration de 1.806 a 3.632 dias corridos (CRI-III) e de 1.146 a 1.311 dias (CRI-I)",
     "ANX-LAM-K3; ANX-LAM-K1", "2025-04-22 e 2024-01-15",
     "As durations são registradas série a série, sem média entre operações",
     "A duration curta não e característica do programa: e característica de CRI-V. A mesma camada "
     "Mezanino tem duration de 3.632 dias em CRI-III e de 690 dias em CRI-V. Tratar '660 a 713 dias' "
     "como o padrão do programa seria erro material.", "sim"),

    ("C9", "Contagem de 34 em duas dimensões diferentes",
     "34 séries de CRI em seis operações", "ANX-DECK (sl.9)", "2026-08-21",
     "34 séries/subclasses de cotas emitidas pelos sete FIDCs", "ANX-DECK (sl.8 e sl.28-30)", "2026-08-21",
     "Os dois números são mantidos e rotulados separadamente",
     "Coincidência numérica sem relação causal. 02_Series traz 70 linhas: 34 séries de CRI e 34 classes "
     "de cotas de FIDC. Confundir as duas contagens produziria dupla contagem do programa.", "não"),

    ("C10", "Completude do universo na data-base",
     "7 FIDCs e 6 operações de CRI; nenhum fundo >= VIII localizado em 31/07/2026",
     "ANX-DECK (sl.7)", "2026-07-31",
     "Verificação independente no cadastro CVM e em Fundos.NET não foi possível nesta sessão",
     "BUSCA-FIDC8; BUSCA-CRI7", "2026-08-22",
     "Universo mantido em 7 FIDCs e 6 CRIs, com a limitação registrada",
     "A ausência de FIDC VIII e de CRI posterior a 31/07/2026 está apoiada apenas na verificação do "
     "deck, de 21/08/2026. Sem acesso a rede nesta sessão, a confirmação independente fica pendente e "
     "é o primeiro item da lista de lacunas.", "sim"),
    ("C11", "Data de vencimento da 1ª série da debênture",
     "18/02/2033 - 132 meses contados da data de emissão", "ANX-ESC-DEB (cl. 3.6.5)", "2022-02-18",
     "18/08/2035 - mesma data da 2ª série", "ANX-RMA-DEB (tabela de dados gerais das séries)", "2026-07-31",
     "18/02/2033, conforme a escritura",
     "A escritura é o documento constitutivo e fixa prazos distintos para as duas séries: 132 meses para a "
     "1ª e 162 para a 2ª. O relatório mensal repete 18/08/2035 nas duas linhas, o que é consistente com o "
     "campo de vencimento da emissão, e não da série. A data da escritura prevalece.", "sim"),

    ("C12", "Perímetro do universo de veículos",
     "Sete FIDCs e seis operações de CRI", "Escopo do trabalho e ANX-DECK", "2026-08-21",
     "Existe ainda uma emissão de debêntures da Amazônia Solar, de 18/02/2022, lastreada em CCBs originadas "
     "pela Solfácil, e a análise de crédito menciona uma segunda operação de debêntures (SFCL11/21/31/41, R$ 150 mi)",
     "ANX-ESC-DEB; ANX-RMA-DEB; ANX-DECK", "2026-07-31",
     "Universo ampliado para 14 veículos: 7 FIDCs, 6 CRIs e 1 debênture; a segunda operação de debêntures fica registrada como lacuna",
     "A debênture da Amazônia Solar entrou no perímetro porque tem documento primário no acervo e financia o "
     "mesmo ativo, originado pela mesma empresa. As debêntures SFCL não entraram: não há documento no acervo, "
     "apenas a menção de R$ 150 mi na análise de crédito. Registrá-las como lacuna é mais honesto do que estimar.", "sim"),

    ("C13", "Montante por série da 177ª emissão VERT (CRI-VI)",
     "n/d por série; total de R$ 647,1 mi", "ANX-DECK", "2026-08-21",
     "Sênior A R$ 100,0 mi; Sênior B R$ 450,0 mi; Mezanino I R$ 51,765 mi; Mezanino II R$ 25,882 mi; "
     "Subordinado R$ 19,412 mi; total de R$ 647,059 mi",
     "ANX-TS-V177 (cl. 5.6.4 e 5.6.6)", "2026-07-20",
     "Os valores do Termo de Securitização, que fecham em R$ 647,059 mi",
     "O Termo de Securitização resolve a última lacuna de montante do programa: com ele, todas as 34 séries de "
     "CRI passam a ter valor documentado e a soma fecha em R$ 3.670,64 mi. O deck arredondava para R$ 647,1 mi.", "não"),
]

# ============================================================ 18_Metodologia
METODOLOGIA_COLS = ["metrica", "formula", "qualificador", "fonte_id"]
METODOLOGIA = [
    ("WAM contratual", "Média Ponderada dos Prazos de Vencimento das CCBs integrantes do Patrimônio Separado, considerada pro forma a cessão pretendida, limitada a 2.000 dias",
     "E teto, não observação. Em CRI-V a média é medida sobre o valor presente da cessão, o que muda o peso de cada CCB frente a CRI-III. O WAM observado não é publicado em nenhuma operação.",
     "ANX-LAM-K3; ANX-LAM-V174"),
    ("Prazo máximo por recebível", "3.845 dias corridos contados da data de emissão da CCB",
     "Limite por ativo individual, não média. Equivale a 126,4 meses.", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Duration da série", "Duration informada na lâmina, em dias corridos",
     "Aproximada e sujeita a redução por amortização extraordinária, conforme ressalva expressa da própria lâmina. Varia por operação: 1.146-1.311 dias em CRI-I, 1.806-3.632 em CRI-III, 659-713 em CRI-V.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174"),
    ("Prazo legal da série", "Data de vencimento menos data de emissão, em meses",
     "E o prazo máximo de vida do papel, não o prazo esperado. A distância entre prazo legal e duration mede o quanto a estrutura conta com amortização antecipada.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-DECK"),
    ("Attachment point da sênior", "(NAV mezanino + NAV subordinado + NAV subordinado Jr.) / carteira bruta de direitos creditórios",
     "Estático, sem considerar recuperação nem ordem de pagamentos dinâmica. Recalculo antes e depois de cada saque subordinado exige o NAV por classe na data do saque, que não é público.",
     "ANX-DECK (sl.35)"),
    ("Folga ao piso de subordinação", "[Sub_NAV - piso x PL] / [1 - piso]",
     "Piso analítico de 25% nos FIDCs VI e VII. Mede quanto a subordinada poderia ser sacada sem furar o piso, não quanto será.",
     "ANX-DECK (sl.35)"),
    ("PDD / carteira", "PDD / carteira bruta de direitos creditórios",
     "A PDD já reduz o PL. Não é taxa de perda esperada.", "ANX-DECK (sl.35)"),
    (">90d / carteira", "Saldo vencido acima de 90 dias / carteira bruta",
     "Soma parcelas vencidas, não o saldo integral do contrato.", "ANX-DECK (sl.35)"),
    ("Efeito vagão", "Sinalizar quando PDD / saldo >90d ultrapassar 100%",
     "Dois mecanismos distintos produzem essa razão acima de 100%: (a) a provisão incide sobre o valor presente do recebível, não sobre a parcela vencida; (b) o Efeito Vagão contratual arrasta a pior faixa de atraso de um devedor para todas as CCBs dele. A razão não equivale a cobertura de LGD.",
     "ANX-PRO-K1; ANX-PRO-K2; ANX-DECK"),
    ("Concentração do maior titular", "Quantidade subscrita pela maior categoria de investidor / quantidade total da série",
     "Categoria não é titular. Só quando a categoria tem exatamente 1 subscritor o número mede um titular único - por isso a tabela separa maior_categoria_pct de maior_titular_unico_pct.",
     "ANX-ENC-K1"),
    ("Equivalencia de taxas", "Conversão de Pre, %DI, DI+ e IPCA+ para spread sobre DI na data-base, usando a curva DI futura da B3 e a inflação implícita das NTN-B daquela data",
     "Não éxecutada: a curva DI de cada data-base não esta disponível nesta sessão. Todas as células de taxa equivalente ficam n/d, sem estimativa.",
     "n/a"),
    ("Custo all-in", "Custo ponderado das séries públicas + custos fixos anualizados em bps sobre o PL médio",
     "Não apurável: falta a curva DI para ponderar séries de indexadores diferentes, e nenhum custo fixo por veículo é público.",
     "n/a"),
    ("Perna que prevaleceu no bookbuilding", "Comparação entre a taxa contratada e o piso fixo da lâmina",
     "Quando a contratada supera o piso, prevaleceu a perna indexada ao DI futuro; quando iguala o piso, prevaleceu o piso. Em CRI-III as duas séries pre pararam exatamente no piso (15,50% e 16,50%); em CRI-I e CRI-V a perna DI prevaleceu em todas.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-DECK"),
    ("n/d", "Informação não disponível no documento aplicável",
     "Nunca substituído por zero, média ou estimativa. Conta como lacuna.", "n/a"),
    ("Documentado / Inferido", "Documentado: consta em documento do acervo. Inferido: deduzido por cruzamento, com o método declarado na própria linha",
     "Toda linha inferida nomeia a evidência que a sustenta.", "n/a"),
]

# ============================================================ 19_Glossario
GLOSSARIO_COLS = ["termo", "definicao"]
GLOSSARIO = [
    ("Waterfall / Ordem de Alocação de Recursos", "A fila em que o dinheiro que entra é gasto: primeiro despesas, depois juros e principal de cada camada, do mais protegido ao mais exposto."),
    ("Pró-rata (neste programa)", "Regime em que várias camadas podem receber na mesma data, mas cada uma só recebe se as camadas acima dela estiverem com sua cobertura em dia - não e pagamento simultaneo e proporcional."),
    ("Sequencial", "Regime em que uma camada só começa a receber principal depois que a camada acima foi praticamente toda paga."),
    ("Saldo Devedor Target", "O saldo que uma série deveria ter numa data. A amortização paga o quanto for preciso para chegar nesse número, e não um valor fixo de tabela."),
    ("Attachment point", "Quanto de prejuízo a carteira aguenta antes de a camada sênior começar a perder dinheiro."),
    ("Razão de Cobertura", "Quantas vezes o valor da carteira cobre o saldo devido a uma camada e a todas acima dela. Em CRI-II os patamares são 159%, 123%, 110% e 105%."),
    ("Efeito vagão", "Regra contratual pela qual, se um devedor atrasa em um contrato, todos os contratos dele passam a ser tratados pelo pior atraso - inclusive os que estão em dia."),
    ("Seasoning", "Tempo que o crédito já rodou pagando antes de ser vendido. Nenhuma das seis operações exige um mínimo."),
    ("Take-out", "A venda definitiva da carteira do fundo para uma operação de prazo mais longo, que devolve caixa ao fundo."),
    ("Warehouse", "O fundo que financia a carteira enquanto ela esta sendo originada, antes de ser vendida."),
    ("Cash sweep", "Regra que manda todo o caixa que sobra amortizar divida, em vez de ficar parado ou ser distribuido."),
    ("MTM (marcacao a mercado)", "Reavaliar um ativo pelo preço de hoje, e não pelo preço de compra."),
    ("Patrimônio Separado", "O conjunto de recebíveis e caixa de uma emissão, isolado por lei do restante da securitizadora: se ela quebrar, esse patrimônio não responde pelas dividas dela."),
    ("Vasos comunicantes", "Mecanismo em que duas séries dividem um limite comum e a divisão entre elas só e definida no bookbuilding."),
    ("Bookbuilding", "O processo de coletar ordens dos investidores para descobrir a taxa e o tamanho de cada série."),
    ("Lote adicional", "Percentual a mais que pode ser emitido se a demanda superar a oferta. Em CRI-III os 25% foram usados integralmente."),
    ("Duration", "O prazo médio em que o investidor efetivamente recebe seu dinheiro de volta, sempre menor que a data de vencimento."),
    ("Cota subordinada", "A cota que absorve o prejuízo primeiro e recebe por último; em troca, fica com o que sobrar."),
    ("Subordinado Jr.", "A camada mais exposta de cada CRI, colocada de forma privada e subscrita pela própria Solfácil e/ou partes relacionadas, sem oferta ao mercado."),
    ("Prêmio Final", "Todo o dinheiro que sobra no Patrimônio Separado depois que as séries públicas foram resgatadas, e que vai inteiro para a série Subordinada Jr."),
    ("Alienação fiduciária dos Equipamentos", "A garantia real do financiamento: o sistema solar fica no nome do credor até a divida ser paga."),
    ("Resgate compulsório", "Obrigaçação de quitar a série de uma vez quando já se amortizou quase tudo dela - em CRI-V, 98% do valor unitário."),
]

# ============================================================ 15_FIDC_vs_CRI
VEREDITO_COLS = ["dimensao", "como_funciona_no_FIDC", "como_funciona_no_CRI",
                 "vantagem_real", "evidencia", "o_que_falta_para_confirmar"]
VEREDITO = [
    ("Velocidade de originação",
     "Compra continua e revolvente; o fundo absorve o descompasso entre produção e mercado. O FIDC VII tem revolvência obrigatória de 12 meses.",
     "Pool fechado por emissão; só compra no momento da cessão.",
     "FIDC", "Mandatos preveem reinvestimento em I, II, III e V e revolvência obrigatória de 12 meses no VII (ANX-DECK sl.8).",
     "Nada - a diferença é estrutural e documentada."),
    ("Prazo do passivo",
     "Curto a médio, com refinanciamento recorrente.",
     "Vencimentos legais de 2029 a 2038, com duration de 659 a 3.632 dias conforme a operação e a camada.",
     "CRI", "Vencimentos e durations nas lâminas de CRI-I, III e V; datas de vencimento das 34 séries no deck.",
     "WAM observado do pool de cada operação, que nenhuma fonte pública."),
    ("Risco de rollover",
     "Recorrente: a cada vencimento de cota o funding precisa ser renovado.",
     "Eliminado até o vencimento legal, mas substituído por risco de extensão - se a carteira amortizar mais devagar que o previsto, a duration alonga.",
     "CRI", "Toda amortização de CRI é condicionada a 'caso exista disponibilidade' e ao Saldo Devedor Target (ANX-LAM-V174; ANX-TS2-K2 cl. 6.5.1).",
     "Curva de pre-pagamento realizada por safra."),
    ("Custo",
     "Sênior do FIDC VII em DI + 2,00% a.a.; do VI em DI + 3,50%.",
     "Mezanino caiu de DI+6,00% para DI+5,50% e Subordinado de DI+10,00% para DI+8,00% ao longo das seis operações.",
     "Neutro - não comparável com dado público",
     "Taxas contratadas por série nos comunicados e lâminas; spread sênior dos FIDCs no deck.",
     "A curva DI de cada data-base para pôr pré, %DI e DI+ na mesma régua, e os custos fixos por veículo."),
    ("Base de investidores",
     "Institucional e profissional por cota; contagens de cotistas de 1 a 148 por classe.",
     "De 2,1 mil a 7,9 mil pessoas físicas por oferta encerrada, além de fundos e instituições financeiras.",
     "CRI", "Tabelas de subscritores do Anúncio de Encerramento de CRI-I e contagens agregadas das demais ofertas.",
     "Posição corrente por titular - n/d em todas as seis operações."),
    ("Granularidade exigida do pool",
     "Cap individual de 2% a 20% do patrimônio; até 20% no FIDC IV.",
     "Cap individual de 0,07% a 0,25% do Patrimônio Separado.",
     "CRI", "Critérios de Elegibilidade literais das lâminas de CRI-I, III e V; parâmetros dos FIDCs no deck.",
     "Concentração observada, que não é publicada em nenhum veículo."),
    ("Retenção de risco pelo originador",
     "Cota júnior dentro do fundo, com saque permitido sob testes; já saiu principal nos sete fundos.",
     "Série Subordinada Jr. privada, de 2,49% a 3,00% do total, subscrita pela Solfácil e/ou partes relacionadas.",
     "Neutro", "R$ 1,06 bi de mezanino e júnior já amortizados nos FIDCs; R$ 107,0 mi de séries privadas júnior nos CRIs.",
     "O split nominal entre Solfácil e partes relacionadas, e a exposição consolidada da originadora."),
    ("Flexibilidade de revolvência",
     "Reinvestimento permitido em cinco dos sete fundos; obrigatório por 12 meses no VII.",
     "Não há revolvência: o pool e fechado na cessão.",
     "FIDC", "Coluna de reinvestimento por fundo (ANX-DECK sl.8).",
     "Nada - a diferença é estrutural."),
    ("Custo fixo por veículo",
     "Administrador, gestor, custódia, auditoria e rating recorrentes; diluídos pela reutilizacao dos fundos.",
     "Estruturacao, distribuição e agente fiduciário por emissão; seis patrimônios separados montados em 31 meses.",
     "FIDC", "Três fundos (II, IV e VI) foram reutilizados em vários take-outs, em vez de um fundo por operação.",
     "Os valores efetivos - nenhum custo fixo por veículo é público."),
    ("Transparência pos-emissão",
     "Informe Mensal FIDC com PL, carteira, PDD, aging e cotas por classe, mensal e padronizado.",
     "Informe Mensal CRI com saldo, PDD e amortização por série; a VERT 177ª ainda não tem informe.",
     "FIDC", "282 fundo-mês de informe mensal contra 5 de 6 operações de CRI com informe (ANX-DECK sl.36).",
     "Nada - a diferença de granularidade dos formularios e conhecida."),
    ("Garantia real sobre o equipamento",
     "A garantia acompanha o recebível: alienação fiduciária do sistema solar contratada na CCB.",
     "Idêntica - é a mesma CCB. Nenhuma garantia e constituída no âmbito do CRI.",
     "Neutro", "'Não serão constituídas garantias no âmbito dos CRI diretamente' nas lâminas de CRI-I, III e V.",
     "Histórico de execução e recuperação efetiva sobre equipamento retomado."),
    ("Acesso a varejo PF",
     "Fechado - as cotas vao a investidor profissional e qualificado.",
     "Aberto após 180 dias do fim da oferta; 989 pessoas físicas só na série Super Sênior de CRI-I.",
     "CRI", "Restrição a livre negociação das lâminas e tabelas de subscritores do Anúncio de Encerramento.",
     "Nada - a diferença e documentada."),
]

# ============================================================ Lacunas
LACUNAS_COLS = ["prioridade", "o_que_falta", "pergunta_que_responderia", "a_quem_pedir", "aba_afetada"]
LACUNAS = [
    ("1", "Confirmação independente, no cadastro CVM e no Fundos.NET, de que não existe FIDC Solfácil VIII nem emissão de CRI posterior a 31/07/2026",
     "O universo de 7 FIDCs e 6 CRIs esta completo na data-base?", "CVM - Cadastro de Fundos e Fundos.NET", "01_Veiculos; 16_Conflitos"),
    ("2", "Termos de Securitização das 1ª, 3ª e 4ª emissões Kanastra e das 174ª e 177a VERT",
     "Quais FIDCs cederam para cada CRI, qual a Ordem de Alocação e quais os gatilhos numéricos de cada operação?",
     "CVM - Fundos.NET; Kanastra; VERT", "06_Waterfall; 09_Eventos; 11_Matriz_FIDC_CRI"),
    ("3", "Anúncios de Encerramento das 3ª e 4ª emissões Kanastra e da 174a VERT",
     "Quanto foi efetivamente subscrito e quem subscreveu, por tipo de investidor?", "CVM - Ofertas públicas",
     "02_Series; 10_Subscritores"),
    ("4", "Ledger de cessões por lote, com data, volume, preço e composição",
     "Qual o preço efetivo de cessão e houve seleção adversa na escolha do pool?", "Solfácil / gestoras dos FIDCs",
     "11b_Cessoes; 14_Antes_Depois"),
    ("5", "Tape de CCBs com originação, score, parcelas, pre-pagamento e recuperação",
     "Como é a performance por safra e qual o WAM observado de cada pool?", "Solfácil, como originadora e agente de cobrança",
     "05_Prazos_WAM; 08_PDD; 14_Antes_Depois"),
    ("6", "Curva DI futura da B3 e inflação implícita das NTN-B em cada data-base de emissão",
     "Qual o custo all-in de cada estrutura na mesma unidade?", "B3 e ANBIMA", "12_Custo_Captacao"),
    ("7", "Regulamentos vigentes dos sete FIDCs, com os suplementos de classe",
     "Qual a redação literal dos critérios de elegibilidade e dos testes de saque da subordinada por fundo?",
     "CVM - Fundos.NET", "03_Elegibilidade; 07_Subordinada"),
    ("8", "Demonstrativos dos testes de subordinação e cobertura na data de cada amortização subordinada",
     "As saídas de principal da subordinada respeitaram os pisos e as reservas em cada competência?",
     "Administradores dos FIDCs", "07_Subordinada"),
    ("9", "Posição de titulares por ISIN na B3 e no escriturador",
     "Qual a concentração atual e existe mercado secundario?", "B3; Oliveira Trust como escriturador", "10_Subscritores"),
    ("10", "Escritura e relatórios das debêntures SFCL11, SFCL21, SFCL31 e SFCL41",
     "Qual o custo e o prazo da segunda operação de debêntures, que a análise de crédito dimensiona em R$ 150 mi?",
     "Solfácil; agente fiduciário da emissão; B3", "01_Veiculos; 21_Funding_por_Tranche"),
    ("11", "Memória contábil da queda de PL do FIDC VI em julho de 2026",
     "Quanto da variação de R$ 226,3 mi foi cessão, ajuste de valor ou distribuição?", "Administrador do FIDC VI",
     "14_Antes_Depois"),
]

# ============================================================ 14_Antes_Depois
ANTES_DEPOIS_COLS = ["fidc", "competencia", "posicao_relativa_ao_evento", "pl_Rmi", "carteira_Rmi",
                     "outros_ativos_liquidos_Rmi", "pdd_pct_carteira", "saldo_90d_pct_carteira",
                     "evento", "fonte_id", "status"]
ANTES_DEPOIS = [
    ("FIDC-VI", "2026-06-30", "t-1", "437.4", "399.3", "103.1", ND, ND,
     "Competência anterior ao take-out da VERT 177ª", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "2026-07-31", "t=0", "211.1", "147.7", "135.5", "48,8", "8,4",
     "Take-out VERT 177ª (emissão em 31/07/2026)", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "2026-06-30", "t-1", "564.7", "544.1", "21.6", ND, ND,
     "Competência anterior ao take-out da VERT 177ª", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "2026-07-31", "t=0", "619.6", "446.1", "174.6", "0,2", "0,0",
     "Take-out VERT 177ª; fluxo líquido de cotas de +R$ 42,4 mi", "ANX-DECK", "Documentado"),
]

NOTA_ANTES_DEPOIS = (
    "Só uma janela de duas competências é observável, e apenas para os FIDCs VI e VII. A carteira dos "
    "dois cai R$ 349,0 mi juntos e outros ativos líquidos sobem R$ 185,4 mi, o que é consistente com "
    "uma cessão - mas o informe do FIDC VI não decompõe a queda de PU e PL. O que os dados NÃO permitem "
    "afirmar: se a qualidade do que ficou piorou. Sem tape por CCB não há como separar cherry-pick de "
    "simples mudança de denominador - a PDD/carteira de 48,8% no VI pode ser deterioração real ou efeito "
    "de ter vendido a parte boa da carteira. As competências t-3 a t+3 pedidas não existem: o take-out "
    "é de 31/07/2026 e a última competência disponível é a própria."
)
