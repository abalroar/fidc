"""Build an auditable Top-20 FIDC curation package.

This file intentionally lives under ``outputs/analysis``.  It does not mutate
the presentation, workbook, or production pipeline.  Ranking fields come from
the May-2026 CVM snapshot; documentary descriptions are conservative manual
curation of official FundosNet files listed in ``SOURCE_DOCS``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "analysis"
UNIVERSE_PATH = ROOT / "data" / "industry_study" / "universe_latest.csv"
ANBIMA_PATH = ROOT / "data" / "industry_study" / "industry_anbima_classification.csv.gz"
DOC_LEDGER_PATHS = [
    ROOT / "data" / "industry_study" / "industry_large_fund_documents.csv.gz",
    OUT / "tmp_industry" / "industry_large_fund_documents.csv.gz",
]

AS_OF = "2026-05"
CONSULTED_AT = "2026-07-16"
CVM_DATASET_URL = "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal"
CVM_DATA_URL = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/"
ANBIMA_URL = "https://data.anbima.com.br/"
FUNDOSNET_VIEW = "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={doc_id}&cvm=true"
FUNDOSNET_DOWNLOAD = "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={doc_id}"
FUNDOSNET_MANAGER = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM"
    "?cnpjFundo={cnpj}"
)


def only_digits(value: Any) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def normalize_cnpj(value: Any) -> str:
    raw = only_digits(value)
    return raw.zfill(14) if raw else ""


def format_cnpj(value: Any) -> str:
    value = normalize_cnpj(value)
    if len(value) != 14:
        return value
    return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"


def bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "t", "sim", "yes"})


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return " ".join(str(value).split())


@dataclass(frozen=True)
class Emission:
    date: str
    event: str
    amount_brl: float | None
    source_document_id: int
    note: str = ""


def em(date: str, event: str, amount_brl: float | None, doc: int, note: str = "") -> Emission:
    return Emission(date, event, amount_brl, doc, note)


# ``supports`` is copied verbatim to the source ledger.  The regulation chosen
# is the latest substantive version found in the local official corpus, except
# where the only available primary evidence is explicitly identified.
SOURCE_DOCS: dict[str, list[dict[str, Any]]] = {
    "09195235000150": [
        {"id": 792797, "supports": "cedente; devedor; recebíveis; fluxo de cobrança; subclasses; prestadores"},
    ],
    "26287464000114": [
        {"id": 1066031, "supports": "cedentes; devedores; recebíveis de pagamento e sub-rogação; classes; subordinação"},
    ],
    "62393679000183": [
        {"id": 1117954, "supports": "cedente; devedores; recebíveis; classes; subordinação"},
        {"id": 1166893, "supports": "oferta primária de 2026; volume; séries"},
        {"id": 993253, "supports": "oferta secundária de 2025; volume; séries"},
    ],
    "53286499000101": [
        {"id": 579249, "supports": "política de investimento; instrumentos de crédito; prestadores"},
        {"id": 579248, "supports": "constituição e primeira emissão; valor não localizado"},
    ],
    "53263761000100": [
        {"id": 830304, "supports": "política ampla de NPL, precatórios e créditos litigiosos; subclasses"},
    ],
    "52242420000188": [
        {"id": 938243, "supports": "originação; CCB; FGTS e consignado; devedores"},
        {"id": 523931, "supports": "constituição e primeira emissão de 2023; volume"},
    ],
    "65473848000183": [
        {"id": 1142758, "supports": "incorporação de parcela cindida da classe BTG Empresas"},
        {"id": 1196918, "supports": "relatório 1T26; aquisição de precatórios federais; cessões; garantias; pré-pagamentos"},
    ],
    "52610624000124": [
        {"id": 794164, "supports": "cedente; devedores; energia; classes; subordinação"},
        {"id": 551833, "supports": "constituição em 2023; índice histórico de subordinação de 15%"},
    ],
    "28169275000172": [
        {"id": 1149521, "supports": "cedentes; PagSeguro como devedor; transações de pagamento; subordinação"},
        {"id": 1148251, "supports": "oferta de 2026; volume e série"},
        {"id": 773514, "supports": "encerramento e integralização da oferta da 3ª série em 2024"},
    ],
    "63953620000165": [
        {"id": 1222863, "supports": "Parati como endossante; CCB consignada privada; Dataprev; subordinação"},
        {"id": 1087883, "supports": "colocação privada de cotas; volume agregado das classes"},
    ],
    "26286939000158": [
        {"id": 1017493, "supports": "cedentes; Cielo como devedor; transações de pagamento; classes; subordinação"},
        {"id": 1026980, "supports": "oferta de 2025; volume e série"},
    ],
    "53216449000158": [
        {"id": 880741, "supports": "política ampla de NPL, precatórios e créditos litigiosos; cotas pari passu"},
        {"id": 587879, "supports": "anúncio de início de oferta de 2024; texto não extraído"},
    ],
    "50906397000153": [
        {"id": 939418, "supports": "regulamento consolidado em ato de 2025; CCB; FGTS e consignado; subclasse única"},
        {"id": 483282, "supports": "constituição e primeira emissão de 2023; volume"},
    ],
    "29225241000110": [
        {"id": 784984, "supports": "NPL, precatórios e créditos litigiosos; cota única pari passu"},
    ],
    "63700113000110": [
        {"id": 1074015, "supports": "crédito privado multicarteira; rótulo ANBIMA documental; subclasse única sem índice"},
        {"id": 1057972, "supports": "incorporação decorrente de cisão parcial; valor e quantidade de cotas"},
    ],
    "42922136000107": [
        {"id": 1159092, "supports": "SHPP como originadora; empréstimos e recebíveis de pagamento; cotas pari passu"},
    ],
    "32527650000186": [
        {"id": 1203914, "supports": "cedentes usuários PicPay; PicPay como devedor; pagamentos; subordinação"},
    ],
    "30576260000170": [
        {"id": 702468, "supports": "transformação de FIC-FIDC em FIDC direto em julho de 2024"},
        {"id": 703355, "supports": "política de investimento direta; instrumentos amplos; ausência de subordinação"},
    ],
    "51152102000163": [
        {"id": 750230, "supports": "direitos não padronizados multissetoriais; classes; subordinação"},
        {"id": 487085, "supports": "constituição e primeira emissão; volume máximo"},
        {"id": 1187381, "supports": "cotista único; administradora em liquidação extrajudicial em maio de 2026"},
    ],
    "34197588000137": [
        {"id": 974471, "supports": "política multicarteira; precatórios; NPL; classes; subordinação"},
    ],
}


CURATION: dict[str, dict[str, Any]] = {
    "09195235000150": {
        "documentary_economic_segment": "Recebíveis comerciais de empresas do Sistema Petrobras",
        "cedent_originator": "Empresas integrantes do Sistema Petrobras que cedam direitos ao fundo; o regulamento não traz lista fechada de cedentes.",
        "debtor_profile": "Pessoas jurídicas às quais as cedentes prestam serviços ou alienam bens.",
        "receivables": "Direitos originados em operações industriais, comerciais e de prestação de serviços das empresas do Sistema Petrobras.",
        "functioning": "As empresas do Sistema Petrobras cedem os recebíveis ao fundo. O pagamento dos devedores passa por conta escrow no Banco do Brasil; as cedentes podem atuar na cobrança dos créditos inadimplidos.",
        "classes_subordination": "Subclasses sênior e subordinada. Enquanto houver cota sênior em circulação, deve existir ao menos uma cota subordinada; o regulamento não fixa razão percentual adicional.",
        "guarantees": "Garantia específica dos recebíveis não identificada no regulamento consultado; o investimento não conta com garantia geral do administrador, gestor ou FGC.",
        "emissions": [],
        "curation_status": "documentado_com_lacuna_de_emissao",
        "not_identified": "lista nominal de cedentes; sacados individuais; emissão pública relevante; garantias por crédito",
        "classification_note": "A leitura documental é compatível com o Tipo/Foco oficial ANBIMA.",
        "provider_note": "Administração e gestão têm o mesmo CNPJ; custódia é Banco do Brasil, CNPJ distinto. Não é monoestrutura pela definição estrita de mesma entidade legal nas três funções.",
    },
    "26287464000114": {
        "documentary_economic_segment": "Meios de pagamento e recebíveis de arranjos de pagamento",
        "cedent_originator": "Estabelecimentos credenciados, representados por Stone/Pagar.me ou adquirente autorizada, e instituições financeiras parceiras; o regulamento cita a Stone Sociedade de Crédito Direto no fluxo de sub-rogação.",
        "debtor_profile": "Stone, Pagar.me e demais adquirentes/subadquirentes autorizadas nos contratos da operação.",
        "receivables": "Unidades/recebíveis de transações de pagamento e créditos sub-rogados de instituições financeiras parceiras.",
        "functioning": "A classe adquire recebíveis dos estabelecimentos e direitos sub-rogados de parceiros financeiros, com revolvência e pagamento pelos participantes do arranjo de pagamento.",
        "classes_subordination": "Cotas sênior, mezanino A, mezanino B e subordinada; razão total mínima de subordinação de 20% do PL da classe.",
        "guarantees": "O regulamento admite cessão fiduciária para assegurar promessa de cessão; não há garantia geral de prestadores ou FGC.",
        "emissions": [],
        "curation_status": "documentado_com_lacuna_de_emissao",
        "not_identified": "lista integral de estabelecimentos cedentes; volume/data de emissão pública relevante",
        "classification_note": "O cadastro ANBIMA traz Financeiro/Crédito Pessoal; o regulamento consultado descreve predominantemente recebíveis de meios de pagamento. Manter as duas leituras separadas.",
        "provider_note": "Administração e custódia têm o mesmo CNPJ; gestão é Oliveira Trust Servicer, CNPJ distinto. Não é monoestrutura pela definição estrita de mesma entidade legal nas três funções.",
    },
    "62393679000183": {
        "documentary_economic_segment": "Meios de pagamento e adquirência",
        "cedent_originator": "CloudWalk Instituição de Pagamento.",
        "debtor_profile": "Emissores e instituições de pagamento responsáveis pela liquidação das transações capturadas no sistema CloudWalk.",
        "receivables": "Valores devidos pelos emissores à CloudWalk, como credenciadora, decorrentes de transações de cartão realizadas por estabelecimentos.",
        "functioning": "A CloudWalk cede à classe recebíveis de liquidação de transações de pagamento; os fluxos dos emissores alimentam o pagamento das cotas.",
        "classes_subordination": "Sênior, mezanino A, mezanino B e júnior. O regulamento contém índices de subordinação por fase e marcos ligados à oferta da 2ª série; a fase aplicável em mai/26 não foi reconciliada e não deve ser resumida como percentual único.",
        "guarantees": "Subordinação por subclasses; garantia específica adicional não identificada nos documentos selecionados.",
        "emissions": [
            em("2026-04-20", "encerramento de oferta primária da 2ª série", 5_500_000_000.0, 1166893),
            em("2025-09-16", "encerramento de oferta secundária da 1ª série", 4_200_000_000.0, 993253, "Oferta secundária; não representa captação nova da classe."),
        ],
        "curation_status": "documentado",
        "not_identified": "concentração atual por emissor/devedor; garantias adicionais por crédito",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a estrutura econômica documental é de meios de pagamento.",
    },
    "53286499000101": {
        "documentary_economic_segment": "Crédito privado multicarteira",
        "cedent_originator": "Não identificado como entidade única; os instrumentos podem ser adquiridos de emissores ou no mercado, conforme seleção do gestor.",
        "debtor_profile": "Emissores, devedores, coobrigados ou garantidores dos instrumentos de crédito da carteira.",
        "receivables": "Debêntures, CRI, CRA, notas comerciais, letras financeiras, LCI, LCA, CDB, CCB, CDCA, cotas de FIDC e outros direitos de crédito previstos no regulamento.",
        "functioning": "Carteira discricionária de crédito privado, sem um único cedente ou fluxo operacional padronizado identificado no regulamento.",
        "classes_subordination": "Classe e subclasse únicas, sem cotas subordinadas no regulamento consultado.",
        "guarantees": "Variam por instrumento; não há pacote único de garantias descrito para toda a carteira.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes e devedores atuais; composição efetiva; subordinação; montante da primeira emissão",
        "classification_note": "A leitura documental é compatível com Outros/Multicarteira Outros.",
    },
    "53263761000100": {
        "documentary_economic_segment": "Política permite NPL, precatórios e créditos litigiosos multissetoriais",
        "cedent_originator": "Pessoas físicas, jurídicas ou fundos que transfiram os direitos; nomes não identificados no regulamento.",
        "debtor_profile": "União, estados, municípios, autarquias, fundações e demais devedores de créditos vencidos ou litigiosos, conforme o direito adquirido.",
        "receivables": "Precatórios e créditos públicos; créditos vencidos; direitos em litígio, penhorados ou dados em garantia; direitos futuros e outros não padronizados permitidos.",
        "functioning": "O gestor seleciona direitos judiciais/NPL e outros créditos não padronizados. O regulamento permite aquisição com ou sem coobrigação do cedente.",
        "classes_subordination": "O regulamento prevê subclasses e apêndice de cotas subordinadas; eventual índice deve constar do apêndice/suplemento e não foi identificado com segurança.",
        "guarantees": "Podem existir no direito adquirido; não há garantia uniforme para toda a carteira.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes e devedores atuais; concentração por tese; índice de subordinação; emissões relevantes",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a política permite carteira judicial/NPL ampla.",
    },
    "52242420000188": {
        "documentary_economic_segment": "Crédito consignado e antecipação do saque-aniversário FGTS",
        "cedent_originator": "Instituições financeiras que concedam as CCBs; nomes individuais não identificados no regulamento selecionado.",
        "debtor_profile": "Pessoas físicas, incluindo beneficiários de INSS/Auxílio Brasil e trabalhadores com saldo de FGTS, conforme a modalidade da CCB.",
        "receivables": "Parcelas vincendas de CCB de empréstimo pessoal com cessão fiduciária do saque-aniversário FGTS ou consignação operacionalizada pela Dataprev.",
        "functioning": "A classe adquire ou recebe por endosso parcelas de CCB; o pagamento ocorre pelo fluxo do FGTS/CEF ou por consignação processada pela Dataprev.",
        "classes_subordination": "Classe única com cotas pari passu no regulamento atual; não há índice de subordinação.",
        "guarantees": "Cessão fiduciária do saque-aniversário nas CCB de FGTS; nas demais modalidades, consignação conforme convênio aplicável.",
        "emissions": [em("2023-09-19", "aprovação de primeira emissão privada", 2_500_000_000.0, 523931, "Valor máximo aprovado; o documento não comprova colocação integral.")],
        "curation_status": "documentado_com_lacuna_de_composicao",
        "not_identified": "cedentes individuais; composição atual entre FGTS e consignado; valor efetivamente colocado na emissão privada",
        "classification_note": "A leitura documental é compatível com Financeiro/Crédito Pessoal do snapshot, embora o foco contratual seja mais específico.",
    },
    "65473848000183": {
        "documentary_economic_segment": "Exposição inclui precatórios federais no 1T26; política integral da carteira não identificada",
        "cedent_originator": "Não identificado nos documentos selecionados.",
        "debtor_profile": "Entes públicos responsáveis pelos precatórios federais adquiridos no 1T26; nomes não identificados.",
        "receivables": "O relatório trimestral confirma que a exposição incluiu precatórios federais no 1T26. O documento não demonstra que toda a carteira era de precatórios e não há evidência primária suficiente para classificá-la como financiamento de veículos.",
        "functioning": "A classe recebeu parcela cindida da Classe Única do BTG Empresas em março de 2026. No 1T26 houve novas cessões definitivas, alterações de garantias, pré-pagamentos e alienação parcial de direitos.",
        "classes_subordination": "Não identificado nos documentos selecionados.",
        "guarantees": "O relatório confirma alteração de garantias no trimestre, mas não descreve seu conteúdo.",
        "emissions": [em("2026-03-18", "incorporação de parcela cindida da Classe Única do BTG Empresas", None, 1142758, "Evento societário/patrimonial; não é oferta pública.")],
        "curation_status": "lacunas_materiais",
        "not_identified": "regulamento completo; cedentes; devedores individuais; natureza integral da carteira; classes; subordinação; garantias; emissões",
        "classification_note": "O nome PAN AUTO não é evidência de crédito automotivo. O classificador local baseado no nome deve ser descartado; a única evidência econômica primária localizada foi a aquisição de precatórios federais no 1T26.",
    },
    "52610624000124": {
        "documentary_economic_segment": "Recebíveis de comercialização de energia",
        "cedent_originator": "XP Comercializadora de Energia S.A. — CNPJ 34.475.373/0001-30.",
        "debtor_profile": "Contrapartes compradoras nos contratos de compra e venda de energia elétrica.",
        "receivables": "Fluxos presentes e futuros decorrentes de contratos de comercialização de energia elétrica.",
        "functioning": "A XP Comercializadora cede os recebíveis de contratos de energia; os pagamentos dos devedores transitam por conta escrow da operação.",
        "classes_subordination": "Cotas sênior e subordinada. O regulamento vigente em 21/11/2024 fixa índice mínimo de 10% do PL; o instrumento de constituição de 19/10/2023 trazia 15%, indicando alteração contratual entre as versões.",
        "guarantees": "O regulamento admite acessórios e garantias dos contratos, sem garantia geral de prestadores/FGC.",
        "emissions": [],
        "curation_status": "documentado_com_lacuna_de_emissao",
        "not_identified": "devedores individuais; concentração atual; montante da primeira emissão",
        "classification_note": "A leitura documental é compatível com Agro, Indústria e Comércio/Recebíveis Comerciais.",
    },
    "28169275000172": {
        "documentary_economic_segment": "Recebíveis de arranjos de pagamento",
        "cedent_originator": "Estabelecimentos credenciados ao sistema PagSeguro.",
        "debtor_profile": "PagSeguro, como devedor dos valores de liquidação devidos aos estabelecimentos.",
        "receivables": "Unidades/recebíveis de transações de pagamento a débito e crédito, à vista ou parceladas, capturadas e liquidadas pelo sistema PagSeguro.",
        "functioning": "Os estabelecimentos cedem à classe seus recebíveis contra PagSeguro; a liquidação das transações alimenta o caixa da classe.",
        "classes_subordination": "Cotas sênior, mezanino e subordinada; razão mínima de cotas subordinadas de 50% do PL da classe.",
        "guarantees": "Reforço estrutural pela subordinação; garantia adicional uniforme não identificada.",
        "emissions": [
            em("2026-03-30", "início de oferta da 4ª série sênior", 1_000_000_000.0, 1148251, "Valor ofertado; o anúncio de início não comprova colocação."),
            em("2024-11-06", "encerramento da oferta da 3ª série sênior", 1_000_000_000.0, 773514, "Documento informa 1.000.000 de cotas subscritas e integralizadas."),
        ],
        "curation_status": "documentado",
        "not_identified": "lista de estabelecimentos cedentes; concentração atual; garantias adicionais",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a estrutura econômica documental é de meios de pagamento.",
    },
    "63953620000165": {
        "documentary_economic_segment": "Crédito consignado privado",
        "cedent_originator": "Parati Crédito, Financiamento e Investimento S.A. — CNPJ 03.311.443/0001-91, como endossante das CCB.",
        "debtor_profile": "Pessoas físicas empregadas em empresas privadas, tomadoras de empréstimos consignados.",
        "receivables": "Parcelas de CCB de empréstimo consignado privado, processadas pela infraestrutura Dataprev/CEF prevista no regulamento.",
        "functioning": "A Parati origina e endossa eletronicamente as CCB à classe, sem coobrigação geral; o desconto em folha direciona o pagamento das parcelas.",
        "classes_subordination": "Cotas sênior e subordinada. Índice mínimo de 1% do PL e índice-alvo de 10%; os dois parâmetros não são equivalentes.",
        "guarantees": "Desconto consignado em folha; cessão/endosso definitivo sem proteção geral contra inadimplência.",
        "emissions": [
            em("2026-01-08", "aprovação de colocação privada de cotas sênior em vasos comunicantes", 15_000_000_000.0, 1087883, "Valor máximo aprovado entre classes; não comprova captação nem pertence integralmente a esta classe."),
            em("2026-01-08", "aprovação de colocação privada de cotas subordinadas da classe Consignado Privado", 7_000_000.0, 1087883, "Valor máximo aprovado; não comprova colocação integral."),
        ],
        "curation_status": "documentado_com_ressalva_de_emissao",
        "not_identified": "empregadores e devedores individuais; parcela do R$15 bi atribuível à classe; concentração atual",
        "classification_note": "Tipo/Foco não identificado no snapshot ANBIMA de 29/12/2025; o anexo documental descreve consignado privado.",
    },
    "26286939000158": {
        "documentary_economic_segment": "Meios de pagamento e adquirência",
        "cedent_originator": "Estabelecimentos credenciados à Cielo.",
        "debtor_profile": "Cielo, como adquirente e devedora dos recebíveis cedidos pelos estabelecimentos.",
        "receivables": "Valores de liquidação de transações de pagamento/unidades de recebíveis processadas no Sistema Cielo.",
        "functioning": "Os estabelecimentos cedem recebíveis contra a Cielo; a Cielo liquida os créditos para a classe conforme os registros da operação.",
        "classes_subordination": "Cotas sênior, mezanino e subordinada; mezanino mais subordinada devem somar ao menos 20% do PL.",
        "guarantees": "Reforço estrutural por subordinação; garantia adicional uniforme não identificada.",
        "emissions": [em("2025-11-03", "encerramento da oferta da 4ª série sênior", 1_000_000_000.0, 1026980)],
        "curation_status": "documentado",
        "not_identified": "estabelecimentos individuais; concentração atual; garantias adicionais",
        "classification_note": "O cadastro ANBIMA traz Financeiro/Multicarteira Financeiro; a estrutura documental é de meios de pagamento.",
    },
    "53216449000158": {
        "documentary_economic_segment": "Política permite NPL, precatórios e créditos litigiosos multissetoriais",
        "cedent_originator": "Pessoas físicas, jurídicas ou fundos que transfiram os direitos; nomes não identificados no regulamento.",
        "debtor_profile": "Entes públicos e demais pessoas físicas/jurídicas devedoras dos direitos adquiridos.",
        "receivables": "Precatórios e créditos públicos; créditos vencidos; direitos litigiosos, penhorados, futuros e outros não padronizados permitidos.",
        "functioning": "A classe adquire carteiras de NPL/direitos judiciais com ou sem coobrigação, segundo seleção do gestor.",
        "classes_subordination": "Cotas em séries pari passu; o regulamento consultado declara ausência de preferência, prioridade ou subordinação entre titulares.",
        "guarantees": "Variam conforme cada direito; não há garantia uniforme de carteira.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes e devedores atuais; composição efetiva; montante da oferta; garantias por crédito",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a política documental permite NPL e precatórios.",
    },
    "50906397000153": {
        "documentary_economic_segment": "Crédito consignado e antecipação do saque-aniversário FGTS",
        "cedent_originator": "Instituições financeiras que concedam as CCB; nomes individuais não identificados no regulamento.",
        "debtor_profile": "Pessoas físicas, incluindo beneficiários de INSS e trabalhadores com saldo de FGTS.",
        "receivables": "Parcelas vincendas de CCB de empréstimo pessoal com garantia do saque-aniversário FGTS ou consignação processada pela Dataprev.",
        "functioning": "A classe adquire CCB/parcelas por cessão ou endosso; CEF/FGTS e Dataprev processam os fluxos conforme a modalidade.",
        "classes_subordination": "Subclasse única de cotas no regulamento consolidado; não há índice de subordinação entre subclasses.",
        "guarantees": "Cessão fiduciária do saque-aniversário nas operações FGTS; consignação nas demais modalidades.",
        "emissions": [em("2023-06-01", "aprovação de primeira emissão privada", 11_000_000_000.0, 483282, "Valor máximo aprovado; o documento não comprova colocação integral.")],
        "curation_status": "documentado",
        "not_identified": "cedentes individuais; composição atual entre FGTS e consignado; concentração por originador",
        "classification_note": "A leitura documental é compatível com Financeiro/Crédito Pessoal, com foco contratual mais específico.",
    },
    "29225241000110": {
        "documentary_economic_segment": "Política permite NPL, precatórios e créditos litigiosos",
        "cedent_originator": "Pessoas jurídicas ou fundos que transfiram os direitos; nomes não identificados no regulamento.",
        "debtor_profile": "Pessoas físicas ou jurídicas, privadas ou públicas, obrigadas nos direitos adquiridos.",
        "receivables": "Créditos em litígio, precatórios e direitos vencidos/inadimplidos já performados.",
        "functioning": "A política permite comprar direitos judiciais/NPL integral ou parcialmente; o regulamento não comprova que esses ativos compunham a carteira em mai/26.",
        "classes_subordination": "Única subclasse de cotas pari passu; sem preferência, prioridade ou subordinação entre titulares.",
        "guarantees": "Variam por direito; não há garantia uniforme da carteira nem garantia geral de prestadores/FGC.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes e devedores atuais; concentração; garantias por crédito; emissões relevantes",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a política documental é de NPL/direitos judiciais.",
    },
    "63700113000110": {
        "documentary_economic_segment": "Crédito privado multicarteira",
        "cedent_originator": "Não há cedente único nomeado; o gestor pode adquirir direitos nos mercados primário e secundário.",
        "debtor_profile": "Devedores/emissores dos instrumentos selecionados; nomes não identificados no regulamento.",
        "receivables": "Direitos creditórios permitidos pelo art. 2º, XII, do Anexo II da RCVM 175, em qualquer setor; o regulamento exclui os direitos não padronizados do inciso XIII.",
        "functioning": "Carteira discricionária de crédito privado, sem concentração setorial contratual e com possibilidade de concentração em um mesmo devedor dentro das condições do regulamento.",
        "classes_subordination": "Subclasse única; o regulamento declara que não observa índice de subordinação.",
        "guarantees": "Variam por instrumento; não há pacote uniforme de garantias.",
        "emissions": [em("2025-12-09", "incorporação decorrente de cisão parcial do NC 2025", 5_299_999_394.29, 1057972, "Foram incorporadas 4.953.498,00000167 cotas; não foi captação em dinheiro.")],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes/devedores atuais; composição e concentração efetivas; emissões relevantes",
        "classification_note": "Não está no snapshot ANBIMA; o regulamento declara Tipo Outros/Foco Multicarteiras Outros. Tratar como evidência documental, não cadastro oficial da fotografia.",
        "anbima_document_type": "Outros",
        "anbima_document_focus": "Multicarteiras Outros",
    },
    "42922136000107": {
        "documentary_economic_segment": "Crédito pessoal e recebíveis de pagamento",
        "cedent_originator": "SHPP Brasil Instituição de Pagamento e Serviços de Pagamentos Ltda. — CNPJ 38.372.267/0001-82 — atua como originadora/correspondente; CCB são endossadas por instituições financeiras parceiras e recebíveis de pagamento são cedidos por estabelecimentos.",
        "debtor_profile": "Pessoas físicas ou jurídicas tomadoras dos empréstimos e participantes das operações de pagamento, conforme o ativo.",
        "receivables": "CCB de empréstimos e unidades de recebíveis de transações de cartão realizadas em estabelecimentos.",
        "functioning": "A SHPP capta e analisa clientes como correspondente dos endossantes; a classe adquire CCB por endosso e recebíveis de pagamento por cessão.",
        "classes_subordination": "Cotas pari passu; o regulamento consultado declara ausência de preferência, prioridade ou subordinação.",
        "guarantees": "Não há garantia uniforme identificada; a transferência é sem coobrigação geral nos contratos descritos.",
        "emissions": [],
        "curation_status": "documentado_com_lacuna_de_emissao",
        "not_identified": "instituições financeiras endossantes; estabelecimentos cedentes; devedores atuais; emissões relevantes",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a política documental combina crédito pessoal e meios de pagamento.",
    },
    "32527650000186": {
        "documentary_economic_segment": "Recebíveis de pagamentos no ecossistema PicPay",
        "cedent_originator": "Usuários finais do PicPay que transferem seus recebíveis à classe por mandato previsto no regulamento.",
        "debtor_profile": "PicPay, responsável pelos pagamentos devidos aos cedentes nas transações abrangidas.",
        "receivables": "Valores de transações de pagamento, cash-in e moeda eletrônica processados no sistema PicPay.",
        "functioning": "Usuários cedem à classe os direitos contra o PicPay; o PicPay efetua os pagamentos que alimentam o caixa da classe.",
        "classes_subordination": "Cotas sênior e subordinadas júnior; razão mínima de subordinação júnior de 10% do PL.",
        "guarantees": "Reforço estrutural por subordinação; garantia adicional uniforme não identificada.",
        "emissions": [],
        "curation_status": "documentado_com_lacuna_de_emissao",
        "not_identified": "cedentes individuais; concentração atual; emissões relevantes; garantias adicionais",
        "classification_note": "O cadastro ANBIMA traz Financeiro/Multicarteira Financeiro; a estrutura documental é de meios de pagamento.",
    },
    "30576260000170": {
        "documentary_economic_segment": "Crédito privado multicarteira",
        "cedent_originator": "Pessoas físicas ou jurídicas titulares dos instrumentos elegíveis; nenhuma entidade única foi identificada.",
        "debtor_profile": "Emissores/devedores dos instrumentos adquiridos; nomes não identificados no regulamento.",
        "receivables": "Direitos e títulos de crédito, valores mobiliários de crédito, instrumentos de securitização e cotas de FIDC previstos na política ampla.",
        "functioning": "O veículo era FIC-FIDC e foi transformado em FIDC direto com vigência em 23/07/2024; desde então a política permite aquisição direta de instrumentos de crédito.",
        "classes_subordination": "Cotas sem preferência, prioridade ou subordinação entre os titulares.",
        "guarantees": "Variam por instrumento; não há pacote uniforme de garantias.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes/devedores atuais; composição efetiva; garantias; emissões relevantes",
        "classification_note": "O cadastro ANBIMA traz Financeiro/Crédito Pessoal; a política documental atual é ampla. A quebra histórica FIC→FIDC em julho de 2024 deve ser tratada explicitamente.",
    },
    "51152102000163": {
        "documentary_economic_segment": "Direitos creditórios não padronizados multissetoriais",
        "cedent_originator": "Empresas de diferentes setores, em recuperação judicial ou não; nomes não identificados no regulamento.",
        "debtor_profile": "Clientes/sacados das cedentes e demais devedores dos direitos adquiridos.",
        "receivables": "Política ampla de direitos financeiros, comerciais, industriais, imobiliários, de serviços, leasing e contratos de performance futura, inclusive não padronizados. Warrants não foram listados por haver conflito interno entre itens do regulamento.",
        "functioning": "A classe compra carteiras de cedentes distintos e setores diversos, sob critérios de elegibilidade e cobrança próprios.",
        "classes_subordination": "Cotas sênior e subordinada; subordinação mínima de 5% do PL após emissão de cotas sênior.",
        "guarantees": "Variam por direito; não há garantia uniforme identificada.",
        "emissions": [em("2023-06-22", "lançamento da primeira oferta", 100_000_000.0, 487085, "Valor máximo; distribuição parcial permitida e colocação integral não comprovada.")],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes/devedores atuais; composição efetiva; garantias por crédito",
        "classification_note": "A leitura documental é compatível com Outros/Multicarteira Outros, com direitos não padronizados amplos. Ata de 06/05/2026 identifica cotista único e administradora em liquidação extrajudicial; reconciliar a denominação dos prestadores com o cadastro CVM.",
        "provider_note": "A ata FundosNet de 06/05/2026 identifica a administradora pelo mesmo CNPJ do snapshot, mas em liquidação extrajudicial e com denominação diferente; a ficha deve mostrar a divergência até reconciliação cadastral.",
    },
    "34197588000137": {
        "documentary_economic_segment": "Política multicarteira permite NPL, precatórios e cotas de outros FIDC",
        "cedent_originator": "Pessoas físicas ou jurídicas que cedam os direitos; nomes não identificados no regulamento.",
        "debtor_profile": "Pessoas físicas, jurídicas e entes públicos, conforme os direitos adquiridos.",
        "receivables": "A política permite títulos de crédito; recebíveis mercantis, de transporte, industriais e de serviços; contratos futuros; precatórios federais; direitos não padronizados; créditos de cedentes em recuperação judicial; e até 100% do PL em cotas de outros FIDC, inclusive mezanino/júnior.",
        "functioning": "A política permite exposição direta a recebíveis/NPL e indireta via cotas de FIDC; o regulamento não comprova a composição efetiva em mai/26.",
        "classes_subordination": "Cotas sênior, mezanino e júnior; índice mínimo de cotas subordinadas de 25% do PL. A amortização antecipada exige subordinação mínima de 30%.",
        "guarantees": "Variam por direito; não há garantia uniforme da carteira.",
        "emissions": [],
        "curation_status": "parcial_por_politica_ampla",
        "not_identified": "cedentes/devedores atuais; composição e concentração efetivas; garantias; emissões relevantes",
        "classification_note": "O cadastro ANBIMA traz Outros/Multicarteira Outros; a política documental é ampla e inclui NPL/precatórios.",
    },
}


def local_text_path(doc_id: int) -> str:
    roots = [ROOT / "data" / "raw" / "industry_large_funds", OUT / "raw_top20_new"]
    candidates: list[Path] = []
    for base in roots:
        if base.exists():
            candidates.extend(base.rglob(f"{doc_id}_*.txt"))
    if not candidates:
        for base in roots:
            if base.exists():
                candidates.extend(base.rglob(f"{doc_id}_*.pdf"))
    if not candidates:
        return ""
    # Prefer a text file whose parent CNPJ is in the curated set and the shortest
    # deterministic path if a legacy duplicate exists.
    chosen = sorted(candidates, key=lambda p: (len(str(p)), str(p)))[0]
    return str(chosen.resolve())


def load_document_metadata() -> dict[int, dict[str, Any]]:
    frames = []
    for path in DOC_LEDGER_PATHS:
        if path.exists():
            frame = pd.read_csv(path, dtype={"cnpj": str}, low_memory=False)
            frame["ledger_path"] = str(path.resolve())
            frames.append(frame)
    all_docs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result: dict[int, dict[str, Any]] = {}
    if not all_docs.empty:
        all_docs["document_id"] = pd.to_numeric(all_docs["document_id"], errors="coerce")
        for row in all_docs.dropna(subset=["document_id"]).to_dict("records"):
            result[int(row["document_id"])] = row
    # This quarterly report was added specifically to audit the name-based PAN
    # Auto classification and is not in the original selected-document ledger.
    result[1196918] = {
        "cnpj": "65473848000183",
        "fund_name": "PAN AUTO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA",
        "categoria": "Informe Trimestral",
        "tipo": "Demonstrativo Trimestral de FIDC",
        "especie": "",
        "data_referencia": "31/03/2026",
        "data_entrega": "não identificado no arquivo local",
        "declared_file_name": "1196918_informe_trimestral.pdf",
        "read_status": "texto_extraído",
        "ledger_path": "adicionado na auditoria Top 20",
    }
    return result


def provider_model(row: pd.Series) -> tuple[str, bool, str]:
    a = normalize_cnpj(row.get("admin_cnpj"))
    g = normalize_cnpj(row.get("gestor_cnpj"))
    c = normalize_cnpj(row.get("custodiante_cnpj"))
    present = [v for v in [a, g, c] if v]
    missing = [name for name, value in [("admin", a), ("gestor", g), ("custodiante", c)] if not value]
    if missing:
        return "prestador não informado", False, ", ".join(missing)
    if len(set(present)) == 1:
        return "mesma entidade legal nas três funções", True, ""
    pairs = []
    if a == g:
        pairs.append("administração + gestão")
    if a == c:
        pairs.append("administração + custódia")
    if g == c:
        pairs.append("gestão + custódia")
    return (("; ".join(pairs)) if pairs else "três entidades legais distintas"), False, ""


def flatten_emissions(emissions: list[Emission]) -> str:
    if not emissions:
        return "não identificado no corpus primário selecionado"
    parts = []
    for item in emissions:
        amount = "montante não identificado" if item.amount_brl is None else f"R$ {item.amount_brl / 1e9:.3f} bi"
        note = f"; {item.note}" if item.note else ""
        parts.append(f"{item.date} | {item.event} | {amount} | doc. {item.source_document_id}{note}")
    return " || ".join(parts)


def main() -> None:
    universe = pd.read_csv(
        UNIVERSE_PATH,
        dtype={
            "cnpj": str,
            "cnpj_fundo": str,
            "admin_cnpj": str,
            "gestor_cnpj": str,
            "custodiante_cnpj": str,
        },
        low_memory=False,
    )
    universe["cnpj"] = universe["cnpj"].map(normalize_cnpj)
    universe["cnpj_fundo"] = universe["cnpj_fundo"].map(normalize_cnpj)
    universe["is_fic_fidc_bool"] = bool_series(universe["is_fic_fidc"])
    universe["pl"] = pd.to_numeric(universe["pl"], errors="coerce")
    ex_fic = universe.loc[~universe["is_fic_fidc_bool"] & universe["pl"].notna()].copy()
    denominator = float(ex_fic["pl"].sum())
    top20 = ex_fic.sort_values(["pl", "cnpj"], ascending=[False, True]).head(20).copy()
    top20["rank"] = range(1, 21)
    assert len(top20) == 20
    assert top20["cnpj"].is_unique
    assert set(top20["cnpj"]) == set(CURATION), "Curation keys do not match derived Top 20"
    assert set(top20["cnpj"]) == set(SOURCE_DOCS), "Source keys do not match derived Top 20"
    assert set(top20["competencia"].astype(str)) == {AS_OF}

    anbima = pd.read_csv(ANBIMA_PATH, dtype=str, low_memory=False)
    anbima["cnpj_classe_norm"] = anbima["cnpj_classe"].map(normalize_cnpj)
    anbima_by_cnpj = {
        row["cnpj_classe_norm"]: row
        for row in anbima.sort_values(["cnpj_classe_norm", "active_record_count"], ascending=[True, False]).to_dict("records")
        if row["cnpj_classe_norm"]
    }
    doc_meta = load_document_metadata()

    flat_rows: list[dict[str, Any]] = []
    json_profiles: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    for _, row in top20.sort_values("rank").iterrows():
        cnpj = row["cnpj"]
        curated = CURATION[cnpj]
        anb = anbima_by_cnpj.get(cnpj)
        if anb:
            tipo = clean_text(anb.get("tipo_anbima")) or "não identificado"
            foco = clean_text(anb.get("foco_anbima")) or "não identificado"
            anbima_origin = "oficial_anbima_snapshot"
            anbima_reference = clean_text(anb.get("source_snapshot_date"))
            anbima_source = clean_text(anb.get("source_kind"))
        elif curated.get("anbima_document_type"):
            tipo = curated["anbima_document_type"]
            foco = curated["anbima_document_focus"]
            anbima_origin = "evidencia_documental"
            anbima_reference = "2025-12-31"
            anbima_source = "Regulamento FundosNet, doc. 1074015"
        else:
            tipo = "não identificado"
            foco = "não identificado"
            anbima_origin = "nao_identificado"
            anbima_reference = "2025-12-29"
            anbima_source = "snapshot ANBIMA consultado sem correspondência por CNPJ da classe"

        model, mono_same_entity, missing_providers = provider_model(row)
        emissions: list[Emission] = curated["emissions"]
        document_ids = [item["id"] for item in SOURCE_DOCS[cnpj]]
        pl = float(row["pl"])
        share = pl / denominator
        base = {
            "competencia": AS_OF,
            "rank": int(row["rank"]),
            "cnpj_classe": cnpj,
            "cnpj_classe_formatado": format_cnpj(cnpj),
            "cnpj_fundo": normalize_cnpj(row.get("cnpj_fundo")),
            "cnpj_fundo_formatado": format_cnpj(row.get("cnpj_fundo")),
            "denominacao": clean_text(row.get("denominacao")),
            "tipo_registro_cvm": clean_text(row.get("tp_registro")),
            "pl_brl": round(pl, 2),
            "market_share_ex_fic": share,
            "market_share_ex_fic_pct": share * 100.0,
            "denominador_pl_ex_fic_brl": round(denominator, 2),
            "administrador": clean_text(row.get("admin_nome")) or "não informado",
            "administrador_cnpj": normalize_cnpj(row.get("admin_cnpj")) or "não informado",
            "gestor": clean_text(row.get("gestor_nome")) or "não informado",
            "gestor_cnpj": normalize_cnpj(row.get("gestor_cnpj")) or "não informado",
            "custodiante": clean_text(row.get("custodiante_nome")) or "não informado",
            "custodiante_cnpj": normalize_cnpj(row.get("custodiante_cnpj")) or "não informado",
            "modelo_prestacao_entidade_legal": model,
            "monoestrutura_mesma_entidade_legal": mono_same_entity,
            "prestadores_ausentes": missing_providers,
            "nota_prestadores": curated.get("provider_note", ""),
            "tipo_anbima": tipo,
            "foco_anbima": foco,
            "origem_tipo_foco": anbima_origin,
            "data_referencia_tipo_foco": anbima_reference,
            "fonte_tipo_foco": anbima_source,
            "segmento_economico_documental": curated["documentary_economic_segment"],
            "cedente_originador": curated["cedent_originator"],
            "sacado_devedor": curated["debtor_profile"],
            "natureza_recebiveis": curated["receivables"],
            "funcionamento_economico": curated["functioning"],
            "classes_subordinacao": curated["classes_subordination"],
            "garantias": curated["guarantees"],
            "emissoes_relevantes": flatten_emissions(emissions),
            "quantidade_eventos_emissao_identificados": len(emissions),
            "status_curadoria": curated["curation_status"],
            "campos_nao_identificados": curated["not_identified"],
            "nota_classificacao": curated["classification_note"],
            "documentos_primarios_ids": ";".join(map(str, document_ids)),
            "fundosnet_gerenciador": FUNDOSNET_MANAGER.format(cnpj=cnpj),
            "data_consulta": CONSULTED_AT,
        }
        flat_rows.append(base)
        nested = dict(base)
        nested["emissions"] = [asdict(item) for item in emissions]
        nested["primary_documents"] = [
            {
                "document_id": source["id"],
                "supports": source["supports"],
                "view_url": FUNDOSNET_VIEW.format(doc_id=source["id"]),
                "download_url": FUNDOSNET_DOWNLOAD.format(doc_id=source["id"]),
                "local_text_path": local_text_path(source["id"]),
            }
            for source in SOURCE_DOCS[cnpj]
        ]
        json_profiles.append(nested)

        source_rows.append(
            {
                "rank": int(row["rank"]),
                "cnpj_classe": cnpj,
                "denominacao": clean_text(row.get("denominacao")),
                "source_type": "CVM Informe Mensal FIDC",
                "source_id": f"universe_latest:{AS_OF}:{cnpj}",
                "source_reference_date": AS_OF,
                "source_delivery_date": "",
                "source_title": "CVM Informe Mensal FIDC — fotografia por veículo/classe",
                "supports_fields": "ranking; PL; CNPJ de classe/fundo; administrador; gestor; custodiante",
                "source_url": CVM_DATASET_URL,
                "download_url": CVM_DATA_URL,
                "fund_manager_url": FUNDOSNET_MANAGER.format(cnpj=cnpj),
                "local_path": str(UNIVERSE_PATH.resolve()),
                "read_status": "linha reconciliada",
                "consulted_at": CONSULTED_AT,
                "source_note": "PL e prestadores vêm da fotografia CVM de mai/26; o ranking exclui FIC-FIDC.",
            }
        )
        source_rows.append(
            {
                "rank": int(row["rank"]),
                "cnpj_classe": cnpj,
                "denominacao": clean_text(row.get("denominacao")),
                "source_type": "ANBIMA Data" if anb else "ANBIMA — ausência/evidência documental",
                "source_id": f"anbima:{cnpj}:{anbima_reference}",
                "source_reference_date": anbima_reference,
                "source_delivery_date": "",
                "source_title": anbima_source,
                "supports_fields": "Tipo ANBIMA; Foco ANBIMA; origem da classificação",
                "source_url": ANBIMA_URL,
                "download_url": "",
                "fund_manager_url": FUNDOSNET_MANAGER.format(cnpj=cnpj),
                "local_path": str(ANBIMA_PATH.resolve()),
                "read_status": anbima_origin,
                "consulted_at": CONSULTED_AT,
                "source_note": curated["classification_note"],
            }
        )
        for source in SOURCE_DOCS[cnpj]:
            doc_id = int(source["id"])
            meta = doc_meta.get(doc_id, {})
            source_rows.append(
                {
                    "rank": int(row["rank"]),
                    "cnpj_classe": cnpj,
                    "denominacao": clean_text(row.get("denominacao")),
                    "source_type": "CVM/FundosNet",
                    "source_id": f"fundosnet:{doc_id}",
                    "source_reference_date": clean_text(meta.get("data_referencia")),
                    "source_delivery_date": clean_text(meta.get("data_entrega")),
                    "source_title": " — ".join(
                        part
                        for part in [
                            clean_text(meta.get("categoria")),
                            clean_text(meta.get("tipo")),
                            clean_text(meta.get("especie")),
                        ]
                        if part
                    )
                    or f"Documento FundosNet {doc_id}",
                    "supports_fields": source["supports"],
                    "source_url": FUNDOSNET_VIEW.format(doc_id=doc_id),
                    "download_url": FUNDOSNET_DOWNLOAD.format(doc_id=doc_id),
                    "fund_manager_url": FUNDOSNET_MANAGER.format(cnpj=cnpj),
                    "local_path": local_text_path(doc_id),
                    "read_status": clean_text(meta.get("read_status")) or "texto_extraído",
                    "consulted_at": CONSULTED_AT,
                    "source_note": "Paráfrase conservadora; consultar o documento integral antes de publicar citação literal.",
                }
            )

    flat = pd.DataFrame(flat_rows).sort_values("rank")
    sources = pd.DataFrame(source_rows).sort_values(["rank", "source_type", "source_id"])
    assert len(flat) == 20
    assert flat["rank"].tolist() == list(range(1, 21))
    assert not flat["denominacao"].eq("").any()
    assert abs(flat["pl_brl"].sum() - float(top20["pl"].sum())) < 1.0
    pan_segment = flat.loc[flat["cnpj_classe"].eq("65473848000183"), "segmento_economico_documental"].iloc[0]
    assert "precatórios federais" in pan_segment.lower()
    assert "auto/veículos" not in pan_segment.lower()

    csv_path = OUT / "top20_fidcs_curadoria.csv"
    json_path = OUT / "top20_fidcs_curadoria.json"
    ledger_path = OUT / "top20_fidcs_source_ledger.csv"
    flat.to_csv(csv_path, index=False, encoding="utf-8-sig")
    sources.to_csv(ledger_path, index=False, encoding="utf-8-sig")

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "consulted_at": CONSULTED_AT,
        "competencia": AS_OF,
        "ranking_definition": "Top 20 CNPJ de classe/veículo por PL na fotografia CVM de mai/26, excluindo FIC-FIDC.",
        "denominator_definition": "Soma algébrica do PL de todos os veículos ex-FIC, incluindo registros com PL negativo, para reconciliar o total da fonte.",
        "denominator_pl_ex_fic_brl": denominator,
        "universe_ex_fic_count": int(len(ex_fic)),
        "negative_pl_record_count": int((ex_fic["pl"] < 0).sum()),
        "negative_pl_total_brl": float(ex_fic.loc[ex_fic["pl"] < 0, "pl"].sum()),
        "top20_pl_brl": float(flat["pl_brl"].sum()),
        "top20_share_ex_fic": float(flat["pl_brl"].sum() / denominator),
        "class_fund_cnpj_mismatch_count_top20": int((flat["cnpj_classe"] != flat["cnpj_fundo"]).sum()),
        "anbima_official_matches": int((flat["origem_tipo_foco"] == "oficial_anbima_snapshot").sum()),
        "anbima_documentary_matches": int((flat["origem_tipo_foco"] == "evidencia_documental").sum()),
        "anbima_not_identified": int((flat["origem_tipo_foco"] == "nao_identificado").sum()),
        "warnings": [
            "PL e prestadores são fotografia de mai/26; documentos têm datas próprias e podem não refletir a carteira corrente em todos os detalhes.",
            "Política de investimento e critérios de elegibilidade demonstram ativos permitidos, não a composição efetiva da carteira. A redação usa 'política permite' quando não há informe de carteira.",
            "CNPJ da classe e CNPJ do fundo não são intercambiáveis; a classe MT Global tem CNPJ distinto do fundo.",
            "Cedente, sacado, ativo ou segmento não foram inferidos pelo nome do fundo.",
            "Montantes de ofertas não equivalem a PL atual nem a saldo em circulação.",
            "O rótulo oficial ANBIMA foi mantido separado da leitura econômica documental, inclusive quando divergem.",
            "PAN AUTO: a única evidência econômica primária localizada confirma precatórios federais no 1T26; a classificação nominal Auto/Veículos é inválida.",
            "Monoestrutura por conglomerado não foi classificada aqui: coincidência de marca não prova vínculo societário. O arquivo mostra apenas coincidência por CNPJ de entidade legal.",
        ],
        "profiles": json_profiles,
    }
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # Short handoff note: quantitative statements are generated from the output
    # rather than hand-copied, reducing drift when the input snapshot changes.
    p = flat.set_index("cnpj_classe")
    two_share = float(flat.head(2)["pl_brl"].sum() / denominator)
    anb_off = int((flat["origem_tipo_foco"] == "oficial_anbima_snapshot").sum())
    anb_doc = int((flat["origem_tipo_foco"] == "evidencia_documental").sum())
    anb_nd = int((flat["origem_tipo_foco"] == "nao_identificado").sum())
    note = f"""# Top 20 FIDCs — achados de curadoria

