# -*- coding: utf-8 -*-
"""Conflitos, metodologia, glossario, veredito FIDC x CRI e lacunas."""

ND = "n/d"

# ============================================================ 16_Conflitos
CONFLITOS_COLS = ["id", "campo_em_conflito", "valor_fonte_A", "fonte_A", "data_base_A",
                  "valor_fonte_B", "fonte_B", "data_base_B", "decisao_adotada",
                  "justificativa", "conflito"]

CONFLITOS = [
    ("C1", "Total de series do programa de CRI",
     "34 series em seis operacoes", "ANX-DECK (sl.9 e sl.20)", "2026-08-21",
     "27 series se CRI-I e CRI-II forem contados como 4 series cada, conforme os anuncios de oferta",
     "ANX-ENC-K1 ('de 4 (quatro) series'); ANX-INI-K4 ('de 6 (seis) series')", "2024-02-23 e 2025-09-29",
     "34 series - o deck esta correto e nao ha divergencia real",
     "Os anuncios de oferta contam apenas as series de distribuicao publica. A lamina de CRI-I diz "
     "textualmente '1a Emissao, em 5 (cinco) series, sendo 1 para colocacao privada e 4 para colocacao "
     "publica', e o titulo do Termo de Securitizacao de CRI-IV diz 'em 7 (Sete) Series, sendo 1 (Uma) "
     "Serie para Colocacao Privada e 6 (Seis) Series para Distribuicao Publica'. Somando a serie privada "
     "de cada operacao: 5+5+6+7+6+5 = 34. A hipotese de que a VERT 177a precisaria ter 7 series para "
     "fechar a conta esta descartada - ela tem 5.", "nao"),

    ("C2", "Numero de series e volume da 4a emissao Kanastra (CRI-IV)",
     "7 series e R$ 450,0 mi", "ANX-DECK (sl.9)", "2026-08-21",
     "6 series publicas e R$ 436,5 mi", "ANX-INI-K4", "2025-09-29",
     "7 series e R$ 450,0 mi no total, dos quais 6 series e R$ 436,5 mi publicos e 1 serie e R$ 13,5 mi privados",
     "Nao e divergencia, e perimetro. O proprio Anuncio de Inicio cita o Termo de Securitizacao 'em 7 "
     "(Sete) Series, sendo 1 (Uma) Serie para Colocacao Privada'. R$ 436,5 mi + R$ 13,5 mi = R$ 450,0 mi. "
     "As duas colunas ficam separadas em 02_Series.", "nao"),

    ("C3", "Datas da 2a emissao Kanastra (CRI-II)",
     "Bookbuilding em 20/06/2024", "ANX-CM-K2", "2024-06-20",
     "Data de emissao em 25/06/2024", "ANX-DECK (sl.9); ANX-PRO-K2", "2024-06-25",
     "As duas datas sao mantidas em colunas separadas: data_bookbuilding e data_inicio_ou_emissao",
     "Sao eventos distintos do mesmo processo - a apuracao de taxas e quantidades precede a emissao em "
     "cinco dias. Nenhuma das duas e erro da outra.", "nao"),

    ("C4", "Volume da 3a emissao Kanastra (CRI-III)",
     "Ate 582.000 CRI / R$ 582,0 mi de lote base, com lote adicional de ate 25% (R$ 145,5 mi)",
     "ANX-LAM-K3", "2025-04-22",
     "R$ 727,5 mi publicos e R$ 750,0 mi no total", "ANX-DECK (sl.20)", "2026-08-21",
     "Lote base de R$ 582,0 mi e volume reportado de R$ 727,5 mi ficam em colunas distintas; o lote "
     "adicional de 25% foi integralmente exercido",
     "582.000 x 1,25 = 727.500 exatamente, o que confirma o exercicio integral do lote adicional. Como "
     "o Anuncio de Encerramento da 3a emissao nao esta no acervo, a coluna montante_subscrito permanece "
     "n/d e o valor do deck fica na coluna montante_reportado_deck.", "sim"),

    ("C5", "Volume da 174a emissao VERT (CRI-V)",
     "Ate 727.500 CRI / R$ 727,5 mi de lote base, sem lote suplementar nem adicional",
     "ANX-LAM-V174", "2026-04-17",
     "R$ 456,5 mi publicos e R$ 470,6 mi no total", "ANX-DECK (sl.20 e sl.33)", "2026-08-21",
     "Lote base de R$ 727,5 mi e volume reportado de R$ 470,6 mi ficam em colunas distintas",
     "Ao contrario de CRI-III, aqui a operacao colocou bem menos que o teto: R$ 456,5 mi de series "
     "publicas contra um lote base de R$ 727,5 mi, ou 62,7%. Sem Anuncio de Encerramento no acervo, "
     "montante_subscrito permanece n/d.", "sim"),

    ("C6", "Cap de concentracao por devedor",
     "0,10% do Patrimonio Separado (CRI-III); 0,15% caindo a 0,07% (CRI-V)",
     "ANX-LAM-K3; ANX-LAM-V174", "2025-04-22 e 2026-04-17",
     "Maximo de 20% dos creditos por um unico devedor", "ANX-CM-K2 (classificacao ANBIMA)", "2024-06-20",
     "Os tres numeros sao tabulados lado a lado, sem conciliacao",
     "Medem coisas diferentes: o cap contratual limita a exposicao a um devedor dentro do Patrimonio "
     "Separado; o limite ANBIMA e criterio de classificacao de mercado para chamar a operacao de "
     "'Pulverizada'. Estao a duas ordens de grandeza de distancia e o que morde e o contratual.", "nao"),

    ("C7", "Numero de series da 1a emissao Kanastra (CRI-I)",
     "4 series", "ANX-ENC-K1 (titulo e item 2)", "2024-02-23",
     "5 series, sendo 1 privada e 4 publicas", "ANX-LAM-K1 (item a.1)", "2024-01-15",
     "5 series, das quais 4 publicas",
     "A lamina descreve a emissao completa; o anuncio de encerramento so encerra a oferta publica. A "
     "5a serie e subscrita integralmente pela Solfacil e/ou partes relacionadas, sem esforco de venda, "
     "e por isso nao entra no registro da oferta.", "sim"),

    ("C8", "Prazo de referencia usado no descasamento",
     "Duration de 659 a 713 dias corridos (CRI-V)", "ANX-LAM-V174", "2026-04-17",
     "Duration de 1.806 a 3.632 dias corridos (CRI-III) e de 1.146 a 1.311 dias (CRI-I)",
     "ANX-LAM-K3; ANX-LAM-K1", "2025-04-22 e 2024-01-15",
     "As durations sao registradas serie a serie, sem media entre operacoes",
     "A duration curta nao e caracteristica do programa: e caracteristica de CRI-V. A mesma camada "
     "Mezanino tem duration de 3.632 dias em CRI-III e de 690 dias em CRI-V. Tratar '660 a 713 dias' "
     "como o padrao do programa seria erro material.", "sim"),

    ("C9", "Contagem de 34 em duas dimensoes diferentes",
     "34 series de CRI em seis operacoes", "ANX-DECK (sl.9)", "2026-08-21",
     "34 series/subclasses de cotas emitidas pelos sete FIDCs", "ANX-DECK (sl.8 e sl.28-30)", "2026-08-21",
     "Os dois numeros sao mantidos e rotulados separadamente",
     "Coincidencia numerica sem relacao causal. 02_Series traz 68 linhas: 34 series de CRI e 34 classes "
     "de cotas de FIDC. Confundir as duas contagens produziria dupla contagem do programa.", "nao"),

    ("C10", "Completude do universo na data-base",
     "7 FIDCs e 6 operacoes de CRI; nenhum fundo >= VIII localizado em 31/07/2026",
     "ANX-DECK (sl.7)", "2026-07-31",
     "Verificacao independente no cadastro CVM e em Fundos.NET nao foi possivel nesta sessao",
     "BUSCA-FIDC8; BUSCA-CRI7", "2026-08-22",
     "Universo mantido em 7 FIDCs e 6 CRIs, com a limitacao registrada",
     "A ausencia de FIDC VIII e de CRI posterior a 31/07/2026 esta apoiada apenas na verificacao do "
     "deck, de 21/08/2026. Sem acesso a rede nesta sessao, a confirmacao independente fica pendente e "
     "e o primeiro item da lista de lacunas.", "sim"),
]

