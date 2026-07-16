from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_CLASSIFICATION_DIR = Path("outputs/fidc_classification_practices_20260609")
DEFAULT_ISSUANCE_DIR = Path("outputs/fidc_issuance_study_20260609")
DEFAULT_OUTPUT_DIR = Path("outputs/fidc_director_diagnostic_plan_20260609")


FEATURE_SCHEMA = [
    {
        "feature_key": "asset_class_confirmed",
        "label": "Lastro/setor confirmado no regulamento",
        "type": "tem_nao_tem",
        "why_it_matters": "Evita classificar apenas por nome do fundo ou metadado genérico.",
        "evidence_source": "Regulamento, anexo descritivo, suplemento da emissão, ata de constituição.",
        "extraction_prompt": "O documento descreve explicitamente os direitos creditórios elegíveis, origem, cedentes e devedores?",
    },
    {
        "feature_key": "named_originator_or_cedente",
        "label": "Cedente/originador nomeado",
        "type": "tem_nao_tem",
        "why_it_matters": "Distingue mono-originador, plataforma, multicedente e risco de concentração operacional.",
        "evidence_source": "Definições de Cedente, Originador, Consultora, Política de Aquisição.",
        "extraction_prompt": "Há cedente(s), originador(es), consultora(s) ou plataforma(s) explicitamente nomeados?",
    },
    {
        "feature_key": "named_debtor_or_sacado",
        "label": "Sacado/devedor nomeado",
        "type": "tem_nao_tem",
        "why_it_matters": "Identifica risco sacado, bancos emissores, devedor concentrado e estruturas pulverizadas.",
        "evidence_source": "Definições de Devedor, Sacado, Comprador, Arranjo de Pagamento, anexos.",
        "extraction_prompt": "Há sacado(s), devedor(es), bancos emissores, convênios ou entes públicos nomeados?",
    },
    {
        "feature_key": "monocedente_or_multicedente",
        "label": "Mono/multicedente determinado",
        "type": "categorical",
        "why_it_matters": "É uma das primeiras segmentações de risco e governança de originação.",
        "evidence_source": "Política de investimento, critérios de elegibilidade, limites de concentração.",
        "extraction_prompt": "Classifique como monocedente, multicedente, plataforma, FIC/alocador ou indeterminado.",
    },
    {
        "feature_key": "concentrated_or_pulverized_debtors",
        "label": "Sacados/devedores concentrados ou pulverizados",
        "type": "categorical",
        "why_it_matters": "Permite comparar subordinação e eventos de inadimplência dentro de universos comparáveis.",
        "evidence_source": "Tipo_lastro CVM, concentração por devedor/sacado, limites e anexos.",
        "extraction_prompt": "Classifique devedores como concentrado, pulverizado ou indeterminado.",
    },
    {
        "feature_key": "revolving_period",
        "label": "Tem período revolvente",
        "type": "tem_nao_tem",
        "why_it_matters": "Revolvência muda risco de seleção, elegibilidade e substituição de carteira.",
        "evidence_source": "Capítulos de aquisição, amortização, eventos de avaliação e período de carência.",
        "extraction_prompt": "O fundo pode comprar novos direitos creditórios durante a vida das cotas?",
    },
    {
        "feature_key": "subordination_minimum",
        "label": "Tem subordinação mínima ou razão de garantia",
        "type": "numeric_percent_and_tem_nao_tem",
        "why_it_matters": "É o principal parâmetro de proteção por tipo de FIDC.",
        "evidence_source": "Razão de subordinação, razão de garantia, índice de cobertura.",
        "extraction_prompt": "Extraia percentuais e diga se são júnior/PL, sub total/PL, cobertura sênior ou outro.",
    },
    {
        "feature_key": "mezzanine_layer",
        "label": "Tem cota mezanino",
        "type": "tem_nao_tem",
        "why_it_matters": "Afeta waterfall, interpretação da subordinação e preço por tranche.",
        "evidence_source": "Capítulo de cotas, suplementos, ata de emissão.",
        "extraction_prompt": "Há classe/cota/série mezanino em circulação ou prevista?",
    },
    {
        "feature_key": "cash_or_liquidity_reserve",
        "label": "Tem reserva de caixa/liquidez",
        "type": "numeric_percent_or_formula",
        "why_it_matters": "Padrão operacional importante para comparar pagamento de juros/amortização.",
        "evidence_source": "Reserva de Caixa, Reserva de Liquidez, Reserva de Despesas, Reserva de Amortização.",
        "extraction_prompt": "Extraia fórmula, percentual, gatilho de recomposição e uso dos recursos.",
    },
    {
        "feature_key": "repurchase_or_indemnity",
        "label": "Tem recompra/substituição/indenização",
        "type": "tem_nao_tem",
        "why_it_matters": "Mostra mitigação de elegibilidade, fraude, vício de lastro e inadimplência inicial.",
        "evidence_source": "Condições de cessão, recompra obrigatória, substituição, indenização.",
        "extraction_prompt": "Há obrigação ou faculdade de recompra/substituição/indenização por cedente/originador?",
    },
    {
        "feature_key": "eligibility_criteria",
        "label": "Tem critérios de elegibilidade objetivos",
        "type": "tem_nao_tem_and_text",
        "why_it_matters": "Base para comparar underwriting por tipo de fundo.",
        "evidence_source": "Critérios de Elegibilidade, Condições de Cessão.",
        "extraction_prompt": "Liste critérios objetivos de prazo, documentação, atraso, concentração, garantias e formalização.",
    },
    {
        "feature_key": "concentration_limits",
        "label": "Tem limites de concentração",
        "type": "tem_nao_tem_and_numeric",
        "why_it_matters": "É uma prática comum que varia fortemente por setor.",
        "evidence_source": "Limites por cedente, sacado, devedor, grupo econômico, convênio, produto.",
        "extraction_prompt": "Extraia os limites percentuais por cedente/sacado/devedor/grupo econômico.",
    },
    {
        "feature_key": "default_or_performance_triggers",
        "label": "Tem gatilhos de inadimplência/performance",
        "type": "tem_nao_tem_and_numeric",
        "why_it_matters": "Permite comparar padrões de liquidação/amortização acelerada.",
        "evidence_source": "Eventos de Avaliação, Eventos de Liquidação, Índices de Inadimplência.",
        "extraction_prompt": "Extraia eventos por atraso, PDD, over 30/60/90, recompra, renegociação ou perda.",
    },
    {
        "feature_key": "rating_required",
        "label": "Tem rating obrigatório",
        "type": "tem_nao_tem",
        "why_it_matters": "Importante para oferta pública, governança e comparabilidade de senioridade.",
        "evidence_source": "Suplementos, anúncios, capítulo de cotas e obrigações periódicas.",
        "extraction_prompt": "O regulamento ou suplemento exige rating inicial, manutenção ou revisão periódica?",
    },
    {
        "feature_key": "derivatives_allowed",
        "label": "Derivativos permitidos",
        "type": "categorical",
        "why_it_matters": "Distingue hedge permitido, vedação e exposição adicional.",
        "evidence_source": "Política de investimento e vedações.",
        "extraction_prompt": "Classifique como vedado, hedge apenas, permitido com limite, ou amplo.",
    },
    {
        "feature_key": "amortization_profile",
        "label": "Perfil de amortização definido",
        "type": "categorical",
        "why_it_matters": "Conecta preço da emissão com duration e risco de refinanciamento.",
        "evidence_source": "Suplemento da série/classe, cronograma de amortização e resgate.",
        "extraction_prompt": "Classifique como bullet, amortização programada, pass-through, revolvente+amortização, residual.",
    },
]