Base: CVM mai/26. Ranking por CNPJ de classe/veículo, com exclusão de FIC-FIDC. Consulta documental: {CONSULTED_AT}.

- Os 20 maiores somam **R$ {flat['pl_brl'].sum()/1e9:.1f} bi**, ou **{flat['pl_brl'].sum()/denominator:.1%}** do PL ex-FIC de R$ {denominator/1e9:.1f} bi. Petrobras e TAPSO, juntos, representam **{two_share:.1%}** do mesmo denominador.
- O Top 20 foi derivado de {len(ex_fic):,} registros ex-FIC, não da aba de fundos acima de R$ 5 bi. O 20º colocado tem PL de R$ {flat.iloc[-1]['pl_brl']/1e9:.2f} bi.
- Tipo/Foco ANBIMA: {anb_off} correspondências no snapshot oficial de 29/12/2025, {anb_doc} classificação localizada apenas no regulamento e {anb_nd} sem rótulo identificado. Leitura econômica documental permanece em coluna separada.
- Em 19 dos 20 casos, CNPJ da classe e do fundo coincidem na fotografia; a classe Consignado Privado do MT Global usa CNPJ de classe distinto do CNPJ do fundo.
- **PAN AUTO:** o relatório trimestral FundosNet de 31/03/2026 (doc. 1196918) informa aquisição de precatórios federais. Não há suporte primário para classificar o fundo como Auto/Veículos; a inferência pelo nome deve ser removida.
- **Artesanal Master:** era FIC-FIDC e foi transformado em FIDC direto com vigência em 23/07/2024. Comparações históricas devem marcar essa mudança de mandato.
- **Petrobras:** administração e gestão têm o mesmo CNPJ; custódia é Banco do Brasil, CNPJ distinto. **TAPSO:** administração e custódia têm o mesmo CNPJ; gestão é Oliveira Trust Servicer, CNPJ distinto. Nenhum dos dois é monoestrutura pela definição estrita de mesma entidade legal nas três funções.
- Vínculo por conglomerado não foi inferido pela marca. A classificação por grupo econômico deve ser reconciliada com a base normalizada e evidência societária por CNPJ.
- Ofertas foram registradas somente quando havia documento primário e valor legível. Montante de oferta não foi tratado como PL corrente; a oferta CloudWalk de 2025 é secundária e o R$ 15 bi do MT Global pertence ao instrumento conjunto, não necessariamente à classe inteira.
- Política de investimento não foi tratada como carteira efetiva. Para fundos multicarteira/NPL, a ficha distingue ativos permitidos pelo regulamento de exposições efetivamente observadas.

Arquivos: `top20_fidcs_curadoria.csv`, `top20_fidcs_curadoria.json` e `top20_fidcs_source_ledger.csv`.
"""
    (OUT / "top20_fidcs_findings.md").write_text(note, encoding="utf-8")

    print(json.dumps({
        "csv": str(csv_path),
        "json": str(json_path),
        "ledger": str(ledger_path),
        "profiles": len(flat),
        "source_rows": len(sources),
        "top20_share": float(flat["pl_brl"].sum() / denominator),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