# ============================================================ 18_Metodologia
METODOLOGIA_COLS = ["metrica", "formula", "qualificador", "fonte_id"]
METODOLOGIA = [
    ("WAM contratual", "Media Ponderada dos Prazos de Vencimento das CCBs integrantes do Patrimonio Separado, considerada pro forma a cessao pretendida, limitada a 2.000 dias",
     "E teto, nao observacao. Em CRI-V a media e medida sobre o valor presente da cessao, o que muda o peso de cada CCB frente a CRI-III. O WAM observado nao e publicado em nenhuma operacao.",
     "ANX-LAM-K3; ANX-LAM-V174"),
    ("Prazo maximo por recebivel", "3.845 dias corridos contados da data de emissao da CCB",
     "Limite por ativo individual, nao media. Equivale a 126,4 meses.", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Duration da serie", "Duration informada na lamina, em dias corridos",
     "Aproximada e sujeita a reducao por amortizacao extraordinaria, conforme ressalva expressa da propria lamina. Varia por operacao: 1.146-1.311 dias em CRI-I, 1.806-3.632 em CRI-III, 659-713 em CRI-V.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174"),
    ("Prazo legal da serie", "Data de vencimento menos data de emissao, em meses",
     "E o prazo maximo de vida do papel, nao o prazo esperado. A distancia entre prazo legal e duration mede o quanto a estrutura conta com amortizacao antecipada.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-DECK"),
    ("Attachment point da senior", "(NAV mezanino + NAV subordinado + NAV subordinado Jr.) / carteira bruta de direitos creditorios",
     "Estatico, sem considerar recuperacao nem ordem de pagamentos dinamica. Recalculo antes e depois de cada saque subordinado exige o NAV por classe na data do saque, que nao e publico.",
     "ANX-DECK (sl.35)"),
    ("Folga ao piso de subordinacao", "[Sub_NAV - piso x PL] / [1 - piso]",
     "Piso analitico de 25% nos FIDCs VI e VII. Mede quanto a subordinada poderia ser sacada sem furar o piso, nao quanto sera.",
     "ANX-DECK (sl.35)"),
    ("PDD / carteira", "PDD / carteira bruta de direitos creditorios",
     "A PDD ja reduz o PL. Nao e taxa de perda esperada.", "ANX-DECK (sl.35)"),
    (">90d / carteira", "Saldo vencido acima de 90 dias / carteira bruta",
     "Soma parcelas vencidas, nao o saldo integral do contrato.", "ANX-DECK (sl.35)"),
    ("Efeito vagao", "Sinalizar quando PDD / saldo >90d ultrapassar 100%",
     "Dois mecanismos distintos produzem essa razao acima de 100%: (a) a provisao incide sobre o valor presente do recebivel, nao sobre a parcela vencida; (b) o Efeito Vagao contratual arrasta a pior faixa de atraso de um devedor para todas as CCBs dele. A razao nao equivale a cobertura de LGD.",
     "ANX-PRO-K1; ANX-PRO-K2; ANX-DECK"),
    ("Concentracao do maior titular", "Quantidade subscrita pela maior categoria de investidor / quantidade total da serie",
     "Categoria nao e titular. So quando a categoria tem exatamente 1 subscritor o numero mede um titular unico - por isso a tabela separa maior_categoria_pct de maior_titular_unico_pct.",
     "ANX-ENC-K1"),
    ("Equivalencia de taxas", "Conversao de Pre, %DI, DI+ e IPCA+ para spread sobre DI na data-base, usando a curva DI futura da B3 e a inflacao implicita das NTN-B daquela data",
     "Nao executada: a curva DI de cada data-base nao esta disponivel nesta sessao. Todas as celulas de taxa equivalente ficam n/d, sem estimativa.",
     "n/a"),
    ("Custo all-in", "Custo ponderado das series publicas + custos fixos anualizados em bps sobre o PL medio",
     "Nao apuravel: falta a curva DI para ponderar series de indexadores diferentes, e nenhum custo fixo por veiculo e publico.",
     "n/a"),
    ("Perna que prevaleceu no bookbuilding", "Comparacao entre a taxa contratada e o piso fixo da lamina",
     "Quando a contratada supera o piso, prevaleceu a perna indexada ao DI futuro; quando iguala o piso, prevaleceu o piso. Em CRI-III as duas series pre pararam exatamente no piso (15,50% e 16,50%); em CRI-I e CRI-V a perna DI prevaleceu em todas.",
     "ANX-LAM-K1; ANX-LAM-K3; ANX-LAM-V174; ANX-DECK"),
    ("n/d", "Informacao nao disponivel no documento aplicavel",
     "Nunca substituido por zero, media ou estimativa. Conta como lacuna.", "n/a"),
    ("Documentado / Inferido", "Documentado: consta em documento do acervo. Inferido: deduzido por cruzamento, com o metodo declarado na propria linha",
     "Toda linha inferida nomeia a evidencia que a sustenta.", "n/a"),
]

