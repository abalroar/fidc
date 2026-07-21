"""Point-in-time provider history for the current FIDC cohort.

The CVM ``cad_fi_hist.zip`` resource exposes dated administrator, manager and
custodian records.  This module keeps the historical legal entity identifier
as the primary provider key, resolves the records active on two reference
dates and weights every transition with the fund's latest-period PL.

The official resource is labelled by the CVM as the historical register for
ICVM 555 funds.  FIDC coverage is therefore measured explicitly and no missing
fund is backfilled with a current provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Iterable, Mapping
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd

from services.industry_intelligence import canonical_provider


CAD_FI_HISTORY_URL = (
    "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip"
)
CAD_FI_DATASET_URL = "https://dados.cvm.gov.br/dataset/fi-cad"
DEFAULT_LATEST_COMPETENCE = "2026-05"
DEFAULT_FROM_DATE = "2024-12-31"
DEFAULT_TO_DATE = "2026-05-31"
DEFAULT_EXCLUDED_FUND_CNPJS: tuple[str, ...] = (
    "09195235000150",  # FIDC Sistema Petrobras
    "26287464000114",  # FIDC TAPSO
)
SOURCE_SCOPE_NOTE = (
    "Recurso histórico do cadastro CVM identificado no portal como ICVM 555; "
    "a cobertura observada na coorte de FIDCs é reportada e não extrapolada."
)


@dataclass(frozen=True)
class RoleSpec:
    archive_name: str
    provider_id_column: str
    provider_name_column: str
    start_column: str
    end_column: str
    person_type_column: str = ""


ROLE_SPECS: Mapping[str, RoleSpec] = {
    "administrador": RoleSpec(
        archive_name="cad_fi_hist_admin.csv",
        provider_id_column="CNPJ_ADMIN",
        provider_name_column="ADMIN",
        start_column="DT_INI_ADMIN",
        end_column="DT_FIM_ADMIN",
    ),
    "gestor": RoleSpec(
        archive_name="cad_fi_hist_gestor.csv",
        provider_id_column="CPF_CNPJ_GESTOR",
        provider_name_column="GESTOR",
        start_column="DT_INI_GESTOR",
        end_column="DT_FIM_GESTOR",
        person_type_column="PF_PJ_GESTOR",
    ),
    "custodiante": RoleSpec(
        archive_name="cad_fi_hist_custodiante.csv",
        provider_id_column="CNPJ_CUSTODIANTE",
        provider_name_column="CUSTODIANTE",
        start_column="DT_INI_CUSTODIANTE",
        end_column="DT_FIM_CUSTODIANTE",
    ),
}


@dataclass(frozen=True)
class ProviderHistoryOutputs:
    snapshot: pd.DataFrame
    detail: pd.DataFrame
    links: pd.DataFrame
    coverage: pd.DataFrame
    checks: Mapping[str, object]


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return "" if text.lower() in {"", "nan", "none", "nat", "n/d"} else text


def _digits(value: object) -> str:
    return re.sub(r"\D", "", _clean(value))


def _fund_cnpj(value: object) -> str:
    digits = _digits(value)
    if 0 < len(digits) < 14:
        digits = digits.zfill(14)
    return digits if len(digits) == 14 else ""


def _provider_legal_id(value: object) -> str:
    """Preserve CPF (11 digits) or CNPJ (14 digits) without false padding."""

    digits = _digits(value)
    return digits if len(digits) in {11, 14} else ""


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.map(_clean).str.upper()
    return normalized.isin({"1", "TRUE", "T", "SIM", "S", "YES", "Y"})


def format_cnpj(value: object) -> str:
    digits = _fund_cnpj(value)
    if not digits:
        return ""
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_provider_history_zip(
    destination: Path,
    *,
    source_url: str = CAD_FI_HISTORY_URL,
    timeout_seconds: int = 120,
) -> Path:
    """Download the official archive atomically."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(source_url, headers={"User-Agent": "fidc-industry-study/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed official URL by default
        payload = response.read()
    if not payload.startswith(b"PK"):
        raise ValueError("resposta do cadastro histórico CVM não é um arquivo ZIP")
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, delete=False, prefix=f".{destination.name}."
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(destination)
    return destination


