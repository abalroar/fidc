"""Gera as matrizes auditáveis da revisão do Glossário de 100 FIDCs.

As evidências contratuais abaixo foram conferidas no corpus primário. O script
reabre a página indicada e extrai um trecho curto do próprio PDF, evitando que
paráfrases editoriais sejam apresentadas como citação. Frequências usam apenas
os 15 fundos com regulamento/anexo substantivo; o PAN Auto não entra no
denominador contratual e FIC-FIDCs não entram em práticas do crédito subjacente.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "reports" / "glossario_100_fidcs_20260716"
BOOK_DATA = ROOT / "docs" / "fidc" / "_data"


FUND_DOCUMENT: dict[str, str] = {
    "09195235000150": "fnet_reg_792797",
    "26286939000158": "fnet_reg_1017493",
    "26287464000114": "fnet_reg_1066031",
    "28169275000172": "fnet_reg_1149521",
    "29225241000110": "fnet_reg_784984",
    "42922136000107": "fnet_reg_1159092",
    "50906397000153": "fnet_reg_939418",
    "52242420000188": "fnet_reg_938243",
    "52610624000124": "fnet_reg_794164",
    "53216449000158": "fnet_reg_880741",
    "53263761000100": "fnet_reg_830304",
    "53286499000101": "fnet_reg_579249",
    "62393679000183": "fnet_reg_1117954",
    "63700113000110": "fnet_reg_1074015",
    "63953619000130": "fnet_reg_1222863",
}

FUNCTIONAL_TAXONOMY = {
    "09195235000150": "recebíveis de empresas do Sistema Petrobras",
    "26286939000158": "meios de pagamento",
    "26287464000114": "meios de pagamento",
    "28169275000172": "unidades de recebíveis de arranjo de pagamento",
    "29225241000110": "NPL, precatórios e créditos litigiosos",
    "42922136000107": "crédito pessoal",
    "50906397000153": "consignado e antecipação FGTS",
    "52242420000188": "consignado e antecipação FGTS",
    "52610624000124": "contratos de venda de energia",
    "53216449000158": "NPL e precatórios",
    "53263761000100": "NPL e precatórios",
    "53286499000101": "crédito privado multicarteira",
    "62393679000183": "meios de pagamento",
    "63700113000110": "crédito privado multicarteira",
    "63953619000130": "consignado privado",
}

TEMPLATE_FAMILY = {
    "09195235000150": "petrobras",
    "26286939000158": "cielo",
    "26287464000114": "tapso",
    "28169275000172": "pagseguro",
    "29225241000110": "alternative_assets_iii",
    "42922136000107": "monee",
    "50906397000153": "btg_consignados",
    "52242420000188": "btg_consignados",
    "52610624000124": "aetos",
    "53216449000158": "rio_esperanza",
    "53263761000100": "rio_esperanza",
    "53286499000101": "itau_nc",
    "63700113000110": "itau_nc",
    "62393679000183": "cloudwalk_bela",
    "63953619000130": "mt_global",
}


# termo, CNPJ do fundo, página física (1-based), cláusula, padrão para o trecho,
# categoria, definição proposta, tipo de afirmação, status editorial
CONTRACT_EVIDENCE: list[tuple[Any, ...]] = [
    ("fundo, classe, subclasse, série e cota", "26286939000158", 6, "definições do anexo", r"Classe|Subclasse|Série|Cota", "regime e arquitetura", "Níveis distintos: classe tem patrimônio; subclasses e séries diferenciam direitos de cotas.", "normativa refletida no contrato", "corrigir"),
    ("patrimônio segregado", "26286939000158", 7, "definição da classe", r"patrimônio segregado", "regime e arquitetura", "Patrimônio próprio da classe, sem patrimônio separado por subclasse.", "normativa refletida no contrato", "expandir"),
    ("fundo versus CNPJ da classe", "28169275000172", 1, "cabeçalho", r"CNPJ", "regime e arquitetura", "O identificador documental pode pertencer à classe; o fundo e as classes devem ser reconciliados.", "específica de fundo", "novo"),
    ("ausência de subordinação", "42922136000107", 58, "item 1.2(b)", r"pari passu|subordinação", "estrutura de capital", "Waterfall não implica necessariamente subclasses subordinadas.", "contraprova específica", "novo"),
    ("critérios de elegibilidade", "26286939000158", 59, "art. 4.1", r"Critérios de Elegibilidade|individualmente|cumulativamente", "elegibilidade", "Testes contratuais de entrada, distintos de existência e transferência.", "prática recorrente", "expandir"),
    ("elegibilidade versus concentração", "52610624000124", 38, "arts. 4.1 e 4.2", r"Critérios de Elegibilidade|concentração", "elegibilidade", "Teste individual e limite agregado são dimensões separadas.", "prática recorrente", "corrigir"),
    ("elegibilidade de NPL e precatório", "29225241000110", 8, "art. 4.7", r"precatório|inadimplid|litig", "termo por recebível", "Créditos vencidos ou litigiosos exigem critérios próprios; não definem todo FIDC.", "específica de subtipo", "novo"),
    ("limite de concentração", "26287464000114", 25, "art. 3.6.1", r"20%|concentração", "concentração", "Limites podem ter exceções e requisitos; o percentual de um fundo não é universal.", "prática recorrente", "expandir"),
    ("ausência de limite contratual", "63700113000110", 19, "art. 5.14", r"concentração máxima|devedor|cedente|originador", "concentração", "A inexistência contratual de determinado limite é caso específico, não regra.", "específica de fundo", "novo"),
    ("cessão sem regresso", "26286939000158", 55, "arts. 3.6 e 3.7", r"sem direito de regresso|coobrigação|existência", "transferência", "Ausência de regresso por solvência não elimina responsabilidade por existência e formalização.", "prática recorrente", "expandir"),
    ("cessão sem regresso", "26287464000114", 24, "arts. 3.1.5 e 3.1.6", r"sem regresso|coobrigação|existência", "transferência", "Ausência de regresso por solvência não elimina responsabilidade por vício.", "prática recorrente", "expandir"),
    ("cessão sem regresso", "28169275000172", 17, "arts. 3.14 e 3.15", r"sem direito de regresso|coobrigação|solvência", "transferência", "A responsabilidade do cedente precisa ser decomposta por risco de crédito e vício.", "prática recorrente", "expandir"),
    ("endosso eletrônico em preto", "63953619000130", 5, "arts. 4.5 a 4.10.3", r"endoss|eletronicamente|em preto", "transferência", "Endosso é forma própria de transferência e não alias automático de cessão civil.", "específica de subtipo", "novo"),
    ("recompra ou resolução por vício", "63953619000130", 8, "art. 4.22", r"recompra|resolução|desconform", "transferência", "Remédio por desconformidade original não equivale a proteção geral contra inadimplência.", "específica de fundo", "corrigir"),
    ("coobrigação possível", "53216449000158", 28, "arts. 5.2.1 e 5.7", r"com ou sem coobrigação|solvência", "transferência", "Coobrigação varia conforme o direito e o instrumento.", "específica de template", "novo"),
    ("verificação de lastro na aquisição", "28169275000172", 19, "arts. 3.27 a 3.29", r"verifica|existência|integridade|titularidade", "lastro", "Gestor ou terceiro supervisionado verifica lastro na aquisição.", "prática recorrente", "corrigir"),
    ("lastro na aquisição versus periódico", "50906397000153", 22, "arts. 12.15 a 12.21", r"Gestor|Custodiante|inadimplid|substitu", "lastro", "Aquisição e verificação periódica possuem responsáveis e objetos distintos.", "prática recorrente", "corrigir"),
    ("custodiante contratado para lastro", "62393679000183", 60, "arts. 9.6 a 9.8", r"Custodiante|verifica|document", "lastro", "O prestador efetivo depende do contrato, sob responsabilidade normativa aplicável.", "prática recorrente", "corrigir"),
    ("dispensa de verificação de lastro", "09195235000150", 18, "arts. 6º e 7º", r"dispens|lastro|Cedentes", "lastro", "Há dispensa específica; custodiante não é verificador universal.", "específica de fundo", "corrigir"),
    ("não incidência da verificação de lastro", "53286499000101", 55, "regra de lastro", r"artigo 36|verificação|não se enquad", "lastro", "A natureza do instrumento pode afastar a rotina do art. 36.", "específica de subtipo", "novo"),
    ("não incidência da verificação de lastro", "63700113000110", 52, "regra de lastro", r"artigo 36|verificação|guarda", "lastro", "A guarda documental pode permanecer mesmo quando a verificação não incide.", "específica de subtipo", "novo"),
    ("índice de subordinação", "52610624000124", 40, "art. 5.2.1", r"10%|subordinad", "estrutura de capital", "O índice é contratual; 10% é exemplo específico, não threshold universal.", "específica de fundo", "corrigir"),
    ("waterfall de caixa", "26286939000158", 106, "art. 12.8", r"Reserva|Sênior|Mezanino|Subordinad", "estrutura de capital", "Ordem de caixa é distinta da apropriação de resultado e da absorção de perdas.", "prática recorrente", "corrigir"),
    ("benchmark não garantido", "26286939000158", 105, "arts. 12.4 e 12.5", r"buscarão atingir|Benchmark|Patrimônio", "oferta e remuneração", "Índice ou meta não é obrigação incondicional de retorno.", "prática recorrente", "corrigir"),
    ("waterfall sem subordinação", "42922136000107", 56, "ordem de aplicação", r"ordem|Reserva|pari passu", "estrutura de capital", "Waterfall operacional pode coexistir com cotas pari passu.", "contraprova específica", "novo"),
    ("reserva de liquidez", "26286939000158", 104, "arts. 12.1 a 12.8", r"Reserva de Liquidez|Reserva de Caixa", "reforços e liquidez", "Reserva exige finalidade, alvo, saques e recomposição próprios.", "prática recorrente", "expandir"),
    ("reserva de despesas", "29225241000110", 10, "art. 4.23", r"Reserva|Encargos|3 \(três\) meses", "reforços e liquidez", "Reserva de despesas não deve ser fundida com reserva de amortização ou perdas.", "prática recorrente", "expandir"),
    ("reserva de aquisição", "62393679000183", 131, "definição operacional", r"Reserva de Aquisição|aquisição", "reforços e liquidez", "Reserva de aquisição financia compras e não é sinônimo de caixa livre.", "específica de fundo", "novo"),
    ("excesso de spread", "26286939000158", 106, "art. 12.8(f)", r"remanescente|Subordinad|resultado", "reforços de crédito", "Conceito analítico de margem residual; o rótulo literal não apareceu nos 15 regulamentos.", "inferência analítica", "conflito"),
    ("revolvência", "42922136000107", 32, "art. 5.8", r"novos Direitos Creditórios|recursos", "ciclo da carteira", "Aquisição de novos direitos com recursos da carteira durante período admitido.", "prática recorrente", "novo"),
    ("revolvência", "26287464000114", 26, "art. 3.11", r"Revolvência|novos Direitos Creditórios", "ciclo da carteira", "Aquisição de novos direitos com recursos da carteira durante período admitido.", "prática recorrente", "novo"),
    ("período de investimento", "63953619000130", 7, "arts. 4.17 a 4.17.3", r"29 de junho de 2031|reinvest", "ciclo da carteira", "Período de investimento delimita reinvestimento e não é sinônimo de ramp-up.", "específica de fundo", "novo"),
    ("ramp-up contratual", "62393679000183", 127, "índice mínimo inicial", r"180|Índice de Subordinação|primeiros", "ciclo da carteira", "Mudança inicial de parâmetro é específica; ocorreu em uma família no corpus.", "idiossincrática", "idiossincrático"),
    ("evento de avaliação", "52610624000124", 45, "arts. 8.1 e 8.2", r"Evento de Avaliação|Assembleia|sanad", "eventos e governança", "Evento, cura e consequência precisam ser capturados separadamente.", "prática recorrente", "corrigir"),
    ("dispensa de descumprimento", "28169275000172", 48, "deliberação de cotistas", r"dispens|Benchmark|Assembleia", "eventos e governança", "Dispensa específica é um waiver; não altera permanentemente a regra sem ato competente.", "específica de fundo", "novo"),
    ("não liquidação após evento", "26286939000158", 110, "art. 13.1.1", r"não liquidação|converter|Assembleia", "eventos e governança", "Evento de avaliação não equivale necessariamente a liquidação automática.", "prática recorrente", "corrigir"),
    ("rating não universal", "52610624000124", 40, "art. 5.1.4", r"não terão|classificação|agência", "oferta e rating", "Rating não é atributo obrigatório de toda cota de FIDC.", "contraprova específica", "corrigir"),
    ("rating por série", "62393679000183", 140, "apêndice de série", r"AAA|AA\+|rating|classificação", "oferta e rating", "Objeto, série, escala e data-base devem ser identificados.", "específica de fundo", "expandir"),
    ("aging contratual", "42922136000107", 42, "art. 13.2", r"1 a 30|31 a 60|61 a 90|91", "desempenho", "Faixas contratuais podem divergir da granularidade do Informe Mensal.", "específica de fundo", "expandir"),
    ("provisão versus perda", "26286939000158", 105, "art. 12.2", r"provisões|perdas reconhecidas", "desempenho e contabilidade", "Provisão e perda reconhecida são registros diferentes.", "prática recorrente", "corrigir"),
    ("provisão versus perda", "52610624000124", 43, "art. 6.1.3", r"provisões|perdas", "desempenho e contabilidade", "Política de mensuração deve distinguir estimativa e perda reconhecida.", "prática recorrente", "corrigir"),
]


NORMATIVE_EVIDENCE = [
    ("fundo", "rcvm_175_parte_geral", "art. 4º", "Fundo de investimento é comunhão de recursos sob condomínio de natureza especial.", "regime e arquitetura", "normativa", "expandir"),
    ("classe e patrimônio segregado", "rcvm_175_parte_geral", "art. 5º", "Cada classe possui patrimônio segregado; subclasse não recebe parcela patrimonial afetada.", "regime e arquitetura", "normativa", "corrigir"),
    ("cota", "rcvm_175_parte_geral", "art. 14", "Cota corresponde a fração do patrimônio da classe.", "regime e arquitetura", "normativa", "corrigir"),
    ("subclasse sênior, mezanino e subordinada", "rcvm_175_anexo_ii", "art. 2º, VIII a X", "Senioridade é atributo de subclasses de cotas dentro da classe.", "regime e arquitetura", "normativa", "corrigir"),
    ("série", "rcvm_175_anexo_ii", "arts. 2º, XXIII, e 8º", "Série é subconjunto de cotas seniores de classe fechada nas condições normativas.", "regime e arquitetura", "normativa", "novo"),
    ("índice referencial", "rcvm_175_anexo_ii", "art. 2º, XIV", "Índice usado como referência de rentabilidade de subclasse sênior ou mezanino.", "oferta e remuneração", "normativa", "expandir"),
    ("índice de subordinação", "rcvm_175_anexo_ii", "art. 2º, XV", "Relação mínima referente à subclasse subordinada ou mezanino e ao PL da classe.", "estrutura de capital", "normativa", "corrigir"),
    ("revolvência", "rcvm_175_anexo_ii", "art. 2º, XXII", "Aquisição de novos direitos com recursos da carteira conforme política e período definidos.", "ciclo da carteira", "normativa", "novo"),
    ("rating da subclasse sênior", "rcvm_175_anexo_ii", "art. 13, V", "Exigência específica quando cotas seniores são distribuídas ao público em geral.", "oferta e rating", "normativa", "corrigir"),
    ("verificação de lastro na aquisição", "rcvm_175_anexo_ii", "art. 36", "Responsabilidade do gestor, com contratação e amostragem admitidas nas condições da norma.", "lastro", "normativa", "corrigir"),
    ("custódia e verificação periódica", "rcvm_175_anexo_ii", "arts. 37 a 39", "Custódia depende do tipo de ativo; verificação periódica tem hipóteses próprias.", "lastro", "normativa", "corrigir"),
    ("alocação em direitos creditórios", "rcvm_175_anexo_ii", "art. 44", "Mais de 50% do PL em direitos creditórios; classe de cotas de FIDC observa mínimo de 67%.", "política de investimento", "normativa", "corrigir"),
    ("provisão", "icvm_489", "Capítulo III", "Ajuste contábil por redução do valor recuperável, distinto de perda realizada e caixa reservado.", "contabilidade", "normativa contábil", "corrigir"),
    ("write-off", "oficio_sin_snc_01_2013", "item 3", "Lançamento para perdas segue critérios próprios e não encerra necessariamente a cobrança.", "contabilidade", "orientação oficial", "novo"),
    ("segmentos da Tabela II", "oficio_sin_snc_01_2013", "item 5.2 e seguintes", "Tabela II classifica valores reportados; as aberturas financeiras possuem semântica própria.", "reporte regulatório", "orientação oficial", "novo"),
]


ANALYTIC_EVIDENCE = [
    (
        "First Payment Default (FPD)",
        "FPD; first payment default; default na primeira parcela",
        "glossary_methodology_20260716",
        "Convenções analíticas de desempenho",
        "Exposição da coorte em default na primeira obrigação dividida pela exposição elegível da coorte; coorte, janela e critério de default devem ser declarados.",
        "desempenho",
        "convenção analítica; ausência de definição literal no corpus varrido",
        "legado; corrigir",
    ),
]


PRACTICES: dict[str, dict[str, Any]] = {
    "critérios de elegibilidade explícitos": {"funds": list(FUND_DOCUMENT), "families": 12, "status": "expandir"},
    "linguagem explícita de concentração": {"funds": ["26286939000158", "26287464000114", "28169275000172", "29225241000110", "42922136000107", "50906397000153", "52242420000188", "52610624000124", "53216449000158", "53263761000100", "53286499000101", "62393679000183", "63700113000110", "63953619000130"], "families": 11, "status": "expandir"},
    "ordem de aplicação ou alocação de recursos": {"funds": list(FUND_DOCUMENT), "families": 12, "status": "corrigir"},
    "estrutura subordinada efetiva": {"funds": ["26286939000158", "26287464000114", "28169275000172", "52610624000124", "62393679000183", "63953619000130"], "families": 6, "status": "corrigir"},
    "reserva nominada": {"funds": ["26286939000158", "26287464000114", "28169275000172", "29225241000110", "42922136000107", "52610624000124", "53216449000158", "53263761000100", "62393679000183", "63953619000130"], "families": 9, "status": "expandir"},
    "revolvência ou reinvestimento autorizado": {"funds": ["26287464000114", "28169275000172", "29225241000110", "42922136000107", "50906397000153", "52242420000188", "53216449000158", "53263761000100", "62393679000183", "63700113000110", "63953619000130"], "families": 9, "status": "novo"},
    "ramp-up contratualmente definido": {"funds": ["62393679000183"], "families": 1, "status": "idiossincrático"},
    "evento de avaliação separado": {"funds": ["09195235000150", "26286939000158", "26287464000114", "28169275000172", "42922136000107", "50906397000153", "52242420000188", "52610624000124", "53216449000158", "53263761000100", "53286499000101", "62393679000183", "63700113000110", "63953619000130"], "families": 11, "status": "corrigir"},
    "evento de liquidação": {"funds": list(FUND_DOCUMENT), "families": 12, "status": "corrigir"},
    "cessão ou endosso estritamente sem regresso/coobrigação": {"funds": ["26286939000158", "26287464000114", "28169275000172", "42922136000107", "63953619000130"], "families": 5, "status": "expandir"},
    "dever positivo de verificação de lastro": {"funds": ["26286939000158", "26287464000114", "28169275000172", "29225241000110", "42922136000107", "50906397000153", "52242420000188", "52610624000124", "53216449000158", "53263761000100", "62393679000183", "63953619000130"], "families": 10, "status": "corrigir"},
    "dispensa ou não incidência de verificação de lastro": {"funds": ["09195235000150", "53286499000101", "63700113000110"], "families": 2, "status": "novo"},
    "expressão literal excesso de spread": {"funds": [], "families": 0, "status": "descartar como prática; manter apenas inferência analítica"},
}


GAP_ROWS = [
    ("overview", "escopo e Informe Mensal", "Limites repetidos e sem Tabela II.", "IME; visão geral", "RCVM 175; XML; Seller", "introdução", "Repete outras páginas.", "Níveis fundo/classe e fonte do gestor inconsistentes.", "PL por nível e cobertura do Informe.", "corrigir e expandir"),
    ("o-que-e-fidc", "FIDC e direitos creditórios", "Fundo como entidade separada e maioria sem coobrigação.", "recebíveis; créditos elegíveis", "RCVM 175; fundos antigos", "fundamentos", "Repete famílias e cessão.", "Recebível e elegibilidade fundidos; generalização sem denominador.", "Arquitetura RCVM 175.", "corrigir"),
    ("participantes", "prestadores", "Custodiante descrito como verificador universal.", "administrador; gestor; cedente", "RCVM 175; fundos antigos", "participantes", "Lastro repetido.", "INSS tratado como devedor; gestor do cadastro confundido com Informe.", "Arts. 36 a 39 e papéis operacionais.", "corrigir e expandir"),
    ("cessao-e-resolucao", "transferência e remédios", "Validade, elegibilidade, recompra e resolução agregadas.", "cessão; recompra", "três regulamentos ausentes", "transferência", "Coobrigação repetida.", "Cessão tratada como único modo; remédios universalizados.", "Endosso, regresso, coobrigação e lastro.", "corrigir e dividir"),
    ("hierarquia-regulatoria", "mapa normativo", "Mapa parcial de RCVM 175, 160, 30 e XML.", "175; 160; 30; 576", "fontes oficiais", "regulação", "Limites do Informe repetidos.", "Anexo II descrito com linguagem pré-RCVM 175.", "Contabilidade, ofícios e regime legado.", "corrigir e expandir"),
    ("oferta-rating-investidores", "oferta e rating", "Ritos e documentos generalizados.", "rating; rito automático", "RCVM 160; 30; ofertas ausentes", "oferta", "Rating repetido.", "Rating descrito como retrospectivo; rito automático simplificado.", "Emissão, benchmark, remuneração e objeto do rating.", "corrigir"),
    ("classes-cotas-waterfall", "arquitetura e waterfall", "Classe, subclasse, série, tranche e perdas misturadas.", "waterfall; subordinação", "RCVM 175; fundos antigos", "estrutura", "Subordinação repetida em métricas.", "Patrimônio segregado atribuído ao nível errado.", "Separar níveis, caixa, resultado e perdas.", "corrigir substancialmente"),
    ("recebiveis-financeiros", "famílias", "Cinco famílias e afirmação de que o Informe não as captura.", "consignado; cartão; veículos", "fundos antigos ausentes", "recebíveis", "Repete origem financeira.", "INSS como devedor; garantia implícita; Cielo contraditória.", "11 segmentos, F1-F8 e taxonomia documental.", "corrigir e expandir"),
    ("fidcs-originacao-if", "originação financeira", "Banco e fintech tratados como equivalentes.", "originação; fintech", "fundos antigos ausentes", "originação", "Repete famílias.", "Prevalências sem denominador.", "SCD/SEP, canal, safra, servicing e dependência.", "corrigir e expandir"),
    ("metricas-estruturais", "métricas", "Fórmulas sem nível, numerador, denominador ou unidade.", "PL; cobertura; FPD", "XML; fundos antigos", "métricas", "Subordinação duplicada.", "Proxy tratado como índice contratual; quase universal sem amostra.", "Fórmulas, WAL, liquidez, reservas separadas.", "corrigir e expandir"),
    ("provisao-perdas-e-inadimplencia", "desempenho contábil", "Provisão e perda esperada agregadas; aging truncado.", "PDD; atraso", "fundos antigos", "desempenho", "Atraso repetido em métricas.", "Cobertura acima/abaixo de 100% interpretada categoricamente.", "10 buckets, Over, cura, recuperação e write-off.", "corrigir e dividir"),
    ("eventos-avaliacao-liquidacao", "eventos", "Taxonomia contratual apresentada como escala geral.", "gatilho; liquidação", "RCVM 175; fundos antigos", "eventos", "Lastro repetido.", "Evento e liquidação confundidos; cura e governança ausentes.", "Waiver, consentimento, quórum e estados do evento.", "corrigir e expandir"),
    ("lastro-rating-reporting", "documentos e controles", "Título promete rating/reporting, corpo incompleto.", "lastro; assembleia", "ofício; documentos ausentes", "monitoramento", "Lastro repetido.", "Custodiante generalizado; demonstrativo trimestral omitido.", "Estados documentais e hierarquia de evidência.", "corrigir e expandir"),
    ("fundos-de-referencia", "casos narrativos", "10 fundos no texto e 8 no JSON, sem CNPJ ou versão.", "Seller; Facta; Geru", "13 caminhos locais ausentes", "exemplos", "Repete perfis por família.", "Cielo e coobrigação exigiam revalidação.", "Converter em metodologia e 10 casos primários reconciliados.", "depreciar catálogo e corrigir"),
    ("__lacuna__", "regime fundo/classe/subclasse", "Ausente ou incorreto.", "patrimônio segregado; série; tranche", "RCVM 175", "regime", "—", "—", "Página canônica e conceitos separados.", "criar"),
    ("__lacuna__", "participantes e prestadores", "Cobertura parcial.", "registradora; escriturador; distribuidor", "RCVM 175", "participantes", "—", "—", "Responsabilidade, contratação e continuidade.", "criar"),
    ("__lacuna__", "instrumentos e garantias", "Quase ausente.", "CCB; duplicata; CPR; aval; fiança", "RCVM 175; corpus", "ativos", "—", "—", "Instrumentos, garantias e diluição.", "criar"),
    ("__lacuna__", "Tabela II", "Ausente.", "11 segmentos; F1-F8", "XML; dados CVM", "reporte", "—", "—", "Página canônica com qualidade de dados.", "criar"),
    ("__lacuna__", "reforços, revolvência e liquidez", "Parcial ou ausente.", "reserva; excesso de spread; ramp-up; WAL", "RCVM 175; corpus", "estrutura", "—", "—", "Separar crédito e liquidez.", "criar"),
    ("__lacuna__", "recuperação e baixa", "Ausente.", "cura; roll rate; write-off; recuperação", "ICVM 489; ofícios", "desempenho", "—", "—", "Métricas com coorte e denominador.", "criar"),
    ("__lacuna__", "waivers e governança", "Ausente.", "waiver; consentimento; quórum", "RCVM 175; corpus", "eventos", "—", "—", "Estados auditáveis do evento.", "criar"),
    ("__lacuna__", "termos por recebível", "Cobertura financeira estreita.", "NPL; risco sacado; energia; precatório", "Tabela II; corpus", "recebíveis", "—", "—", "Cobrir segmentos e taxonomia documental.", "criar"),
]


def _normalize_cnpj(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(14)[-14:] if digits else ""


def _load_documents() -> dict[str, dict[str, Any]]:
    payload = json.loads((BOOK_DATA / "document_index.json").read_text(encoding="utf-8"))
    return {item["document_id"]: item for item in payload["documents"]}


def _snippet(path: Path, page_number: int, pattern: str) -> str:
    reader = PdfReader(path)
    if page_number < 1 or page_number > len(reader.pages):
        raise ValueError(f"Página {page_number} fora de {path} ({len(reader.pages)} páginas)")
    text = re.sub(r"\s+", " ", reader.pages[page_number - 1].extract_text() or "").strip()
    if not text:
        return "[página sem texto extraível; evidência conferida no corpus e marcada para OCR]"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    center = match.start() if match else 0
    start = max(0, center - 65)
    end = min(len(text), center + 150)
    snippet = text[start:end].strip()
    if start:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def build_evidence(report_dir: Path) -> pd.DataFrame:
    selection = pd.read_csv(report_dir / "selection_100.csv", dtype={"cnpj_fundo": str})
    selection["cnpj_fundo"] = selection["cnpj_fundo"].map(_normalize_cnpj)
    selected = selection.set_index("cnpj_fundo")
    documents = _load_documents()
    rows: list[dict[str, Any]] = []

    for term, source_id, article, excerpt, category, claim_type, status in NORMATIVE_EVIDENCE:
        source = json.loads((BOOK_DATA / "sources.json").read_text(encoding="utf-8"))["sources"]
        source_item = next(item for item in source if item["source_id"] == source_id)
        rows.append(
            {
                "termo_canonico": term,
                "aliases_grafias": "",
                "termo_legado_pre_rcvm175": "",
                "categoria": category,
                "definicao_proposta": excerpt,
                "tipo_afirmacao": claim_type,
                "cnpj_fundo": "",
                "fundo": "",
                "segmento_oficial": "",
                "subtipo_funcional_documental": "",
                "pl": "",
                "familia_documental_independente": "norma",
                "documento": source_item["title"],
                "documento_id": source_id,
                "documento_cnpj": "",
                "data_versao": "verificado em 2026-07-16",
                "pagina": "",
                "secao_clausula_artigo": article,
                "trecho_curto": excerpt,
                "trecho_tipo": "paráfrase normativa; conferir artigo indicado",
                "sha256": "",
                "confianca": "alta",
                "status": status,
                "fonte_primaria": source_item["location"],
                "fonte_metodologica": "",
            }
        )

    for term, aliases, source_id, section, excerpt, category, claim_type, status in ANALYTIC_EVIDENCE:
        source = json.loads((BOOK_DATA / "sources.json").read_text(encoding="utf-8"))["sources"]
        source_item = next(item for item in source if item["source_id"] == source_id)
        rows.append(
            {
                "termo_canonico": term,
                "aliases_grafias": aliases,
                "termo_legado_pre_rcvm175": "",
                "categoria": category,
                "definicao_proposta": excerpt,
                "tipo_afirmacao": claim_type,
                "cnpj_fundo": "",
                "fundo": "",
                "segmento_oficial": "",
                "subtipo_funcional_documental": "",
                "pl": "",
                "familia_documental_independente": "convenção analítica",
                "documento": source_item["title"],
                "documento_id": source_id,
                "documento_cnpj": "",
                "data_versao": "2026-07-16",
                "pagina": "",
                "secao_clausula_artigo": section,
                "trecho_curto": excerpt,
                "trecho_tipo": "definição metodológica interna; não é cláusula contratual",
                "sha256": "",
                "confianca": "alta quanto à convenção; não aplicável como prevalência contratual",
                "status": status,
                "fonte_primaria": "",
                "fonte_metodologica": source_item["location"],
            }
        )

    for term, cnpj, page, clause, pattern, category, definition, claim_type, status in CONTRACT_EVIDENCE:
        cnpj = _normalize_cnpj(cnpj)
        document_id = FUND_DOCUMENT[cnpj]
        document = documents[document_id]
        path = ROOT / document["local_path"]
        selection_row = selected.loc[cnpj]
        rows.append(
            {
                "termo_canonico": term,
                "aliases_grafias": "",
                "termo_legado_pre_rcvm175": "",
                "categoria": category,
                "definicao_proposta": definition,
                "tipo_afirmacao": claim_type,
                "cnpj_fundo": cnpj,
                "fundo": selection_row["nome"],
                "segmento_oficial": selection_row["segmento_oficial_tabela_ii"],
                "subtipo_funcional_documental": FUNCTIONAL_TAXONOMY[cnpj],
                "pl": float(selection_row["pl_agregado"]),
                "familia_documental_independente": TEMPLATE_FAMILY[cnpj],
                "documento": document["title"],
                "documento_id": document["fundosnet_id"],
                "documento_cnpj": document["cnpj"],
                "data_versao": document["document_date"] + "; " + document["version"],
                "pagina": page,
                "secao_clausula_artigo": clause,
                "trecho_curto": _snippet(path, page, pattern),
                "trecho_tipo": "extração do PDF primário na página conferida",
                "sha256": document["sha256"],
                "confianca": "alta",
                "status": status,
                "fonte_primaria": document["official_url"],
                "fonte_metodologica": "",
            }
        )

    evidence = pd.DataFrame(rows)
    evidence.to_csv(report_dir / "evidence_long.csv", index=False)
    return evidence


def build_candidates(report_dir: Path) -> pd.DataFrame:
    selection = pd.read_csv(report_dir / "selection_100.csv", dtype={"cnpj_fundo": str})
    selection["cnpj_fundo"] = selection["cnpj_fundo"].map(_normalize_cnpj)
    selected = selection.set_index("cnpj_fundo")
    denominator = list(FUND_DOCUMENT)
    denominator_pl = float(selected.loc[denominator, "pl_agregado"].sum())
    rows: list[dict[str, Any]] = []
    for term, practice in PRACTICES.items():
        funds = practice["funds"]
        subset = selected.loc[funds] if funds else selected.iloc[0:0]
        rows.append(
            {
                "termo_canonico": term,
                "aliases_grafias": "",
                "categoria": "prática contratual",
                "definicao_proposta": "Ver evidence_long.csv e verbete canônico; thresholds permanecem específicos do documento.",
                "tipo_afirmacao": "prática contratual" if funds else "ausência de expressão literal no corpus",
                "fundos_com_evidencia": len(funds),
                "denominador_documentacao_suficiente": len(denominator),
                "frequencia_equal_weight": len(funds) / len(denominator),
                "frequencia_ponderada_pl": (float(subset["pl_agregado"].sum()) / denominator_pl) if funds else 0.0,
                "familias_economicas_independentes": practice["families"],
                "administradores_distintos": int(subset["admin_cnpj"].replace("", pd.NA).nunique()) if funds else 0,
                "gestores_distintos": int(subset["gestor_cnpj"].replace("", pd.NA).nunique()) if funds else 0,
                "segmentos_oficiais": ";".join(sorted(set(subset["segmento_oficial_tabela_ii"].dropna()))) if funds else "",
                "cnpjs_com_evidencia": ";".join(funds),
                "exclui_fic_fidc": True,
                "escopo_calculo": "prevalência contratual no denominador substantivo",
                "status": practice["status"],
            }
        )

    evidence = pd.read_csv(report_dir / "evidence_long.csv", dtype={"cnpj_fundo": str}).fillna("")
    practice_terms = set(PRACTICES)
    for term, group in evidence.groupby("termo_canonico", sort=True):
        if term in practice_terms:
            continue
        funds = sorted({_normalize_cnpj(value) for value in group["cnpj_fundo"] if _normalize_cnpj(value)})
        subset = selected.loc[funds] if funds else selected.iloc[0:0]
        families = {
            value
            for value in group["familia_documental_independente"]
            if value and value not in {"norma", "convenção analítica"}
        }
        methodological = any("convenção analítica" in value for value in group["tipo_afirmacao"])
        no_fund_denominator = "não aplicável — convenção analítica" if methodological else "não aplicável — base normativa"
        no_fund_scope = "convenção analítica auditada; não implica prática de mercado" if methodological else "conceito de base normativa"
        rows.append(
            {
                "termo_canonico": term,
                "aliases_grafias": ";".join(sorted({value for value in group["aliases_grafias"] if value})),
                "categoria": ";".join(sorted(set(group["categoria"]))),
                "definicao_proposta": group.iloc[0]["definicao_proposta"],
                "tipo_afirmacao": ";".join(sorted(set(group["tipo_afirmacao"]))),
                "fundos_com_evidencia": len(funds),
                "denominador_documentacao_suficiente": len(denominator) if funds else no_fund_denominator,
                "frequencia_equal_weight": (len(funds) / len(denominator)) if funds else "",
                "frequencia_ponderada_pl": (float(subset["pl_agregado"].sum()) / denominator_pl) if funds else "",
                "familias_economicas_independentes": len(families),
                "administradores_distintos": int(subset["admin_cnpj"].replace("", pd.NA).nunique()) if funds else 0,
                "gestores_distintos": int(subset["gestor_cnpj"].replace("", pd.NA).nunique()) if funds else 0,
                "segmentos_oficiais": ";".join(sorted(set(subset["segmento_oficial_tabela_ii"].dropna()))) if funds else "",
                "cnpjs_com_evidencia": ";".join(funds),
                "exclui_fic_fidc": True,
                "escopo_calculo": "candidato atômico; frequência não implica prática de mercado" if funds else no_fund_scope,
                "status": ";".join(sorted(set(group["status"]))),
            }
        )
    candidates = pd.DataFrame(rows)
    candidates.to_csv(report_dir / "term_candidates.csv", index=False)
    return candidates


def build_gap_matrix(report_dir: Path) -> pd.DataFrame:
    columns = [
        "pagina",
        "conceito_ou_metrica",
        "definicao_atual_pre_revisao",
        "aliases_pre_revisao",
        "fontes_atuais_pre_revisao",
        "cobertura_tematica",
        "redundancias",
        "contradicoes",
        "afirmacoes_a_revalidar",
        "status_proposto",
    ]
    gap = pd.DataFrame(GAP_ROWS, columns=columns)
    gap.to_csv(report_dir / "glossary_gap_matrix.csv", index=False)
    return gap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    evidence = build_evidence(args.report_dir)
    candidates = build_candidates(args.report_dir)
    gap = build_gap_matrix(args.report_dir)
    print({"evidence_rows": len(evidence), "candidate_rows": len(candidates), "gap_rows": len(gap)})


if __name__ == "__main__":
    main()
