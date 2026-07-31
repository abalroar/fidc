"""Materializa a curadoria comparável dos FIDCs flagship.

A seleção de CNPJs é editorial e versionada em
``data/industry_study/industry_flagship_scope.csv``. PL e subordinação atual
vêm do Informe Mensal CVM da competência do payload. Mínimos contratuais,
preços/VNUs, mezanino e eventos usam exclusivamente os pacotes documentais já
publicados em ``data/deep_dives``. A ausência de pacote ou de campo permanece
explícita; nenhuma lacuna é convertida em zero ou estimativa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd


PL_RECONCILIATION_WARNING_PCT = 0.5
FLAGSHIP_DOCUMENTARY_FIELDS = (
    "documento_id_regulamento",
    "documento_data_regulamento",
    "pagina_clausula",
    "paginas_lidas",
    "status_curadoria_documental",
    "observacao_documental",
    "subordinacao_minima_junior_pct",
    "subordinacao_minima_junior_display",
    "subordinacao_minima_texto",
    "subordinacao_minima_fonte",
)
FUNDOSNET_CNPJ_BASE = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/"
    "abrirGerenciadorDocumentosCVM?cnpjFundo="
)


@dataclass(frozen=True)
class FlagshipCurationResult:
    detail: pd.DataFrame
    families: pd.DataFrame
    summary: dict[str, object]


@dataclass(frozen=True)
class PortfolioCurationResult:
    detail: pd.DataFrame
    ranges: pd.DataFrame
    summary: dict[str, object]


def _digits(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(14) if digits else ""


def _format_cnpj(value: object) -> str:
    digits = _digits(value)
    if len(digits) != 14:
        return digits
    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in text if not unicodedata.combining(char)).upper()


def _read_table(package_dir: Path, name: str) -> pd.DataFrame:
    path = package_dir / "tables" / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _row_text(row: pd.Series, *columns: str) -> str:
    return " · ".join(_text(row.get(column)) for column in columns if _text(row.get(column)))


def _unique_join(values: list[str], *, separator: str = " | ") -> str:
    unique: list[str] = []
    for value in values:
        cleaned = _text(value)
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return separator.join(unique)


def _extract_percentages(value: object) -> list[float]:
    return [
        float(raw.replace(",", "."))
        for raw in re.findall(r"(\d{1,3}(?:[.,]\d+)?)\s*%", _text(value))
    ]


def _format_pct_number(value: float) -> str:
    digits = 0 if float(value).is_integer() else 1
    return f"{value:.{digits}f}".replace(".", ",") + "%"


def _format_brl_number(value: float) -> str:
    if float(value).is_integer():
        rendered = f"{int(value):,}".replace(",", ".")
    else:
        rendered = f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {rendered}"


def _parse_brl(value: object) -> float | None:
    text = _text(value)
    match = re.search(r"R\$\s*([\d.]+(?:,\d+)?)", text)
    if not match:
        return None
    normalized = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _is_concrete_price(value: object) -> bool:
    folded = _fold(value)
    return bool(_parse_brl(value) is not None) and not any(
        token in folded for token in ("CALCULADO", "EM VIGOR", "NAO INFORM")
    )


def _month_year_display(value: object) -> str:
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return "N/D"
    months = (
        "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
    )
    return f"{months[int(parsed.month) - 1]}/{str(int(parsed.year))[-2:]}"


def _document_fields(
    *,
    package_dir: Path | None,
    cnpj: str,
) -> dict[str, object]:
    if package_dir is None:
        return {
            "pacote_documental_status": "Lacuna documental — pacote não disponível",
            "subordinacao_minima_junior_pct": None,
            "subordinacao_minima_junior_display": "N/D",
            "subordinacao_minima_texto": "N/D — pacote documental não disponível",
            "subordinacao_minima_fonte": "N/D",
            "preco_emissao_brl": None,
            "preco_emissao_display": "N/D",
            "preco_emissao_classe": "N/D",
            "preco_emissao_data": "N/D",
            "preco_emissao_fonte": "N/D",
            "emissao_data": "N/D",
            "emissao_data_display": "N/D",
            "emissao_fonte": "N/D",
            "cota_mezanino": "N/D",
            "cota_mezanino_fonte": "N/D",
            "vencimento_antecipado": "N/D — pacote documental não disponível",
            "vencimento_antecipado_fonte": "N/D",
        }

    thresholds = _read_table(package_dir, "thresholds")
    emissions = _read_table(package_dir, "emissions")
    if not thresholds.empty:
        thresholds = thresholds[
            thresholds["CNPJ"].map(_digits).eq(cnpj)
        ].copy()
    if not emissions.empty:
        emissions = emissions[emissions["CNPJ"].map(_digits).eq(cnpj)].copy()

    threshold_combined = thresholds.apply(
        lambda row: _row_text(
            row,
            "Critério",
            "Evento",
            "Comparação",
            "Limite",
            "Métrica IME",
        ),
        axis=1,
    ) if not thresholds.empty else pd.Series(dtype=str)
    subordinate_mask = threshold_combined.map(_fold).str.contains(
        "SUBORDIN", regex=False, na=False
    )
    subordinate = thresholds.loc[subordinate_mask].copy()
    subordinate["_combined"] = threshold_combined.loc[subordinate.index]
    junior_metric = subordinate.get(
        "Métrica IME", pd.Series("", index=subordinate.index)
    ).map(_fold)
    junior_criterion = subordinate.get(
        "Critério", pd.Series("", index=subordinate.index)
    ).map(_fold)
    junior_mask = (
        junior_metric.str.startswith("COTAS SUB JR / PL", na=False)
        | junior_metric.str.startswith(
            "COTAS SUBORDINADAS JUNIORES / PL", na=False
        )
        | (
            junior_criterion.str.contains("JUNIOR", na=False)
            & ~junior_criterion.str.contains(
                r"MEZANINO A|SENIOR", regex=True, na=False
            )
        )
    )
    junior = subordinate.loc[junior_mask].copy()
    junior_values = sorted(
        {
            value
            for text in junior["_combined"].tolist()
            for value in _extract_percentages(text)
        }
    )
    junior_scalar = junior_values[0] if len(junior_values) == 1 else None
    junior_display = (
        _format_pct_number(junior_values[0])
        if len(junior_values) == 1
        else (
            " / ".join(_format_pct_number(value) for value in junior_values)
            if junior_values
            else "N/D"
        )
    )
    threshold_texts = [
        f"{_text(row.get('Critério'))}: {_text(row.get('Limite'))}"
        for _, row in subordinate.iterrows()
        if _text(row.get("Critério")) or _text(row.get("Limite"))
    ]
    threshold_sources = [
        _text(row.get("Fonte"))
        for _, row in subordinate.iterrows()
        if _text(row.get("Fonte"))
    ]

    concrete = emissions[
        emissions.get("Preço/VNU", pd.Series(dtype=str)).map(_is_concrete_price)
    ].copy()
    if not concrete.empty:
        concrete["_date"] = pd.to_datetime(
            concrete.get("Data"), format="%d/%m/%Y", errors="coerce"
        )
        concrete["_type_priority"] = (
            concrete.get("Tipo", pd.Series("", index=concrete.index))
            .map(_fold)
            .map(lambda value: 0 if "SENIOR" in value else 1 if "MEZ" in value else 2)
        )
        concrete = concrete.sort_values(
            ["_date", "_type_priority"],
            ascending=[False, True],
            na_position="last",
            kind="stable",
        )
        selected_date = concrete.iloc[0]["_date"]
        selected = (
            concrete[concrete["_date"].eq(selected_date)]
            if pd.notna(selected_date)
            else concrete.head(1)
        )
        price_values = sorted(
            {
                value
                for value in selected["Preço/VNU"].map(_parse_brl)
                if value is not None
            }
        )
        price_scalar = price_values[0] if len(price_values) == 1 else None
        price_display = _unique_join(selected["Preço/VNU"].tolist(), separator=" / ")
        price_classes = _unique_join(selected["Classe/Série"].tolist(), separator=" / ")
        price_sources = _unique_join(selected["Fonte"].tolist())
        price_date = (
            selected_date.strftime("%d/%m/%Y")
            if pd.notna(selected_date)
            else _text(selected.iloc[0].get("Data")) or "N/D"
        )
    else:
        price_scalar = None
        price_display = "N/D"
        price_classes = "N/D"
        price_sources = "N/D"
        price_date = "N/D"

    if not emissions.empty:
        emission_dates = pd.to_datetime(
            emissions.get("Data"), format="%d/%m/%Y", errors="coerce"
        )
        if emission_dates.notna().any():
            latest_emission_date = emission_dates.max()
            latest_emission_rows = emissions.loc[emission_dates.eq(latest_emission_date)]
            emission_date = latest_emission_date.strftime("%d/%m/%Y")
            emission_source = _unique_join(latest_emission_rows["Fonte"].tolist()) or "N/D"
        else:
            emission_date = _text(emissions.iloc[-1].get("Data")) or "N/D"
            emission_source = _text(emissions.iloc[-1].get("Fonte")) or "N/D"
    else:
        emission_date = "N/D"
        emission_source = "N/D"

    documentary_text = " ".join(
        threshold_combined.tolist()
        + (
            emissions.apply(
                lambda row: _row_text(row, "Classe/Série", "Tipo", "Fonte"),
                axis=1,
            ).tolist()
            if not emissions.empty
            else []
        )
    )
    has_mezzanine = bool(re.search(r"\bMEZ(?:ANINO|ZANINO|Z)?\b", _fold(documentary_text)))
    mezzanine_sources = []
    if has_mezzanine:
        if not subordinate.empty:
            mezzanine_sources.extend(
                subordinate.loc[
                    subordinate["_combined"].map(_fold).str.contains("MEZ", na=False),
                    "Fonte",
                ].tolist()
            )
        if not emissions.empty:
            mezzanine_sources.extend(
                emissions.loc[
                    emissions.apply(
                        lambda row: "MEZ" in _fold(
                            _row_text(row, "Classe/Série", "Tipo")
                        ),
                        axis=1,
                    ),
                    "Fonte",
                ].tolist()
            )

    event_mask = threshold_combined.map(_fold).str.contains(
        r"VENCIMENTO ANTECIPADO|EVENTO DE AVALIACAO|EVENTO DE LIQUIDACAO|ACELERACAO",
        regex=True,
        na=False,
    )
    event_rows = thresholds.loc[event_mask].copy()
    event_texts = [
        f"{_text(row.get('Critério') or row.get('Evento'))}: {_text(row.get('Limite'))}"
        for _, row in event_rows.iterrows()
        if _text(row.get("Critério") or row.get("Evento")) or _text(row.get("Limite"))
    ]
    event_sources = [
        _text(row.get("Fonte"))
        for _, row in event_rows.iterrows()
        if _text(row.get("Fonte"))
    ]

    has_threshold = not subordinate.empty
    has_emission = not emissions.empty
    if has_threshold and has_emission:
        package_status = "Curadoria documental disponível"
    elif has_threshold or has_emission:
        package_status = "Curadoria documental parcial"
    else:
        package_status = "Pacote localizado; CNPJ sem linhas curadas"

    return {
        "pacote_documental_status": package_status,
        "subordinacao_minima_junior_pct": junior_scalar,
        "subordinacao_minima_junior_display": junior_display,
        "subordinacao_minima_texto": _unique_join(threshold_texts)
        or "N/D — mínimo de subordinação não localizado no pacote",
        "subordinacao_minima_fonte": _unique_join(threshold_sources) or "N/D",
        "preco_emissao_brl": price_scalar,
        "preco_emissao_display": price_display,
        "preco_emissao_classe": price_classes,
        "preco_emissao_data": price_date,
        "preco_emissao_fonte": price_sources,
        "emissao_data": emission_date,
        "emissao_data_display": _month_year_display(emission_date),
        "emissao_fonte": emission_source,
        "cota_mezanino": "Sim" if has_mezzanine else "N/D",
        "cota_mezanino_fonte": _unique_join(mezzanine_sources) or "N/D",
        "vencimento_antecipado": _unique_join(event_texts)
        or "N/D — condição não localizada no pacote",
        "vencimento_antecipado_fonte": _unique_join(event_sources) or "N/D",
    }


def _range_label(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "N/D"
    pct = value * 100.0
    if pct < 10:
        return "< 10%"
    if pct < 15:
        return "10%–15%"
    if pct < 20:
        return "15%–20%"
    if pct < 35:
        return "20%–35%"
    if pct < 60:
        return "35%–60%"
    return "≥ 60%"


def _compact_values(values: list[str], *, limit: int = 2) -> str:
    unique = [value for value in dict.fromkeys(values) if value and value != "N/D"]
    if not unique:
        return "N/D"
    if len(unique) <= limit:
        return " / ".join(unique)
    return f"{len(unique)} valores; ver aba"


def build_flagship_curation(
    *,
    scope_path: Path,
    funds: pd.DataFrame,
    vehicle: pd.DataFrame,
    latest: str,
    deep_dives_dir: Path,
    documentary_path: Path | None = None,
) -> FlagshipCurationResult:
    """Build CNPJ detail and family comparison from published project sources."""

    scope = pd.read_csv(scope_path, dtype={"cnpj_fundo": str}, keep_default_na=False)
    required = {
        "ordem_categoria",
        "categoria",
        "ordem_familia",
        "familia_flagship",
        "cnpj_fundo",
        "representante_familia",
        "pacote_documental",
    }
    missing = sorted(required.difference(scope.columns))
    if missing:
        raise ValueError("escopo flagship sem campos: " + ", ".join(missing))
    scope["cnpj_fundo"] = scope["cnpj_fundo"].map(_digits)
    if scope["cnpj_fundo"].eq("").any() or scope["cnpj_fundo"].duplicated().any():
        raise ValueError("escopo flagship contém CNPJ vazio ou duplicado")
    representative_counts = scope.groupby("ordem_familia")[
        "representante_familia"
    ].apply(lambda values: pd.to_numeric(values, errors="coerce").fillna(0).eq(1).sum())
    if not representative_counts.eq(1).all():
        raise ValueError("cada família flagship deve ter exatamente um representante")

    current_funds = funds[funds["competencia"].astype(str).eq(latest)].copy()
    current_funds["cnpj_fundo"] = current_funds["cnpj_fundo"].map(_digits)
    current_funds = current_funds.drop_duplicates("cnpj_fundo", keep="last")
    current_funds["pl_atual_brl"] = pd.to_numeric(
        current_funds.get("pl"), errors="coerce"
    )
    current_funds = current_funds[
        ["cnpj_fundo", "denominacao", "pl_atual_brl"]
    ]

    current_vehicle = vehicle[vehicle["competencia"].astype(str).eq(latest)].copy()
    current_vehicle["cnpj_fundo"] = current_vehicle.get(
        "cnpj_fundo", current_vehicle.get("cnpj")
    ).map(_digits)
    current_vehicle["cnpj_fundo"] = current_vehicle["cnpj_fundo"].where(
        current_vehicle["cnpj_fundo"].ne(""),
        current_vehicle.get("cnpj", pd.Series("", index=current_vehicle.index)).map(_digits),
    )
    quota = (
        current_vehicle.groupby("cnpj_fundo")[
            ["vl_cotas_total", "vl_cotas_subordinadas"]
        ]
        .sum(min_count=1)
        .reset_index()
        .rename(
            columns={
                "vl_cotas_total": "pl_classes_reportadas_brl",
                "vl_cotas_subordinadas": "pl_subordinado_atual_brl",
            }
        )
    )

    detail = (
        scope.merge(current_funds, on="cnpj_fundo", how="left", validate="one_to_one")
        .merge(quota, on="cnpj_fundo", how="left", validate="one_to_one")
    )
    detail["cnpj_fundo_formatado"] = detail["cnpj_fundo"].map(_format_cnpj)
    detail["fundosnet_url"] = FUNDOSNET_CNPJ_BASE + detail["cnpj_fundo"]
    detail["pl_reconciliacao_delta_pct"] = (
        (
            detail["pl_classes_reportadas_brl"]
            - detail["pl_atual_brl"]
        ).abs()
        / detail["pl_atual_brl"]
        * 100.0
    ).where(detail["pl_atual_brl"].gt(0))
    detail["subordinacao_atual_pct"] = (
        detail["pl_subordinado_atual_brl"] / detail["pl_atual_brl"]
    ).where(
        detail["pl_atual_brl"].gt(0)
        & detail["pl_classes_reportadas_brl"].gt(0)
        & detail["pl_reconciliacao_delta_pct"].le(
            PL_RECONCILIATION_WARNING_PCT
        )
    )
    detail["subordinacao_atual_status"] = np.select(
        [
            detail["pl_atual_brl"].isna() | detail["pl_atual_brl"].le(0),
            detail["pl_classes_reportadas_brl"].isna()
            | detail["pl_classes_reportadas_brl"].le(0),
            detail["pl_reconciliacao_delta_pct"].gt(
                PL_RECONCILIATION_WARNING_PCT
            ),
        ],
        [
            f"PL oficial ausente em {latest}",
            f"classes de cotas ausentes em {latest}",
            "N/D — PL oficial diverge das classes acima de 0,5%",
        ],
        default="Calculado com classes reportadas e PL oficial reconciliado",
    )

    document_rows: list[dict[str, object]] = []
    for row in detail.to_dict("records"):
        package_name = _text(row.get("pacote_documental"))
        package_dir = deep_dives_dir / package_name if package_name else None
        if package_dir is not None and not (package_dir / "manifest.json").exists():
            raise FileNotFoundError(
                f"pacote documental flagship não encontrado: {package_dir}"
            )
        document_rows.append(
            _document_fields(
                package_dir=package_dir,
                cnpj=str(row["cnpj_fundo"]),
            )
        )
    detail = pd.concat(
        [detail.reset_index(drop=True), pd.DataFrame(document_rows)],
        axis=1,
    )
    if documentary_path is not None:
        documentary = pd.read_csv(
            documentary_path,
            dtype={"cnpj_fundo": str},
            keep_default_na=False,
        )
        missing = sorted(
            {"cnpj_fundo", *FLAGSHIP_DOCUMENTARY_FIELDS}.difference(
                documentary.columns
            )
        )
        if missing:
            raise ValueError(
                "curadoria documental flagship sem campos: " + ", ".join(missing)
            )
        documentary["cnpj_fundo"] = documentary["cnpj_fundo"].map(_digits)
        if (
            documentary["cnpj_fundo"].eq("").any()
            or documentary["cnpj_fundo"].duplicated().any()
        ):
            raise ValueError(
                "curadoria documental flagship contém CNPJ vazio ou duplicado"
            )
        expected_cnpjs = set(detail["cnpj_fundo"])
        documentary_cnpjs = set(documentary["cnpj_fundo"])
        if documentary_cnpjs != expected_cnpjs:
            missing_cnpjs = sorted(expected_cnpjs - documentary_cnpjs)
            extra_cnpjs = sorted(documentary_cnpjs - expected_cnpjs)
            raise ValueError(
                "curadoria documental flagship não fecha o escopo: "
                f"ausentes={missing_cnpjs}; extras={extra_cnpjs}"
            )
        documentary["subordinacao_minima_junior_pct"] = pd.to_numeric(
            documentary["subordinacao_minima_junior_pct"], errors="coerce"
        )
        manual_columns = ["cnpj_fundo", *FLAGSHIP_DOCUMENTARY_FIELDS]
        detail = detail.merge(
            documentary[manual_columns],
            on="cnpj_fundo",
            how="left",
            validate="one_to_one",
            suffixes=("", "_documental"),
        )
        # A leitura integral versionada é a autoridade para o mínimo júnior.
        # Os demais campos dos pacotes (emissão, mezanino e eventos) continuam
        # preservados e rastreáveis na mesma linha.
        for column in (
            "subordinacao_minima_junior_pct",
            "subordinacao_minima_junior_display",
            "subordinacao_minima_texto",
            "subordinacao_minima_fonte",
        ):
            detail[column] = detail.pop(f"{column}_documental")
    else:
        detail["documento_id_regulamento"] = "N/D"
        detail["documento_data_regulamento"] = "N/D"
        detail["pagina_clausula"] = "N/D"
        detail["paginas_lidas"] = "N/D"
        detail["status_curadoria_documental"] = (
            "N/D — leitura integral não versionada"
        )
        detail["observacao_documental"] = (
            "N/D — arquivo de curadoria documental não informado"
        )
    detail["pacote_documental_path"] = detail["pacote_documental"].map(
        lambda value: (
            f"data/deep_dives/{_text(value)}/manifest.json"
            if _text(value)
            else "N/D"
        )
    )
    detail["faixa_subordinacao_atual"] = detail["subordinacao_atual_pct"].map(
        lambda value: _range_label(float(value)) if pd.notna(value) else "N/D"
    )
    detail["lacunas"] = detail.apply(
        lambda row: _unique_join(
            [
                label
                for condition, label in (
                    (
                        pd.isna(row.get("subordinacao_atual_pct")),
                        "subordinação atual não calculável",
                    ),
                    (
                        _text(row.get("subordinacao_minima_junior_display")) == "N/D",
                        "mínimo júnior não localizado",
                    ),
                    (
                        _text(row.get("preco_emissao_display")) == "N/D",
                        "preço/VNU não localizado",
                    ),
                    (
                        _text(row.get("cota_mezanino")) == "N/D",
                        "existência de mezanino não comprovada",
                    ),
                    (
                        _text(row.get("vencimento_antecipado")).startswith("N/D"),
                        "vencimento antecipado não localizado",
                    ),
                )
                if condition
            ],
            separator="; ",
        )
        or "Sem lacunas nos campos prioritários",
        axis=1,
    )

    family_rows: list[dict[str, object]] = []
    for (order, category, family), group in detail.groupby(
        ["ordem_familia", "categoria", "familia_flagship"],
        sort=True,
    ):
        pl = pd.to_numeric(group["pl_atual_brl"], errors="coerce").sum(min_count=1)
        subordinate = pd.to_numeric(
            group["pl_subordinado_atual_brl"], errors="coerce"
        ).sum(min_count=1)
        current_ratio = (
            float(subordinate / pl)
            if pd.notna(pl) and float(pl) > 0 and group["subordinacao_atual_pct"].notna().all()
            else None
        )
        representative = group[
            pd.to_numeric(group["representante_familia"], errors="coerce").eq(1)
        ].iloc[0]
        junior_displays = [
            _text(value)
            for value in group["subordinacao_minima_junior_display"]
            if _text(value) != "N/D"
        ]
        price_displays = [
            _text(value)
            for value in group["preco_emissao_display"]
            if _text(value) != "N/D"
        ]
        family_rows.append(
            {
                "ordem_familia": int(order),
                "ordem_categoria": int(group["ordem_categoria"].iloc[0]),
                "categoria": category,
                "familia_flagship": family,
                "cnpjs": "; ".join(group["cnpj_fundo_formatado"].tolist()),
                "fundos": int(len(group)),
                "pl_atual_brl": float(pl) if pd.notna(pl) else None,
                "pl_subordinado_atual_brl": (
                    float(subordinate) if pd.notna(subordinate) else None
                ),
                "subordinacao_atual_pct": current_ratio,
                "faixa_subordinacao_atual": _range_label(current_ratio),
                "subordinacao_minima_junior_display": _compact_values(
                    junior_displays
                ),
                "preco_emissao_display": _compact_values(price_displays),
                "emissao_data": representative["emissao_data"],
                "emissao_data_display": representative["emissao_data_display"],
                "emissao_fonte": representative["emissao_fonte"],
                "cota_mezanino": (
                    "Sim" if group["cota_mezanino"].eq("Sim").any() else "N/D"
                ),
                "cnpjs_com_pacote_documental": int(
                    group["pacote_documental"].map(_text).ne("").sum()
                ),
                "cnpjs_com_minimo_junior": int(
                    group["subordinacao_minima_junior_display"].ne("N/D").sum()
                ),
                "cnpjs_com_preco_vnu": int(
                    group["preco_emissao_display"].ne("N/D").sum()
                ),
                "cnpjs_com_evento": int(
                    (~group["vencimento_antecipado"].str.startswith("N/D")).sum()
                ),
                "representante_cnpj": representative["cnpj_fundo_formatado"],
                "representante_fundo": representative["denominacao"],
                "status_curadoria": (
                    f"{int(group['pacote_documental'].map(_text).ne('').sum())}/"
                    f"{len(group)} CNPJs com pacote documental"
                ),
            }
        )
    families = pd.DataFrame(family_rows).sort_values("ordem_familia").reset_index(
        drop=True
    )

    summary = {
        "competencia": latest,
        "familias": int(len(families)),
        "cnpjs": int(len(detail)),
        "cnpjs_com_pl_atual": int(detail["pl_atual_brl"].notna().sum()),
        "cnpjs_com_subordinacao_atual": int(
            detail["subordinacao_atual_pct"].notna().sum()
        ),
        "cnpjs_com_pacote_documental": int(
            detail["pacote_documental"].map(_text).ne("").sum()
        ),
        "cnpjs_com_regulamento_lido": int(
            detail["status_curadoria_documental"]
            .map(_fold)
            .str.startswith("REVISTO")
            .sum()
        ),
        "cnpjs_com_minimo_junior": int(
            detail["subordinacao_minima_junior_display"].ne("N/D").sum()
        ),
        "cnpjs_com_preco_vnu": int(
            detail["preco_emissao_display"].ne("N/D").sum()
        ),
        "cnpjs_com_data_emissao": int(detail["emissao_data"].ne("N/D").sum()),
        "cnpjs_com_mezanino_comprovado": int(detail["cota_mezanino"].eq("Sim").sum()),
        "cnpjs_com_evento": int(
            (~detail["vencimento_antecipado"].str.startswith("N/D")).sum()
        ),
        "fonte_pl_subordinacao": (
            f"CVM, Informe Mensal FIDC, competência {latest}; PL oficial e "
            "classes de cotas reconciliados com tolerância de 0,5%"
        ),
        "fonte_documental": (
            "curadoria integral versionada em "
            "data/industry_study/industry_flagship_document_curation.csv; "
            "pacotes em data/deep_dives preservam emissões, séries e eventos"
        ),
        "metodologia": (
            "uma linha por CNPJ da shortlist aprovada; família agrega PL e "
            "subordinação atual ponderada. Mínimo júnior e VNU permanecem "
            "textuais quando há múltiplos valores ou condição temporal"
        ),
    }
    return FlagshipCurationResult(
        detail=detail.sort_values(
            ["ordem_familia", "representante_familia", "pl_atual_brl"],
            ascending=[True, False, False],
            na_position="last",
        ).reset_index(drop=True),
        families=families,
        summary=summary,
    )


def _flagship_reference(row: pd.Series) -> tuple[str, str]:
    """Map only direct, auditable correspondences to the approved flagship set."""

    cnpj = _digits(row.get("cnpj_fundo"))
    direct = {
        "54810968000102": "Consignado FGTS",
        "53270983000142": "Consignado FGTS",
        "53577135000180": "Consignado FGTS",
        "54252144000164": "Consignado FGTS",
        "55401645000128": "Consignado FGTS",
        "54464892000100": "Consignado FGTS",
        "44173467000109": "Consignado INSS",
        "62588266000154": "Consignado INSS",
        "65976848000104": "Consignado INSS",
        "63546406000194": "Consignado INSS",
        "65347578000164": "Consignado INSS",
        "44124617000194": "Adquirência — banco emissor",
        "42085816000105": "Adquirência — banco emissor",
        "42102603000144": "Adquirência — banco emissor",
        "42085830000109": "Adquirência — banco emissor",
        "28169275000172": "Adquirência — risco adquirente",
        "50473039000102": "Adquirência — risco adquirente",
        "35868110000154": "Veículos",
    }
    if cnpj in direct:
        return direct[cnpj], "correspondência direta por CNPJ e família aprovada"
    if (
        _text(row.get("status_taxonomia")) == "aprovado"
        and _fold(row.get("foco_analitico")) == "FOMENTO MERCANTIL"
    ):
        return "Factoring", "correspondência por classificação analítica aprovada"
    return "N/D — sem família flagship equivalente", "nenhuma correspondência direta aprovada"


def build_portfolio_curation(
    *,
    scope_path: Path,
    documentary_path: Path,
    funds: pd.DataFrame,
    vehicle: pd.DataFrame,
    taxonomy_actions: pd.DataFrame,
    latest: str,
) -> PortfolioCurationResult:
    """Build the saved Carteira 1 comparison without filling source gaps."""

    scope = pd.read_csv(scope_path, dtype=str, keep_default_na=False)
    required_scope = {
        "ordem",
        "imagem",
        "raiz_cnpj_foto",
        "nome_foto",
        "cnpj_fundo",
        "status_identidade",
        "regra_identidade",
        "observacao_identidade",
    }
    missing_scope = sorted(required_scope.difference(scope.columns))
    if missing_scope:
        raise ValueError("escopo Carteira 1 sem campos: " + ", ".join(missing_scope))
    scope["cnpj_fundo"] = scope["cnpj_fundo"].map(_digits)
    scope["ordem"] = pd.to_numeric(scope["ordem"], errors="raise").astype(int)
    if len(scope) != 101 or scope["cnpj_fundo"].nunique() != 101:
        raise ValueError("escopo Carteira 1 deve conter 101 CNPJs únicos")
    if scope["ordem"].tolist() != list(range(1, 102)):
        raise ValueError("escopo Carteira 1 deve preservar a ordem 1–101 das imagens")

    documentary = pd.read_csv(documentary_path, dtype=str, keep_default_na=False)
    required_documentary = {
        "cnpj_fundo",
        "documento_id_regulamento",
        "documento_data_regulamento",
        "pagina_clausula",
        "subordinacao_minima_junior_pct",
        "subordinacao_minima_junior_display",
        "subordinacao_minima_texto",
        "subordinacao_minima_fonte",
        "emissao_data",
        "emissao_data_display",
        "emissao_fonte",
        "paginas_lidas",
        "status_curadoria_documental",
        "observacao_documental",
    }
    missing_documentary = sorted(required_documentary.difference(documentary.columns))
    if missing_documentary:
        raise ValueError(
            "curadoria documental Carteira 1 sem campos: "
            + ", ".join(missing_documentary)
        )
    documentary["cnpj_fundo"] = documentary["cnpj_fundo"].map(_digits)
    if documentary["cnpj_fundo"].duplicated().any():
        raise ValueError("curadoria documental Carteira 1 contém CNPJ duplicado")
    if set(documentary["cnpj_fundo"]) != set(scope["cnpj_fundo"]):
        raise ValueError("curadoria documental Carteira 1 não cobre exatamente o escopo")

    fund_history = funds.copy()
    fund_history["cnpj_fundo"] = fund_history["cnpj_fundo"].map(_digits)
    fund_history = fund_history.sort_values("competencia", kind="stable")
    identity_columns = ["cnpj_fundo", "denominacao", "competencia"]
    for column in ("classificacao_anbima", "anbima_tipo", "anbima_foco"):
        if column in fund_history.columns:
            identity_columns.append(column)
    latest_identity = fund_history.drop_duplicates("cnpj_fundo", keep="last")[
        identity_columns
    ].rename(columns={"competencia": "competencia_classificacao"})

    current_funds = fund_history[
        fund_history["competencia"].astype(str).eq(latest)
    ].copy()
    current_funds = current_funds.drop_duplicates("cnpj_fundo", keep="last")
    current_funds["pl_atual_brl"] = pd.to_numeric(
        current_funds.get("pl"), errors="coerce"
    )
    current_funds = current_funds[["cnpj_fundo", "pl_atual_brl"]]

    current_vehicle = vehicle[vehicle["competencia"].astype(str).eq(latest)].copy()
    current_vehicle["cnpj_fundo"] = current_vehicle.get(
        "cnpj_fundo", current_vehicle.get("cnpj")
    ).map(_digits)
    current_vehicle["cnpj_fundo"] = current_vehicle["cnpj_fundo"].where(
        current_vehicle["cnpj_fundo"].ne(""),
        current_vehicle.get("cnpj", pd.Series("", index=current_vehicle.index)).map(_digits),
    )
    quota = (
        current_vehicle.groupby("cnpj_fundo")[
            ["vl_cotas_total", "vl_cotas_subordinadas"]
        ]
        .sum(min_count=1)
        .reset_index()
        .rename(
            columns={
                "vl_cotas_total": "pl_classes_reportadas_brl",
                "vl_cotas_subordinadas": "pl_subordinado_atual_brl",
            }
        )
    )

    actions = taxonomy_actions.copy()
    if not actions.empty:
        actions["cnpj_fundo"] = actions["cnpj_fundo"].map(_digits)
        actions = actions[actions.get("status", "").astype(str).eq("aprovado")]
        actions = actions.sort_values("updated_at_utc", kind="stable").drop_duplicates(
            "cnpj_fundo", keep="last"
        )
        action_columns = [
            "cnpj_fundo",
            "status",
            "tipo_analitico",
            "foco_analitico",
            "taxonomia_funcional_n1",
            "taxonomia_funcional_n2",
            "fonte_documental",
            "confianca",
        ]
        actions = actions[[column for column in action_columns if column in actions.columns]].rename(
            columns={"status": "status_taxonomia", "fonte_documental": "fonte_taxonomia"}
        )

    detail = (
        scope.merge(latest_identity, on="cnpj_fundo", how="left", validate="one_to_one")
        .merge(current_funds, on="cnpj_fundo", how="left", validate="one_to_one")
        .merge(quota, on="cnpj_fundo", how="left", validate="one_to_one")
        .merge(documentary, on="cnpj_fundo", how="left", validate="one_to_one")
    )
    if not actions.empty:
        detail = detail.merge(actions, on="cnpj_fundo", how="left", validate="one_to_one")
    detail["denominacao"] = detail["denominacao"].where(
        detail["denominacao"].map(_text).ne(""), detail["nome_foto"]
    )
    detail["cnpj_fundo_formatado"] = detail["cnpj_fundo"].map(_format_cnpj)
    detail["fundosnet_url"] = FUNDOSNET_CNPJ_BASE + detail["cnpj_fundo"]
    detail["pl_reconciliacao_delta_pct"] = (
        (detail["pl_classes_reportadas_brl"] - detail["pl_atual_brl"]).abs()
        / detail["pl_atual_brl"]
        * 100.0
    ).where(detail["pl_atual_brl"].gt(0))
    detail["subordinacao_atual_pct"] = (
        detail["pl_subordinado_atual_brl"] / detail["pl_atual_brl"]
    ).where(
        detail["pl_atual_brl"].gt(0)
        & detail["pl_classes_reportadas_brl"].gt(0)
        & detail["pl_reconciliacao_delta_pct"].le(PL_RECONCILIATION_WARNING_PCT)
    )
    detail["subordinacao_atual_status"] = np.select(
        [
            detail["pl_atual_brl"].isna() | detail["pl_atual_brl"].le(0),
            detail["pl_classes_reportadas_brl"].isna()
            | detail["pl_classes_reportadas_brl"].le(0),
            detail["pl_reconciliacao_delta_pct"].gt(PL_RECONCILIATION_WARNING_PCT),
        ],
        [
            f"PL oficial ausente em {latest}",
            f"classes de cotas ausentes em {latest}",
            "N/D — PL oficial diverge das classes acima de 0,5%",
        ],
        default="Calculado com classes reportadas e PL oficial reconciliado",
    )
    detail["subordinacao_minima_junior_pct"] = pd.to_numeric(
        detail["subordinacao_minima_junior_pct"], errors="coerce"
    )
    detail["faixa_subordinacao_atual"] = detail["subordinacao_atual_pct"].map(
        lambda value: _range_label(float(value)) if pd.notna(value) else "N/D"
    )
    analytical = detail.get("tipo_analitico", pd.Series("", index=detail.index)).map(_text)
    official = detail.get("anbima_tipo", pd.Series("", index=detail.index)).map(_text)
    official = official.where(
        official.ne(""),
        detail.get("classificacao_anbima", pd.Series("", index=detail.index)).map(_text),
    )
    detail["tipo_exibicao"] = analytical.where(analytical.ne(""), official).replace("", "N/D")
    analytical_focus = detail.get("foco_analitico", pd.Series("", index=detail.index)).map(_text)
    official_focus = detail.get("anbima_foco", pd.Series("", index=detail.index)).map(_text)
    detail["foco_exibicao"] = analytical_focus.where(
        analytical_focus.ne(""), official_focus
    ).replace("", "N/D")
    detail["classificacao_fonte"] = np.where(
        analytical.ne(""),
        "taxonomia analítica aprovada",
        np.where(
            official.ne(""),
            "classificação oficial ANBIMA · competência "
            + detail["competencia_classificacao"].map(_text),
            "N/D",
        ),
    )
    references = detail.apply(_flagship_reference, axis=1)
    detail["familia_flagship_referencia"] = [item[0] for item in references]
    detail["familia_flagship_regra"] = [item[1] for item in references]
    detail["lacunas"] = detail.apply(
        lambda row: _unique_join(
            [
                label
                for condition, label in (
                    (pd.isna(row.get("pl_atual_brl")), "PL atual ausente"),
                    (pd.isna(row.get("subordinacao_atual_pct")), "subordinação atual não calculável"),
                    (_text(row.get("subordinacao_minima_junior_display")) == "N/D", "mínimo júnior não localizado"),
                    (_text(row.get("emissao_data_display")) == "N/D", "data de emissão não localizada"),
                    (_text(row.get("tipo_exibicao")) == "N/D", "tipo não localizado"),
                )
                if condition
            ],
            separator="; ",
        )
        or "Sem lacunas nos campos do slide",
        axis=1,
    )

    range_order = {label: index for index, label in enumerate(
        ("< 10%", "10%–15%", "15%–20%", "20%–35%", "35%–60%", "≥ 60%", "N/D")
    )}
    range_rows: list[dict[str, object]] = []
    for label, group in detail.groupby("faixa_subordinacao_atual", sort=False):
        type_counts = group["tipo_exibicao"].value_counts()
        type_summary = " · ".join(
            f"{name} {int(count)}" for name, count in type_counts.head(4).items()
        )
        if len(type_counts) > 4:
            type_summary += f" · +{int(type_counts.iloc[4:].sum())} outros"
        pl = pd.to_numeric(group["pl_atual_brl"], errors="coerce").sum(min_count=1)
        range_rows.append(
            {
                "ordem_faixa": range_order.get(str(label), 99),
                "faixa_subordinacao_atual": str(label),
                "fundos": int(len(group)),
                "fundos_com_pl": int(group["pl_atual_brl"].notna().sum()),
                "pl_atual_brl": float(pl) if pd.notna(pl) else None,
                "tipos": int(type_counts.size),
                "tipos_resumo": type_summary or "N/D",
            }
        )
    ranges = pd.DataFrame(range_rows).sort_values("ordem_faixa").reset_index(drop=True)
    summary = {
        "carteira": "Carteira 1",
        "competencia": latest,
        "cnpjs": int(len(detail)),
        "cnpjs_localizados_base_fidc": int(detail["pl_atual_brl"].notna().sum()),
        "cnpjs_fora_base_fidc": int(scope["status_identidade"].eq("fora_base_fidc").sum()),
        "cnpjs_com_subordinacao_atual": int(detail["subordinacao_atual_pct"].notna().sum()),
        "cnpjs_com_minimo_junior": int(detail["subordinacao_minima_junior_pct"].notna().sum()),
        "cnpjs_com_data_emissao": int(detail["emissao_data_display"].ne("N/D").sum()),
        "cnpjs_com_familia_flagship": int(
            detail["familia_flagship_referencia"].ne("N/D — sem família flagship equivalente").sum()
        ),
        "fonte": (
            f"CVM, Informe Mensal FIDC, {latest}; FundosNet/B3 e curadoria documental "
            "versionada por CNPJ"
        ),
    }
    return PortfolioCurationResult(
        detail=detail.sort_values("ordem").reset_index(drop=True),
        ranges=ranges,
        summary=summary,
    )