def read_provider_history_zip(
    archive_path: Path,
    *,
    cohort_cnpjs: Iterable[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Read and standardize the three provider histories from the CVM ZIP."""

    archive_path = Path(archive_path)
    cohort = (
        {_fund_cnpj(value) for value in cohort_cnpjs if _fund_cnpj(value)}
        if cohort_cnpjs is not None
        else None
    )
    histories: dict[str, pd.DataFrame] = {}
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        missing_files = {
            spec.archive_name for spec in ROLE_SPECS.values()
        }.difference(names)
        if missing_files:
            raise ValueError(
                "cad_fi_hist.zip sem arquivos obrigatórios: "
                + ", ".join(sorted(missing_files))
            )
        for role, spec in ROLE_SPECS.items():
            required = [
                "CNPJ_FUNDO",
                spec.provider_id_column,
                spec.provider_name_column,
                spec.start_column,
                spec.end_column,
            ]
            if spec.person_type_column:
                required.append(spec.person_type_column)
            frame = pd.read_csv(
                archive.open(spec.archive_name),
                sep=";",
                encoding="latin1",
                dtype=str,
                usecols=required,
                low_memory=False,
            )
            frame = frame.rename(
                columns={
                    "CNPJ_FUNDO": "cnpj_fundo",
                    spec.provider_id_column: "prestador_id_legal",
                    spec.provider_name_column: "prestador_nome",
                    spec.start_column: "data_inicio",
                    spec.end_column: "data_fim",
                    spec.person_type_column: "tipo_pessoa_prestador",
                }
            )
            if "tipo_pessoa_prestador" not in frame:
                frame["tipo_pessoa_prestador"] = "PJ"
            frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_fund_cnpj)
            frame["prestador_id_legal"] = frame["prestador_id_legal"].map(
                _provider_legal_id
            )
            frame["prestador_nome"] = frame["prestador_nome"].map(_clean)
            frame["tipo_pessoa_prestador"] = frame[
                "tipo_pessoa_prestador"
            ].map(_clean)
            frame["data_inicio"] = pd.to_datetime(
                frame["data_inicio"], errors="coerce"
            )
            frame["data_fim"] = pd.to_datetime(frame["data_fim"], errors="coerce")
            frame = frame.loc[
                frame["cnpj_fundo"].ne("") & frame["data_inicio"].notna()
            ].copy()
            if cohort is not None:
                frame = frame.loc[frame["cnpj_fundo"].isin(cohort)].copy()
            frame["papel"] = role
            frame["arquivo_fonte"] = spec.archive_name
            histories[role] = frame[
                [
                    "papel",
                    "cnpj_fundo",
                    "prestador_id_legal",
                    "prestador_nome",
                    "tipo_pessoa_prestador",
                    "data_inicio",
                    "data_fim",
                    "arquivo_fonte",
                ]
            ].reset_index(drop=True)
    return histories


def _ownership_rules(ownership_curation: pd.DataFrame | None) -> list[tuple[re.Pattern[str], str]]:
    if ownership_curation is None or ownership_curation.empty:
        return []
    required = {"participant_pattern", "normalized_group"}
    missing = required.difference(ownership_curation.columns)
    if missing:
        raise ValueError(
            "curadoria societária sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )
    rules: list[tuple[re.Pattern[str], str]] = []
    for row in ownership_curation.itertuples(index=False):
        pattern = _clean(getattr(row, "participant_pattern"))
        group = _clean(getattr(row, "normalized_group"))
        if not pattern or not group:
            continue
        rules.append((re.compile(pattern), group))
    return rules


def normalize_provider_group(
    provider_name: object,
    ownership_rules: Iterable[tuple[re.Pattern[str], str]] = (),
) -> str:
    """Apply reviewed group aliases first, then the shared canonical rules."""

    name = _clean(provider_name)
    canonical = canonical_provider(name)
    matches = {
        group
        for pattern, group in ownership_rules
        if pattern.search(name) or pattern.search(canonical)
    }
    if len(matches) > 1:
        raise ValueError(f"regras de grupo conflitantes para {name!r}: {sorted(matches)}")
    if matches:
        return next(iter(matches))
    return canonical


def build_current_fund_cohort(
    fund_base: pd.DataFrame,
    *,
    latest_competence: str = DEFAULT_LATEST_COMPETENCE,
    excluded_fund_cnpjs: Iterable[str] = DEFAULT_EXCLUDED_FUND_CNPJS,
) -> pd.DataFrame:
    """Return one positive-PL, ex-FIC legal fund row for the latest period."""

    required = {"competencia", "cnpj_fundo", "pl"}
    missing = required.difference(fund_base.columns)
    if missing:
        raise ValueError(f"base de fundos sem colunas obrigatórias: {sorted(missing)}")
    frame = fund_base.loc[
        fund_base["competencia"].astype(str).str[:7].eq(str(latest_competence)[:7])
    ].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(_fund_cnpj)
    frame["pl_mai26_brl"] = pd.to_numeric(frame["pl"], errors="coerce")
    if "is_fic_fidc" in frame:
        is_fic = _as_bool(frame["is_fic_fidc"])
    else:
        is_fic = pd.Series(False, index=frame.index, dtype=bool)
    excluded = {_fund_cnpj(value) for value in excluded_fund_cnpjs}
    frame = frame.loc[
        frame["cnpj_fundo"].ne("")
        & frame["pl_mai26_brl"].gt(0)
        & ~is_fic
        & ~frame["cnpj_fundo"].isin(excluded)
    ].copy()
    if frame["cnpj_fundo"].duplicated().any():
        duplicated = frame.loc[
            frame["cnpj_fundo"].duplicated(keep=False), "cnpj_fundo"
        ].unique()
        raise ValueError(
            "coorte de mai/26 contém CNPJ de fundo duplicado: "
            + ", ".join(sorted(duplicated)[:10])
        )
    if "denominacao" not in frame:
        frame["denominacao"] = ""
    frame["denominacao"] = frame["denominacao"].map(_clean)
    frame["cnpj_fundo_formatado"] = frame["cnpj_fundo"].map(format_cnpj)
    return frame[
        ["cnpj_fundo", "cnpj_fundo_formatado", "denominacao", "pl_mai26_brl"]
    ].sort_values(["pl_mai26_brl", "cnpj_fundo"], ascending=[False, True]).reset_index(
        drop=True
    )


def _resolved_role_snapshot(
    cohort: pd.DataFrame,
    history: pd.DataFrame,
    *,
    role: str,
    reference_date: str,
    ownership_rules: Iterable[tuple[re.Pattern[str], str]],
) -> pd.DataFrame:
    as_of = pd.Timestamp(reference_date)
    active = history.loc[
        history["data_inicio"].le(as_of)
        & (history["data_fim"].isna() | history["data_fim"].gt(as_of))
    ].copy()
    active["prestador_chave"] = active["prestador_id_legal"].where(
        active["prestador_id_legal"].ne(""),
        "NOME:" + active["prestador_nome"].str.upper(),
    )
    active = active.loc[active["prestador_chave"].ne("NOME:")].copy()
    active["prestador_grupo"] = active["prestador_nome"].map(
        lambda value: normalize_provider_group(value, ownership_rules)
    )
    active = active.sort_values(
        ["cnpj_fundo", "prestador_chave", "data_inicio"],
        ascending=[True, True, False],
    ).drop_duplicates(["cnpj_fundo", "prestador_chave"], keep="first")

    resolved_rows: list[dict[str, object]] = []
    for fund_cnpj, group in active.groupby("cnpj_fundo", sort=False):
        distinct = int(group["prestador_chave"].nunique())
        ordered = group.sort_values(["prestador_grupo", "prestador_nome", "prestador_chave"])
        resolved_rows.append(
            {
                "cnpj_fundo": fund_cnpj,
                "status_resolucao": (
                    "resolvido_unico" if distinct == 1 else "multiplos_registros_ativos"
                ),
                "registros_ativos": int(len(group)),
                "prestadores_distintos": distinct,
                "prestador_chave": " | ".join(ordered["prestador_chave"]),
                "prestador_id_legal": " | ".join(
                    value for value in ordered["prestador_id_legal"] if value
                ),
                "prestador_nome": " | ".join(
                    value for value in ordered["prestador_nome"] if value
                ),
                "prestador_grupo": " | ".join(
                    dict.fromkeys(ordered["prestador_grupo"])
                ),
                "tipo_pessoa_prestador": " | ".join(
                    dict.fromkeys(
                        value for value in ordered["tipo_pessoa_prestador"] if value
                    )
                ),
                "data_inicio_registro": ordered["data_inicio"].min(),
                "data_fim_registro": ordered["data_fim"].max(),
            }
        )
    resolved = pd.DataFrame(resolved_rows)
    snapshot = cohort.merge(resolved, on="cnpj_fundo", how="left", validate="one_to_one")
    snapshot["papel"] = role
    snapshot["data_referencia"] = as_of.strftime("%Y-%m-%d")
    snapshot["competencia_referencia"] = as_of.strftime("%Y-%m")
    snapshot["status_resolucao"] = snapshot["status_resolucao"].fillna(
        "sem_registro_ativo"
    )
    for column in (
        "prestador_chave",
        "prestador_id_legal",
        "prestador_nome",
        "prestador_grupo",
        "tipo_pessoa_prestador",
    ):
        snapshot[column] = snapshot[column].fillna("")
    for column in ("registros_ativos", "prestadores_distintos"):
        snapshot[column] = snapshot[column].fillna(0).astype(int)
    snapshot["fonte_url"] = CAD_FI_HISTORY_URL
    snapshot["escopo_fonte"] = SOURCE_SCOPE_NOTE
    return snapshot


def _coverage_rows(snapshot: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (role, reference_date), group in snapshot.groupby(
        ["papel", "data_referencia"], sort=True
    ):
        total_pl = float(group["pl_mai26_brl"].sum())
        active = group["status_resolucao"].ne("sem_registro_ativo")
        resolved = group["status_resolucao"].eq("resolvido_unico")
        multiple = group["status_resolucao"].eq("multiplos_registros_ativos")
        missing = group["status_resolucao"].eq("sem_registro_ativo")
        rows.append(
            {
                "papel": role,
                "data_referencia": reference_date,
                "fundos_coorte": int(group["cnpj_fundo"].nunique()),
                "pl_coorte_mai26_brl": total_pl,
                "fundos_com_registro_ativo": int(active.sum()),
                "pl_com_registro_ativo_brl": float(
                    group.loc[active, "pl_mai26_brl"].sum()
                ),
                "cobertura_fundos_registro_ativo": float(active.mean()),
                "cobertura_pl_registro_ativo": (
                    float(group.loc[active, "pl_mai26_brl"].sum()) / total_pl
                    if total_pl
                    else float("nan")
                ),
                "fundos_resolvidos_unicos": int(resolved.sum()),
                "pl_resolvido_unico_brl": float(
                    group.loc[resolved, "pl_mai26_brl"].sum()
                ),
                "cobertura_fundos_resolvida": float(resolved.mean()),
                "cobertura_pl_resolvida": (
                    float(group.loc[resolved, "pl_mai26_brl"].sum()) / total_pl
                    if total_pl
                    else float("nan")
                ),
                "fundos_multiplos_registros_ativos": int(multiple.sum()),
                "pl_multiplos_registros_ativos_brl": float(
                    group.loc[multiple, "pl_mai26_brl"].sum()
                ),
                "fundos_sem_registro_ativo": int(missing.sum()),
                "pl_sem_registro_ativo_brl": float(
                    group.loc[missing, "pl_mai26_brl"].sum()
                ),
                "fonte_url": CAD_FI_HISTORY_URL,
                "escopo_fonte": SOURCE_SCOPE_NOTE,
            }
        )
    return rows


def build_provider_history_outputs(
    fund_base: pd.DataFrame,
    histories: Mapping[str, pd.DataFrame],
    *,
    ownership_curation: pd.DataFrame | None = None,
    latest_competence: str = DEFAULT_LATEST_COMPETENCE,
    from_date: str = DEFAULT_FROM_DATE,
    to_date: str = DEFAULT_TO_DATE,
    excluded_fund_cnpjs: Iterable[str] = DEFAULT_EXCLUDED_FUND_CNPJS,
) -> ProviderHistoryOutputs:
    """Build snapshots, PL-weighted transitions, links and coverage checks."""

    missing_roles = set(ROLE_SPECS).difference(histories)
    if missing_roles:
        raise ValueError(f"histórico sem papéis: {sorted(missing_roles)}")
    cohort = build_current_fund_cohort(
        fund_base,
        latest_competence=latest_competence,
        excluded_fund_cnpjs=excluded_fund_cnpjs,
    )
    rules = _ownership_rules(ownership_curation)
    snapshots: list[pd.DataFrame] = []
    for role in ROLE_SPECS:
        for reference_date in (from_date, to_date):
            snapshots.append(
                _resolved_role_snapshot(
                    cohort,
                    histories[role],
                    role=role,
                    reference_date=reference_date,
                    ownership_rules=rules,
                )
            )
    snapshot = pd.concat(snapshots, ignore_index=True)

    detail_rows: list[pd.DataFrame] = []
    link_rows: list[pd.DataFrame] = []
    coverage_rows = _coverage_rows(snapshot)
    for role in ROLE_SPECS:
        common = [
            "cnpj_fundo",
            "cnpj_fundo_formatado",
            "denominacao",
            "pl_mai26_brl",
        ]
        value_columns = [
            "status_resolucao",
            "prestador_chave",
            "prestador_id_legal",
            "prestador_nome",
            "prestador_grupo",
            "registros_ativos",
            "prestadores_distintos",
        ]
        old = snapshot.loc[
            snapshot["papel"].eq(role)
            & snapshot["data_referencia"].eq(pd.Timestamp(from_date).strftime("%Y-%m-%d")),
            common + value_columns,
        ].rename(columns={column: f"origem_{column}" for column in value_columns})
        new = snapshot.loc[
            snapshot["papel"].eq(role)
            & snapshot["data_referencia"].eq(pd.Timestamp(to_date).strftime("%Y-%m-%d")),
            ["cnpj_fundo"] + value_columns,
        ].rename(columns={column: f"destino_{column}" for column in value_columns})
        detail = old.merge(new, on="cnpj_fundo", how="inner", validate="one_to_one")
        detail.insert(0, "papel", role)
        detail.insert(1, "data_origem", pd.Timestamp(from_date).strftime("%Y-%m-%d"))
        detail.insert(2, "data_destino", pd.Timestamp(to_date).strftime("%Y-%m-%d"))
        detail["comparavel"] = detail["origem_status_resolucao"].eq(
            "resolvido_unico"
        ) & detail["destino_status_resolucao"].eq("resolvido_unico")
        detail["mudou_grupo"] = pd.Series(pd.NA, index=detail.index, dtype="boolean")
        detail["mudou_entidade_legal"] = pd.Series(
            pd.NA, index=detail.index, dtype="boolean"
        )
        comparable = detail["comparavel"]
        detail.loc[comparable, "mudou_grupo"] = detail.loc[
            comparable, "origem_prestador_grupo"
        ].ne(detail.loc[comparable, "destino_prestador_grupo"])
        detail.loc[comparable, "mudou_entidade_legal"] = detail.loc[
            comparable, "origem_prestador_chave"
        ].ne(detail.loc[comparable, "destino_prestador_chave"])
        detail["fonte_url"] = CAD_FI_HISTORY_URL
        detail["escopo_fonte"] = SOURCE_SCOPE_NOTE
        detail_rows.append(detail)

        comparable_detail = detail.loc[detail["comparavel"]].copy()
        comparable_pl = float(comparable_detail["pl_mai26_brl"].sum())
        changed = comparable_detail["mudou_grupo"].fillna(False).astype(bool)
        changed_pl = float(comparable_detail.loc[changed, "pl_mai26_brl"].sum())
        coverage_rows.append(
            {
                "papel": role,
                "data_referencia": f"{pd.Timestamp(from_date).date()} → {pd.Timestamp(to_date).date()}",
                "fundos_coorte": int(len(detail)),
                "pl_coorte_mai26_brl": float(detail["pl_mai26_brl"].sum()),
                "fundos_com_registro_ativo": int(len(comparable_detail)),
                "pl_com_registro_ativo_brl": comparable_pl,
                "cobertura_fundos_registro_ativo": (
                    len(comparable_detail) / len(detail) if len(detail) else float("nan")
                ),
                "cobertura_pl_registro_ativo": (
                    comparable_pl / float(detail["pl_mai26_brl"].sum())
                    if float(detail["pl_mai26_brl"].sum())
                    else float("nan")
                ),
                "fundos_resolvidos_unicos": int(len(comparable_detail)),
                "pl_resolvido_unico_brl": comparable_pl,
                "cobertura_fundos_resolvida": (
                    len(comparable_detail) / len(detail) if len(detail) else float("nan")
                ),
                "cobertura_pl_resolvida": (
                    comparable_pl / float(detail["pl_mai26_brl"].sum())
                    if float(detail["pl_mai26_brl"].sum())
                    else float("nan")
                ),
                "fundos_multiplos_registros_ativos": int(
                    (
                        detail["origem_status_resolucao"].eq(
                            "multiplos_registros_ativos"
                        )
                        | detail["destino_status_resolucao"].eq(
                            "multiplos_registros_ativos"
                        )
                    ).sum()
                ),
                "pl_multiplos_registros_ativos_brl": float(
                    detail.loc[
                        detail["origem_status_resolucao"].eq(
                            "multiplos_registros_ativos"
                        )
                        | detail["destino_status_resolucao"].eq(
                            "multiplos_registros_ativos"
                        ),
                        "pl_mai26_brl",
                    ].sum()
                ),
                "fundos_sem_registro_ativo": int((~detail["comparavel"]).sum()),
                "pl_sem_registro_ativo_brl": float(
                    detail.loc[~detail["comparavel"], "pl_mai26_brl"].sum()
                ),
                "fundos_mudaram_grupo": int(changed.sum()),
                "pl_mudou_grupo_mai26_brl": changed_pl,
                "share_pl_mudou_grupo_sobre_comparavel": (
                    changed_pl / comparable_pl if comparable_pl else float("nan")
                ),
                "fonte_url": CAD_FI_HISTORY_URL,
                "escopo_fonte": SOURCE_SCOPE_NOTE,
            }
        )
        if not comparable_detail.empty:
            links = (
                comparable_detail.groupby(
                    [
                        "origem_prestador_grupo",
                        "destino_prestador_grupo",
                        "mudou_grupo",
                    ],
                    dropna=False,
                    as_index=False,
                )
                .agg(
                    fundos=("cnpj_fundo", "nunique"),
                    pl_mai26_brl=("pl_mai26_brl", "sum"),
                )
                .sort_values(
                    ["pl_mai26_brl", "origem_prestador_grupo", "destino_prestador_grupo"],
                    ascending=[False, True, True],
                )
            )
            links.insert(0, "papel", role)
            links.insert(1, "data_origem", pd.Timestamp(from_date).strftime("%Y-%m-%d"))
            links.insert(2, "data_destino", pd.Timestamp(to_date).strftime("%Y-%m-%d"))
            links["share_pl_comparavel"] = links["pl_mai26_brl"].div(comparable_pl)
            links["fonte_url"] = CAD_FI_HISTORY_URL
            links["escopo_fonte"] = SOURCE_SCOPE_NOTE
            link_rows.append(links)

    detail = pd.concat(detail_rows, ignore_index=True)
    links = pd.concat(link_rows, ignore_index=True) if link_rows else pd.DataFrame()
    coverage = pd.DataFrame(coverage_rows)
    snapshot = snapshot.sort_values(
        ["papel", "data_referencia", "pl_mai26_brl", "cnpj_fundo"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)
    detail = detail.sort_values(
        ["papel", "comparavel", "mudou_grupo", "pl_mai26_brl", "cnpj_fundo"],
        ascending=[True, False, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    checks = {
        "latest_competence": str(latest_competence)[:7],
        "from_date": pd.Timestamp(from_date).strftime("%Y-%m-%d"),
        "to_date": pd.Timestamp(to_date).strftime("%Y-%m-%d"),
        "cohort_funds": int(cohort["cnpj_fundo"].nunique()),
        "cohort_pl_may26_brl": float(cohort["pl_mai26_brl"].sum()),
        "excluded_fund_cnpjs": sorted(
            _fund_cnpj(value) for value in excluded_fund_cnpjs if _fund_cnpj(value)
        ),
        "weight_definition": "PL de mai/26 por CNPJ legal de fundo",
        "interval_definition": "data_inicio <= referência < data_fim; data_fim vazia permanece ativa",
        "multiple_active_definition": (
            "mais de um prestador legal ativo na mesma data; excluído do fluxo comparável"
        ),
        "provider_group_definition": (
            "curadoria societária revisada quando disponível; canonical_provider nos demais"
        ),
        "source_scope_note": SOURCE_SCOPE_NOTE,
    }
    return ProviderHistoryOutputs(
        snapshot=snapshot,
        detail=detail,
        links=links,
        coverage=coverage,
        checks=checks,
    )


def write_provider_history_outputs(
    outputs: ProviderHistoryOutputs,
    output_dir: Path,
    *,
    source_archive: Path,
) -> dict[str, object]:
    """Write compact, traceable analytical outputs and return the manifest."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "snapshot": output_dir / "prestadores_historico_cvm_snapshot.csv.gz",
        "detail": output_dir / "prestadores_historico_cvm_transicoes_detalhe.csv.gz",
        "links": output_dir / "prestadores_historico_cvm_transicoes_links.csv",
        "coverage": output_dir / "prestadores_historico_cvm_cobertura.csv",
    }
    outputs.snapshot.to_csv(files["snapshot"], index=False, compression="gzip")
    outputs.detail.to_csv(files["detail"], index=False, compression="gzip")
    outputs.links.to_csv(files["links"], index=False)
    outputs.coverage.to_csv(files["coverage"], index=False)
    manifest: dict[str, object] = {
        "schema_version": "provider_history_cvm_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "url": CAD_FI_HISTORY_URL,
            "dataset_url": CAD_FI_DATASET_URL,
            "archive_sha256": _sha256(Path(source_archive)),
            "archive_bytes": Path(source_archive).stat().st_size,
            "archive_files": {
                role: spec.archive_name for role, spec in ROLE_SPECS.items()
            },
            "scope_note": SOURCE_SCOPE_NOTE,
        },
        "checks": dict(outputs.checks),
        "outputs": {
            name: {
                "path": path.name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "rows": int(
                    {
                        "snapshot": len(outputs.snapshot),
                        "detail": len(outputs.detail),
                        "links": len(outputs.links),
                        "coverage": len(outputs.coverage),
                    }[name]
                ),
            }
            for name, path in files.items()
        },
    }
    manifest_path = output_dir / "prestadores_historico_cvm_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


__all__ = [
    "CAD_FI_DATASET_URL",
    "CAD_FI_HISTORY_URL",
    "DEFAULT_EXCLUDED_FUND_CNPJS",
    "DEFAULT_FROM_DATE",
    "DEFAULT_LATEST_COMPETENCE",
    "DEFAULT_TO_DATE",
    "ProviderHistoryOutputs",
    "SOURCE_SCOPE_NOTE",
    "build_current_fund_cohort",
    "build_provider_history_outputs",
    "download_provider_history_zip",
    "normalize_provider_group",
    "read_provider_history_zip",
    "write_provider_history_outputs",
]