# ============================================================ 19_Glossario
GLOSSARIO_COLS = ["termo", "definicao"]
GLOSSARIO = [
    ("Waterfall / Ordem de Alocacao de Recursos", "A fila em que o dinheiro que entra e gasto: primeiro despesas, depois juros e principal de cada camada, do mais protegido ao mais exposto."),
    ("Pro rata (neste programa)", "Regime em que varias camadas podem receber na mesma data, mas cada uma so recebe se as camadas acima dela estiverem com sua cobertura em dia - nao e pagamento simultaneo e proporcional."),
    ("Sequencial", "Regime em que uma camada so comeca a receber principal depois que a camada acima foi praticamente toda paga."),
    ("Saldo Devedor Target", "O saldo que uma serie deveria ter numa data. A amortizacao paga o quanto for preciso para chegar nesse numero, e nao um valor fixo de tabela."),
    ("Attachment point", "Quanto de prejuizo a carteira aguenta antes de a camada senior comecar a perder dinheiro."),
    ("Razao de Cobertura", "Quantas vezes o valor da carteira cobre o saldo devido a uma camada e a todas acima dela. Em CRI-II os patamares sao 159%, 123%, 110% e 105%."),
    ("Efeito vagao", "Regra contratual pela qual, se um devedor atrasa em um contrato, todos os contratos dele passam a ser tratados pelo pior atraso - inclusive os que estao em dia."),
    ("Seasoning", "Tempo que o credito ja rodou pagando antes de ser vendido. Nenhuma das seis operacoes exige um minimo."),
    ("Take-out", "A venda definitiva da carteira do fundo para uma operacao de prazo mais longo, que devolve caixa ao fundo."),
    ("Warehouse", "O fundo que financia a carteira enquanto ela esta sendo originada, antes de ser vendida."),
    ("Cash sweep", "Regra que manda todo o caixa que sobra amortizar divida, em vez de ficar parado ou ser distribuido."),
    ("MTM (marcacao a mercado)", "Reavaliar um ativo pelo preco de hoje, e nao pelo preco de compra."),
    ("Patrimonio Separado", "O conjunto de recebiveis e caixa de uma emissao, isolado por lei do restante da securitizadora: se ela quebrar, esse patrimonio nao responde pelas dividas dela."),
    ("Vasos comunicantes", "Mecanismo em que duas series dividem um limite comum e a divisao entre elas so e definida no bookbuilding."),
    ("Bookbuilding", "O processo de coletar ordens dos investidores para descobrir a taxa e o tamanho de cada serie."),
    ("Lote adicional", "Percentual a mais que pode ser emitido se a demanda superar a oferta. Em CRI-III os 25% foram usados integralmente."),
    ("Duration", "O prazo medio em que o investidor efetivamente recebe seu dinheiro de volta, sempre menor que a data de vencimento."),
    ("Cota subordinada", "A cota que absorve o prejuizo primeiro e recebe por ultimo; em troca, fica com o que sobrar."),
    ("Subordinado Jr.", "A camada mais exposta de cada CRI, colocada de forma privada e subscrita pela propria Solfacil e/ou partes relacionadas, sem oferta ao mercado."),
    ("Premio Final", "Todo o dinheiro que sobra no Patrimonio Separado depois que as series publicas foram resgatadas, e que vai inteiro para a serie Subordinada Jr."),
    ("Alienacao fiduciaria dos Equipamentos", "A garantia real do financiamento: o sistema solar fica no nome do credor ate a divida ser paga."),
    ("Resgate compulsorio", "Obrigacao de quitar a serie de uma vez quando ja se amortizou quase tudo dela - em CRI-V, 98% do valor unitario."),
]

