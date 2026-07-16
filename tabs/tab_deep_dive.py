from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
import math
import re
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from services.deep_dive_ppt_export import build_deep_dive_pptx_bytes
from services.deep_dive_store import (
    deep_dive_matches_portfolio,
    list_deep_dives,
    load_deep_dive_table,
)
from services.fundonet_dashboard import build_dashboard_data
from services.fundonet_service import InformeMensalService
from services.ime_loader import load_or_extract_informe
from services.ime_period import current_default_end_month, shift_month
from services.monitoring_metrics import build_monitoring_tables, read_wide_csv
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from services.waterfall_schedule import (
    DEFAULT_CLOUDWALK_EMISSIONS,
    DEFAULT_WATERFALL_OUTPUT_DIR,
    build_waterfall_schedule,
    export_waterfall,
    load_cloudwalk_emissions,
    load_cloudwalk_ime_assets,
    only_digits,
)
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    list_saved_portfolios,
)


_CSS = """
<style>
.deepdive-kicker {
    color: #6b7280;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.deepdive-title {
    color: #1f1f1f;
    font-size: 1.55rem;
    font-weight: 650;
    line-height: 1.15;
    margin: 0.1rem 0 0.25rem 0;
}
.deepdive-subtitle {
    color: #6b7280;
    font-size: 0.86rem;
    line-height: 1.35;
    margin-bottom: 0.65rem;
}
.deepdive-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin: 0.45rem 0 0.8rem 0;
}
.deepdive-chip {
    background: #f7f7f7;
    border: 1px solid #e0e0e0;
    border-radius: 999px;
    color: #4d4d4d;
    display: inline-flex;
    font-size: 0.74rem;
    line-height: 1.15;
    padding: 5px 9px;
}
.deepdive-table-wrap {
    border: 1px solid #d9dee5;
    border-radius: 4px;
    max-width: 100%;
    overflow-x: auto;
}
.deepdive-table {
    border-collapse: collapse;
    font-size: 0.76rem;
    table-layout: fixed;
    width: 100%;
}
.deepdive-table th {
    background: #111827;
    border-right: 1px solid rgba(255,255,255,0.14);
    color: #ffffff;
    font-weight: 650;
    line-height: 1.18;
    padding: 6px 7px;
    text-align: center;
    vertical-align: middle;
}
.deepdive-table th:first-child {
    text-align: left;
    width: 230px;
}
.deepdive-table th.highlight {
    background: #ec7000;
}
.deepdive-table td {
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #eeeeee;
    color: #1f1f1f;
    line-height: 1.20;
    padding: 5px 7px;
    text-align: center;
    vertical-align: middle;
    word-break: normal;
    overflow-wrap: anywhere;
}
.deepdive-table td.longtext {
    font-size: 0.72rem;
    line-height: 1.26;
    text-align: left;
    vertical-align: top;
}
.deepdive-cell-list {
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.deepdive-cell-list div {
    border-bottom: 1px solid #eeeeee;
    padding-bottom: 3px;
}
.deepdive-cell-list div:last-child {
    border-bottom: 0;
    padding-bottom: 0;
}
.deepdive-table td:first-child {
    background: #f7f7f7;
    font-weight: 650;
    text-align: left;
}
.deepdive-table td.highlight {
    background: #fff2e8;
}
.deepdive-table tr:nth-child(even) td:not(:first-child):not(.highlight) {
    background: #fbfbfb;
}
.deepdive-live-note {
    color: #6b7280;
    font-size: 0.74rem;
    line-height: 1.25;
    margin: 0.25rem 0 0.55rem 0;
}
.deepdive-curadoria-note {
    color: #6b7280;
    font-size: 0.76rem;
    line-height: 1.35;
    margin: 0.1rem 0 0.45rem 0;
}
</style>
"""

_LIVE_IME_ROWS = {
    "PL (R$ mm)": "PL (R$ MM)",
    "Direitos creditórios / PL": "Dir Cred / PL",
    "Vencidos Over 30d / crédito": "Vencidos Over 30 d / Crédito",
    "Vencidos Over 60d / crédito": "Vencidos Over 60 d / Crédito",
    "Vencidos Over 90d / crédito": "Vencidos Over 90 d / Crédito",
    "Vencidos Over 180d / crédito": "Vencidos Over 180 d / Crédito",
    "Vencidos Over 360d / crédito": "Vencidos Over 360 d / Crédito",
    "PDD / crédito": "PDD / Crédito",
    "PDD / vencidos": "PDD / Venc Total",
    "Cotas sênior / PL": "Cotas SR / PL %",
    "Cotas mezanino / PL": "Cotas MZ / PL %",
    "Cotas subordinadas / PL": "Cotas Sub / PL %",
}

_LONG_TEXT_ROWS = {
    "Emissões detectadas (data, classe, preço e volume)",
    "Remuneração-alvo por emissão detectada",
    "Amortização/vencimento por emissão detectada",
    "Hedges permitidos",
}

