#!/usr/bin/env python3
"""Close the five CNPJs left open by the historical Top 20 documentary review.

Each decision below was produced by reading the primary documents obtained from
FundosNet for the specific CNPJ: the current regulation, the audited financial
statements, the portfolio composition file (CDA) or the structured monthly
report (IME), whichever carries the decisive description of the receivables.
The evidence quoted in ``evidence_summary`` is the literal passage used.

Official ANBIMA and CVM fields are not touched; the script only materializes the
curation CSV consumed by ``apply_fidc_documentary_decisions.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_fidc_outros_reclassification import OUTPUT_COLUMNS  # noqa: E402


DECISIONS: tuple[dict[str, object], ...] = (
    {
        "cnpj_fundo": "65473848000183",
        "nome_fidc": (
            "PAN AUTO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS "
            "RESPONSABILIDADE LIMITADA"
        ),
        "pl_max": "17971763062.82",
        "competencia_pl_max": "2026-06",
        "competencias_observadas": "2026-06",
        "tipo_anbima_oficial": "Agro, Indústria e Comércio",
        "foco_anbima_oficial": "Recebíveis Comerciais",
        "document_id": "1245057",
        "document_reference_date": "2026-06-30",
        "documentos_lidos": (
            "Informes Mensais Estruturados 1162975 (03/2026), 1189871 "
            "(04/2026), 1216989 (05/2026) e 1245057 (06/2026); Informe "
            "Trimestral 1196918 (03/2026); Instrumento Particular de "
            "Deliberacao Conjunta 1142758 (18/03/2026); demonstracoes "
            "financeiras de cisao do BTG EMPRESAS FIDC 1223038 (18/03/2026) e "
            "1241702 (08/04/2026); AGE 1142743 (18/03/2026)"
        ),
        "pagina_clausula": (
            "IME 03 a 06/2026, blocos SEGMT, COMPMT_DICRED_SEM_AQUIS e "
            "PRAZO_VENC; DF de cisao 18/03/2026, balanco patrimonial"
        ),
        "cedent_originator_expresso": (
            "Nao nomeado em documento. A parcela cindida do BTG EMPRESAS FIDC "
            "(CNPJ 55.521.594/0001-78) era caixa: em 18/03/2026 aquela classe "
            "tinha R$ 1,254 bi de PL com apenas R$ 2,3 mi em direitos "
            "creditorios (0,19%). A carteira de R$ 17,3 bi foi adquirida depois."
        ),
        "evidence_summary": (
            "Informes mensais de 03 a 06/2026, os quatro consistentes entre si: "
            "100% da carteira de direitos creditorios no segmento Comercial da "
            "Tabela II (VL_SOM_SEGMT_COMERC = VL_DICRED, R$ 17,285 bi em "
            "06/2026); 100% do saldo no bucket VL_PRAZO_VENC_1080, ou seja "
            "vencimento acima de 1.080 dias; todo o saldo registrado no bloco "
            "COMPMT_DICRED_SEM_AQUIS, isto e, aquisicao SEM transferencia "
            "substancial de riscos e beneficios; VL_DICRED_CEDENT igual ao "
            "total; inadimplencia zero em todos os aging; um unico cotista, que "
            "e outro fundo; condominio fechado, sem estrutura de subordinacao. "
            "O informe trimestral de 03/2026 afirma aquisicao de precatorios "
            "federais, mas o informe mensal da mesma competencia reporta "
            "Acoes judiciais = R$ 0,00 e Comercial = 100%; o texto e o "
            "formulario-padrao do administrador, cuja versao do BTG EMPRESAS "
            "FIDC responde a mesma pergunta com outra opcao."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Financiamento de Veículos",
        "tabela_ii_sugerida_documental": "Comercial",
        "taxonomia_funcional_n1_sugerida": "Crédito PF",
        "taxonomia_funcional_n2_sugerida": "Auto/Veículos",
        "decision_status": "em_revisao",
        "confianca_documental": "media",
        "justificativa_curta": (
            "A hipotese de carteira de credito PF veiculos e sustentada por "
            "quatro fatos documentais convergentes e nao e refutada por nenhum: "
            "(i) 100% do saldo com vencimento acima de 1.080 dias, perfil "
            "impossivel para recebiveis comerciais e tipico de CDC de veiculos "
            "de 48 a 60 meses; (ii) registro integral como aquisicao sem "
            "transferencia substancial de riscos, que e a estrutura de funding "
            "em que o originador retem o risco; (iii) o segmento Comercial e "
            "exatamente o que o FIDC GM - Venda de Veiculos e o Venda de "
            "Veiculos FIDC declaram para carteiras de veiculos, enquanto bancos "
            "que cedem CDC proprio declaram Financeiro; (iv) o administrador e "
            "a BTG Pactual Servicos Financeiros e o custodiante e o Banco BTG "
            "Pactual, controlador do Banco Pan, que constituiu na mesma data o "
            "PAN CONSIGNADO FIDC - uma familia segmentada por produto de "
            "varejo. Falta a clausula que nomeie o lastro, de modo que a "
            "decisao fica em revisao e nao entra no mix analitico."
        ),
        "reading_method": (
            "informes_mensais_estruturados_trimestral_e_demonstracoes_de_cisao"
        ),
        "manual_validation_reason": (
            "O regulamento do fundo nao foi publicado no FundosNet - as unicas "
            "pecas disponiveis sob o CNPJ sao informes periodicos e um ato de "
            "emissao de cotas. Reprocessar quando o regulamento for publicado."
        ),
        "source_limitations": (
            "Sem regulamento publicado, nenhum documento nomeia o produto de "
            "credito. O nome do fundo nao e usado como evidencia. A Tabela II "
            "analitica adota o segmento declarado pelo proprio veiculo."
        ),
    },
    {
        "cnpj_fundo": "40906116000109",
        "nome_fidc": "FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS CIELO EMISSORES II",
        "pl_max": "10583128000.00",
        "competencia_pl_max": "2024-12",
        "competencias_observadas": "2024-12, 2023-12",
        "tipo_anbima_oficial": "Financeiro",
        "foco_anbima_oficial": "Multicarteira Financeiro",
        "document_id": "977307",
        "document_reference_date": "2025-07-23",
        "documentos_lidos": (
            "Demonstrações Financeiras 977307 (23/07/2025); Regulamento 908304 "
            "(10/02/2025)"
        ),
        "pagina_clausula": "Demonstrações financeiras, nota explicativa 5 (a) — descrição",
        "cedent_originator_expresso": (
            "Cedente: Cielo (sistema Cielo, credenciadora); devedores: emissores "
            "dos instrumentos de pagamento"
        ),
        "evidence_summary": (
            "Nota 5 (a): «OS DIREITOS CREDITÓRIOS ERAM ORIUNDOS DO PAGAMENTO "
            "DEVIDO PELO DEVEDOR À CEDENTE, DECORRENTES DE TRANSAÇÕES DE "
            "PAGAMENTO REALIZADAS POR USUÁRIOS-FINAIS, OPERACIONALIZADAS PELO "
            "SISTEMA CIELO»; e «DIREITOS CREDITÓRIOS EM FACE DO DEVEDOR (QUE ERA "
            "UM EMISSOR) DOS INSTRUMENTOS DE PAGAMENTO COM BANDEIRA VISA». A "
            "mesma nota registra que a estrutura foi desenhada para que o fundo "
            "não assumisse chargebacks, isolando o risco no emissor."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Cartão de crédito",
        "tabela_ii_sugerida_documental": "Cartão de crédito",
        "taxonomia_funcional_n1_sugerida": "Meios de Pagamento e Cartões",
        "taxonomia_funcional_n2_sugerida": "Bancos Emissores",
        "decision_status": "aprovado",
        "confianca_documental": "alta",
        "justificativa_curta": (
            "As demonstrações financeiras auditadas fecham a verificação tripla "
            "pendente: o cedente é a credenciadora, o devedor é o banco emissor "
            "e o fundo não assume o risco de chargeback do estabelecimento. O "
            "risco predominante é o do emissor, e não o da adquirência."
        ),
        "reading_method": "leitura_pagina_a_pagina_demonstracoes_financeiras",
        "source_limitations": (
            "O fundo foi encerrado em 23/07/2025; a conclusão vale para as "
            "competências em que o veículo integrou o ranking."
        ),
    },
    {
        "cnpj_fundo": "38376526000143",
        "nome_fidc": (
            "HOTFUND FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO "
            "MEIOS DE PAGAMENTO DE RESPONSABILIDADE LIMITADA"
        ),
        "pl_max": "2088000000.00",
        "competencia_pl_max": "2025-12",
        "competencias_observadas": "2025-12, 2024-12",
        "tipo_anbima_oficial": "Agro, Indústria e Comércio",
        "foco_anbima_oficial": "Recebíveis Comerciais",
        "document_id": "1072072",
        "document_reference_date": "2025-09-30",
        "documentos_lidos": (
            "Demonstrações Financeiras 1072072 (30/09/2025); Regulamento 948252 "
            "(02/07/2025)"
        ),
        "pagina_clausula": "Demonstrações financeiras, nota explicativa 6 (a) e 6 (e)",
        "cedent_originator_expresso": (
            "Cedentes: Produtores (estabelecimentos comerciais da plataforma "
            "Hotmart); devedora dos direitos creditórios cartões: Launch Pad "
            "Tecnologia, Serviços e Pagamentos Ltda. (Hotmart), subcredenciadora"
        ),
        "evidence_summary": (
            "Nota 6 (a): «…DECORRENTES DE TRANSAÇÕES DE PAGAMENTO REALIZADAS "
            "POR USUÁRIOS COMPRADORES COM CARTÃO, À VISTA OU PARCELADAS, "
            "OPERACIONALIZADA PELO SISTEMA HOTPAY NO ÂMBITO DO RESPECTIVO "
            "ARRANJO DE PAGAMENTO»; «A MAIS RELEVANTE PARA FINS DA OPERAÇÃO DA "
            "CLASSE É O CRÉDITO DO PRODUTOR EM FACE DA SUBCREDENCIADORA (I.E., "
            "HOTMART)». A liquidação descrita na mesma nota passa por bandeiras, "
            "CIP/SILOC e credenciadoras."
        ),
        "tipo_anbima_sugerido": "Financeiro",
        "foco_anbima_sugerido": "Adquirência",
        "tabela_ii_sugerida_documental": "Adquirência",
        "taxonomia_funcional_n1_sugerida": "Meios de Pagamento e Cartões",
        "taxonomia_funcional_n2_sugerida": "Arranjos de pagamento/adquirência",
        "decision_status": "aprovado",
        "confianca_documental": "media",
        "justificativa_curta": (
            "As demonstrações financeiras resolvem a mistura apontada na "
            "revisão anterior: os cursos e conteúdos são a mercadoria "
            "subjacente, não a família do direito creditório. O crédito "
            "adquirido é o do produtor contra a subcredenciadora dentro de um "
            "arranjo de pagamento, o que caracteriza adquirência."
        ),
        "reading_method": "leitura_pagina_a_pagina_demonstracoes_financeiras",
        "source_limitations": (
            "A carteira também admite «direitos creditórios recebíveis a prazo» "
            "devidos por usuários compradores, cedidos com coobrigação do "
            "produtor; as demonstrações não abrem a participação de cada "
            "família no saldo."
        ),
    },
    {
        "cnpj_fundo": "53323654000112",
        "nome_fidc": (
            "POSITIVO IV FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO "
            "INVESTIMENTO NO EXTERIOR RESP LIMITADA"
        ),
        "pl_max": "3002443914.92",
        "competencia_pl_max": "2023-12",
        "competencias_observadas": "2023-12",
        "tipo_anbima_oficial": "N/D",
        "foco_anbima_oficial": "",
        "document_id": "731526",
        "document_reference_date": "2024-08-27",
        "documentos_lidos": (
            "Regulamento 731526 (27/08/2024); Demonstrações Financeiras 910283 "
            "(09/10/2024)"
        ),
        "pagina_clausula": "Anexo A — Anexo Descritivo da Classe de Cotas A, p. 48, artigo 2º",
        "cedent_originator_expresso": (
            "Cedente definido no Anexo Descritivo A; direitos creditórios "
            "judiciais e de empresas em recuperação"
        ),
        "evidence_summary": (
            "Anexo Descritivo A, p. 48: os Direitos Creditórios Elegíveis "
            "Classe A podem referir-se a créditos que «VIEREM A SER ATRIBUÍDOS, "
            "CONSTITUÍDOS E/OU RECONHECIDOS EM SEU ÂMBITO, E AOS OFÍCIOS "
            "REQUISITÓRIOS E/OU PRECATÓRIOS JÁ EXPEDIDOS OU A EXPEDIR; OU, "
            "AINDA, SER ORIGINADOS DE EMPRESAS EM PROCESSO DE RECUPERAÇÃO "
            "JUDICIAL OU EXTRAJUDICIAL». As demonstrações financeiras de "
            "09/10/2024 confirmam que o CNPJ operava como POSITIVO III FIDC, "
            "criado em 28/12/2023 pela cisão do POSITIVO II FIDC-NP."
        ),
        "tipo_anbima_sugerido": "Outros",
        "foco_anbima_sugerido": "Poder Público",
        "tabela_ii_sugerida_documental": "Ações judiciais",
        "taxonomia_funcional_n1_sugerida": "Judicial/Precatórios/NPL",
        "taxonomia_funcional_n2_sugerida": "Precatórios/direitos judiciais",
        "decision_status": "aprovado",
        "confianca_documental": "alta",
        "justificativa_curta": (
            "A proposta anterior de correção de perímetro estava incompleta: na "
            "competência em que o CNPJ integra o ranking (dez/2023) o veículo "
            "era o POSITIVO III FIDC, com lastro expresso em ofícios "
            "requisitórios, precatórios e créditos de empresas em recuperação. "
            "O fundo permanece em Outros, mas o foco deixa de ser N/D."
        ),
        "reading_method": "leitura_pagina_a_pagina_regulamento_e_demonstracoes",
        "source_limitations": (
            "O CNPJ foi transformado em fundo de investimento financeiro em "
            "09/10/2024 e deixa o perímetro FIDC a partir de então; a "
            "classificação vale para as competências anteriores."
        ),
    },
    {
        "cnpj_fundo": "34218864000104",
        "nome_fidc": (
            "CLASSE ÚNICA MULTIMERCADO DO FUNDO DE INVESTIMENTO FINANCEIRO "
            "MOTO-HONDA"
        ),
        "pl_max": "1877653522.98",
        "competencia_pl_max": "2026-02",
        "competencias_observadas": "2025-12, 2024-12, 2023-12",
        "tipo_anbima_oficial": "Agro, Indústria e Comércio",
        "foco_anbima_oficial": "Recebíveis Comerciais",
        "document_id": "1140797",
        "document_reference_date": "2026-03-13",
        "documentos_lidos": "Regulamento 1140797 (13/03/2026), 45 páginas",
        "pagina_clausula": "Anexo da Classe Única Multimercado, p. 19 a 24 — política de investimentos",
        "cedent_originator_expresso": (
            "Moto Honda da Amazônia e rede de Concessionárias citadas apenas na "
            "7ª Convenção Parcial da Marca Honda, sem cessão de direitos "
            "creditórios prevista na política vigente"
        ),
        "evidence_summary": (
            "Anexo p. 19: «INVESTIR EM ATIVOS FINANCEIROS E/OU MODALIDADES "
            "OPERACIONAIS QUE ENVOLVAM DIVERSOS FATORES DE RISCO, SEM O "
            "COMPROMISSO DE CONCENTRAÇÃO EM QUALQUER FATOR EM ESPECIAL». Os "
            "quadros de limites da p. 21 admitem cotas de FIDC entre 0% e 40%, "
            "debêntures, certificados de recebíveis e BDR, sem qualquer "
            "previsão de aquisição direta de direitos creditórios nem de "
            "critérios de elegibilidade."
        ),
        "tipo_anbima_sugerido": "",
        "foco_anbima_sugerido": "",
        "tabela_ii_sugerida_documental": "",
        "taxonomia_funcional_n1_sugerida": "",
        "taxonomia_funcional_n2_sugerida": "",
        "decision_status": "rejeitado",
        "confianca_documental": "alta",
        "perimeter_proposal": (
            "Excluir o CNPJ do universo FIDC a partir da vigência do "
            "regulamento de 13/03/2026, mediante confirmação cadastral na CVM."
        ),
        "justificativa_curta": (
            "A hipótese de classificar o CNPJ como FIDC está incorreta para o "
            "regulamento vigente: trata-se de um fundo de investimento "
            "financeiro multimercado, cuja política de investimentos não "
            "contempla aquisição de direitos creditórios, apenas cotas de FIDC "
            "e ativos financeiros."
        ),
        "reading_method": "leitura_pagina_a_pagina_regulamento",
        "source_limitations": (
            "A exclusão do ranking histórico depende de confirmação do "
            "enquadramento da classe no cadastro CVM; o veículo reportou "
            "informe mensal de FIDC de 2019 a 2026."
        ),
    },
    {
        "cnpj_fundo": "55859549000128",
        "nome_fidc": "ZETA FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO",
        "pl_max": "4172307002.74",
        "competencia_pl_max": "2025-12",
        "competencias_observadas": "2025-12, 2024-12",
        "tipo_anbima_oficial": "Outros",
        "foco_anbima_oficial": "",
        "document_id": "1081923",
        "document_reference_date": "2025-12-31",
        "documentos_lidos": (
            "Composição da Carteira (CDA) 1081923 (12/2025); Demonstrações "
            "Financeiras 891916 (31/01/2025)"
        ),
        "pagina_clausula": "CDA 12/2025, blocos COTAS e TIT_PUB",
        "cedent_originator_expresso": (
            "Nenhum cedente: a carteira é composta por cotas de outros fundos"
        ),
        "evidence_summary": (
            "CDA de 12/2025 com VL_PL 4.172.307.002,74: a carteira registra "
            "exclusivamente cotas de outros fundos e títulos públicos — "
            "3.830.956.071,90 em cotas do MT CONSIGNADO PRIVADO I FIDC "
            "(60.010.416/0001-12), 162.513.170,19 e 29.228.461,81 em cotas dos "
            "PLGN MARKETPLACE FIC-FIDC, 47.723.071,56 no V CDT 1 FIDC, "
            "46.254.947,28 no BTG PACTUAL CERES CONFINA e 55.825.279,23 em "
            "LTN. Não há aquisição direta de direitos creditórios."
        ),
        "tipo_anbima_sugerido": "",
        "foco_anbima_sugerido": "",
        "tabela_ii_sugerida_documental": "",
        "taxonomia_funcional_n1_sugerida": "",
        "taxonomia_funcional_n2_sugerida": "",
        "decision_status": "rejeitado",
        "confianca_documental": "alta",
        "is_fic_fidc_suggested": "True",
        "perimeter_proposal": (
            "Marcar o CNPJ como veículo de cotas (FIC) para evitar dupla "
            "contagem de R$ 4,17 bi já reportados pelos fundos investidos."
        ),
        "justificativa_curta": (
            "A hipótese de reclassificar o veículo como FIDC direto em Outros "
            "está incorreta: a composição de carteira mostra um alimentador que "
            "detém apenas cotas de outros fundos, sendo 92% em um único FIDC de "
            "consignado privado. Classificá-lo por tipo duplicaria patrimônio "
            "já contado."
        ),
        "reading_method": "leitura_da_composicao_de_carteira_e_demonstracoes",
        "source_limitations": (
            "O regulamento não está publicado no FundosNet; a conclusão apoia-se "
            "na composição de carteira reportada à CVM."
        ),
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    return parser.parse_args()


def build_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for decision in DECISIONS:
        row = {column: "" for column in OUTPUT_COLUMNS}
        row.update(
            {
                "review_scope": "top20_pendentes_encerramento",
                "rank_reference": "Top 20 ANBIMA — fila remanescente",
                "document_url": (
                    "https://fnet.bmfbovespa.com.br/fnet/publico/"
                    f"abrirGerenciadorDocumentosCVM?cnpjFundo={decision['cnpj_fundo']}"
                ),
                "is_fic_fidc_suggested": "False",
            }
        )
        row.update({key: value for key, value in decision.items() if key in row})
        row["cedent_originator_explicit"] = str(
            decision.get("cedente_originador_expresso", "")
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))


def main() -> None:
    args = parse_args()
    frame = build_frame()
    path = args.data_dir / "industry_top20_pending_curation.csv"
    frame.to_csv(path, index=False)
    print(f"{len(frame)} decisões documentais gravadas em {path}")


if __name__ == "__main__":
    main()