# ============================================================ 15_FIDC_vs_CRI
VEREDITO_COLS = ["dimensao", "como_funciona_no_FIDC", "como_funciona_no_CRI",
                 "vantagem_real", "evidencia", "o_que_falta_para_confirmar"]
VEREDITO = [
    ("Velocidade de originacao",
     "Compra continua e revolvente; o fundo absorve o descompasso entre producao e mercado. O FIDC VII tem revolvencia obrigatoria de 12 meses.",
     "Pool fechado por emissao; so compra no momento da cessao.",
     "FIDC", "Mandatos preveem reinvestimento em I, II, III e V e revolvencia obrigatoria de 12 meses no VII (ANX-DECK sl.8).",
     "Nada - a diferenca e estrutural e documentada."),
    ("Prazo do passivo",
     "Curto a medio, com refinanciamento recorrente.",
     "Vencimentos legais de 2029 a 2038, com duration de 659 a 3.632 dias conforme a operacao e a camada.",
     "CRI", "Vencimentos e durations nas laminas de CRI-I, III e V; datas de vencimento das 34 series no deck.",
     "WAM observado do pool de cada operacao, que nenhuma fonte publica."),
    ("Risco de rollover",
     "Recorrente: a cada vencimento de cota o funding precisa ser renovado.",
     "Eliminado ate o vencimento legal, mas substituido por risco de extensao - se a carteira amortizar mais devagar que o previsto, a duration alonga.",
     "CRI", "Toda amortizacao de CRI e condicionada a 'caso exista disponibilidade' e ao Saldo Devedor Target (ANX-LAM-V174; ANX-TS2-K2 cl. 6.5.1).",
     "Curva de pre-pagamento realizada por safra."),
    ("Custo",
     "Senior do FIDC VII em DI + 2,00% a.a.; do VI em DI + 3,50%.",
     "Mezanino caiu de DI+6,00% para DI+5,50% e Subordinado de DI+10,00% para DI+8,00% ao longo das seis operacoes.",
     "Neutro - nao comparavel com dado publico",
     "Taxas contratadas por serie nos comunicados e laminas; spread senior dos FIDCs no deck.",
     "A curva DI de cada data-base para por pre, %DI e DI+ na mesma regua, e os custos fixos por veiculo."),
    ("Base de investidores",
     "Institucional e profissional por cota; contagens de cotistas de 1 a 148 por classe.",
     "De 2,1 mil a 7,9 mil pessoas fisicas por oferta encerrada, alem de fundos e instituicoes financeiras.",
     "CRI", "Tabelas de subscritores do Anuncio de Encerramento de CRI-I e contagens agregadas das demais ofertas.",
     "Posicao corrente por titular - n/d em todas as seis operacoes."),
    ("Granularidade exigida do pool",
     "Cap individual de 2% a 20% do patrimonio; ate 20% no FIDC IV.",
     "Cap individual de 0,07% a 0,25% do Patrimonio Separado.",
     "CRI", "Criterios de Elegibilidade literais das laminas de CRI-I, III e V; parametros dos FIDCs no deck.",
     "Concentracao observada, que nao e publicada em nenhum veiculo."),
    ("Retencao de risco pelo originador",
     "Cota junior dentro do fundo, com saque permitido sob testes; ja saiu principal nos sete fundos.",
     "Serie Subordinada Jr. privada, de 2,49% a 3,00% do total, subscrita pela Solfacil e/ou partes relacionadas.",
     "Neutro", "R$ 1,06 bi de mezanino e junior ja amortizados nos FIDCs; R$ 107,0 mi de series privadas junior nos CRIs.",
     "O split nominal entre Solfacil e partes relacionadas, e a exposicao consolidada da originadora."),
    ("Flexibilidade de revolvencia",
     "Reinvestimento permitido em cinco dos sete fundos; obrigatorio por 12 meses no VII.",
     "Nao ha revolvencia: o pool e fechado na cessao.",
     "FIDC", "Coluna de reinvestimento por fundo (ANX-DECK sl.8).",
     "Nada - a diferenca e estrutural."),
    ("Custo fixo por veiculo",
     "Administrador, gestor, custodia, auditoria e rating recorrentes; diluidos pela reutilizacao dos fundos.",
     "Estruturacao, distribuicao e agente fiduciario por emissao; seis patrimonios separados montados em 31 meses.",
     "FIDC", "Tres fundos (II, IV e VI) foram reutilizados em varios take-outs, em vez de um fundo por operacao.",
     "Os valores efetivos - nenhum custo fixo por veiculo e publico."),
    ("Transparencia pos-emissao",
     "Informe Mensal FIDC com PL, carteira, PDD, aging e cotas por classe, mensal e padronizado.",
     "Informe Mensal CRI com saldo, PDD e amortizacao por serie; a VERT 177a ainda nao tem informe.",
     "FIDC", "282 fundo-mes de informe mensal contra 5 de 6 operacoes de CRI com informe (ANX-DECK sl.36).",
     "Nada - a diferenca de granularidade dos formularios e conhecida."),
    ("Garantia real sobre o equipamento",
     "A garantia acompanha o recebivel: alienacao fiduciaria do sistema solar contratada na CCB.",
     "Identica - e a mesma CCB. Nenhuma garantia e constituida no ambito do CRI.",
     "Neutro", "'Nao serao constituidas garantias no ambito dos CRI diretamente' nas laminas de CRI-I, III e V.",
     "Historico de execucao e recuperacao efetiva sobre equipamento retomado."),
    ("Acesso a varejo PF",
     "Fechado - as cotas vao a investidor profissional e qualificado.",
     "Aberto apos 180 dias do fim da oferta; 989 pessoas fisicas so na serie Super Senior de CRI-I.",
     "CRI", "Restricao a livre negociacao das laminas e tabelas de subscritores do Anuncio de Encerramento.",
     "Nada - a diferenca e documentada."),
]

