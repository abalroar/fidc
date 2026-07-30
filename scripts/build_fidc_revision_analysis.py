"""Materialize the auditable analytical tables used by the revised FIDC deck."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.fic_detection import (
    annotate_fic_detection,
    assert_universe_excludes_fics,
    split_fidc_universe,
)
from services.fic_perimeter import (
    apply_fic_perimeter_overrides,
    load_fic_perimeter_overrides,
)
from services.industry_revision_analysis import (
    TABLE_II_RECEIVABLE_COLUMNS,
    build_revision_outputs,
    write_revision_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/industry_study")
    parser.add_argument(
        "--output-dir",
        default="data/industry_study/generated_revision",
    )
    parser.add_argument(
        "--latest-complete",
        default="",
        help="competência AAAA-MM; vazio usa a última marcada como completa",
    )
    parser.add_argument("--raw-dir", default=".cache/cvm-industry-study")
    parser.add_argument(
        "--refresh-source-presence",
        action="store_true",
        help="reprocessa competências críticas no bruto CVM para preservar vazio versus zero e aging",
    )
    parser.add_argument(
        "--presence-months",
        default="all",
        help=(
            "competências separadas por vírgula; 'all' reprocessa todo o histórico "
            "disponível para preservar vazio versus zero"
        ),
    )
    parser.add_argument(
        "--source-presence-overlay",
        default="",
        help=(
            "overlay bruto já validado para reutilização quando não houver "
            "reprocessamento; preserva vazio versus zero e aging"
        ),
    )
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args(argv)


def _read_optional(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path, low_memory=False) if path.exists() else None


#: Produtos analíticos que jamais podem conter um FIC.  ``base_vehicle`` fica
#: de fora de propósito: é a base bruta que carrega os dois lados, e é dela que
#: o saldo de FIC é calculado.
_FIC_FREE_PRODUCTS: tuple[str, ...] = (
    "top20_fidcs",
    "top20_outros",
    "acquiring_reclassified_mix",
)


def _validate_no_fic_in_products(outputs: object, excluded: list[str]) -> None:
    if not excluded:
        return
    for name in _FIC_FREE_PRODUCTS:
        frame = getattr(outputs, name, None)
        if frame is None:
            continue
        for column in ("cnpj_fundo", "cnpj"):
            if column in getattr(frame, "columns", []):
                assert_universe_excludes_fics(
                    frame, excluded, label=name, cnpj_column=column
                )
                break


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    vehicle_path = data_dir / "vehicle_monthly.csv.gz"
    if not vehicle_path.exists():
        raise SystemExit(f"base ausente: {vehicle_path}")
    vehicle = pd.read_csv(vehicle_path, low_memory=False)
    # A curadoria de perímetro precede qualquer agregação: um veículo que só
    # detém cotas de outros FIDCs tem de sair dos quatro tipos ANBIMA antes de
    # o mix ser calculado, sob pena de contar o mesmo patrimônio duas vezes.
    fic_overrides = load_fic_perimeter_overrides(data_dir)
    vehicle, fic_correction = apply_fic_perimeter_overrides(vehicle, fic_overrides)
    if fic_correction.cnpj_count:
        print(
            f"correção de perímetro FIC: {fic_correction.cnpj_count} CNPJs, "
            f"{fic_correction.rows_changed} linhas-mês, "
            f"R$ {fic_correction.pl_moved_last_competence_brl / 1e9:.2f} bi de PL "
            f"em {fic_correction.last_competence or 'n/d'} movidos para o saldo de FIC"
        )
    # O portão único: anota is_fic e as colunas auditáveis, e separa o universo
    # elegível dos FICs. Os dois lados são necessários — o elegível alimenta
    # tudo que é analítico, o excluído alimenta o saldo de FIC. Apagar as linhas
    # excluídas zeraria justamente o saldo que a exclusão existe para construir.
    vehicle = annotate_fic_detection(
        vehicle,
        curated_cnpjs=fic_overrides["cnpj_fundo"].tolist() if not fic_overrides.empty else (),
        curated_evidence=(
            dict(zip(fic_overrides["cnpj_fundo"], fic_overrides["evidencia"]))
            if not fic_overrides.empty
            else None
        ),
        cnpj_column="cnpj",
    )
    _eligible, excluded_fics, exclusion = split_fidc_universe(vehicle, cnpj_column="cnpj")
    excluded_fic_cnpjs = (
        sorted(set(excluded_fics["cnpj"].astype(str))) if not excluded_fics.empty else []
    )
    print(
        f"universo elegível: {exclusion.rows_out} linhas-mês; "
        f"{exclusion.cnpj_excluded} CNPJs excluídos como FIC, "
        f"R$ {exclusion.pl_excluded_last_competence_brl / 1e9:.2f} bi de PL em "
        f"{exclusion.last_competence or 'n/d'} fora dos quatro tipos ANBIMA"
    )
    latest_complete = str(args.latest_complete or "").strip()
    if not latest_complete:
        status = _read_optional(data_dir / "industry_competence_status.csv")
        if status is not None and not status.empty and "publication_status" in status:
            complete = status[status["publication_status"].astype(str).eq("completa")]
            if not complete.empty:
                latest_complete = str(complete["competencia"].astype(str).max())
        if not latest_complete:
            latest_complete = str(vehicle["competencia"].astype(str).max())
    official = _read_optional(data_dir / "industry_anbima_classification.csv.gz")
    published = _read_optional(data_dir / "industry_large_fund_classification.csv")
    documentary_overrides = _read_optional(
        data_dir / "anbima_documentary_overrides.csv"
    )
    if documentary_overrides is not None and not documentary_overrides.empty:
        published = pd.concat(
            [
                published if published is not None else pd.DataFrame(),
                documentary_overrides,
            ],
            ignore_index=True,
            sort=False,
        )
    provider_ownership = _read_optional(data_dir / "provider_ownership_curation.csv")
    bank_fidcs = _read_optional(data_dir / "bank_fidc_curation.csv")
    acquiring_reclassification = _read_optional(
        data_dir / "acquiring_reclassification_curation.csv"
    )
    from scripts.build_fidc_industry_study import RawStore, aggregate_month, load_tab4

    store = RawStore(Path(args.raw_dir), allow_download=not args.skip_download)
    raw_frames: list[pd.DataFrame] = []
    reused_presence_overlay: pd.DataFrame | None = None
    overlay_path = Path(str(args.source_presence_overlay or "").strip())
    if str(args.source_presence_overlay or "").strip():
        if not overlay_path.is_file():
            raise SystemExit(f"overlay de presença ausente: {overlay_path}")
        reused_presence_overlay = pd.read_csv(overlay_path, low_memory=False)
        required_overlay = {
            "competencia",
            "cnpj",
            "carteira_dc",
            "dc_inadimplentes",
        }
        missing_overlay = required_overlay.difference(reused_presence_overlay.columns)
        if missing_overlay:
            raise SystemExit(
                "overlay de presença incompatível; colunas ausentes: "
                + ", ".join(sorted(missing_overlay))
            )
        # `build_base_by_vehicle` requires PL, although the presence overlay
        # never replaces PL. A neutral value keeps the audit transformation
        # reusable without duplicating the full monthly analytical base.
        if "pl" not in reused_presence_overlay:
            reused_presence_overlay["pl"] = 0.0
    table_ii_columns = list(TABLE_II_RECEIVABLE_COLUMNS)
    latest_table_ii = vehicle[
        vehicle["competencia"].astype(str).eq(latest_complete)
    ].copy()
    if not set(table_ii_columns).issubset(latest_table_ii.columns) or not latest_table_ii[
        table_ii_columns
    ].notna().any(axis=1).any():
        raise SystemExit(
            "Tabela II da competencia atual ausente em vehicle_monthly; "
            "interrompendo para nao publicar uma coorte parcial"
        )
    # A base mensal versionada já contém a fotografia completa de Tabela II da
    # competência atual. O bruto é carregado apenas para a competência anterior,
    # necessária à ponte de coorte; caches parciais do mês atual não podem reduzir
    # silenciosamente o universo publicado.
    raw_table_ii_frames: list[pd.DataFrame] = [latest_table_ii]
    previous_complete = str(pd.Period(latest_complete, freq="M") - 1)
    presence_tokens = [
        item.strip() for item in args.presence_months.split(",") if item.strip()
    ]
    if any(item.casefold() == "all" for item in presence_tokens):
        start_complete = str(vehicle["competencia"].astype(str).str[:7].min())
        requested_months = [
            str(period)
            for period in pd.period_range(
                start=start_complete,
                end=latest_complete,
                freq="M",
            )
        ]
    else:
        requested_months = presence_tokens
    months_to_read = list(requested_months) if args.refresh_source_presence else []
    if previous_complete not in months_to_read:
        months_to_read.append(previous_complete)
    for competence in months_to_read:
        yyyymm = competence.replace("-", "")
        tab4 = load_tab4(store, yyyymm)
        aggregate = aggregate_month(store, yyyymm, tab4) if tab4 is not None else None
        if aggregate is None:
            print(f"[warn] bruto CVM indisponível para {competence}; auditoria omitida")
            continue
        frame = pd.DataFrame(aggregate.vehicle)
        if competence == previous_complete:
            raw_table_ii_frames.append(frame.copy())
        if args.refresh_source_presence and competence in requested_months:
            raw_frames.append(frame)
    if args.refresh_source_presence:
        audit_parts = [
            frame
            for frame in (reused_presence_overlay, *raw_frames)
            if frame is not None and not frame.empty
        ]
        raw_audit = (
            pd.concat(audit_parts, ignore_index=True, sort=False)
            if audit_parts
            else pd.DataFrame()
        )
        if not raw_audit.empty:
            raw_audit["competencia"] = raw_audit["competencia"].astype(str).str[:7]
            raw_audit["cnpj"] = raw_audit["cnpj"].astype(str).str.replace(
                r"\D",
                "",
                regex=True,
            ).str.zfill(14)
            raw_audit = raw_audit.drop_duplicates(
                ["competencia", "cnpj"],
                keep="last",
            )
    else:
        raw_audit = reused_presence_overlay
    raw_table_ii = (
        pd.concat(raw_table_ii_frames, ignore_index=True)
        if raw_table_ii_frames
        else pd.DataFrame()
    )
    outputs = build_revision_outputs(
        vehicle_monthly=vehicle,
        anbima_classification=official,
        published_classifications=published,
        raw_audit_vehicle=raw_audit,
        raw_table_ii_vehicle=raw_table_ii,
        provider_ownership_curation=provider_ownership,
        bank_fidc_curation=bank_fidcs,
        acquiring_reclassification_curation=acquiring_reclassification,
        latest_complete=latest_complete,
    )
    manifest = write_revision_outputs(outputs, Path(args.output_dir))
    # A regra é centralizada acima, mas uma regressão silenciosa num produto
    # derivado é justamente o que esta verificação torna impossível: se um FIC
    # reaparecer num ranking ou no mix, a materialização falha em voz alta.
    _validate_no_fic_in_products(outputs, excluded_fic_cnpjs)
    checks = manifest["checks"]
    print(
        "[ok] revisão analítica materializada em "
        f"{args.output_dir}: {checks['latest_vehicles']} veículos, "
        f"{checks['latest_funds']} fundos, {checks['top20_fidcs_rows']} no Top 20"
    )


if __name__ == "__main__":
    main()