ISSUANCE_DATA_SPEC = [
    {
        "field": "volume_emitido",
        "source": "CVM ofertas, anúncio de encerramento, suplemento",
        "chart_use": "barra principal de tamanho da emissão",
        "notes": "Separar volume registrado, encerrado e efetivamente subscrito quando disponível.",
    },
    {
        "field": "preco_unitario_vnu",
        "source": "CVM ofertas, suplemento, documentos de emissão",
        "chart_use": "tabela de apoio; sanity check de volume = quantidade x preço",
        "notes": "Nem toda emissão informa preço unitário em formato confiável.",
    },
    {
        "field": "tipo_cota",
        "source": "suplemento, nome da cota/classe/série",
        "chart_use": "facet/cores: sênior, mezanino, subordinada/júnior",
        "notes": "Normalizar SEN/MES/SUB e preservar rótulo original.",
    },
    {
        "field": "taxa_referencia",
        "source": "suplemento, ata de bookbuilding, anúncio de encerramento",
        "chart_use": "pontinho do spread na barra",
        "notes": "Separar CDI+, %CDI, IPCA+, pré e residual. O gráfico CDI+x% só deve usar tranches CDI+.",
    },
    {
        "field": "spread_cdi_aa",
        "source": "texto de remuneração extraído",
        "chart_use": "ponto sobre a barra de volume",
        "notes": "Extrair CDI + x% a.a.; quando %CDI, não converter sem premissa explícita.",
    },
    {
        "field": "data_emissao_encerramento",
        "source": "CVM ofertas, documentos de emissão",
        "chart_use": "filtros por ano/quarter e timeline",
        "notes": "Usar encerramento para emissão realizada; registro para pipeline/abertas.",
    },
    {
        "field": "administrador_gestor_custodiante",
        "source": "CVM cadastro, ofertas RCVM160, regulamento",
        "chart_use": "rankings por subtipo e função",
        "notes": "CVM cadastro cobre fundo/classe; regulamento confirma prestadores vigentes.",
    },
    {
        "field": "cedentes_sacados_devedores",
        "source": "regulamento, suplemento, anexos de cessão, descrição de lastro",
        "chart_use": "rankings e mapas de concentração por universo",
        "notes": "Tratar como alto risco de falso negativo; muitos documentos dizem 'multicedente' sem nomear.",
    },
]