# ============================================================ Lacunas
LACUNAS_COLS = ["prioridade", "o_que_falta", "pergunta_que_responderia", "a_quem_pedir", "aba_afetada"]
LACUNAS = [
    ("1", "Confirmacao independente, no cadastro CVM e no Fundos.NET, de que nao existe FIDC Solfacil VIII nem emissao de CRI posterior a 31/07/2026",
     "O universo de 7 FIDCs e 6 CRIs esta completo na data-base?", "CVM - Cadastro de Fundos e Fundos.NET", "01_Veiculos; 16_Conflitos"),
    ("2", "Termos de Securitizacao das 1a, 3a e 4a emissoes Kanastra e das 174a e 177a VERT",
     "Quais FIDCs cederam para cada CRI, qual a Ordem de Alocacao e quais os gatilhos numericos de cada operacao?",
     "CVM - Fundos.NET; Kanastra; VERT", "06_Waterfall; 09_Eventos; 11_Matriz_FIDC_CRI"),
    ("3", "Anuncios de Encerramento das 3a e 4a emissoes Kanastra e da 174a VERT",
     "Quanto foi efetivamente subscrito e quem subscreveu, por tipo de investidor?", "CVM - Ofertas publicas",
     "02_Series; 10_Subscritores"),
    ("4", "Ledger de cessoes por lote, com data, volume, preco e composicao",
     "Qual o preco efetivo de cessao e houve selecao adversa na escolha do pool?", "Solfacil / gestoras dos FIDCs",
     "11b_Cessoes; 14_Antes_Depois"),
    ("5", "Tape de CCBs com originacao, score, parcelas, pre-pagamento e recuperacao",
     "Como e a performance por safra e qual o WAM observado de cada pool?", "Solfacil, como originadora e agente de cobranca",
     "05_Prazos_WAM; 08_PDD; 14_Antes_Depois"),
    ("6", "Curva DI futura da B3 e inflacao implicita das NTN-B em cada data-base de emissao",
     "Qual o custo all-in de cada estrutura na mesma unidade?", "B3 e ANBIMA", "12_Custo_Captacao"),
    ("7", "Regulamentos vigentes dos sete FIDCs, com os suplementos de classe",
     "Qual a redacao literal dos criterios de elegibilidade e dos testes de saque da subordinada por fundo?",
     "CVM - Fundos.NET", "03_Elegibilidade; 07_Subordinada"),
    ("8", "Demonstrativos dos testes de subordinacao e cobertura na data de cada amortizacao subordinada",
     "As saidas de principal da subordinada respeitaram os pisos e as reservas em cada competencia?",
     "Administradores dos FIDCs", "07_Subordinada"),
    ("9", "Posicao de titulares por ISIN na B3 e no escriturador",
     "Qual a concentracao atual e existe mercado secundario?", "B3; Oliveira Trust como escriturador", "10_Subscritores"),
    ("10", "Memoria contabil da queda de PL do FIDC VI em julho de 2026",
     "Quanto da variacao de R$ 226,3 mi foi cessao, ajuste de valor ou distribuicao?", "Administrador do FIDC VI",
     "14_Antes_Depois"),
]

