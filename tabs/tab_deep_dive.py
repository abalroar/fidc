from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import re
from typing import Any
import unicodedata

import pandas as pd
import streamlit as st

from services.dashboard_ui import render_page_header
from services.deep_dive_store import (
    deep_dive_matches_portfolio,
    list_deep_dives,
    load_deep_dive_table,
)
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    list_saved_portfolios,
)


_CSS = """
<style>
.deepdive-curation-date {
    color: #525f6d;
    font-size: 0.86rem;
    line-height: 1.45;
    margin: 0 0 0.65rem;
}
.deepdive-curation-date strong {
    color: #17202a;
    font-weight: 650;
}
</style>
"""

_LEGACY_REVERSE_ENGINEERING_PROMPT = """Você é Codex trabalhando no repositório local `/fidc`.

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

_REVERSE_ENGINEERING_PROMPT = """Atualize a Curadoria de Leitura de uma única carteira.

1. Confirme a carteira, os CNPJs e a assinatura atual da cesta de fundos.
2. Leia todos os documentos CVM/Fundos.NET incorporados e acessíveis para esses CNPJs.
3. Registre lacunas, documentos inacessíveis e conflitos sem completar dados por inferência.
4. Atualize `manifest.generated_at` com a data efetiva da leitura.
5. Grave `tables/key_findings.csv` com as colunas `Tema` e `Conclusão` e 3 a 5 fatos materiais.
6. Inclua `key_findings` em `manifest.tables`, apontando para o CSV e usando `Tema` como primeira coluna.
7. Priorize elegibilidade, alocação, subordinação, gatilhos, reservas, concentração e derivativos.
8. Não exponha contagens técnicas, nomes internos de tabelas ou classificações intermediárias.
9. Preserve as fontes auditáveis nos artefatos internos e valide a leitura pelo app.
"""


_REVERSE_ENGINEERING_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "fidc"
    / "monitoramento"
    / "prompt_deep_dive_nova_carteira.md"
)


def _load_reverse_engineering_prompt() -> str:
    try:
        return _REVERSE_ENGINEERING_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return _REVERSE_ENGINEERING_PROMPT


_GENERIC_WARNING_SNIPPETS = (
    "pacote gerado exclusivamente",
    "metricas ime foram enriquecidas",
    "tabela principal com",
    "custos estruturais:",
    "custos estruturais incluidos",
)

_MATERIAL_WARNING_SNIPPETS = (
    "lacuna",
    "inacess",
    "nao acessivel",
    "nao estava acessivel",
    "nao localizado",
    "nao disponivel",
    "ausente",
    "sem pdf",
    "conflito",
    "diverg",
)

_KEY_FINDING_SKIP_THEMES = {
    "escopo",
    "identidade",
    "administrador",
    "gestor",
    "custodiante",
    "reuso delta",
    "ime",
    "ime mais recente",
    "emissoes identificadas",
}

_DOCUMENT_FACT_THEMES = (
    (
        "Elegibilidade",
        ("Critérios de elegibilidade",),
        ("criterios de elegibilidade", "elegibilidade dos recebiveis"),
    ),
    (
        "Alocação mínima",
        ("Alocação mínima em DCs",),
        ("alocacao minima em direitos creditorios", "alocacao minima regulatoria"),
    ),
    (
        "Subordinação",
        ("Subordinação mínima",),
        ("subordinacao minima", "relacao minima", "indice de cobertura senior"),
    ),
    (
        "Gatilhos",
        ("Evento de avaliação por atraso", "Liquidação/vencimento por atraso"),
        ("atraso", "inadimplencia", "inadimplemento"),
    ),
    (
        "Reservas e cobertura",
        ("Cobertura mínima PDD", "Reserva/caixa mínimo"),
        ("cobertura minima de pdd", "reserva de caixa", "reserva de liquidez"),
    ),
    (
        "Concentração",
        ("Limites de concentração",),
        ("limite de concentracao", "limite por devedor", "coobrigado"),
    ),
    (
        "Derivativos",
        ("Hedges permitidos",),
        ("derivativos", "hedge"),
    ),
    (
        "Governança",
        ("Cross default do cedente", "Troca de gestor/administrador"),
        ("prestador-chave", "troca de administrador", "cross default"),
    ),
)

_DOCUMENT_ROW_PREFIXES = {
    "evento de avaliação por atraso": "Avaliação",
    "liquidação/vencimento por atraso": "Liquidação",
    "cobertura mínima pdd": "Cobertura",
    "reserva/caixa mínimo": "Reserva",
    "cross default do cedente": "Cross default",
    "troca de gestor/administrador": "Prestadores",
}


def render_tab_deep_dive(
    *,
    selected_portfolio: PortfolioRecord | None = None,
    show_portfolio_selector: bool = True,
    show_curation_tools: bool = True,
    compact: bool = False,
) -> None:
    _ = show_curation_tools
    manifests = list_deep_dives()
    if not compact:
        render_page_header(
            "Curadoria de Leitura (Documentos)",
            "Síntese dos documentos públicos associados à carteira.",
        )

    if not manifests:
        st.info("Ainda não há curadoria documental disponível.")
        _render_update_prompt()
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
        st.info("Ainda não há curadoria documental para esta carteira.")
        _render_update_prompt()
        return

    manifest = available[0]
    if not compact and len(available) > 1:
        manifest = st.selectbox(
            "Data da curadoria",
            options=available,
            format_func=lambda item: _format_reading_date(item.generated_at),
            key="deep_dive_manifest",
        )

    _render_document_curation(manifest)
    _render_update_prompt()


def _render_document_curation(manifest: Any) -> None:
    reading_date = _format_reading_date(getattr(manifest, "generated_at", ""))
    st.markdown("### Síntese dos documentos")
    st.markdown(
        f"<div class='deepdive-curation-date'>Data da leitura: <strong>{escape(reading_date)}</strong></div>",
        unsafe_allow_html=True,
    )
    st.markdown("\n".join(f"- {item}" for item in _curation_base_bullets(manifest)))
    st.info(
        "Use esta curadoria como apoio. Ela depende do prompt específico de atualização; "
        "confirme limites, datas e condições nos documentos originais."
    )

    findings = _curated_key_findings(manifest)
    if findings:
        st.markdown("#### Destaques da carteira")
        st.markdown(
            "\n".join(
                f"- **{escape(theme)}:** {escape(conclusion)}"
                for theme, conclusion in findings
            )
        )

    _render_fund_reading(manifest)

    warnings = _useful_manifest_warnings(manifest)
    if warnings:
        st.markdown("#### Pontos de atenção")
        st.markdown("\n".join(f"- {escape(item)}" for item in warnings))


def _curation_base_bullets(manifest: Any) -> tuple[str, ...]:
    _ = manifest
    return (
        "**Fonte:** documentos públicos disponibilizados pela CVM e pelo Fundos.NET.",
        "**Escopo:** todos os documentos incorporados à curadoria e acessíveis para os CNPJs desta carteira "
        "até a data da leitura.",
        "**Método:** curadoria produzida por IA a partir da leitura documental da carteira.",
        "**Lacunas:** informações não localizadas ou documentos inacessíveis permanecem indicados como lacuna, sem inferência.",
    )


def _render_update_prompt() -> None:
    with st.expander("Prompt usado para atualizar este artefato", expanded=False):
        st.code(_load_reverse_engineering_prompt(), language="markdown")


def _format_reading_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "data não informada"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not match:
            return _sanitize_visible_text(text)
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return parsed.strftime("%d/%m/%Y")


def _curated_key_findings(manifest: Any, *, limit: int = 4) -> tuple[tuple[str, str], ...]:
    table_spec = _find_manifest_table(manifest, "key_findings")
    if table_spec is None:
        return ()
    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty or "Conclusão" not in frame.columns:
        return ()

    output: list[tuple[str, str]] = []
    for _, row in frame.iterrows():
        theme = _sanitize_visible_text(row.get("Tema", "Ponto relevante")) or "Ponto relevante"
        if _fold_text(theme) in _KEY_FINDING_SKIP_THEMES:
            continue
        conclusion = _clean_document_fact(row.get("Conclusão"), max_parts=4, max_chars=280)
        if not conclusion:
            continue
        output.append((theme, conclusion))
        if len(output) >= limit:
            break
    return tuple(output)


def _render_fund_reading(manifest: Any) -> None:
    funds = tuple(getattr(manifest, "funds", ()) or ())
    if not funds:
        return

    st.markdown("#### Pontos essenciais por fundo")
    if len(funds) == 1:
        fund = funds[0]
        st.markdown(f"**{escape(_fund_display_name(fund))}**")
    else:
        selected_cnpj = st.selectbox(
            "Fundo",
            options=[_digits(fund.get("cnpj")) for fund in funds],
            format_func=lambda cnpj: _fund_display_name(
                next((fund for fund in funds if _digits(fund.get("cnpj")) == cnpj), {})
            ),
            key=f"deep_dive_fund::{getattr(manifest, 'deep_dive_id', 'curation')}",
        )
        fund = next((item for item in funds if _digits(item.get("cnpj")) == selected_cnpj), funds[0])

    st.caption(f"CNPJ {_format_cnpj(fund.get('cnpj'))}.")

    facts = _build_fund_curation_facts(manifest, fund)
    if not facts:
        st.caption("Não há uma síntese documental confiável para este fundo neste pacote.")
        return
    st.markdown(
        "\n".join(
            f"- **{escape(label)}:** {escape(value)}"
            for label, value in facts
        )
    )


def _fund_display_name(fund: dict[str, str]) -> str:
    return _short_name(fund.get("short_name") or fund.get("name") or fund.get("cnpj") or "Fundo")


def _build_fund_curation_facts(manifest: Any, fund: dict[str, str], *, limit: int = 5) -> tuple[tuple[str, str], ...]:
    comparison = pd.DataFrame()
    comparison_spec = _find_manifest_table(manifest, "comparison_main")
    if comparison_spec is not None:
        comparison = load_deep_dive_table(manifest, comparison_spec)

    row_values: dict[str, object] = {}
    if not comparison.empty:
        fund_column = _find_fund_column(comparison, fund)
        first_column = comparison.columns[0]
        if fund_column is not None:
            row_values = {
                _normalize_text(row.get(first_column)): row.get(fund_column)
                for _, row in comparison.iterrows()
            }

    thresholds = _fund_thresholds(manifest, fund)
    facts: list[tuple[str, str]] = []
    for label, comparison_labels, threshold_keywords in _DOCUMENT_FACT_THEMES:
        values: list[tuple[str, str]] = []
        for row_label in comparison_labels:
            value = _clean_comparison_fact(
                row_values.get(_normalize_text(row_label)),
                theme=label,
            )
            if value:
                values.append((row_label, value))
        if not values:
            fallback = _best_threshold_fact(thresholds, threshold_keywords, theme=label)
            if fallback:
                values.append(("", fallback))
        if not values:
            continue
        facts.append((label, _combine_document_values(values)))
        if len(facts) >= limit:
            break
    return tuple(facts)


def _fund_thresholds(manifest: Any, fund: dict[str, str]) -> pd.DataFrame:
    table_spec = _find_manifest_table(manifest, "thresholds")
    if table_spec is None:
        return pd.DataFrame()
    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty or "CNPJ" not in frame.columns:
        return pd.DataFrame()
    cnpj = _digits(fund.get("cnpj"))
    return frame[frame["CNPJ"].map(_digits).eq(cnpj)].copy()


def _best_threshold_fact(frame: pd.DataFrame, keywords: tuple[str, ...], *, theme: str) -> str:
    if frame.empty or "Critério" not in frame.columns:
        return ""
    folded_keywords = tuple(_fold_text(keyword) for keyword in keywords)
    candidates: dict[str, int] = {}
    for _, row in frame.iterrows():
        criterion = _fold_text(row.get("Critério"))
        if not any(keyword in criterion for keyword in folded_keywords):
            continue
        value = _compose_threshold_fact(row, theme=theme)
        if not value:
            continue
        score = len(value) + (40 if re.search(r"[A-Za-zÀ-ÿ]", value) else 0)
        candidates[value] = max(candidates.get(value, 0), score)
    if not candidates:
        return ""
    if len(candidates) > 1:
        return ""
    return next(iter(candidates))


def _compose_threshold_fact(row: pd.Series, *, theme: str) -> str:
    criterion = _sanitize_visible_text(row.get("Critério"))
    comparison = _sanitize_visible_text(row.get("Comparação"))
    limit = _clean_document_fact(row.get("Limite"), max_parts=2, max_chars=240)
    if not criterion or not limit:
        return ""

    comparison_folded = _fold_text(comparison)
    if comparison and comparison_folded not in {">=", "<=", ">", "<", "="}:
        return ""
    operator = _comparison_operator(limit) or comparison
    if comparison and not _comparison_operator(limit):
        rule = f"{comparison} {limit}"
    else:
        rule = limit

    if theme in {"Alocação mínima", "Subordinação"}:
        if operator in {"<=", "<"}:
            return ""
        if _is_numeric_rule(rule) and any(value > 100 for value in _percentage_values(rule)):
            return ""
        return rule

    if theme == "Concentração":
        folded_rule = _fold_text(rule)
        if operator not in {"<=", "<"} and not any(
            token in folded_rule for token in ("ate ", "no maximo", "limitado a")
        ):
            return ""
        percentages = _percentage_values(rule)
        if percentages and any(value >= 100 for value in percentages):
            return ""
        return rule

    if theme == "Gatilhos":
        context = " ".join(
            filter(None, (criterion, _sanitize_visible_text(row.get("Evento"))))
        )
        if not any(
            token in _fold_text(context)
            for token in ("atraso", "inadimpl", "default", "evento", "liquid", "over ", "indice")
        ):
            return ""
        return f"{criterion}: {rule}"

    if theme == "Reservas e cobertura":
        if not re.search(r"[A-Za-zÀ-ÿ]", limit):
            return ""
        return f"{criterion}: {rule}"

    if theme == "Derivativos":
        folded = _fold_text(limit)
        if not re.search(r"[A-Za-zÀ-ÿ]", limit) or not any(
            token in folded for token in ("derivativ", "hedge", "protec", "indexador", "vedad")
        ):
            return ""
        return rule

    if theme in {"Elegibilidade", "Governança"}:
        if not re.search(r"[A-Za-zÀ-ÿ]", limit):
            return ""
        return rule if theme == "Elegibilidade" else f"{criterion}: {rule}"

    return ""


def _combine_document_values(values: list[tuple[str, str]]) -> str:
    rendered: list[str] = []
    for row_label, value in values:
        prefix = _DOCUMENT_ROW_PREFIXES.get(_normalize_text(row_label), "")
        item = f"{prefix}: {value}" if prefix else value
        if item not in rendered:
            rendered.append(item)
    return "; ".join(rendered)


def _clean_comparison_fact(value: object, *, theme: str) -> str:
    text = _sanitize_visible_text(value)
    if not text:
        return ""
    parts: list[str] = []
    for raw_part in re.split(r"\s*;\s*", text):
        part = _clean_document_fact(raw_part, max_parts=1, max_chars=300)
        if not part or not _comparison_fragment_fits_theme(part, theme=theme):
            continue
        if part not in parts:
            parts.append(part)
    if not parts:
        return ""
    return _clean_document_fact("; ".join(parts), max_parts=3, max_chars=300)


def _comparison_fragment_fits_theme(value: str, *, theme: str) -> bool:
    folded = _fold_text(value)
    has_words = bool(re.search(r"[A-Za-zÀ-ÿ]", value))
    operator = _comparison_operator(value)

    if theme == "Elegibilidade":
        return has_words and any(
            token in folded for token in ("elegib", "direito creditorio", "ccb", "recebivel", "parcela", "devedor")
        )
    if theme == "Alocação mínima":
        if operator in {"<=", "<"}:
            return False
        if any(token in folded for token in ("default", "evento", "liquid", "atraso", "inadimpl")):
            return False
        return not (_is_numeric_rule(value) and any(item > 100 for item in _percentage_values(value)))
    if theme == "Subordinação":
        if operator in {"<=", "<"}:
            return False
        return not (_is_numeric_rule(value) and any(item > 100 for item in _percentage_values(value)))
    if theme == "Gatilhos":
        return has_words and any(
            token in folded for token in ("atraso", "inadimpl", "default", "evento", "liquid", "over ", "indice")
        )
    if theme == "Reservas e cobertura":
        return has_words and any(
            token in folded
            for token in ("reserva", "cobertura", "pdd", "caixa", "liquidez", "amortiz", "despesa", "pagamento")
        )
    if theme == "Concentração":
        return has_words and any(token in folded for token in ("concentr", "devedor", "cedente", "sacado"))
    if theme == "Derivativos":
        return has_words and any(
            token in folded for token in ("derivativ", "hedge", "protec", "indexador", "vedad")
        )
    if theme == "Governança":
        return has_words
    return False


def _clean_document_fact(value: object, *, max_parts: int = 3, max_chars: int = 300) -> str:
    text = _sanitize_visible_text(value)
    if not text:
        return ""
    parts: list[str] = []
    for raw_part in re.split(r"\s*;\s*", text):
        part = re.sub(r"\s+", " ", raw_part).strip(" .")
        folded = _fold_text(part)
        if not part or folded in {"n/d", "nao identificado", "texto", ">=", "<=", ">", "<", "="}:
            continue
        if folded.startswith("texto") or "regra textual" in folded or "verificar observacao" in folded:
            continue
        if re.fullmatch(r"(?:[<>]=?\s*)?0(?:[,.]0+)?%?", part):
            continue
        numeric_key = re.sub(r"^[<>]=?\s*", "", part)
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(parts)
                if re.sub(r"^[<>]=?\s*", "", existing) == numeric_key
            ),
            None,
        )
        if duplicate_index is None:
            parts.append(part)
        elif re.match(r"^[<>]=?", part) and not re.match(r"^[<>]=?", parts[duplicate_index]):
            parts[duplicate_index] = part
    if not parts:
        return ""
    if len(parts) > 1 and all(not re.search(r"[A-Za-zÀ-ÿ]", part) for part in parts):
        return ""
    clipped = parts[:max_parts]
    result = "; ".join(clipped)
    if len(parts) > max_parts:
        result += "; demais condições no documento original"
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return result


def _comparison_operator(value: object) -> str:
    match = re.search(r"(?<!\w)(<=|>=|<|>|=)", str(value or ""))
    return match.group(1) if match else ""


def _percentage_values(value: object) -> tuple[float, ...]:
    output: list[float] = []
    for raw in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", str(value or "")):
        try:
            output.append(float(raw.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return tuple(output)


def _is_numeric_rule(value: object) -> bool:
    return bool(re.fullmatch(r"[\s<>=\d.,%xX]+", str(value or "").strip()))


def _useful_manifest_warnings(manifest: Any, *, limit: int = 2) -> tuple[str, ...]:
    output: list[str] = []
    for value in getattr(manifest, "warnings", ()) or ():
        warning = _sanitize_visible_text(value)
        folded = _fold_text(warning)
        if (
            not warning
            or any(snippet in folded for snippet in _GENERIC_WARNING_SNIPPETS)
            or not any(snippet in folded for snippet in _MATERIAL_WARNING_SNIPPETS)
        ):
            continue
        output.append(warning)
        if len(output) >= limit:
            break
    return tuple(output)


def _sanitize_visible_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or text.casefold() in {"nan", "none", "<na>", "—", "-"}:
        return ""
    return text.replace("—", "-").replace("–", "-").replace(" · ", ", ")


def _fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.strip()).casefold()


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
