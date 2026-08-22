# -*- coding: utf-8 -*-
"""Inventário de fontes do estudo CRI x FIDC Solfácil.

Cada linha de dado dos entregaveis carrega um fonte_id que resolve aqui.
"""

DATA_BASE_TRABALHO = "2026-08-22"

FONTES = [
    # fonte_id, documento, tipo, url, data_acesso, data_base, trecho_pagina, status
    ("ANX-ENC-K1", "Anúncio de Encerramento da 1ª emissão de CRI da Kanastra Securitizadora S.A. (CRI Solfácil I)",
     "Documento de oferta CVM (Res. CVM 160, art. 76)",
     "Anexo desta conversa; original em CVM/Fundos.NET e kanastra.com.br/securitizadora",
     "2026-08-22", "2024-02-23", "p.1 quantidades e séries; p.2 consórcio e escriturador; p.2-4 tabelas 6.1 a 6.4 de subscritores", "Obtido"),

    ("ANX-CM-K2", "Comunicado ao Mercado - resultado do bookbuilding da 2ª emissão de CRI da Kanastra (CRI Solfácil II)",
     "Comunicado ao mercado CVM (Res. CVM 160, art. 61 par.4 e art. 13)",
     "Anexo desta conversa; original em CVM/Fundos.NET e Itaú.com.br/itaubba-pt/ofertas-públicas",
     "2026-08-22", "2024-06-20", "p.1 coordenadores e sucessão Itaú BBA; p.2 quantidades e taxas finais por série; p.3 classificação ANBIMA", "Obtido"),

    ("ANX-LAM-K1", "Lâmina da Oferta de CRI da 1ª emissão da Kanastra Securitizadora (CRI Solfácil I)",
     "Lâmina da oferta (Anexo E da Res. CVM 160)",
     "Anexo desta conversa (arquivos 'CRI Solfácil - Lâmina da Oferta.pdf' e 'Memorando Oferta.pdf', idênticos)",
     "2026-08-22", "2024-01-15", "p.1 emissão em 5 séries (1 privada + 4 públicas); p.2-3 intervalos de taxa; p.3 lote adicional e título verde; p.4-5 Critérios de Elegibilidade i a xi", "Obtido"),

    ("ANX-LAM-K3", "Lâmina da Oferta de CRI da 3ª emissão da Kanastra Securitizadora (CRI Solfácil III)",
     "Lâmina da oferta (Anexo E da Res. CVM 160)",
     "Anexo desta conversa; original em CVM/Fundos.NET e kanastra.com.br/securitizadora",
     "2026-08-22", "2025-04-22", "p.2-3 quantidades, ISIN e intervalos de taxa; p.4-5 Critérios de Elegibilidade i a xi; p.8 duration, resgate e garantias", "Obtido"),

    ("ANX-LAM-V174", "Lâmina da Oferta de CRI da 174ª emissão da VERT Companhia Securitizadora (CRI Solfácil V)",
     "Lâmina da oferta (Anexo E da Res. CVM 160)",
     "Anexo desta conversa; original em CVM/Fundos.NET e vert-capital.com",
     "2026-08-22", "2026-04-17", "p.1-3 séries, ISIN e intervalos de taxa; p.4-5 Critérios de Elegibilidade i a xiii; p.6-9 vencimentos, duration, resgate compulsório e garantias", "Obtido"),

    ("ANX-INI-K4", "Anúncio de Início da oferta pública da 4ª emissão de CRI da Kanastra (CRI Solfácil IV)",
     "Documento de oferta CVM (Res. CVM 160, art. 59)",
     "Anexo desta conversa; original em CVM/Fundos.NET",
     "2026-08-22", "2025-09-29", "p.1 séries públicas, montante e ratings preliminares Moody's; p.2 título do Termo de Securitização (7 séries) e agente fiduciário; p.2 cronograma da oferta", "Obtido"),

    ("ANX-PRO-K1", "Prospecto Definitivo da 1ª emissão de CRI da Kanastra Securitizadora (CRI Solfácil I)",
     "Prospecto definitivo de distribuição pública",
     "Anexo desta conversa (arquivos 'Prospecto Definitivo.pdf' e 'CRI Solfácil - Prospecto Definitivo - 1emissao.pdf', idênticos)",
     "2026-08-22", "2024-01-15", "capa ISIN e montante; sec. 11.1.2 cedentes FIDC II e IV; definições Efeito Vagão, Taxa Média Mínima de Retorno e tabela de PDD por faixa de atraso", "Obtido"),

    ("ANX-PRO-K2", "Prospecto Definitivo da 2ª emissão de CRI da Kanastra Securitizadora (CRI Solfácil II)",
     "Prospecto definitivo de distribuição pública",
     "Anexo desta conversa (arquivo 'Prospecto Definitivo Rating.pdf')",
     "2026-08-22", "2024-06-25", "capa ISIN e montante R$ 727,5 mi; definições de Cedentes (FIDC II e IV), Taxa Média Mínima de Retorno 21% a.a. e tabela de PDD", "Obtido"),

    ("ANX-TS2-K2", "2o Aditamento ao Termo de Securitização da 2ª emissão de CRI da Kanastra, consolidado e registrado na JUCEMG",
     "Termo de securitização consolidado (registro JUCEMG no 12803230, 10/06/2025)",
     "Anexo desta conversa (arquivo '2 ADT CRI Solfácil II Registrado.pdf')",
     "2026-08-22", "2025-05-30", "cl. 6.5.1 ordem pró-rata (a)-(cc); cl. 6.5.2 ordem sequencial (a)-(aa); cl. 6.5.3-6.5.6 gatilhos; definições de Razões de Cobertura e Índice de Atraso de Estoque; Anexo I cronograma de pagamentos", "Obtido"),

    ("ANX-DECK", "Deck 'Solfácil | Crédito Estruturado - Warehouses FIDC e take-outs CRI', 36 slides",
     "Análise de crédito interna consolidando CVM (cadastro, informe mensal FIDC e CRI, ofertas), Fundos.NET, B3, Vortx e ANBIMA",
     "Anexo desta conversa (arquivo 'Solfacil_Analise_Credito_Definitiva_2026-08-22.pptx')",
     "2026-08-22", "2026-08-21", "sl.7-8 FIDCs I-VII; sl.9-10 seis operações de CRI; sl.15/19/34 amortização observada; sl.18 curvas de PDD; sl.28-33 anexos A1 e A2 com as 34 séries", "Obtido"),

    ("ANX-RES-XP", "Relatorio 'Solfácil - Análise de Crédito', Research Renda Fixa, 12 páginas",
     "Relatorio de research de terceiro (encomendado pela companhia, conforme registro no próprio deck)",
     "Anexo desta conversa (arquivo 'Análise-de-Crédito-Solfácil-4.pdf')",
     "2026-08-22", "2026-04-28", "p.1 perfil da companhia, rede de integradores e originação acumulada", "Obtido"),

    ("ANX-ANB-SAFRA", "Atualização Mensal ANBIMA - Crédito Privado, Safra Credit Research",
     "Relatorio de mercado (contexto de estoque e emissões)",
     "Anexo desta conversa (arquivo 'PROSPECT-36079.pdf')",
     "2026-08-22", "2026-07-27", "p.1 mercado primario de renda fixa 2T26; usado apenas como contexto de mercado", "Obtido"),

    # Fontes procuradas e nao obtidas - ausencia confirmada e informacao
    ("BUSCA-FIDC8", "Busca por FIDC Solfácil VIII ou posterior no cadastro CVM de fundos",
     "Verificação de completude do universo",
     "Não realizada nesta sessão por ausência de acesso a rede; a verificação mais recente consta do deck",
     "2026-08-22", "2026-07-31", "Deck sl.7: '0 fundos >=VIII localizados' em 31/07/2026", "Não localizado - ver Conflitos/Lacunas"),

    ("BUSCA-CRI7", "Busca por emissão de CRI Solfácil posterior a 31/07/2026 (Kanastra, VERT ou outra securitizadora)",
     "Verificação de completude do universo",
     "Não realizada nesta sessão por ausência de acesso a rede; escopo público do deck encerra em 21/08/2026",
     "2026-08-22", "2026-08-21", "Deck sl.1: 'Escopo público até 21/08/2026'; a VERT 177ª e a operação mais recente identificada", "Não localizado - ver Conflitos/Lacunas"),

    ("FALTA-ENC-K3K4V174", "Anúncios de Encerramento das 3ª e 4ª emissões Kanastra e da 174a VERT",
     "Documento de oferta CVM (Res. CVM 160, art. 76)",
     "Não anexado; obtível em CVM/Fundos.NET",
     "2026-08-22", "n/d", "Necessário para montante subscrito e tabelas de subscritores dessas operações", "Não localizado"),

    ("FALTA-TS-K1K3K4V", "Termos de Securitização das 1ª, 3ª e 4ª emissões Kanastra e das 174a/177a VERT",
     "Termo de securitização e aditamentos",
     "Não anexados; obtíveis em CVM/Fundos.NET e nos sites da Kanastra e da VERT",
     "2026-08-22", "n/d", "Necessários para nomear os FIDCs cedentes, a Ordem de Alocação e os gatilhos numéricos dessas operações", "Não localizado"),

    ("FALTA-REG-FIDC", "Regulamentos vigentes dos FIDCs Solfácil I a VII",
     "Regulamento de fundo e suplementos de classe",
     "Não anexados; obtíveis em CVM/Fundos.NET",
     "2026-08-22", "n/d", "Necessários para a redação literal dos critérios de elegibilidade e dos testes de saque da subordinada por fundo", "Não localizado - dados do deck usados com marcação de status"),

    ("ANX-TS-V177", "Termo de Securitização de CRI da 177ª emissão da VERT Companhia Securitizadora (CRI Solfácil VI)",
     "Termo de securitização, versão final",
     "Anexo desta conversa; original em data.vert-capital.app e CVM/Fundos.NET",
     "2026-08-22", "2026-07-20", "cl. 5.6.3 e 5.6.4 séries e quantidades; cl. 5.6.6 montante por série; cl. 5.6.8 data de emissão; cl. 5.6.11 classificação ANBIMA; cl. 6.2 remuneração; definições de Cedentes e Cedentes Fundos", "Obtido"),

    ("ANX-PRO-V174", "Prospecto Definitivo republicado da 174ª emissão de CRI da VERT (CRI Solfácil V)",
     "Prospecto definitivo de distribuição pública, republicação",
     "Anexo desta conversa; original em data.vert-capital.app e CVM/Fundos.NET",
     "2026-08-22", "2026-05-20", "capa e p.1 quantidades efetivamente emitidas por série e montante de R$ 456.481.000,00; taxas contratadas por série", "Obtido"),

    ("ANX-PRO-K3", "Prospecto Definitivo da 3ª emissão de CRI da Kanastra Securitizadora (CRI Solfácil III)",
     "Prospecto definitivo de distribuição pública",
     "Anexo desta conversa; original em documentos.kanastra.com.br e CVM/Fundos.NET",
     "2026-08-22", "2025-06-06", "capa com montante de R$ 727.500.000,00 e ISINs; quantidades por série confirmando o exercício integral do lote adicional de 25%; ratings definitivos da Moody's", "Obtido"),

    ("ANX-CM-K4", "Comunicado ao Mercado da 4ª emissão Kanastra - correção das tabelas de amortização e do cronograma",
     "Comunicado ao mercado CVM (Res. CVM 160, art. 13)",
     "Anexo desta conversa; original em documentos.kanastra.com.br",
     "2026-08-22", "2025-09-04", "correção das datas de pagamento de amortização ordinária do Prospecto Preliminar e ajuste da 2ª data de liquidação de 15/11 para 17/11/2025", "Obtido"),

    ("ANX-ESC-DEB", "Escritura da 1ª emissão de debêntures simples da Amazônia Solar Companhia Securitizadora de Créditos Financeiros",
     "Escritura de emissão de debêntures, versão assinada",
     "Anexo desta conversa; original em data.vert-capital.app (emissão 246)",
     "2026-08-22", "2022-02-18", "cl. 3.3 duas séries e subordinação da 2ª; cl. 3.4 valor total de R$ 60,0 mi; cl. 3.5 destinação à aquisição de CCBs; cl. 3.6.5 prazos e datas de vencimento; cl. 3.7.2 remuneração", "Obtido"),

    ("ANX-RMA-DEB", "Relatório Mensal de Acompanhamento da 1ª emissão de debêntures - competência de julho de 2026",
     "Relatório do agente fiduciário (Vórtx)",
     "Anexo desta conversa; original em data.vert-capital.app (emissão 246)",
     "2026-08-22", "2026-07-31", "dados gerais da emissão e das séries; PU, quantidade em circulação e saldo por série; fluxo de caixa mensal; carteira de créditos acumulada", "Obtido"),

    ("FALTA-DEB-SFCL", "Documentos das debêntures SFCL11, SFCL21, SFCL31 e SFCL41",
     "Escritura e relatórios de emissão de debêntures",
     "Não anexados; a análise de crédito de 21/08/2026 registra que somam R$ 150 mi e não têm taxa indicativa ANBIMA",
     "2026-08-22", "n/d", "Segunda operação de debêntures do grupo, distinta da emissão da Amazônia Solar; fora do acervo", "Não localizado"),

    ("FALTA-CM-K4-BB", "Comunicado ao Mercado com o resultado do bookbuilding da 4ª emissão Kanastra",
     "Comunicado ao mercado CVM",
     "Não anexado; o comunicado de 04/09/2025 no acervo trata de correção de cronograma, não do bookbuilding",
     "2026-08-22", "2025-09-26", "Necessário para as taxas apuradas por série da 4ª emissão", "Não localizado"),
]

FONTES_COLS = ["fonte_id", "documento", "tipo_de_fonte", "url_ou_origem",
               "data_de_acesso", "data_base", "trecho_pagina", "status"]