_REVERSE_ENGINEERING_PROMPT = """Você é Codex trabalhando no repositório local `/fidc`.

Tarefa: fazer o Deep Dive regulatório de UMA ÚNICA carteira específica e atualizar o pacote consumido pela aba Deep Dive. Atue como advogado de mercado de capitais, estruturador de renda fixa e engenheiro Python: leia documentos integralmente quando necessário, reconstrua termos econômicos, traduza regras jurídicas em dados auditáveis e diga claramente o que não é monitorável pelo Informe Mensal Estruturado (IME).

INPUTS DA EXECUÇÃO:
- Nome da carteira: [NOME_DA_CARTEIRA]
- CNPJs dos fundos: [LISTA_DE_CNPJS]
- Caminho do repositório: /Users/matheusjprates/fidc
- Período de análise / competência IME: [PERÍODO]
- Deep Dive ID esperado: [DEEP_DIVE_ID]
- Outputs esperados: perfis curados em `data/regulatory_profiles`, pacote `data/deep_dives/<deep_dive_id>/`, evidências, notas de auditoria e PPTX QA editável.

CONTRATO ATUAL DA ABA DEEP DIVE, JÁ VERIFICADO NO REPOSITÓRIO:
1. A aba consome `data/deep_dives/*/manifest.json`; cada pacote deve ter tabelas em `tables/` e evidências/notas em `evidence/` e `notes/`.
2. Tabelas padrão do manifesto: `comparison_main`, `structural_costs`, `emissions`, `thresholds`. Tabelas adicionais como `key_findings`, `cedentes_sacados_origem`, `source_vehicle_trace`, `document_inventory` ou `fundonet_document_inventory` são bem-vindas quando ajudam a diligência.
3. `comparison_main.csv` precisa ter primeira coluna `Nome` e uma coluna por fundo. As 31 linhas hoje renderizadas são, nesta ordem: Grupo; CNPJ; Páginas locais analisadas; Última competência IME; PL (R$ mm); Direitos creditórios / PL; Vencidos Over 30d / crédito; Vencidos Over 60d / crédito; Vencidos Over 90d / crédito; Vencidos Over 180d / crédito; Vencidos Over 360d / crédito; PDD / crédito; PDD / vencidos; Cotas sênior / PL; Cotas mezanino / PL; Cotas subordinadas / PL; Séries/classes emitidas identificadas; Volume emitido identificado (R$ mm); Primeira emissão identificada; Última emissão identificada; Emissões detectadas (data, classe, preço e volume); Remuneração-alvo por emissão detectada; Amortização/vencimento por emissão detectada; Regulamento-base dos thresholds; Alocação mínima em DCs; Subordinação mínima; Evento de avaliação por atraso; Liquidação/vencimento por atraso; Cobertura mínima PDD; Reserva/caixa mínimo; Hedges permitidos.
4. `emissions.csv` da aba deve ter colunas: `Fundo`, `CNPJ`, `Data`, `Classe/Série`, `Tipo`, `Qtd cotas`, `Preço/VNU`, `Volume identificado (R$ mm)`, `Remuneração-alvo`, `Amortização/vencimento`, `Fonte`.
5. O perfil curado de emissões em `data/regulatory_profiles/<slug>_cotas_emissoes_pagamentos.csv` deve preservar, quando disponível: `Fundo`, `CNPJ`, `Cota/Classe`, `Tipo`, `Data deliberação`, `Data emissão / 1ª integralização`, `Data encerramento/oferta`, `Quantidade`, `Volume`, `VNU`, `Remuneração`, `Juros/remuneração`, `Amortização principal`, `Status/evidência`, `Fonte`, `Status curadoria`, `arquivo_origem_tabela`.
6. `thresholds.csv` da aba deve ter colunas: `fundo`, `CNPJ`, `Data regulamento`, `Critério`, `Evento`, `Comparação`, `Limite`, `Monitorável IME`, `Métrica IME`, `Fonte`.
7. O perfil curado de critérios em `data/regulatory_profiles/<slug>_criteria_monitoraveis_ime.csv` deve ter colunas: `Fundo`, `CNPJ`, `Critério`, `Chave`, `Limite/regra`, `Monitorabilidade IME`, `Métrica IME / proxy`, `Condição de alerta sugerida`, `Observação técnica`, `Fonte`, `Status curadoria`.
8. Chaves já usadas: `credit_rights_allocation_min`, `subordination_ratio_min`, `default_rate_evaluation_event`, `default_rate_early_maturity`, `pdd_coverage_min`, `minimum_cash_ratio`, `permitted_hedges`, `concentration_limits`, `eligibility_criteria`, `repurchase_indemnity`, `credit_rights_tax_allocation`, `day_trade_ban`, `minimum_net_worth`, `cash_sweep_amortization`, `invested_fund_exposure`, `servicer_identification`, `source_vehicle_trace`, `cnpj_resolution`, `originator_debtor_granularity`.
9. Valores de monitorabilidade já aceitos: `monitoravel`, `monitoravel com ressalva`, `direto com validação`, `direto com ressalva`, `direto agregado`, `parcial`, `parcial fraco`, `nao_monitoravel`, `não usar via IME`. Use a grafia existente do perfil que estiver replicando; explique sempre a ressalva.
10. `structural_costs.csv` deve ter colunas: `Fundo`, `CNPJ`, `Item`, `Percentual a.a.`, `Mínimo mensal`, `Fonte`, `Versão vigente / base documental`, `Mudanças relevantes`, `Status curadoria`; deve haver linha de Administração e Gestão por fundo, mesmo que como lacuna explícita.
11. A aba Deep Dive atualiza ao vivo, quando a linha existe em `comparison_main`, as métricas IME: Última competência IME; PL (R$ mm); Direitos creditórios / PL; Vencidos Over 30/60/90/180/360d / crédito; PDD / crédito; PDD / vencidos; Cotas sênior/mezanino/subordinadas / PL.
12. A aba Monitoramento avalia proxies com `build_monitoring_tables`: Dir Cred / PL, Over 30/60/90/180/360, PDD / Crédito, PDD / Venc Total, Recompras / Crédito, Cotas SR/MZ/Sub / PL, PL, caixa/disponibilidades e derivativos agregados. Ela classifica verificações como OK, Alerta, Sem dado, Referência ou Qualitativo.

REGRAS INEGOCIÁVEIS:
1. Analise apenas esta carteira. É proibido atualizar todas as carteiras ou fazer batch.
2. Não misture documentos de outros grupos econômicos, fundos homônimos ou classes guarda-chuva sem demonstrar a trilha CNPJ -> classe -> documento.
3. Use evidências locais do repositório: `reports/regulatory_document_inventory.csv`, `reports/regulatory_criteria_matrix.csv`, `data/raw/<cnpj>/`, `data/regulatory_knowledge/<cnpj>.json`, `data/regulatory_profiles/*`, `data/deep_dives/*` e caches IME locais.
4. Não consulte APIs externas nem crie dados por inferência fraca. Se algo depender de suplemento, bookbuilding, anúncio de encerramento ou ata não localizado, escreva a lacuna.
5. Toda afirmação material precisa ter fonte: arquivo, data, ID CVM, página, seção, cláusula ou trecho curto auditável quando disponível.
6. Lacunas devem aparecer como lacunas textuais, nunca como zero, média, extrapolação ou campo vazio.
7. Conflitos entre documentos, versões de regulamento ou termos econômicos devem ser registrados e resolvidos por hierarquia temporal/documental.
8. Preserve pacotes existentes, dados curados, arquivos não rastreados e separação entre dado documental offline e métrica IME ao vivo.
9. O resultado precisa aparecer na aba Deep Dive e exportar PPTX com tabelas editáveis, sem rasterização e sem truncar cronogramas longos com `...`.

ETAPA 1 - ESCOPO E BASE LOCAL:
- Verifique `git status` e registre mudanças alheias sem revertê-las.
- Identifique a carteira em `portfolios.json`; confirme CNPJs, nomes formais, classes e short names.
- Liste documentos e caches IME somente dos CNPJs escopados.
- Levante pacotes Deep Dive parecidos para copiar schema e padrões, não conteúdo.

ETAPA 2 - INVENTÁRIO E COBERTURA DOCUMENTAL:
Para cada CNPJ, inventarie: regulamentos, consolidados, suplementos/apêndices, atas, anúncios de início/encerramento, documentos de oferta pública, fatos relevantes, comunicados, relatórios trimestrais, demonstrações financeiras, rating, XML/IME e auxiliares. Conte documentos e, quando possível, páginas locais analisáveis. Separe documentos sem PDF local.

ETAPA 3 - DUE DILIGENCE REGULATÓRIA COMPLETA:
Leia os documentos relevantes como advogado/estruturador. Para cada fundo, extraia e explique:
- regulamento vigente e versões anteriores relevantes;
- política de investimento, ativos permitidos e ativos vedados;
- critérios de elegibilidade dos direitos creditórios;
- condições de cessão, recompra, substituição, indenização, coobrigação e vícios de lastro;
- limites de concentração por cedente, sacado, devedor, endossante, grupo econômico, classe de ativo, originador e partes relacionadas;
- derivativos/hedge permitidos, limites e finalidade;
- subordinação, relação mínima, razão de garantia, índice de cobertura, reservas, caixa mínimo, cash sweep e waterfall;
- eventos de avaliação, eventos de liquidação, vencimento antecipado, aceleração/amortização extraordinária, waivers e assembleias;
- gatilhos de atraso/inadimplência, PDD, recompras, diluição, chargeback, cancelamento, fraude, pré-pagamento ou contestação quando aplicável;
- cross default/cross acceleration do cedente, originador, endossante, grupo econômico ou prestadores essenciais;
- troca, renúncia ou substituição de gestor, administrador, custodiante, agente de cobrança/recebimento, escriturador e servicer;
- público-alvo, rating, prazo de duração, responsabilidades e alterações materiais.

ETAPA 4 - EMISSÕES E CALENDÁRIO DE PAGAMENTOS:
Para cada emissão/série/classe, reconstrua:
- fundo, CNPJ, classe/série, tipo de cota;
- data de deliberação, emissão/primeira integralização, início e encerramento da oferta;
- quantidade emitida, VNU/preço unitário, volume máximo/aprovado/distribuído;
- remuneração-alvo, benchmark, DI/CDI + spread aditivo, IPCA + spread, taxa fixa, fator adicional, aceleração e fonte do spread;
- juros, periodicidade, carência, prazo, vencimento final, amortização programada, amortização extraordinária e data de pagamento;
- rating quando estiver vinculado à série;
- fonte documental e status de curadoria.

Regra crítica: procure documentos públicos de emissão para validar tamanho e spread. Se o spread vier como `CDI`, `DI` ou `Taxa DI`, normalize como índice + spread aditivo percentual quando o texto permitir. Se o texto remeter a bookbuilding/suplemento/ato não localizado, escreva explicitamente `spread final não localizado`, `sobretaxa definida em bookbuilding`, `sobretaxa definida em ato`, `sobretaxa definida em suplemento`, `prazo remetido ao suplemento` ou `cronograma fechado não identificado`.

ETAPA 5 - CRITÉRIOS MONITORÁVEIS E QUALITATIVOS:
Monte uma linha por critério material, mesmo que não seja monitorável. Para cada linha, preencha:
- `Critério`: nome legível para analista;
- `Chave`: chave canônica existente ou nova chave curta e estável;
- `Limite/regra`: comparação, limite, janela, cura e evento;
- `Monitorabilidade IME`: direto/monitorável/parcial/não monitorável, com ressalva quando a regra jurídica não for perfeitamente replicável;
- `Métrica IME / proxy`: métrica existente do app ou proxy proposta;
- `Condição de alerta sugerida`: condição operacional que a ferramenta poderia checar mensalmente;
- `Observação técnica`: por que o IME basta, não basta ou exige input manual;
- `Fonte` e `Status curadoria`.

Inclua obrigatoriamente, quando existirem no documento: alocação mínima em DCs, subordinação/relação mínima, índices Over 30/60/90/180/360, PDD/cobertura, recompras, reservas/caixa, derivativos, concentração, elegibilidade, recompra/indenização, chargeback/cancelamento, cross default, troca de prestadores e eventos de avaliação/liquidação.

Não transforme regra jurídica em alerta duro se o IME não tiver granularidade. Exemplo: concentração por devedor/cedente é normalmente `nao_monitoravel`; derivativos são no máximo parciais se o IME só traz posição agregada; reservas são parciais se exigirem cronograma de amortização/despesas; índice de cobertura com VP/fatores/comissões exige parâmetros manuais.

ETAPA 6 - CONFRONTO COM MONITORAMENTO E IME:
- Carregue o IME local via cache quando existir e use `build_monitoring_tables`/`build_dashboard_data` para obter métricas padronizadas.
- Compare os critérios documentais com PL, Dir Cred / PL, Over 30/60/90/180/360, PDD / Crédito, PDD / Venc Total, Recompras / Crédito, Cotas SR/MZ/Sub / PL, caixa/disponibilidades e derivativos.
- Separe: dado documental offline; dado IME ao vivo; proxy calculável; proxy parcial; lacuna sem proxy; divergência; limitação metodológica.
- Se a competência IME estiver ausente, registre `sem competência IME` e preserve o pacote documental.

ETAPA 7 - CUSTOS ESTRUTURAIS:
Extraia administração e gestão separadamente, com percentual a.a., mínimo mensal, indexador/reajuste, bases de cálculo, serviços embutidos, taxas máximas, faixas por PL e mudanças vs versões antigas. Se gestão estiver embutida na administração, escreva explicitamente. Se não houver mínimo separado, escreva `Sem mínimo mensal separado identificado`.

ETAPA 8 - PERSISTÊNCIA:
Crie/atualize somente os arquivos da carteira:
- `data/regulatory_profiles/<slug>_cotas_emissoes_pagamentos.csv`
- `data/regulatory_profiles/<slug>_criteria_monitoraveis_ime.csv`
- `data/regulatory_profiles/<slug>_structural_costs.csv` ou `data/regulatory_profiles/structural_costs.csv`, conforme padrão existente
- `data/deep_dives/<deep_dive_id>/tables/comparison_main.csv`
- `data/deep_dives/<deep_dive_id>/tables/emissions.csv`
- `data/deep_dives/<deep_dive_id>/tables/thresholds.csv`
- `data/deep_dives/<deep_dive_id>/tables/structural_costs.csv`
- `data/deep_dives/<deep_dive_id>/evidence/*.csv`
- `data/deep_dives/<deep_dive_id>/notes/*.md`
- `data/deep_dives/<deep_dive_id>/manifest.json`

Se o gerador ainda não suportar a curadoria específica, implemente a menor generalização segura, sem hardcode frágil e sem quebrar pacotes já existentes.

ETAPA 9 - VALIDAÇÃO:
Antes de encerrar, rode:
- validação de CSV com pandas e colunas esperadas;
- contagem de emissões por fundo e checagem de fonte por emissão;
- checagem de remuneração, spread, volume, amortização/vencimento e lacunas textuais;
- checagem de critérios com chave, monitorabilidade, proxy/alerta/observação e fonte;
- checagem de `structural_costs.csv` com Administração e Gestão por fundo;
- geração/leitura estrutural do pacote pela aba Deep Dive;
- PPTX QA com `services.deep_dive_ppt_export.build_deep_dive_pptx_bytes`;
- `py_compile` dos Python alterados e `git diff --check`.

ETAPA 10 - ENTREGA:
Informe de forma objetiva:
- carteira e CNPJs processados;
- documentos/fontes usados e cobertura;
- emissões/classes detectadas por fundo, volumes, spreads e calendário;
- principais critérios monitoráveis/qualitativos e proxies IME;
- principais lacunas, conflitos e riscos de leitura manual ainda necessários;
- custos estruturais;
- arquivos alterados;
- validações realizadas.

Se for pedido commit/push: adicione somente arquivos rastreados e relevantes; não adicione PDFs soltos, outputs temporários ou arquivos não relacionados; faça commit objetivo e push."""


