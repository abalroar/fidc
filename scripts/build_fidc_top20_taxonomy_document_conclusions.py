"""Conclude the documentary review for every historical Top 20 FIDC.

The source extraction remains in ``industry_top20_taxonomy_document_review.csv``.
This script creates a separate conclusion layer. It reads each available
regulation page by page, selects the decisive definition or investment-policy
clause, and produces one editable proposal per legal CNPJ. Official ANBIMA/CVM
fields and the manual action ledger are never changed here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import unicodedata

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_fidc_top20_taxonomy_document_review import (  # noqa: E402
    DEFAULT_PERIODS,
    OUTPUT_COLUMNS,
)
from services.industry_taxonomy_review import (  # noqa: E402
    ANBIMA_REFERENCE_DATE,
    normalize_cnpj,
)


@dataclass(frozen=True)
class DocumentaryFamily:
    key: str
    patterns: tuple[tuple[str, int], ...]
    tipo: str
    foco: str
    tabela_ii: str
    n1: str
    n2: str


FAMILIES: tuple[DocumentaryFamily, ...] = (
    DocumentaryFamily(
        "fic_fidc",
        (
            (r"PREPONDERANTEMENTE.{0,120}COTAS?.{0,80}(?:FIDC|FUNDOS? DE INVESTIMENTO EM DIREITOS CREDITORIOS)", 13),
            (r"MINIMO DE 9[05]%.{0,140}COTAS?.{0,80}(?:FIDC|FUNDOS? DE INVESTIMENTO EM DIREITOS CREDITORIOS)", 13),
        ),
        "Outros",
        "Multicarteira Outros",
        "N/D",
        "Multissetorial / Outros",
        "Multicarteira outros",
    ),
    DocumentaryFamily(
        "adquirencia",
        (
            (r"DIREITOS? CREDITORIOS?.{0,260}ARRANJOS? DE PAGAMENTO", 13),
            (r"DIREITOS? CREDITORIOS?.{0,260}AGENDA(?:S)? DE RECEBIVEIS", 13),
            (r"TRANSACOES?.{0,160}(?:CARTAO|PAGAMENTO).{0,180}(?:CREDENCIADOR|SUBCREDENCIADOR)", 12),
            (r"CREDENCIADORAS?|SUBCREDENCIADORAS?.{0,260}DIREITOS? CREDITORIOS?", 11),
        ),
        "Agro, Indústria e Comércio",
        "Recebíveis Comerciais",
        "Adquirência",
        "Meios de Pagamento e Cartões",
        "Arranjos de pagamento/adquirência",
    ),
    DocumentaryFamily(
        "bancos_emissores",
        (
            (r"DIREITOS? CREDITORIOS?.{0,240}BANCOS? EMISSORES?.{0,100}CARTAO", 13),
            (r"BANCOS? EMISSORES?.{0,220}DIREITOS? CREDITORIOS?", 12),
            (r"FATURAS? DE CARTAO.{0,180}DIREITOS? CREDITORIOS?", 10),
        ),
        "Financeiro",
        "Multicarteira Financeiro",
        "Cartão de crédito",
        "Meios de Pagamento e Cartões",
        "Bancos Emissores",
    ),
    DocumentaryFamily(
        "consignado",
        (
            (r"DIREITOS? CREDITORIOS?.{0,260}CREDITO CONSIGNADO", 13),
            (r"DIREITOS? CREDITORIOS?.{0,260}CONSIGNACAO EM FOLHA", 13),
            (r"EMPRESTIMOS?.{0,180}(?:CONSIGNADOS?|BENEFICIOS? DO INSS)", 11),
        ),
        "Financeiro",
        "Crédito Consignado",
        "Financeiro",
        "Crédito PF",
        "Consignado/INSS",
    ),
    DocumentaryFamily(
        "veiculos_financeiro",
        (
            (r"DIREITOS? CREDITORIOS?.{0,260}FINANCIAMENTO.{0,80}VEICULOS?", 13),
            (r"CEDULAS? DE CREDITO BANCARIO.{0,220}VEICULOS?", 12),
            (r"ALIENACAO FIDUCIARIA.{0,140}VEICULOS?", 10),
        ),
        "Financeiro",
        "Financiamento de Veículos",
        "Financeiro",
        "Crédito PF",
        "Auto/Veículos",
    ),
    DocumentaryFamily(
        "imobiliario",
        (
            (r"DIREITOS? CREDITORIOS?.{0,260}(?:CREDITO|FINANCIAMENTO) IMOBILIARIO", 13),
            (r"DIREITOS? CREDITORIOS?.{0,180}REPRESENTADOS?.{0,180}CEDULAS? DE CREDITO IMOBILIARIO", 12),
        ),
        "Financeiro",
        "Crédito Imobiliário",
        "Imobiliário",
        "Imobiliário",
        "Imobiliário",
    ),
    DocumentaryFamily(
        "judicial_precatorios",
        (
            (r"DIREITOS? CREDITORIOS?.{0,260}ORIGINADOS?.{0,180}(?:PRECATORIOS?|ACOES? JUDICIAIS?.{0,120}(?:UNIAO|ESTADOS?|MUNICIPIOS?|AUTARQUIAS?))", 14),
            (r"PRECATORIOS?.{0,240}(?:UNIAO|ESTADOS?|MUNICIPIOS?|AUTARQUIAS?|DIVIDAS? PUBLICAS?)", 13),
            (r"DIREITOS? CREDITORIOS?.{0,260}(?:RECEITAS?|DIVIDAS?) PUBLICAS?", 13),
        ),
        "Outros",
        "Poder Público",
        "Ações judiciais",
        "Judicial/Precatórios/NPL",
        "Precatórios/direitos judiciais",
    ),
    DocumentaryFamily(
        "npl",
        (
            (r"(?:ADQUIRIR|AQUISICAO DE).{0,220}DIREITOS? CREDITORIOS?.{0,160}(?:VENCIDOS?|INADIMPLIDOS?)", 14),
            (r"DIREITOS? CREDITORIOS?.{0,180}(?:VENCIDOS?|INADIMPLIDOS?).{0,160}(?:DATA DA CESSAO|QUANDO DE SUA CESSAO)", 13),
            (r"CARTEIRAS?.{0,120}(?:CREDITOS?|DIREITOS? CREDITORIOS?).{0,100}(?:INADIMPLIDOS?|VENCIDOS?)", 13),
            (r"NON[ -]?PERFORMING|\bNPL\b", 11),
        ),
        "Outros",
        "Recuperação",
        "N/D",
        "Judicial/Precatórios/NPL",
        "Não padronizado/NPL",
    ),
    DocumentaryFamily(
        "agronegocio",
        (
            (r"DIREITOS? CREDITORIOS?.{0,300}(?:ORIGINADOS?|DECORRENTES?|REPRESENTADOS?).{0,180}(?:CEDULAS? DE PRODUTO RURAL|PRODUTORES? RURAIS?|AGRONEGOCIO)", 13),
            (r"SEGMENTO ECONOMICO DOS DIREITOS? CREDITORIOS?:? AGRONEGOCIO", 14),
            (r"AQUISICAO DE INSUMOS?.{0,180}(?:AGRICOLAS?|PRODUTORES? RURAIS?)", 10),
        ),
        "Agro, Indústria e Comércio",
        "Agronegócio",
        "Agronegócio",
        "Agro",
        "Agro",
    ),
    DocumentaryFamily(
        "infra_energia",
        (
            (r"DIREITOS? CREDITORIOS?.{0,300}(?:COMPRA E VENDA DE ENERGIA|ENERGIA ELETRICA|PROJETOS? DE INFRAESTRUTURA)", 13),
            (r"CONTRATOS? DE VENDA DE ENERGIA", 11),
            (r"SETOR(?:ES)? DE INFRAESTRUTURA", 10),
        ),
        "Agro, Indústria e Comércio",
        "Infraestrutura",
        "Serviços",
        "Infra/Energia",
        "Energia/infra",
    ),
    DocumentaryFamily(
        "credito_corporativo",
        (
            (r"DIREITOS? CREDITORIOS?.{0,280}(?:REPRESENTADOS?|CONSTITUIDOS?|LASTREADOS?).{0,180}(?:DEBENTURES?|NOTAS? COMERCIAIS?|CREDITO CORPORATIVO)", 12),
            (r"OBJETIVO.{0,280}(?:DEBENTURES?|CREDITO CORPORATIVO)", 12),
        ),
        "Agro, Indústria e Comércio",
        "Crédito Corporativo",
        "Financeiro",
        "Crédito PJ",
        "Crédito privado/mercado de capitais",
    ),
    DocumentaryFamily(
        "credito_financeiro",
        (
            (r"DIREITOS? CREDITORIOS?.{0,300}CEDULAS? DE CREDITO BANCARIO", 11),
            (r"DIREITOS? CREDITORIOS?.{0,260}(?:EMPRESTIMOS?|OPERACOES? DE CREDITO)", 9),
            (r"CEDULAS? DE CREDITO BANCARIO.{0,220}(?:PESSOAS? FISICAS?|CONSUMIDORES?)", 11),
        ),
        "Financeiro",
        "Multicarteira Financeiro",
        "Financeiro",
        "Crédito PJ",
        "CCB/Notas comerciais/Capital de giro",
    ),
    DocumentaryFamily(
        "recebiveis_comerciais",
        (
            (r"DIREITOS? CREDITORIOS?.{0,180}(?:REPRESENTADOS?|DECORRENTES?|ORIUNDOS?).{0,200}(?:DUPLICATAS?|VENDAS? MERCANTIS?|PRESTACAO DE SERVICOS?|FORNECIMENTO DE BENS)", 12),
            (r"DUPLICATAS?.{0,180}(?:DECORRENTES?|ORIUNDAS?).{0,160}(?:VENDAS?|PRESTACAO DE SERVICOS?)", 11),
            (r"DIREITOS? CREDITORIOS?.{0,220}OPERACOES? DE COMPRA E VENDA", 11),
        ),
        "Agro, Indústria e Comércio",
        "Recebíveis Comerciais",
        "Comercial",
        "Crédito PJ",
        "Recebíveis comerciais/multissetorial",
    ),
)


DOCUMENTARY_OVERRIDES: dict[str, dict[str, object]] = {
    "34218864000104": {
        "document_id": "cadastro local CVM/ANBIMA — competência 2025-12",
        "document_reference_date": "2025-12",
        "document_url": "",
        "local_path": "data/industry_study/generated_revision/base_fundo_cnpj.csv.gz",
        "pagina_clausula": "N/D — divergência de perímetro cadastral",
        "cedent_originator_explicit": "N/D — veículo identificado como FIF Multimercado.",
        "evidence_summary": (
            "A denominação cadastral é CLASSE ÚNICA MULTIMERCADO DO FUNDO DE INVESTIMENTO "
            "FINANCEIRO MOTO-HONDA. O CNPJ requer validação de perímetro antes de permanecer no ranking FIDC."
        ),
        "reclassification_status": "propor_correcao_perimetro_documental",
        "confianca_documental": "media",
        "perimeter_proposal": "Excluir do universo FIDC após validar o cadastro CVM da classe",
        "manual_validation_reason": (
            "Validar o enquadramento da classe no cadastro CVM antes de retirar o CNPJ do ranking histórico."
        ),
        "reading_method": "reconciliação cadastral local por CNPJ e denominação da classe",
        "source_limitations": (
            "A correção de perímetro depende de confirmação no cadastro CVM da classe."
        ),
    },
    "35818950000102": {
        "document_id": "Oliveira Trust cod 1327651",
        "document_reference_date": "N/D",
        "document_url": "https://api-site.oliveiratrust.com.br/scot/modulos/downloads/baixar.php?cod=1327651",
        "local_path": "",
        "pagina_clausula": "p. 6-7 e p. 46-48 — critérios, origem e definições",
        "cedent_originator_explicit": (
            "Cedente: Apolo Fundo de Investimento em Direitos Creditórios, CNPJ "
            "34.218.625/0001-46. Originador econômico: Petróleo Brasileiro S.A. — "
            "Petrobras, cedente original dos IADs ao Apolo FIDC."
        ),
        "evidence_summary": (
            "Os direitos decorrem de IADs de operações comerciais de fornecimento de "
            "insumos de óleo e gás pela Petrobras às distribuidoras de energia; o Apolo "
            "FIDC cede esses direitos ao BR Eletro e a Eletrobras figura como devedora."
        ),
        "tipo_anbima_sugerido": "Agro, Indústria e Comércio",
        "foco_anbima_sugerido": "Recebíveis Comerciais",
        "tabela_ii_sugerida_documental": "Comercial",
        "taxonomia_funcional_n1_sugerida": "Crédito PJ",
        "taxonomia_funcional_n2_sugerida": "Recebíveis comerciais/multissetorial",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "alta",
        "manual_validation_reason": (
            "Conclusão baseada no regulamento primário hospedado pela administradora; "
            "confirmar e Aprovar e aplicar no fluxo manual."
        ),
        "reading_method": "revisão visual integral do regulamento digitalizado de 54 páginas",
        "source_limitations": (
            "PDF digitalizado sem camada textual; páginas decisivas verificadas por renderização."
        ),
    },
    "14330038000137": {
        "document_id": "SEI 19957.006097/2018-21 — Ofício Interno 2/2023/CVM/SIN/GSAF",
        "document_reference_date": "2023-01-12",
        "document_url": "https://conteudo.cvm.gov.br/export/sites/cvm/decisoes/anexos/2023/20230207/1510_19.pdf",
        "local_path": "",
        "pagina_clausula": "p. 1 — identificação das partes e do papel econômico",
        "cedent_originator_explicit": (
            "Banco Cruzeiro do Sul S.A., depois Massa Falida do Banco Cruzeiro do Sul S.A.: "
            "cedente, antigo agente de cobrança e cotista subordinado, conforme decisão da CVM."
        ),
        "evidence_summary": (
            "A decisão da CVM identifica o Banco Cruzeiro do Sul como cedente da carteira e "
            "antigo agente de cobrança. O documento não substitui o regulamento para detalhar "
            "a natureza de cada contrato de crédito."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Crédito Consignado",
        "tabela_ii_sugerida_documental": "Financeiro",
        "taxonomia_funcional_n1_sugerida": "Crédito PF",
        "taxonomia_funcional_n2_sugerida": "Consignado/INSS",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "media",
        "manual_validation_reason": (
            "Manter a classificação oficial; o papel do cedente é confirmado pela CVM e o "
            "regulamento não foi localizado no FundosNet."
        ),
        "reading_method": "revisão de decisão administrativa da CVM e fotografia ANBIMA preservada",
        "source_limitations": (
            "Fonte confirma o cedente e a situação de liquidação, sem descrever integralmente o lastro contratual."
        ),
    },
    "55859549000128": {
        "document_id": "cadastro local CVM/ANBIMA — competência 2025-12",
        "document_reference_date": "2025-12",
        "document_url": "",
        "local_path": "data/industry_study/generated_revision/base_fundo_cnpj.csv.gz",
        "pagina_clausula": "N/D — divergência de perímetro cadastral",
        "cedent_originator_explicit": "N/D — veículo identificado como FIF Multimercado.",
        "evidence_summary": (
            "A denominação cadastral é ZETA FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO. "
            "O CNPJ entrou no ranking FIDC por vínculo cadastral que requer correção de perímetro."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "propor_correcao_perimetro_documental",
        "confianca_documental": "media",
        "perimeter_proposal": "Excluir do universo FIDC após validar o cadastro CVM da classe",
        "manual_validation_reason": (
            "Validar o enquadramento da classe no cadastro CVM antes de retirar o CNPJ do ranking histórico."
        ),
        "reading_method": "reconciliação cadastral local por CNPJ e denominação da classe",
        "source_limitations": (
            "Regulamento não localizado; a correção de perímetro depende de confirmação no cadastro CVM da classe."
        ),
    },
    "53323654000112": {
        "document_id": "cadastro local CVM/ANBIMA — competência 2023-12",
        "document_reference_date": "2023-12",
        "document_url": "",
        "local_path": "data/industry_study/generated_revision/base_fundo_cnpj.csv.gz",
        "pagina_clausula": "N/D — divergência de perímetro cadastral",
        "cedent_originator_explicit": "N/D — veículo identificado como FIF Multimercado.",
        "evidence_summary": (
            "A denominação cadastral é POSITIVO IV FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO "
            "INVESTIMENTO NO EXTERIOR. O CNPJ requer validação de perímetro antes de permanecer no ranking FIDC."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "propor_correcao_perimetro_documental",
        "confianca_documental": "media",
        "perimeter_proposal": "Excluir do universo FIDC após validar o cadastro CVM da classe",
        "manual_validation_reason": (
            "Validar o enquadramento da classe no cadastro CVM antes de retirar o CNPJ do ranking histórico."
        ),
        "reading_method": "reconciliação cadastral local por CNPJ e denominação da classe",
        "source_limitations": (
            "A correção de perímetro depende de confirmação no cadastro CVM da classe."
        ),
    },
}


# Documentary conclusions that require reading the clause as a whole rather
# than choosing the highest-scoring lexical family. These remain proposals in
# the review queue and never write to the manual action ledger.
CURATED_CLASSIFICATION_OVERRIDES: dict[str, dict[str, object]] = {
    "57325251000163": {
        "pagina_clausula": "p. 8 — objetivo e política de investimento",
        "evidence_summary": (
            "O regulamento declara o segmento Agro, Indústria e Comércio e admite direitos "
            "creditórios de infraestrutura e agronegócio. A classificação documental mantém "
            "o foco ANBIMA Agronegócio preservado na fotografia oficial."
        ),
        "tipo_anbima_sugerido": "Agro, Indústria e Comércio",
        "foco_anbima_sugerido": "Agronegócio",
        "tabela_ii_sugerida_documental": "Agronegócio",
        "taxonomia_funcional_n1_sugerida": "Agro",
        "taxonomia_funcional_n2_sugerida": "Agro",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": (
            "Conclusão documental recomenda manter a classificação oficial; a decisão "
            "permanece pendente de aprovação manual."
        ),
        "source_limitations": (
            "O mandato admite infraestrutura e agronegócio; a composição efetiva pode variar."
        ),
    },
    "49826785000145": {
        "evidence_summary": (
            "O regulamento admite carteira ampla, incluindo créditos judiciais e precatórios, "
            "CCBs e outros instrumentos. Nenhuma família isolada representa o mandato completo."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato amplo.",
        "source_limitations": "A composição efetiva pode concentrar-se em uma das famílias autorizadas.",
    },
    "56045805000106": {
        "evidence_summary": (
            "O mandato abrange precatórios e dívida pública, créditos vencidos, direitos "
            "judiciais e créditos de existência futura. O conjunto sustenta Multicarteira Outros."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato amplo.",
        "source_limitations": "O regulamento permite várias famílias; a carteira corrente pode ter concentração distinta.",
    },
    "51079269000146": {
        "evidence_summary": (
            "O regulamento admite CCBs, duplicatas, cheques e contratos oriundos de setores "
            "financeiro, comercial, industrial e de serviços. O mandato é multicarteira."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato multissetorial.",
        "source_limitations": "A política autoriza instrumentos e setores diversos.",
    },
    "26142862000142": {
        "evidence_summary": (
            "A política admite direitos creditórios e títulos de naturezas diversas, operações "
            "de securitização e cotas de FIDC. O mandato sustenta Multicarteira Financeiro."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Multicarteira Financeiro",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato amplo.",
        "source_limitations": "O regulamento não determina uma única família material de lastro.",
    },
    "13321819000100": {
        "evidence_summary": (
            "Os documentos admitem cupons e notas fiscais, CCBs, recebíveis de cartão e "
            "renegociações. A diversidade contratual sustenta Multicarteira Outros."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo lastro misto.",
        "source_limitations": "A materialidade de cada família depende da carteira efetivamente cedida.",
    },
    "29492605000129": {
        "evidence_summary": (
            "A política admite recebíveis documentados por NF-e e NFC-e e créditos representados "
            "por CCBs em múltiplos segmentos econômicos. O enquadramento oficial multicarteira é aderente."
        ),
        "tipo_anbima_sugerido": "Agro, Indústria e Comércio",
        "foco_anbima_sugerido": "Multicarteira Agro, Indústria e Comércio",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Crédito PJ",
        "taxonomia_funcional_n2_sugerida": "Recebíveis comerciais/multissetorial",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo lastro multissetorial.",
        "source_limitations": "A carteira pode alternar entre recebíveis comerciais e CCBs.",
    },
    "53029409000105": {
        "evidence_summary": (
            "O regulamento enumera duplicatas, cheques, debêntures, certificados, cédulas rurais, "
            "industriais, comerciais, imobiliárias e bancárias, contratos e agendas de cartão."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo rol amplo de instrumentos.",
        "source_limitations": "A política não fixa uma única família material de recebíveis.",
    },
    "51152102000163": {
        "evidence_summary": (
            "O regulamento autoriza créditos dos setores financeiro, comercial, industrial, "
            "arrendamento e serviços, inclusive CCBs. O mandato é multissetorial."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato multissetorial.",
        "source_limitations": "A composição efetiva pode concentrar-se em um setor autorizado.",
    },
    "08632394000102": {
        "evidence_summary": (
            "A política contempla direitos dos setores comercial, industrial, financeiro e de "
            "serviços. O foco oficial Multicarteira Agro, Indústria e Comércio é aderente."
        ),
        "tipo_anbima_sugerido": "Agro, Indústria e Comércio",
        "foco_anbima_sugerido": "Multicarteira Agro, Indústria e Comércio",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Crédito PJ",
        "taxonomia_funcional_n2_sugerida": "Recebíveis comerciais/multissetorial",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato multissetorial.",
        "source_limitations": "A política autoriza setores distintos sem declarar concentração corrente.",
    },
    "29301202000155": {
        "evidence_summary": (
            "O regulamento admite extensa lista de instrumentos, origens e setores. A leitura "
            "integral da cláusula sustenta Multicarteira Outros."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato amplo.",
        "source_limitations": "A carteira corrente pode ter concentração não imposta pelo regulamento.",
    },
    "46909301000133": {
        "evidence_summary": (
            "A política abrange créditos dos setores financeiro, comercial, industrial, "
            "arrendamento e serviços. O mandato é multicarteira."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pelo mandato multissetorial.",
        "source_limitations": "O regulamento não impõe uma família única de lastro.",
    },
    "49306883000151": {
        "evidence_summary": (
            "O regulamento declara que a origem não pode ser especificada e admite debêntures, "
            "notas, CCBs, precatórios e direitos judiciais. O mandato sustenta Multicarteira Outros."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Multicarteira Outros",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira outros",
        "reclassification_status": "manter_classificacao_oficial",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental recomenda manter a classificação oficial pela origem diversificada.",
        "source_limitations": "A materialidade por instrumento depende da carteira efetiva.",
    },
    "12817329000129": {
        "pagina_clausula": "Regulamento p. 30; DF 2025 p. 17",
        "evidence_summary": (
            "O regulamento reúne vendas varejistas à vista e parceladas, CCBs de renegociação, "
            "recebíveis de cartão e créditos contra devedores especiais de adquirência."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Multicarteira Financeiro",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Multissetorial / Outros",
        "taxonomia_funcional_n2_sugerida": "Multicarteira financeiro",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "alta",
        "manual_validation_reason": "Regulamento e DF confirmam lastro misto sem abertura de saldo por família; aplicada a regra de Multicarteira Financeiro.",
        "source_limitations": "A DF não segrega o PL entre vendas, CCBs, cartão e unidades de recebíveis.",
    },
    "24761946000139": {
        "pagina_clausula": "p. 85-86 — definição dos direitos creditórios",
        "cedent_originator_explicit": "Cedente/originador: Credz Administradora de Cartões Ltda.",
        "evidence_summary": (
            "Os créditos decorrem de compras, financiamento de fatura, crédito rotativo e "
            "parcelamentos de cartão administrado pela Credz."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Crédito Pessoal",
        "tabela_ii_sugerida_documental": "Cartão de crédito",
        "taxonomia_funcional_n1_sugerida": "Crédito PF",
        "taxonomia_funcional_n2_sugerida": "Crédito pessoal/consumo",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "alta",
        "manual_validation_reason": "Conclusão documental propõe Crédito Pessoal pela natureza do crédito ao portador do cartão.",
        "source_limitations": "O regulamento autoriza modalidades distintas dentro da relação de cartão.",
    },
    "38376526000143": {
        "evidence_summary": (
            "O regulamento admite recebíveis de adquirência e créditos parcelados de cursos e "
            "conteúdo. A proposta usa Recebíveis Comerciais e preserva Tabela II como N/D."
        ),
        "tipo_anbima_sugerido": "Agro, Indústria e Comércio",
        "foco_anbima_sugerido": "Recebíveis Comerciais",
        "tabela_ii_sugerida_documental": "N/D",
        "taxonomia_funcional_n1_sugerida": "Crédito PJ",
        "taxonomia_funcional_n2_sugerida": "Recebíveis comerciais/multissetorial",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "media",
        "manual_validation_reason": "Conclusão documental propõe Recebíveis Comerciais; confirmar a materialidade das duas famílias.",
        "source_limitations": "O mandato combina adquirência e créditos parcelados de cursos e conteúdo.",
    },
    "32527650000186": {
        "evidence_summary": (
            "O regulamento abrange créditos de lojistas e subcredenciadores em arranjos de "
            "pagamento e créditos de usuários decorrentes de operações de cash-in."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Adquirência",
        "tabela_ii_sugerida_documental": "Adquirência",
        "taxonomia_funcional_n1_sugerida": "Meios de Pagamento e Cartões",
        "taxonomia_funcional_n2_sugerida": "Arranjos de pagamento/adquirência",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "alta",
        "manual_validation_reason": "PicPay é o devedor direto dos créditos de cash-in e pagamentos; a DF não evidencia empréstimo ao consumidor na carteira.",
        "source_limitations": "A carteira pode variar dentro dos critérios de elegibilidade do regulamento.",
    },
    "42922136000107": {
        "pagina_clausula": "Regulamento p. 29, 31 e 36; DF 2025",
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Crédito PF",
        "tabela_ii_sugerida_documental": "Cartão de crédito",
        "taxonomia_funcional_n1_sugerida": "Crédito PF",
        "taxonomia_funcional_n2_sugerida": "Crédito PF parcelado / BNPL",
        "reclassification_status": "propor_reclassificacao_documental",
        "confianca_documental": "alta",
        "manual_validation_reason": "Crédito PF parcelado/BNPL adotado como risco econômico predominante.",
        "source_limitations": "O regulamento admite mais de uma família; a DF não abre o saldo por família.",
    },
}

ACQUIRING_CNPJS: frozenset[str] = frozenset(
    {
        "57609282000146",  # Cloudwalk A.I.
        "60356171000180",  # Cloudwalk PI
        "28169275000172",  # PagSeguro I
        "26287464000114",  # Tapso
        "50473039000102",  # Seller I
        "55471753000177",  # Seller II
        "63572282000111",  # Seller 3
    }
)


BANK_ISSUER_CNPJS: tuple[str, ...] = (
    "43616756000172",
    "44770267000133",
    "40906116000109",
    "43911620000195",
    "52256912000122",
    "40906126000144",
    "62393679000183",
)

BANK_ISSUER_KEEP_OFFICIAL_CNPJS: frozenset[str] = frozenset({"52256912000122"})


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(
        r"\s+", " ", "".join(char for char in text if not unicodedata.combining(char))
    ).upper().strip()


def _digest(path: Path) -> str:
    content = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _read_pages(path_value: object) -> list[str]:
    raw = str(path_value or "").strip()
    if not raw:
        return []
    path = ROOT / raw
    if not path.is_file():
        return []
    try:
        return [_fold(page.extract_text() or "") for page in PdfReader(str(path)).pages]
    except Exception:  # noqa: BLE001
        return []


def _section_bonus(page: str, match_start: int) -> int:
    before = page[max(0, match_start - 500) : match_start]
    bonus = 0
    if "POLITICA DE INVESTIMENTO" in page:
        bonus += 3
    if re.search(r"DIREITOS? CREDITORIOS?.{0,40}(?:SIGNIFICA|SAO|REPRESENTAD|DECORRENT|ORIUND)", page):
        bonus += 2
    if "CRITERIOS DE ELEGIBILIDADE" in page:
        bonus += 1
    if re.search(r"RISCOS?|FATORES? DE RISCO", before[-180:]):
        bonus -= 3
    if "FATORES DE RISCO" in page or page.count("RISCO") >= 3:
        bonus -= 10
    return bonus


def _family_evidence(pages: list[str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    normalized_pages = [_fold(page) for page in pages]
    for family in FAMILIES:
        best: dict[str, object] | None = None
        for page_number, page in enumerate(normalized_pages, start=1):
            for pattern, weight in family.patterns:
                match = re.search(pattern, page)
                if match is None:
                    continue
                score = weight + _section_bonus(page, match.start())
                start = max(0, match.start() - 180)
                end = min(len(page), match.end() + 520)
                item = {
                    "family": family,
                    "score": score,
                    "page": page_number,
                    "snippet": page[start:end].strip(),
                }
                if best is None or int(item["score"]) > int(best["score"]):
                    best = item
        if best is not None:
            candidates.append(best)
    return sorted(candidates, key=lambda item: int(item["score"]), reverse=True)


def _policy_fallback(pages: list[str]) -> tuple[int | None, str]:
    best: tuple[int, int, str] | None = None
    for page_number, page in enumerate(pages, start=1):
        anchors = (
            re.search(r"POLITICA DE INVESTIMENTO", page),
            re.search(r"DIREITOS? CREDITORIOS?.{0,60}(?:SIGNIFICA|REPRESENTAD|DECORRENT|ORIUND)", page),
            re.search(r"CRITERIOS? DE ELEGIBILIDADE", page),
        )
        match = next((candidate for candidate in anchors if candidate is not None), None)
        if match is None:
            continue
        score = sum(candidate is not None for candidate in anchors)
        start = max(0, match.start() - 100)
        snippet = page[start : min(len(page), match.start() + 720)].strip()
        if best is None or score > best[0]:
            best = (score, page_number, snippet)
    return (best[1], best[2]) if best else (None, "")


def _participant_evidence(pages: list[str], prior: object) -> str:
    patterns = (
        r"[\"“]?(?:CEDENTE|ORIGINADOR)(?:ES)?[\"”]?\s+(?:SIGNIFICA|SAO|SERAO)\s+.{0,700}",
        r"(?:CEDENTE|ORIGINADOR)(?:ES)?.{0,180}?CNPJ.{0,80}",
        r"CNPJ.{0,80}.{0,160}?(?:CEDENTE|ORIGINADOR)",
    )
    for page_number, page in enumerate(pages, start=1):
        for pattern in patterns:
            match = re.search(pattern, page)
            if match:
                return f"p. {page_number}: {match.group(0)[:760].strip()}"
    prior_text = str(prior or "").strip()
    if prior_text and prior_text != "N/D":
        return prior_text
    return "N/D — cedente/originador nominal não identificado no regulamento disponível."


def _official_proposal(row: pd.Series) -> tuple[str, str]:
    tipo = str(row.get("anbima_tipo_oficial") or "").strip()
    foco = str(row.get("anbima_foco_oficial") or "").strip()
    if tipo not in {
        "Fomento Mercantil",
        "Agro, Indústria e Comércio",
        "Financeiro",
        "Outros",
    }:
        return "Outros", "Multicarteira Outros"
    defaults = {
        "Fomento Mercantil": "Fomento Mercantil",
        "Agro, Indústria e Comércio": "Multicarteira Agro, Indústria e Comércio",
        "Financeiro": "Multicarteira Financeiro",
        "Outros": "Multicarteira Outros",
    }
    return tipo, foco if foco and foco != "N/D" else defaults[tipo]


def _family_compatible_with_official(family: DocumentaryFamily, row: pd.Series) -> bool:
    official_type, official_focus = _official_proposal(row)
    if family.tipo == official_type and family.foco == official_focus:
        return True
    if official_type == "Fomento Mercantil" and family.key == "recebiveis_comerciais":
        return True
    if official_type == family.tipo and official_focus.startswith("Multicarteira"):
        return True
    return False


def _select_family(
    candidates: list[dict[str, object]], row: pd.Series
) -> tuple[dict[str, object] | None, bool]:
    official_type, official_focus = _official_proposal(row)
    name = _fold(row.get("nome_fidc"))

    def allowed(item: dict[str, object]) -> bool:
        family = item["family"]
        assert isinstance(family, DocumentaryFamily)
        snippet = _fold(item["snippet"])
        specific_official_focus = official_focus not in {
            "Multicarteira Agro, Indústria e Comércio",
            "Multicarteira Financeiro",
            "Multicarteira Outros",
        }
        if (
            specific_official_focus
            and not _family_compatible_with_official(family, row)
        ):
            explicit_name_exceptions = {
                "adquirencia": r"MEIOS? DE PAGAMENTO|CIELO|SELLER|CLOUDWALK|PAGSEGURO|PICPAY|HOTFUND|TAPSO",
                "bancos_emissores": r"BANCOS? EMISSORES?",
                "consignado": r"CONSIGN",
                "veiculos_financeiro": r"AUTO LOANS?|FINANCIAMENTO DE VEICULOS?|DRIVER",
                "infra_energia": r"ENERG|INFRAESTRUTURA",
                "judicial_precatorios": r"CLAIM|PRECATOR|JUDICIAL",
                "npl": r"(?:^|\W)NPL(?:\W|$)|RECUPERACAO DE CREDITOS",
                "fic_fidc": r"FIC FIDC|FUNDO DE INVESTIMENTO EM COTAS",
            }
            pattern = explicit_name_exceptions.get(family.key)
            if not pattern or not re.search(pattern, name):
                return False
        if family.key == "npl":
            return (
                official_focus == "Recuperação"
                or bool(re.search(r"(?:^|\W)NPL(?:\W|$)|RECUPERACAO DE CREDITOS", name))
                or (
                    "OBJETIVO" in snippet
                    and bool(re.search(r"CREDITOS? INADIMPLIDOS?|DIREITOS? CREDITORIOS?.{0,80}VENCIDOS?", snippet))
                )
            )
        if family.key == "judicial_precatorios":
            return (
                official_focus == "Poder Público"
                or bool(re.search(r"CLAIM|PRECATOR|JUDICIAL", name))
                or (
                    "DIREITOS CREDITORIOS" in snippet
                    and "PRECATOR" in snippet
                    and "E/OU" not in snippet
                    and "PODERA ADQUIRIR" not in snippet
                )
            )
        if family.key == "imobiliario":
            return official_focus == "Crédito Imobiliário" or bool(
                re.search(r"IMOBILI|HABITACIONAL", name)
            )
        if family.key == "agronegocio":
            return (
                official_focus == "Agronegócio"
                or bool(re.search(r"AGRO|FIAGRO|RURAL|CORTEVA|BAYER|UPL|NUTRIEN", name))
                or "SEGMENTO ECONOMICO DOS DIREITOS CREDITORIOS: AGRONEGOCIO" in snippet
            )
        if family.key == "infra_energia":
            return (
                official_focus == "Infraestrutura"
                or bool(re.search(r"ENERG|INFRAESTRUTURA", name))
                or "CONTRATOS DE VENDA DE ENERGIA" in snippet
            )
        if family.key == "credito_corporativo":
            return (
                official_focus == "Crédito Corporativo"
                or bool(re.search(r"CREDITO CORPORATIVO|CREDITO ESTRUTURADO", name))
                or "OBJETIVO" in snippet
            )
        if family.key == "credito_financeiro":
            return official_type == "Financeiro" or bool(
                re.search(r"FINANCEIRO|CREDITO|BANCO|BANK", name)
            )
        if family.key == "consignado":
            return official_focus == "Crédito Consignado" or "CONSIGN" in name
        if family.key == "veiculos_financeiro":
            return official_focus == "Financiamento de Veículos" or bool(
                re.search(r"AUTO|VEICUL|DRIVER|HYUNDAI|HONDA|GM", name)
            )
        if family.key == "recebiveis_comerciais":
            return official_type in {"Fomento Mercantil", "Agro, Indústria e Comércio"} or (
                int(item["score"]) >= 14 and "RISCO" not in snippet
            )
        return True

    candidates = [item for item in candidates if allowed(item)]
    if not candidates:
        return None, False
    top = candidates[0]
    top_score = int(top["score"])
    close = [item for item in candidates if top_score - int(item["score"]) <= 2]
    if len(close) == 1:
        return top, False
    compatible = [
        item
        for item in close
        if _family_compatible_with_official(item["family"], row)
    ]
    if len(compatible) == 1:
        return compatible[0], True
    return top, True


def _is_broad_mandate(snippet: object) -> bool:
    text = _fold(snippet)
    instruments = (
        "DUPLICATA",
        "CEDULA DE CREDITO BANCARIO",
        "CEDULA DE CREDITO IMOBILIARIO",
        "CEDULA DE PRODUTO RURAL",
        "DEBENTURE",
        "NOTA COMERCIAL",
        "CREDITO CONSIGNADO",
        "PRECATORIO",
        "COTAS DE EMISSAO DE FIDC",
    )
    count = sum(term in text for term in instruments)
    return count >= 3 and any(
        marker in text
        for marker in ("TAIS COMO", "INCLUINDO", "SEM LIMITACAO", "ENTRE OUTROS")
    )


def _conclude(row: pd.Series) -> dict[str, object]:
    pages = _read_pages(row.get("local_path"))
    candidates = _family_evidence(pages)
    selected, mixed = _select_family(candidates, row)
    if selected is not None and _is_broad_mandate(selected["snippet"]):
        selected = None
        mixed = True
    official_type, official_focus = _official_proposal(row)
    fallback_page, fallback_snippet = _policy_fallback(pages)

    if selected is None:
        proposal_type, proposal_focus = official_type, official_focus
        table_ii = "N/D"
        n1, n2 = "Multissetorial / Outros", "Multicarteira outros"
        evidence = fallback_snippet or (
            "Regulamento sem texto recuperável; proposta baseada na classificação "
            f"ANBIMA preservada de {ANBIMA_REFERENCE_DATE}."
        )
        page_clause = f"p. {fallback_page}" if fallback_page else "N/D — texto não recuperável"
        confidence = "media" if fallback_snippet else "baixa"
        limitation = (
            "A cláusula disponível não individualiza o lastro; a conclusão mantém a classificação oficial."
            if fallback_snippet
            else "Regulamento ausente ou PDF sem texto extraível; cedente, originador e lastro permanecem não confirmados."
        )
        selected_key = "official_fallback"
        is_fic = False
    else:
        family = selected["family"]
        assert isinstance(family, DocumentaryFamily)
        selected_key = family.key
        proposal_type, proposal_focus = family.tipo, family.foco
        table_ii, n1, n2 = family.tabela_ii, family.n1, family.n2
        evidence = str(selected["snippet"])
        page_clause = f"p. {selected['page']} — política/definição do lastro"
        score = int(selected["score"])
        confidence = "alta" if score >= 14 and not mixed else "media"
        limitation = (
            "O regulamento admite famílias próximas de recebíveis; a proposta usa a cláusula mais específica e requer confirmação de materialidade."
            if mixed
            else "A proposta deriva da definição ou política de investimento; a composição efetiva da carteira pode variar dentro dos limites do regulamento."
        )
        is_fic = family.key == "fic_fidc"

    if selected_key == "recebiveis_comerciais" and official_type == "Fomento Mercantil":
        proposal_type, proposal_focus = official_type, official_focus
        table_ii = "Factoring"
    same = proposal_type == official_type and proposal_focus == official_focus
    status = (
        "manter_classificacao_oficial"
        if same
        else "propor_reclassificacao_documental"
    )
    reason = (
        "Conclusão documental recomenda manter a classificação oficial; a decisão permanece pendente de aprovação manual."
        if same
        else "Conclusão documental propõe reclassificação; confirmar a materialidade do lastro antes de Aprovar e aplicar."
    )
    if not pages:
        status = "manter_provisoriamente_por_limitacao_documental"
        reason = (
            "Conclusão provisória mantém a classificação oficial por insuficiência documental; revisar quando houver regulamento legível."
        )

    result = {column: row.get(column, "") for column in OUTPUT_COLUMNS}
    result.update(
        {
            "review_scope": "top20_documental_concluido_periodos_2023_2026",
            "pagina_clausula": page_clause,
            "cedent_originator_explicit": _participant_evidence(
                pages, row.get("cedent_originator_explicit")
            ),
            "evidence_summary": evidence[:1800],
            "tipo_anbima_sugerido": proposal_type,
            "foco_anbima_sugerido": proposal_focus,
            "tabela_ii_sugerida_documental": table_ii,
            "taxonomia_funcional_n1_sugerida": n1,
            "taxonomia_funcional_n2_sugerida": n2,
            "reclassification_status": status,
            "confianca_documental": confidence,
            "perimeter_proposal": (
                "Excluir do perímetro ex-FIC após validação do cadastro fonte"
                if is_fic
                else ""
            ),
            "is_fic_fidc_suggested": is_fic,
            "manual_validation_reason": reason,
            "reading_method": (
                f"revisão documental assistida de {len(pages)} páginas; definição, política de investimento, elegibilidade e lastro"
                if pages
                else "conclusão provisória por fonte documental sem texto recuperável"
            ),
            "source_limitations": limitation,
        }
    )
    return result


def _latest_official(base: pd.DataFrame, cnpjs: set[str]) -> pd.DataFrame:
    frame = base.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo"].isin(cnpjs)].copy()
    frame = frame.sort_values(["cnpj_fundo", "competencia"]).drop_duplicates(
        "cnpj_fundo", keep="last"
    )
    return frame.rename(
        columns={
            "anbima_tipo": "anbima_tipo_oficial",
            "anbima_foco": "anbima_foco_oficial",
        }
    )[["cnpj_fundo", "anbima_tipo_oficial", "anbima_foco_oficial"]]


def _apply_documentary_overrides(output: pd.DataFrame) -> pd.DataFrame:
    result = output.copy()
    overrides = {**DOCUMENTARY_OVERRIDES, **CURATED_CLASSIFICATION_OVERRIDES}
    for cnpj, values in overrides.items():
        mask = result["cnpj_fundo"].eq(cnpj)
        if int(mask.sum()) != 1:
            raise ValueError(f"override documental sem CNPJ único: {cnpj}")
        for column, value in values.items():
            if column not in result.columns:
                raise ValueError(f"coluna inválida no override documental: {column}")
            result.loc[mask, column] = value

    for cnpj in BANK_ISSUER_CNPJS:
        mask = result["cnpj_fundo"].eq(cnpj)
        if int(mask.sum()) != 1:
            raise ValueError(f"estrutura de bancos emissores sem CNPJ único: {cnpj}")
        status = (
            "manter_classificacao_oficial"
            if cnpj in BANK_ISSUER_KEEP_OFFICIAL_CNPJS
            else "propor_reclassificacao_documental"
        )
        values = {
            "evidence_summary": (
                "Os direitos creditórios são detidos pela credenciadora/cedente contra "
                "bancos emissores de cartões, no fluxo financeiro dos arranjos de pagamento."
            ),
            "tipo_anbima_sugerido": "Financeiro",
            "foco_anbima_sugerido": "Cartão de crédito",
            "tabela_ii_sugerida_documental": "Cartão de crédito",
            "taxonomia_funcional_n1_sugerida": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2_sugerida": "Banco emissor/cartão de crédito",
            "reclassification_status": status,
            "confianca_documental": "alta",
            "manual_validation_reason": (
                "Conclusão documental recomenda manter a classificação oficial de bancos emissores."
                if status == "manter_classificacao_oficial"
                else "Conclusão documental propõe Financeiro / Cartão de crédito pela contraparte bancária emissora."
            ),
            "source_limitations": (
                "A carteira decorre do fluxo de cartão, mas a obrigação cedida recai sobre os bancos emissores."
            ),
        }
        for column, value in values.items():
            result.loc[mask, column] = value

    for cnpj in ACQUIRING_CNPJS:
        mask = result["cnpj_fundo"].eq(cnpj)
        if int(mask.sum()) != 1:
            raise ValueError(f"fundo de adquirência sem CNPJ único: {cnpj}")
        values = {
            "tipo_anbima_sugerido": "Financeiro",
            "foco_anbima_sugerido": "Adquirência",
            "tabela_ii_sugerida_documental": "Adquirência",
            "taxonomia_funcional_n1_sugerida": "Meios de Pagamento e Cartões",
            "taxonomia_funcional_n2_sugerida": "Arranjos de pagamento/adquirência",
            "reclassification_status": "propor_reclassificacao_documental",
            "manual_validation_reason": (
                "Pré-classificação analítica de adquirência; a decisão permanece pendente de revisão manual."
            ),
        }
        for column, value in values.items():
            result.loc[mask, column] = value
    unresolved = {
        "40906116000109": (
            "O regulamento identifica Banco Bradesco e Banco Bradescard como emissores/devedores; "
            "as demonstrações financeiras não foram localizadas no corpus para concluir a verificação tripla.",
            "Ausência de demonstrações financeiras anexadas para confirmar a composição efetiva.",
        ),
        "38376526000143": (
            "O regulamento combina adquirência com créditos parcelados de cursos e conteúdo sem predominância mensurável.",
            "Abertura da carteira por família de lastro não disponível.",
        ),
    }
    for cnpj, (reason, limitation) in unresolved.items():
        mask = result["cnpj_fundo"].eq(cnpj)
        if int(mask.sum()) != 1:
            raise ValueError(f"caso manual sem CNPJ único: {cnpj}")
        result.loc[mask, "reclassification_status"] = "requer_validacao_manual"
        result.loc[mask, "manual_validation_reason"] = reason
        result.loc[mask, "source_limitations"] = limitation
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("data/industry_study/generated_revision/base_fundo_cnpj.csv.gz"),
    )
    parser.add_argument("--periods", nargs="+", default=list(DEFAULT_PERIODS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    source_path = args.data_dir / "industry_top20_taxonomy_document_review.csv"
    output_path = args.data_dir / "industry_top20_taxonomy_document_conclusions.csv"
    manifest_path = (
        args.data_dir / "industry_top20_taxonomy_document_conclusions_manifest.json"
    )
    source = pd.read_csv(source_path, dtype=str, keep_default_na=False)
    source["cnpj_fundo"] = source["cnpj_fundo"].map(normalize_cnpj)
    if len(source) != 143 or source["cnpj_fundo"].nunique() != 143:
        raise ValueError("extração documental deve conter exatamente 143 CNPJs únicos")
    base = pd.read_csv(args.base, dtype={"cnpj_fundo": str}, low_memory=False)
    official = _latest_official(base, set(source["cnpj_fundo"]))
    review = source.merge(official, on="cnpj_fundo", how="left", validate="one_to_one")
    output = pd.DataFrame(
        [_conclude(row) for _, row in review.iterrows()], columns=list(OUTPUT_COLUMNS)
    ).sort_values(["nome_fidc", "cnpj_fundo"])
    output = _apply_documentary_overrides(output)
    if len(output) != 143 or output["cnpj_fundo"].nunique() != 143:
        raise ValueError("conclusões não reconciliaram os 143 CNPJs")
    if output["tipo_anbima_sugerido"].astype(str).str.strip().eq("").any():
        raise ValueError("toda conclusão deve possuir Tipo ANBIMA proposto")
    if output["reclassification_status"].astype(str).str.contains("ambigua").any():
        raise ValueError("a camada concluída não pode conter status ambíguo")
    output.to_csv(output_path, index=False)

    status_counts = output["reclassification_status"].value_counts().to_dict()
    confidence_counts = output["confianca_documental"].value_counts().to_dict()
    manifest = {
        "schema_version": "industry-top20-taxonomy-document-conclusions/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periods": [str(period) for period in args.periods],
        "ranking_positions": 320,
        "unique_cnpjs": int(output["cnpj_fundo"].nunique()),
        "conclusions": int(len(output)),
        "conclusions_with_readable_regulation": int(
            output["reading_method"].str.startswith("revisão documental assistida").sum()
        ),
        "provisional_conclusions": int(
            output["reclassification_status"]
            .eq("manter_provisoriamente_por_limitacao_documental")
            .sum()
        ),
        "status_counts": status_counts,
        "confidence_counts": confidence_counts,
        "official_fields_mutated": False,
        "manual_ledger_mutated": False,
        "input_sha256": {
            str(source_path): _digest(source_path),
            str(args.base): _digest(args.base),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