ONE_MONTH_WORKPLAN = [
    {
        "week": "Semana 1",
        "objective": "Fechar taxonomia e review manual dos maiores desconhecidos",
        "deliverables": "Top 150 emissores não classificados; ajuste de regras; dashboard v0 de setores e volumes.",
        "success_metric": "Reduzir volume não classificado em pelo menos 50% ou documentar blockers.",
    },
    {
        "week": "Semana 2",
        "objective": "Extrair regulamentos e matriz tem/não tem",
        "deliverables": "Matriz regulatória dos top emissores por setor; subordinação, reservas, revolvência, concentração e gatilhos.",
        "success_metric": "Cobrir top 20 por volume de cada macro setor e todos os top 50 overall.",
    },
    {
        "week": "Semana 3",
        "objective": "Preço das emissões e prestadores",
        "deliverables": "Base de tranches com volume, tipo de cota, CDI+/%CDI/IPCA+, admins, gestores, custodiante, cedentes/sacados.",
        "success_metric": "Gráficos de barra+ponto por tipo de FIDC e tipo de cota com flags de qualidade.",
    },
    {
        "week": "Semana 4",
        "objective": "Narrativa de diretoria e QA",
        "deliverables": "Deck executivo, apêndice metodológico, base auditável, lacunas e recomendações de produto/dados.",
        "success_metric": "Diagnóstico defendável: números agregados + equal-weight + exemplos documentais.",
    },
]