_REVERSE_ENGINEERING_PROMPT_PATH = Path("docs/fidc/monitoramento/prompt_deep_dive_nova_carteira.md")


def _load_reverse_engineering_prompt() -> str:
    try:
        return _REVERSE_ENGINEERING_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return _REVERSE_ENGINEERING_PROMPT


def render_tab_deep_dive(
    *,
    selected_portfolio: PortfolioRecord | None = None,
    show_portfolio_selector: bool = True,
    show_curation_tools: bool = True,
    compact: bool = False,
) -> None:
    manifests = list_deep_dives()
    if not compact:
        st.markdown("<div class='deepdive-kicker'>Regulamentos</div>", unsafe_allow_html=True)
        st.markdown("<div class='deepdive-title'>Regulamentos</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='deepdive-subtitle'>Emissões, prazos, custos e critérios documentais relevantes para a análise da carteira.</div>",
            unsafe_allow_html=True,
        )
    if show_curation_tools:
        with st.expander("Prompt de atualização", expanded=False):
            st.code(_load_reverse_engineering_prompt(), language="markdown")
        _render_cloudwalk_waterfall(wrap=True, compact=False)

    if not manifests:
        st.info("Nenhum pacote em `data/deep_dives/`.")
        return

    if show_portfolio_selector:
        portfolios = list_saved_portfolios()
        portfolio_labels = build_portfolio_record_label_lookup(portfolios)
        portfolio_options = ["Todos", *[portfolio.id for portfolio in portfolios]]
        selected_portfolio_id = st.selectbox(
            "Carteira",
            options=portfolio_options,
            format_func=lambda value: "Todos os pacotes" if value == "Todos" else portfolio_labels.get(value, value),
            key="deep_dive_portfolio",
        )
        selected_portfolio = next((portfolio for portfolio in portfolios if portfolio.id == selected_portfolio_id), None)
    else:
        selected_portfolio_id = selected_portfolio.id if selected_portfolio is not None else "Todos"
    selected_signature = portfolio_basket_signature(selected_portfolio.funds) if selected_portfolio else ""
    available = [
        manifest
        for manifest in manifests
        if selected_portfolio_id == "Todos" or deep_dive_matches_portfolio(manifest, selected_portfolio_id, selected_signature)
    ]
    available = sorted(available, key=lambda item: item.generated_at or "", reverse=True)
    if not available:
        st.warning("Não há pacote regulatório salvo para a carteira selecionada.")
        return

    if compact:
        manifest = available[0]
        _render_manifest_context_line(manifest)
        _render_emissions_curadoria(manifest, compact=True)
        return

    manifest = st.selectbox(
        "Pacote regulatório",
        options=available,
        format_func=lambda item: f"{item.title} · {item.generated_at or item.deep_dive_id}",
        key="deep_dive_manifest",
    )
    _render_manifest_header(manifest)
    _render_emissions_curadoria(manifest, compact=False)

    if not manifest.tables:
        st.warning("Pacote sem tabelas configuradas.")
        return
    table_spec = st.selectbox(
        "Tabela regulatória",
        options=list(manifest.tables),
        format_func=lambda item: item.title,
        key=f"deep_dive_table::{manifest.deep_dive_id}",
    )
    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty:
        st.warning("Tabela vazia ou arquivo ausente.")
        return
    live_audit = pd.DataFrame()
    if table_spec.id == "comparison_main":
        frame, live_audit = _apply_live_ime_metrics(frame, manifest)

    highlight_options = ["Nenhuma", *frame.columns[1:].tolist()]
    highlighted_column = st.selectbox(
        "Coluna em destaque",
        options=highlight_options,
        index=0,
        key=f"deep_dive_highlight::{manifest.deep_dive_id}::{table_spec.id}",
    )
    highlight_value = None if highlighted_column == "Nenhuma" else highlighted_column

    try:
        pptx_bytes = build_deep_dive_pptx_bytes(
            manifest,
            [(table_spec, frame)],
            highlighted_column=highlight_value,
        )
        st.download_button(
            "Exportar deck de comitê (PPTX)",
            data=pptx_bytes,
            file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )
    except RuntimeError as exc:
        st.warning(str(exc))
    with st.expander("Dados regulatórios para diligência", expanded=False):
        st.download_button(
            "Baixar CSV da tabela selecionada",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    _render_comparison_table(frame, highlighted_column=highlight_value)

    with st.expander("Fontes e lacunas", expanded=False):
        if manifest.warnings:
            for warning in manifest.warnings:
                st.caption(f"- {warning}")
        if not live_audit.empty:
            st.markdown("**Atualização IME ao vivo**")
            st.dataframe(live_audit, hide_index=True, use_container_width=True)
        st.dataframe(_source_files_df(manifest), hide_index=True, use_container_width=True)


def _render_manifest_context_line(manifest: Any) -> None:
    context = " · ".join(
        item
        for item in [
            str(getattr(manifest, "title", "") or "").strip(),
            str(getattr(manifest, "generated_at", "") or "").strip(),
        ]
        if item
    )
    if context:
        st.markdown(f"<div class='deepdive-curadoria-note'>Base: {escape(context)}</div>", unsafe_allow_html=True)


def _render_emissions_curadoria(manifest: Any, *, compact: bool) -> None:
    table_spec = _find_manifest_table(manifest, "emissions")
    if table_spec is None:
        if not compact:
            st.info("Este pacote ainda não tem tabela de emissões curadas.")
        return

    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty:
        if not compact:
            st.info("Tabela de emissões vazia ou ausente.")
        return

    summary = _build_emissions_type_summary(frame)
    if summary.empty:
        st.info("Não há emissões com tipo de cota identificado para resumir.")
        return

    st.markdown("#### Emissões por tipo de cota")
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.markdown(
        "<div class='deepdive-curadoria-note'>Volumes monetários são somados apenas quando o campo documental está identificado. "
        "Quantidades, prazos e custos/remuneração preservam lacunas explícitas em vez de virar zero.</div>",
        unsafe_allow_html=True,
    )

    detail = _emissions_detail_frame(frame)
    if detail.empty:
        return
    with st.expander("Detalhe documental das emissões", expanded=False):
        st.dataframe(detail, hide_index=True, use_container_width=True)


def _find_manifest_table(manifest: Any, table_id: str) -> Any | None:
    for table in getattr(manifest, "tables", ()) or ():
        if getattr(table, "id", "") == table_id:
            return table
    return None


def _build_emissions_type_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    empty_column = pd.Series(["—"] * len(work), index=work.index)
    work["__tipo"] = work.get("Tipo", empty_column).map(_normalize_quota_type)
    work["__volume_mm"] = work.get("Volume identificado (R$ mm)", empty_column).map(_parse_br_decimal)
    work["__qtd_cotas"] = work.get("Qtd cotas", empty_column).map(_parse_br_decimal)
    rows: list[dict[str, object]] = []
    for tipo, group in work.groupby("__tipo", sort=False):
        volume_values = pd.to_numeric(group["__volume_mm"], errors="coerce")
        quantity_values = pd.to_numeric(group["__qtd_cotas"], errors="coerce")
        volume_count = int(volume_values.notna().sum())
        quantity_count = int(quantity_values.notna().sum())
        rows.append(
            {
                "Tipo de cota": tipo,
                "Emissões": len(group),
                "Volume identificado": _format_mm_sum(volume_values) if volume_count else "N/D",
                "Qtd cotas identificada": _format_quantity_sum(quantity_values) if quantity_count else "N/D",
                "Custo / remuneração": _collapse_text_values(group.get("Remuneração-alvo", pd.Series(dtype=str))),
                "Prazo / amortização": _collapse_text_values(
                    group.get("Amortização/vencimento", pd.Series(dtype=str)),
                    max_chars=132,
                ),
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["__ordem"] = output["Tipo de cota"].map(_quota_type_sort_key)
    output = output.sort_values(["__ordem", "Tipo de cota"], kind="stable").drop(columns=["__ordem"])
    return output.reset_index(drop=True)


def _emissions_detail_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Fundo",
        "Data",
        "Classe/Série",
        "Tipo",
        "Qtd cotas",
        "Volume identificado (R$ mm)",
        "Remuneração-alvo",
        "Amortização/vencimento",
        "Fonte",
    ]
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.DataFrame()
    return frame[available].copy()


def _normalize_quota_type(value: object) -> str:
    text = _display(value)
    folded = _normalize_text(text)
    if "mezanino" in folded or "mezz" in folded:
        return "Mezanino"
    if "subordin" in folded:
        return "Subordinada"
    if "senior" in folded or "sênior" in folded:
        return "Sênior"
    if text in {"—", ""}:
        return "Não classificada"
    return text


def _quota_type_sort_key(value: object) -> int:
    order = {
        "Sênior": 10,
        "Mezanino": 20,
        "Subordinada": 30,
        "Classe única": 40,
        "Não classificada": 90,
    }
    return order.get(str(value), 80)


def _parse_br_decimal(value: object) -> float | None:
    text = _display(value)
    if text == "—":
        return None
    text = text.replace("R$", "").strip()
    if re.search(r"[A-Za-zÀ-ÿ]", text):
        return None
    clean = re.sub(r"[^0-9,.\-]", "", text)
    if not clean or clean in {"-", ",", "."}:
        return None
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "." in clean:
        parts = clean.split(".")
        if len(parts) > 2 or all(len(part) == 3 for part in parts[1:]):
            clean = "".join(parts)
    try:
        return float(clean)
    except ValueError:
        return None


def _format_mm_sum(values: pd.Series) -> str:
    total = pd.to_numeric(values, errors="coerce").dropna().sum()
    return f"R$ {_br_number(float(total), 1)} mm"


def _format_quantity_sum(values: pd.Series) -> str:
    total = float(pd.to_numeric(values, errors="coerce").dropna().sum())
    decimals = 0 if abs(total - round(total)) < 1e-9 else 1
    return _br_number(total, decimals)


def _collapse_text_values(values: pd.Series, *, limit: int = 3, max_chars: int = 96) -> str:
    seen: list[str] = []
    for value in values.tolist() if isinstance(values, pd.Series) else list(values):
        text = _display(value)
        if text == "—":
            continue
        if text not in seen:
            seen.append(text)
    if not seen:
        return "N/D"
    clipped = [_clip_text(item, max_chars=max_chars) for item in seen[:limit]]
    if len(seen) > limit:
        clipped.append(f"+{len(seen) - limit} variação(ões)")
    return " | ".join(clipped)


def _clip_text(value: str, *, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _render_cloudwalk_waterfall(*, wrap: bool = True, compact: bool = False) -> None:
    if wrap:
        with st.expander("Waterfall Cloudwalk", expanded=False):
            _render_cloudwalk_waterfall_body(compact=compact)
        return
    _render_cloudwalk_waterfall_body(compact=compact)


def _render_cloudwalk_waterfall_body(*, compact: bool = False) -> None:
    refresh_ime = st.toggle(
        "Atualizar IME pelo Fundos.NET se não houver cache local",
        value=False,
        key="cloudwalk_waterfall_refresh_ime",
        help="Desligado usa somente cache local para não travar a aba. Ligado busca IME faltante e grava cache.",
    )
    try:
        artifacts = _load_cloudwalk_waterfall_artifacts(refresh_ime)
    except Exception as exc:  # noqa: BLE001
        st.error("Não foi possível carregar o waterfall Cloudwalk.")
        st.caption(f"Detalhe técnico: {type(exc).__name__}: {exc}")
        return

    summary = artifacts["summary"]
    cols = st.columns(4)
    cols[0].metric("Caixa + recebíveis IME", f"R$ {_br_number(summary['caixa_recebiveis_ime'] / 1_000_000, 0)} mi")
    cols[1].metric("Amortizações mapeadas", f"R$ {_br_number(summary['amortizacoes_total'] / 1_000_000, 0)} mi")
    cols[2].metric("CNPJs com IME", f"{summary['ime_included']}/{summary['ime_total']}")
    cols[3].metric("Última amortização", summary["last_date"] or "—")

    if summary["ime_missing"]:
        st.warning(
            "Há CNPJs sem Caixa + Recebíveis via IME no cache local. "
            "Ative a atualização pelo Fundos.NET para buscar os IMEs faltantes."
        )

    chart = _cloudwalk_waterfall_chart(artifacts["chart_df"])
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)
    elif artifacts["plot_png"]:
        st.image(artifacts["plot_png"], use_container_width=True)

    export_label = "Dados do waterfall" if compact else "Arquivos do waterfall"
    with st.expander(export_label, expanded=False):
        st.download_button(
            "Baixar waterfall CSV",
            data=artifacts["waterfall_csv"],
            file_name="waterfall_cloudwalk.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Baixar relatório",
            data=artifacts["report_csv"],
            file_name="waterfall_inclusion_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Baixar IME CSV",
            data=artifacts["ime_assets_csv"],
            file_name="waterfall_ime_assets.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Baixar gráfico PNG",
            data=artifacts["plot_png"],
            file_name="waterfall_cloudwalk_plot.png",
            mime="image/png",
            use_container_width=True,
            disabled=not bool(artifacts["plot_png"]),
        )

    st.dataframe(artifacts["waterfall_df"], hide_index=True, use_container_width=True)
    with st.expander("Caixa + Recebíveis via IME", expanded=False):
        st.dataframe(artifacts["ime_assets_df"], hide_index=True, use_container_width=True)
    with st.expander("Relatório de inclusão/exclusão", expanded=False):
        st.dataframe(artifacts["report_df"], hide_index=True, use_container_width=True)


@st.cache_data(ttl=600, show_spinner=False)
def _load_cloudwalk_waterfall_artifacts(refresh_ime: bool) -> dict[str, Any]:
    reference_date = date(2026, 5, 14)
    schedules = load_cloudwalk_emissions(DEFAULT_CLOUDWALK_EMISSIONS, reference_date=reference_date)
    included = [schedule for schedule in schedules if schedule.included]
    fund_names = {only_digits(schedule.cnpj): schedule.fund_name for schedule in schedules}
    ime_assets = load_cloudwalk_ime_assets(
        [schedule.cnpj for schedule in included],
        fund_names=fund_names,
        fetch_missing=refresh_ime,
        reference_date=reference_date,
    )
    caixa_recebiveis_ime = sum(item.caixa_recebiveis for item in ime_assets if item.included)
    rows = build_waterfall_schedule(schedules, caixa_recebiveis_ime, reference_date=reference_date)
    paths = export_waterfall(
        rows,
        schedules,
        DEFAULT_WATERFALL_OUTPUT_DIR,
        ime_assets=ime_assets,
        caixa_recebiveis_ime=caixa_recebiveis_ime,
    )
    waterfall_path = Path(paths["waterfall_csv"])
    report_path = Path(paths["inclusion_report_csv"])
    ime_assets_path = Path(paths["ime_assets_csv"])
    plot_path = Path(paths["plot_png"])
    waterfall_df = pd.read_csv(waterfall_path, keep_default_na=False)
    report_df = pd.read_csv(report_path, keep_default_na=False)
    ime_assets_df = pd.read_csv(ime_assets_path, keep_default_na=False)
    summary = {
        "included": len(included),
        "excluded": len(schedules) - len(included),
        "caixa_recebiveis_ime": caixa_recebiveis_ime,
        "amortizacoes_total": sum(row.amortizacao_total for row in rows),
        "ime_included": sum(1 for item in ime_assets if item.included),
        "ime_total": len(ime_assets),
        "ime_missing": sum(1 for item in ime_assets if not item.included),
        "last_date": max((item_date for schedule in included for item_date, _ in schedule.schedule), default=None),
    }
    summary["last_date"] = summary["last_date"].isoformat() if summary["last_date"] else ""
    return {
        "summary": summary,
        "waterfall_df": waterfall_df,
        "report_df": report_df,
        "ime_assets_df": ime_assets_df,
        "chart_df": _cloudwalk_waterfall_chart_frame(rows, caixa_recebiveis_ime),
        "waterfall_csv": waterfall_path.read_bytes(),
        "report_csv": report_path.read_bytes(),
        "ime_assets_csv": ime_assets_path.read_bytes(),
        "plot_png": plot_path.read_bytes() if plot_path.exists() else b"",
    }


def _cloudwalk_waterfall_chart_frame(rows: list[Any], caixa_recebiveis_ime: float) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    running = float(caixa_recebiveis_ime or 0.0)
    if abs(running) > 1e-9:
        output.append(
            {
                "ordem": 1,
                "etapa": "Caixa + recebíveis",
                "tipo": "Caixa + recebíveis",
                "valor": running,
                "bar_start": 0.0,
                "bar_end": running,
                "label_y": running,
                "valor_fmt": f"R$ {_br_number(abs(running) / 1_000_000, 1)} mi",
            }
        )
    for row in rows:
        start = running
        value = -float(row.amortizacao_total or 0.0)
        running += value
        output.append(
            {
                "ordem": len(output) + 1,
                "etapa": row.data.strftime("%d/%m/%y"),
                "tipo": "Amortização",
                "valor": value,
                "bar_start": min(start, running),
                "bar_end": max(start, running),
                "label_y": max(start, running),
                "valor_fmt": f"-R$ {_br_number(abs(value) / 1_000_000, 1)} mi",
            }
        )
    frame = pd.DataFrame(output)
    if frame.empty:
        return frame
    for column in ["valor", "bar_start", "bar_end", "label_y"]:
        frame[f"{column}_mi"] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0) / 1_000_000.0
    label_stride = max(1, math.ceil(len(frame) / 18))
    frame["show_label"] = frame["ordem"].isin({1, int(frame["ordem"].max())}) | ((frame["ordem"] - 1) % label_stride == 0)
    return frame


def _cloudwalk_waterfall_chart(chart_df: pd.DataFrame) -> alt.Chart | None:
    if chart_df.empty:
        return None
    chart_df = chart_df.copy()
    x_sort = chart_df.sort_values("ordem")["etapa"].tolist()
    bars = (
        alt.Chart(chart_df)
        .mark_bar(size=max(14, min(56, int(620 / max(len(chart_df), 1)))))
        .encode(
            x=alt.X("etapa:N", title=None, sort=x_sort, axis=alt.Axis(labelAngle=-35, labelLimit=92)),
            y=alt.Y("bar_end_mi:Q", title="R$ milhões"),
            y2="bar_start_mi:Q",
            color=alt.Color(
                "tipo:N",
                scale=alt.Scale(domain=["Caixa + recebíveis", "Amortização"], range=["#1F1F1F", "#EC7000"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("etapa:N", title="Etapa"),
                alt.Tooltip("tipo:N", title="Tipo"),
                alt.Tooltip("valor_fmt:N", title="Valor"),
            ],
        )
    )
    connector_df = chart_df.iloc[:-1].copy()
    connector_df["etapa_proxima"] = chart_df["etapa"].shift(-1)
    connector_df["running_mi"] = chart_df["valor"].cumsum().iloc[:-1].to_numpy() / 1_000_000.0
    connectors = (
        alt.Chart(connector_df)
        .mark_rule(color="#9CA3AF", strokeDash=[4, 4], strokeWidth=1.2)
        .encode(
            x=alt.X("etapa:N", sort=x_sort),
            x2="etapa_proxima:N",
            y="running_mi:Q",
        )
    )
    labels = (
        alt.Chart(chart_df[chart_df["show_label"]])
        .mark_text(dy=-8, fontSize=12, fontWeight=700, color="#1F1F1F", clip=False)
        .encode(
            x=alt.X("etapa:N", sort=x_sort),
            y="label_y_mi:Q",
            text="valor_fmt:N",
        )
    )
    return (bars + connectors + labels).properties(height=380).configure_view(strokeWidth=0)


def _render_manifest_header(manifest: Any) -> None:
    chips = [
        f"{len(manifest.funds)} fundo(s)",
        manifest.generated_at or "sem timestamp",
        manifest.source or "fonte offline",
        manifest.confidentiality,
    ]
    st.markdown(
        "<div class='deepdive-chip-row'>"
        + "".join(f"<span class='deepdive-chip'>{escape(chip)}</span>" for chip in chips if chip)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_comparison_table(frame: pd.DataFrame, *, highlighted_column: str | None) -> None:
    header_cells = []
    for column in frame.columns:
        css_class = " class='highlight'" if column == highlighted_column else ""
        header_cells.append(f"<th{css_class}>{escape(str(column))}</th>")
    rows: list[str] = []
    for _, row in frame.iterrows():
        cells = []
        row_label = str(row.get(frame.columns[0], ""))
        is_long_row = row_label in _LONG_TEXT_ROWS
        for column in frame.columns:
            classes = []
            if column == highlighted_column:
                classes.append("highlight")
            if is_long_row and column != frame.columns[0]:
                classes.append("longtext")
            css_class = f" class='{' '.join(classes)}'" if classes else ""
            cells.append(f"<td{css_class}>{_cell_html(row.get(column, '—'), long_text=is_long_row and column != frame.columns[0])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        "<div class='deepdive-table-wrap'><table class='deepdive-table'><thead><tr>"
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _cell_html(value: object, *, long_text: bool) -> str:
    text = str(value if value is not None else "—").strip() or "—"
    if text.lower() in {"nan", "none", "<na>"}:
        text = "—"
    if not long_text or text == "—":
        return escape(text).replace("\n", "<br>")
    items = [item.strip() for item in re.split(r"\s+\|\s+|\n+", text) if item.strip()]
    if len(items) <= 1:
        return escape(text)
    return "<div class='deepdive-cell-list'>" + "".join(f"<div>{escape(item)}</div>" for item in items) + "</div>"


def _apply_live_ime_metrics(frame: pd.DataFrame, manifest: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty or not getattr(manifest, "funds", None):
        return frame, pd.DataFrame()
    first_col = frame.columns[0]
    if first_col not in frame.columns:
        return frame, pd.DataFrame()
    output = frame.copy()
    label_mask = output[first_col].astype(str)
    if not label_mask.isin({"Última competência IME", *_LIVE_IME_ROWS.keys()}).any():
        return output, pd.DataFrame()

    end_month = current_default_end_month()
    audit_rows: list[dict[str, object]] = []
    for fund in manifest.funds:
        cnpj = _digits(fund.get("cnpj"))
        column = _find_fund_column(output, fund)
        if not cnpj or column is None:
            continue
        metrics = _load_live_ime_metrics(cnpj, end_month.isoformat())
        audit_rows.append(
            {
                "Fundo": column,
                "CNPJ": _format_cnpj(cnpj),
                "Competência": metrics.get("competencia") or "—",
                "Cache": metrics.get("cache_status") or "—",
                "Status": metrics.get("status") or "OK",
            }
        )
        if metrics.get("status") != "OK":
            continue
        _set_row_value(output, first_col, "Última competência IME", column, str(metrics.get("competencia") or "—"))
        for row_label, indicator in _LIVE_IME_ROWS.items():
            value = metrics.get("values", {}).get(indicator, "—")
            _set_row_value(output, first_col, row_label, column, value)
    return output, pd.DataFrame(audit_rows)


def _find_fund_column(frame: pd.DataFrame, fund: dict[str, str]) -> str | None:
    candidates = [
        str(fund.get("short_name") or "").strip(),
        str(fund.get("name") or "").strip(),
        _short_name(fund.get("name") or fund.get("cnpj") or ""),
    ]
    columns = list(frame.columns[1:])
    normalized = {_normalize_text(column): column for column in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        match = normalized.get(_normalize_text(candidate))
        if match:
            return match
    return None


def _set_row_value(frame: pd.DataFrame, first_col: str, row_label: str, column: str, value: str) -> None:
    mask = frame[first_col].astype(str).eq(row_label)
    if mask.any() and column in frame.columns:
        frame.loc[mask, column] = value


@st.cache_data(ttl=1800, show_spinner=False)
def _load_live_ime_metrics(cnpj: str, end_month_iso: str) -> dict[str, Any]:
    end_month = date.fromisoformat(end_month_iso)
    start_month = shift_month(end_month, -5)
    try:
        cached = load_or_extract_informe(
            cnpj_fundo=cnpj,
            data_inicial=start_month,
            data_final=end_month,
        )
        result = cached.result
        cache_status = cached.cache_status
        latest_month = _latest_competencia_month(result.competencias)
        if cached.cache_status == "hit" and latest_month is not None and latest_month < end_month:
            try:
                fresh = InformeMensalService().run(
                    cnpj_fundo=cnpj,
                    data_inicial=start_month,
                    data_final=end_month,
                    progress_callback=None,
                )
                fresh_latest = _latest_competencia_month(fresh.competencias)
                if fresh_latest is not None and fresh_latest >= latest_month:
                    result = fresh
                    cache_status = "live_probe"
            except Exception:  # noqa: BLE001
                cache_status = "hit"
        competencias = list(result.competencias or [])
        if not competencias:
            return {"status": "sem competência IME", "cache_status": cache_status, "values": {}}
        competencia = sorted(competencias, key=_competencia_sort_key)[-1]
        wide_df = read_wide_csv(result.wide_csv_path)
        dashboard_data = None
        try:
            dashboard_data = build_dashboard_data(
                wide_csv_path=result.wide_csv_path,
                listas_csv_path=result.listas_csv_path,
                docs_csv_path=result.docs_csv_path,
            )
        except Exception:  # noqa: BLE001
            dashboard_data = None
        tables = build_monitoring_tables(
            wide_df,
            competencias,
            cnpj=cnpj,
            overrides={},
            dashboard_data=dashboard_data,
        )
        values: dict[str, str] = {}
        for indicator in _LIVE_IME_ROWS.values():
            values[indicator] = _metric_from_indicators(tables.indicators_df, indicator, competencia)
        return {
            "status": "OK",
            "cache_status": cache_status,
            "competencia": competencia,
            "values": values,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": f"{exc.__class__.__name__}: {exc}", "cache_status": "erro", "values": {}}


def _metric_from_indicators(indicators_df: pd.DataFrame, indicator: str, competencia: str) -> str:
    if indicators_df.empty or competencia not in indicators_df.columns:
        return "—"
    match = indicators_df[indicators_df["indicador"].astype(str).eq(indicator)]
    if match.empty:
        return "—"
    row = match.iloc[0]
    return _format_live_metric(row.get(competencia), row.get("unidade"))


def _format_live_metric(value: object, unit: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _display(value)
    unit_text = str(unit or "")
    if "R$ bruto" in unit_text:
        return f"R$ {_br_number(numeric / 1_000_000, 0)} mm"
    if "R$ MM" in unit_text:
        return f"R$ {_br_number(numeric, 0)} mm"
    if unit_text in {"ratio", "%"} or "/" in unit_text:
        if unit_text == "ratio":
            numeric *= 100
        return f"{_br_number(numeric, 1)}%"
    return _br_number(numeric, 1)


def _competencia_sort_key(value: object) -> tuple[int, int]:
    text = str(value or "")
    try:
        month, year = text.split("/", 1)
        return int(year), int(month)
    except Exception:  # noqa: BLE001
        return (0, 0)


def _latest_competencia_month(competencias: list[str] | tuple[str, ...]) -> date | None:
    parsed = []
    for competencia in competencias or []:
        year, month = _competencia_sort_key(competencia)
        if year > 0 and month > 0:
            parsed.append(date(year, month, 1))
    return max(parsed) if parsed else None


def _display(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return "—"
    return text


def _br_number(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _format_cnpj(value: object) -> str:
    digits = _digits(value)
    if len(digits) != 14:
        return str(value or "")
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _short_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    replacements = [
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS",
        "RESPONSABILIDADE LIMITADA",
        "RESP LIMITADAL",
        "RESP LIMITADA",
        "LIMITADA",
    ]
    for token in replacements:
        text = re.sub(token, "", text, flags=re.IGNORECASE).strip(" -")
    return text or str(value or "")


def _source_files_df(manifest: Any) -> pd.DataFrame:
    rows = [
        {
            "Tabela": table.title,
            "Arquivo": str(Path(table.source_file)),
            "Tipo": table.kind,
        }
        for table in manifest.tables
    ]
    return pd.DataFrame(rows)


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip().lower())
    return token.strip("_") or "deep_dive"