# ============================================================ 14_Antes_Depois
ANTES_DEPOIS_COLS = ["fidc", "competencia", "posicao_relativa_ao_evento", "pl_Rmi", "carteira_Rmi",
                     "outros_ativos_liquidos_Rmi", "pdd_pct_carteira", "saldo_90d_pct_carteira",
                     "evento", "fonte_id", "status"]
ANTES_DEPOIS = [
    ("FIDC-VI", "2026-06-30", "t-1", "437.4", "399.3", "103.1", ND, ND,
     "Competencia anterior ao take-out da VERT 177a", "ANX-DECK", "Documentado"),
    ("FIDC-VI", "2026-07-31", "t=0", "211.1", "147.7", "135.5", "48,8", "8,4",
     "Take-out VERT 177a (emissao em 31/07/2026)", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "2026-06-30", "t-1", "564.7", "544.1", "21.6", ND, ND,
     "Competencia anterior ao take-out da VERT 177a", "ANX-DECK", "Documentado"),
    ("FIDC-VII", "2026-07-31", "t=0", "619.6", "446.1", "174.6", "0,2", "0,0",
     "Take-out VERT 177a; fluxo liquido de cotas de +R$ 42,4 mi", "ANX-DECK", "Documentado"),
]

NOTA_ANTES_DEPOIS = (
    "So uma janela de duas competencias e observavel, e apenas para os FIDCs VI e VII. A carteira dos "
    "dois cai R$ 349,0 mi juntos e outros ativos liquidos sobem R$ 185,4 mi, o que e consistente com "
    "uma cessao - mas o informe do FIDC VI nao decompoe a queda de PU e PL. O que os dados NAO permitem "
    "afirmar: se a qualidade do que ficou piorou. Sem tape por CCB nao ha como separar cherry-pick de "
    "simples mudanca de denominador - a PDD/carteira de 48,8% no VI pode ser deterioracao real ou efeito "
    "de ter vendido a parte boa da carteira. As competencias t-3 a t+3 pedidas nao existem: o take-out "
    "e de 31/07/2026 e a ultima competencia disponivel e a propria."
)