def format_brl(value: float) -> str:
    return f"R$ {float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def build_manual_review_batches(issuers: pd.DataFrame) -> pd.DataFrame:
    df = issuers.copy()
    df["volume_total_registrado"] = pd.to_numeric(df["volume_total_registrado"], errors="coerce").fillna(0)
    df["volume_encerrado_conservador"] = pd.to_numeric(
        df["volume_encerrado_conservador"], errors="coerce"
    ).fillna(0)
    df["linhas_oferta"] = pd.to_numeric(df["linhas_oferta"], errors="coerce").fillna(0).astype(int)
    df["needs_manual_review"] = (
        df["setor_n1"].eq("Não classificado")
        | df["confidence"].eq("baixa")
        | ((df["confidence"].eq("media")) & (df["volume_total_registrado"] >= 250_000_000))
    )
    review = df[df["needs_manual_review"]].copy()
    review["review_reason"] = ""
    review.loc[review["setor_n1"].eq("Não classificado"), "review_reason"] = "sem_classificacao_setorial"
    review.loc[
        review["review_reason"].eq("") & review["confidence"].eq("baixa"), "review_reason"
    ] = "confianca_baixa"
    review.loc[
        review["review_reason"].eq("") & review["confidence"].eq("media"), "review_reason"
    ] = "confianca_media_alto_volume"
    review = review.sort_values("volume_total_registrado", ascending=False).reset_index(drop=True)
    review["priority_rank"] = review.index + 1

    def wave(rank: int, row: pd.Series) -> str:
        if rank <= 50:
            return "Onda 1 - top 50 por volume"
        if rank <= 150:
            return "Onda 2 - top 150 por volume"
        if row["volume_total_registrado"] >= 100_000_000:
            return "Onda 3 - acima de R$100mm"
        return "Onda 4 - cauda longa/amostragem"

    review["review_wave"] = [wave(rank, row) for rank, row in zip(review["priority_rank"], review.to_dict("records"))]
    review["review_goal"] = (
        "confirmar setor/lastro; identificar cedentes/sacados; extrair prestadores; preencher matriz tem/não tem; capturar preço/spread se houver emissão"
    )
    review["expected_primary_docs"] = "regulamento vigente; suplemento/anúncio de encerramento; ata de emissão; anexos de cessão se disponíveis"
    cols = [
        "priority_rank",
        "review_wave",
        "review_reason",
        "cnpj_emissor",
        "nome_emissor",
        "setor_n1",
        "setor_n2",
        "confidence",
        "linhas_oferta",
        "volume_total_registrado",
        "volume_encerrado_conservador",
        "platform_coverage_level",
        "classification_evidence",
        "expected_primary_docs",
        "review_goal",
    ]
    return review[cols]


