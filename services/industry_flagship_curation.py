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
FUNDOSNET_CNPJ_BASE = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/"
    "abrirGerenciadorDocumentosCVM?cnpjFundo="
)


@dataclass(frozen=True)
class FlagshipCurationResult:
    detail: pd.DataFrame
    families: pd.DataFrame
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
        "cnpjs_com_minimo_junior": int(
            detail["subordinacao_minima_junior_display"].ne("N/D").sum()
        ),
        "cnpjs_com_preco_vnu": int(
            detail["preco_emissao_display"].ne("N/D").sum()
        ),
        "cnpjs_com_mezanino_comprovado": int(detail["cota_mezanino"].eq("Sim").sum()),
        "cnpjs_com_evento": int(
            (~detail["vencimento_antecipado"].str.startswith("N/D")).sum()
        ),
        "fonte_pl_subordinacao": (
            f"CVM, Informe Mensal FIDC, competência {latest}; PL oficial e "
            "classes de cotas reconciliados com tolerância de 0,5%"
        ),
        "fonte_documental": (
            "pacotes versionados em data/deep_dives; regulamentos, emissões e "
            "assembleias CVM/Fundos.NET identificados em cada linha"
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