def build_director_plan_md(output_dir: Path, manual_batches: pd.DataFrame, issuer_summary: pd.DataFrame) -> None:
    top_unclassified = manual_batches[manual_batches["review_reason"].eq("sem_classificacao_setorial")].head(15)
    wave_summary = (
        manual_batches.groupby("review_wave")
        .agg(
            emissores=("cnpj_emissor", "count"),
            volume=("volume_total_registrado", "sum"),
            volume_encerrado=("volume_encerrado_conservador", "sum"),
        )
        .reset_index()
    )
    lines = [
        "# Próximos passos - diagnóstico profundo de FIDCs",
        "",
        f"Gerado em UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Onde estamos",
        "",
        "- O estudo já tem universo CVM de ofertas 2024FY, 2025FY e 2026YTD.",
        "- A classificação setorial inicial cobre 1.636 emissores, mas 650 ainda estão sem classificação confiável por metadados.",
        "- Há 66 emissores com documentos locais baixados; isso é suficiente para provar metodologia, não para cobrir a indústria inteira.",
        "- A base regulatória local já permite uma primeira matriz de práticas, mas precisa de expansão documental por ondas.",
        "",
        "## Review manual por ondas",
        "",
        "| Onda | Emissores | Volume registrado | Volume encerrado |",
        "|---|---:|---:|---:|",
    ]
    for _, row in wave_summary.iterrows():
        lines.append(
            f"| {row['review_wave']} | {int(row['emissores']):,} | {format_brl(row['volume'])} | {format_brl(row['volume_encerrado'])} |"
        )
    lines.extend(
        [
            "",
            "## Top não classificados para atacar primeiro",
            "",
            "| Rank | CNPJ | Emissor | Volume registrado | Motivo |",
            "|---:|---|---|---:|---|",
        ]
    )
    for _, row in top_unclassified.iterrows():
        lines.append(
            f"| {int(row['priority_rank'])} | {row['cnpj_emissor']} | {row['nome_emissor']} | {format_brl(row['volume_total_registrado'])} | {row['review_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Saídas analíticas que precisamos produzir",
            "",
            "1. **Mapa setorial defendável**: volume por setor e contagem equal-weight de emissores/fundos.",
            "2. **Matriz tem/não tem**: por subtipo, presença de subordinação, mezanino, reserva, revolvência, recompra, concentração, rating, derivativos e gatilhos.",
            "3. **Preço das emissões**: barras de volume por tranche/cota, com ponto de CDI+ x% a.a. quando a remuneração for CDI+.",
            "4. **Mapa de participantes**: administradores, gestores, custodiante, cedentes, sacados/devedores e originadores mais relevantes por subtipo.",
            "5. **Diagnóstico executivo**: padrões de mercado, exceções, lacunas de dados, casos emblemáticos e recomendação de monitoramento contínuo.",
            "",
            "## Plano de 1 mês",
            "",
            "| Semana | Objetivo | Entregáveis | Métrica de sucesso |",
            "|---|---|---|---|",
        ]
    )
    for item in ONE_MONTH_WORKPLAN:
        lines.append(
            f"| {item['week']} | {item['objective']} | {item['deliverables']} | {item['success_metric']} |"
        )
    lines.extend(
        [
            "",
            "## Gráficos-alvo para diretoria",
            "",
            "- **Stacked bars** por ano e subtipo: volume encerrado vs válido/aberto.",
            "- **Barra + ponto** por emissão/tranche: barra = volume; ponto = CDI+ spread; cor = tipo de cota; facet = subtipo FIDC.",
            "- **Box/violin equal-weight** de subordinação por subtipo, sem ponderar por volume.",
            "- **Heatmap tem/não tem** por subtipo: práticas regulatórias nas linhas e setores nas colunas.",
            "- **Rankings horizontais** de administradores, gestores e custodiante por volume e por número de emissores.",
            "- **Sankey/network** cedente -> FIDC -> sacado/devedor quando documentos nomeiam partes.",
            "",
            "## Atenção metodológica",
            "",
            "- O agregado por volume conta a história econômica, mas o padrão de mercado deve ser equal-weight por fundo/emissor.",
            "- Não converter `%CDI`, IPCA+ ou taxa pré em CDI+ sem premissa explícita; marcar como regimes separados.",
            "- Toda classificação precisa ter `confidence` e evidência documental ou metadado de origem.",
            "- `Não classificado` é trabalho legítimo: significa que o documento precisa ser lido, não que o fundo seja irrelevante.",
        ]
    )
    (output_dir / "one_month_director_study_plan.md").write_text("\n".join(lines), encoding="utf-8")


def write_csv(rows: list[dict] | pd.DataFrame, path: Path) -> None:
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    else:
        pd.DataFrame(rows).to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manual-review and one-month director diagnostic plan.")
    parser.add_argument("--classification-dir", default=str(DEFAULT_CLASSIFICATION_DIR))
    parser.add_argument("--issuance-dir", default=str(DEFAULT_ISSUANCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    classification_dir = Path(args.classification_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    issuers = pd.read_csv(classification_dir / "fidc_issuer_sector_classification.csv")
    issuer_summary = pd.read_csv(classification_dir / "fidc_sector_summary_equal_weight.csv")
    manual_batches = build_manual_review_batches(issuers)

    write_csv(manual_batches, output_dir / "manual_review_batches.csv")
    write_csv(FEATURE_SCHEMA, output_dir / "regulatory_feature_schema_tem_nao_tem.csv")
    write_csv(ISSUANCE_DATA_SPEC, output_dir / "issuance_pricing_chart_data_spec.csv")
    write_csv(ONE_MONTH_WORKPLAN, output_dir / "one_month_workplan.csv")
    build_director_plan_md(output_dir, manual_batches, issuer_summary)

    print(
        {
            "manual_review_issuers": int(len(manual_batches)),
            "wave_counts": manual_batches["review_wave"].value_counts().to_dict(),
            "output_dir": str(output_dir),
        }
    )


if __name__ == "__main__":
    main()
