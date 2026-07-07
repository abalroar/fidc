"""Estudo da industria de FIDCs a partir dos dados abertos da CVM.

Fonte primaria: dataset "FIDC - Documentos: Informe Mensal" do Portal de
Dados Abertos da CVM (https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal).

- Historico anual (2013-2024): .../INF_MENSAL/DADOS/HIST/inf_mensal_fidc_AAAA.zip
- Meses correntes (~ultimos 18 meses): .../INF_MENSAL/DADOS/inf_mensal_fidc_AAAAMM.zip
- Cadastro vigente (RCVM 175): .../FI/CAD/DADOS/registro_fundo_classe.zip

Unidade de observacao do informe mensal:
- ate a adaptacao a RCVM 175, uma linha por FUNDO (CNPJ_FUNDO);
- apos a adaptacao, uma linha por CLASSE (TP_FUNDO_CLASSE + CNPJ_FUNDO_CLASSE).
O script normaliza as duas eras numa chave unica por veiculo reportante e
mapeia classe -> fundo via cadastro para contagem de fundos unicos.

Saidas (CSVs pequenos, versionaveis) em data/industry_study/:
- industry_monthly.csv        serie mensal da industria (PL, veiculos, cotistas,
                              captacao, resgate, inadimplencia, subordinacao...)
- segments_monthly.csv        carteira por tipo de recebivel (Tab II)
- flows_monthly.csv           movimentacao de cotas por tipo de operacao (Tab X.4)
- cotistas_tipo_monthly.csv   numero de cotistas por tipo de investidor (Tab X.1.1)
- admin_monthly.csv           PL e nao de veiculos por administrador por mes (Tab I + IV)
- concentration_monthly.csv   HHI e share top 5/10 de administradores
- universe_latest.csv         foto por veiculo no ultimo mes completo
- prestadores_latest.csv      ranking de admin/gestor/custodiante no ultimo mes
- metadata.json               proveniencia e parametros da execucao

Uso:
    python scripts/build_fidc_industry_study.py \
        [--raw-dir .cache/cvm-industry-study] [--output-dir data/industry_study] \
        [--start 2013-01] [--end 2026-05] [--skip-download] [--report]

`--report` renderiza tambem o relatorio executivo em
reports/fidc_industry_study.md a partir dos CSVs agregados.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

BASE_MONTHLY_URL = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS"
BASE_HIST_URL = f"{BASE_MONTHLY_URL}/HIST"
REGISTRO_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
CAD_FI_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
USER_AGENT = "fidc-industry-study/1.0 (dados.cvm.gov.br open data)"
REQUEST_TIMEOUT = 120

# Rotulos oficiais da Tabela II do Informe Mensal (Anexo A da ICVM 489,
# mantidos no layout vigente do dataset aberto).
SEGMENT_LABELS = {
    "TAB_II_A_VL_INDUST": "Industrial",
    "TAB_II_B_VL_IMOBIL": "Imobiliario",
    "TAB_II_C_VL_COMERC": "Comercial",
    "TAB_II_D_VL_SERV": "Servicos",
    "TAB_II_E_VL_AGRONEG": "Agronegocio",
    "TAB_II_F_VL_FINANC": "Financeiro",
    "TAB_II_G_VL_CREDITO": "Cartao de credito",
    "TAB_II_H_VL_FACTOR": "Factoring",
    "TAB_II_I_VL_SETOR_PUBLICO": "Setor publico",
    "TAB_II_J_VL_JUDICIAL": "Acoes judiciais",
    "TAB_II_K_VL_MARCA": "Marcas e patentes",
}
SEGMENT_FIN_SUB_LABELS = {
    "TAB_II_F1_VL_CRED_PESSOA": "Financeiro: credito pessoal",
    "TAB_II_F2_VL_CRED_PESSOA_CONSIG": "Financeiro: consignado",
    "TAB_II_F3_VL_CRED_CORP": "Financeiro: credito corporativo",
    "TAB_II_F4_VL_MIDMARKET": "Financeiro: middle market",
    "TAB_II_F5_VL_VEICULO": "Financeiro: veiculos",
    "TAB_II_F6_VL_IMOBIL_EMPRESA": "Financeiro: imobiliario empresarial",
    "TAB_II_F7_VL_IMOBIL_RESID": "Financeiro: imobiliario residencial",
    "TAB_II_F8_VL_OUTRO": "Financeiro: outros",
}

COTISTA_TIPO_LABELS = {
    "PF": "Pessoa fisica",
    "PJ_NAO_FINANC": "PJ nao financeira",
    "BANCO": "Banco comercial",
    "CORRETORA_DISTRIB": "Corretora/distribuidora",
    "PJ_FINANC": "Outra PJ financeira",
    "INVNR": "Investidor nao residente",
    "EAPC": "Previdencia aberta (EAPC)",
    "EFPC": "Previdencia fechada (EFPC)",
    "RPPS": "Regime proprio (RPPS)",
    "SEGUR": "Seguradora",
    "CAPITALIZ": "Capitalizacao",
    "COTA_FIDC": "Cotas de FIDC (outros FIDC/FIC-FIDC)",
    "FII": "FII",
    "OUTRO_FI": "Outros fundos",
    "CLUBE": "Clube de investimento",
    "OUTRO": "Outros",
}

FIC_FIDC_PATTERN = re.compile(
    r"\bFIC\b|COTAS?\s+DE\s+FUNDOS?\s+DE\s+INVESTIMENTO\s+EM\s+DIREITOS",
    re.IGNORECASE,
)


def _strip_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def month_range(start: str, end: str) -> list[str]:
    """Lista de competencias AAAAMM de start a end (formato AAAA-MM)."""
    y0, m0 = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    months = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return months


def download(url: str, dest: Path, *, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                dest.write_bytes(resp.read())
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            time.sleep(2**attempt)
        except Exception:  # noqa: BLE001
            time.sleep(2**attempt)
    return False


@dataclass
class RawStore:
    """Resolve e le as tabelas do informe mensal por competencia."""

    raw_dir: Path
    allow_download: bool = True
    _zip_cache: dict[Path, zipfile.ZipFile] = field(default_factory=dict)
    _name_cache: dict[Path, set[str]] = field(default_factory=dict)

    def _zip(self, path: Path) -> zipfile.ZipFile | None:
        if path not in self._zip_cache:
            if not path.exists():
                return None
            self._zip_cache[path] = zipfile.ZipFile(path)
            self._name_cache[path] = set(self._zip_cache[path].namelist())
        return self._zip_cache[path]

    def ensure_month(self, yyyymm: str) -> Path | None:
        """Garante o zip que contem a competencia; mensal tem precedencia."""
        monthly = self.raw_dir / f"inf_mensal_fidc_{yyyymm}.zip"
        if monthly.exists():
            return monthly
        if self.allow_download and download(
            f"{BASE_MONTHLY_URL}/inf_mensal_fidc_{yyyymm}.zip", monthly
        ):
            return monthly
        annual = self.raw_dir / f"inf_mensal_fidc_{yyyymm[:4]}.zip"
        if annual.exists():
            return annual
        if self.allow_download and download(
            f"{BASE_HIST_URL}/inf_mensal_fidc_{yyyymm[:4]}.zip", annual
        ):
            return annual
        return None

    def read_table(self, yyyymm: str, table: str) -> pd.DataFrame | None:
        """Le uma tabela (ex.: 'tab_IV') da competencia, ja normalizada.

        Zips anuais (2013-2018) trazem um CSV por ano; o recorte por
        competencia e feito via DT_COMPTC.
        """
        zip_path = self.ensure_month(yyyymm)
        if zip_path is None:
            return None
        archive = self._zip(zip_path)
        if archive is None:
            return None
        names = self._name_cache[zip_path]
        monthly_name = f"inf_mensal_fidc_{table}_{yyyymm}.csv"
        annual_name = f"inf_mensal_fidc_{table}_{yyyymm[:4]}.csv"
        member = monthly_name if monthly_name in names else annual_name
        if member not in names:
            return None
        with archive.open(member) as handle:
            df = pd.read_csv(
                io.BytesIO(handle.read()),
                sep=";",
                encoding="latin-1",
                dtype=str,
                keep_default_na=False,
                quoting=csv.QUOTE_NONE,
            )
        df.columns = [str(c).strip() for c in df.columns]
        if member == annual_name:
            target = f"{yyyymm[:4]}-{yyyymm[4:6]}"
            df = df[df["DT_COMPTC"].str.startswith(target)].copy()
        return self._normalize_keys(df)

    @staticmethod
    def _normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
        """Chave unica pre/pos RCVM 175: cnpj (digitos) + tp_registro."""
        if "CNPJ_FUNDO_CLASSE" in df.columns:
            df["cnpj"] = df["CNPJ_FUNDO_CLASSE"].map(_strip_digits)
            df["tp_registro"] = df.get("TP_FUNDO_CLASSE", "Fundo")
        else:
            df["cnpj"] = df["CNPJ_FUNDO"].map(_strip_digits)
            df["tp_registro"] = "Fundo"
        return df


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def load_classe_fundo_map(raw_dir: Path, *, allow_download: bool) -> pd.DataFrame:
    """Mapa CNPJ_Classe -> CNPJ_Fundo + atributos cadastrais da classe."""
    dest = raw_dir / "registro_fundo_classe.zip"
    if allow_download:
        download(REGISTRO_URL, dest)
    if not dest.exists():
        return pd.DataFrame(
            columns=["cnpj_classe", "cnpj_fundo", "publico_alvo", "classificacao_anbima", "gestor_nome", "gestor_cnpj", "custodiante_nome", "custodiante_cnpj"]
        )
    archive = zipfile.ZipFile(dest)
    with archive.open("registro_classe.csv") as handle:
        classe = pd.read_csv(handle, sep=";", encoding="latin-1", dtype=str, keep_default_na=False, quoting=csv.QUOTE_NONE)
    with archive.open("registro_fundo.csv") as handle:
        fundo = pd.read_csv(handle, sep=";", encoding="latin-1", dtype=str, keep_default_na=False, quoting=csv.QUOTE_NONE)
    fundo_cols = {c: c for c in fundo.columns}
    gestor_name_col = "Gestor" if "Gestor" in fundo_cols else ""
    gestor_cnpj_col = "CPF_CNPJ_Gestor" if "CPF_CNPJ_Gestor" in fundo_cols else ""
    fundo_slim = pd.DataFrame(
        {
            "ID_Registro_Fundo": fundo["ID_Registro_Fundo"],
            "cnpj_fundo": fundo["CNPJ_Fundo"].map(_strip_digits),
            "gestor_nome": fundo[gestor_name_col].map(_norm_name) if gestor_name_col else "",
            "gestor_cnpj": fundo[gestor_cnpj_col].map(_strip_digits) if gestor_cnpj_col else "",
        }
    ).drop_duplicates(subset=["ID_Registro_Fundo"])
    out = pd.DataFrame(
        {
            "ID_Registro_Fundo": classe["ID_Registro_Fundo"],
            "cnpj_classe": classe["CNPJ_Classe"].map(_strip_digits),
            "publico_alvo": classe.get("Publico_Alvo", ""),
            "classificacao_anbima": classe.get("Classificacao_Anbima", ""),
            "custodiante_nome": classe.get("Custodiante", "").map(_norm_name),
            "custodiante_cnpj": classe.get("CNPJ_Custodiante", "").map(_strip_digits),
        }
    )
    out = out.merge(fundo_slim, on="ID_Registro_Fundo", how="left")
    out = out.drop(columns=["ID_Registro_Fundo"])
    out = out[out["cnpj_classe"].str.len() == 14].drop_duplicates(subset=["cnpj_classe"])
    return out


@dataclass
class MonthAggregate:
    competencia: str
    industry: dict
    segments: list[dict]
    flows: list[dict]
    cotistas_tipo: list[dict]
    admin: list[dict]


def aggregate_month(store: RawStore, yyyymm: str) -> MonthAggregate | None:
    comp = f"{yyyymm[:4]}-{yyyymm[4:6]}"
    tab4 = store.read_table(yyyymm, "tab_IV")
    if tab4 is None or tab4.empty:
        return None
    tab4["pl"] = to_num(tab4["TAB_IV_A_VL_PL"])
    tab4 = tab4.drop_duplicates(subset=["cnpj"], keep="last")
    pl_by_cnpj = tab4.set_index("cnpj")["pl"]

    industry: dict = {
        "competencia": comp,
        "n_veiculos": int(len(tab4)),
        "n_registros_classe": int((tab4["tp_registro"] == "Classe").sum()),
        "n_registros_fundo": int((tab4["tp_registro"] == "Fundo").sum()),
        "pl_total": float(tab4["pl"].sum()),
    }
    industry["pl_fic_fidc"] = float(
        tab4.loc[tab4["DENOM_SOCIAL"].str.contains(FIC_FIDC_PATTERN, na=False), "pl"].sum()
    )

    # Tabela I: ativo, carteira de DC, inadimplencia, administrador, condominio
    tab1 = store.read_table(yyyymm, "tab_I")
    admin_rows: list[dict] = []
    if tab1 is not None and not tab1.empty:
        tab1 = tab1.drop_duplicates(subset=["cnpj"], keep="last")
        for col in (
            "TAB_I_VL_ATIVO",
            "TAB_I2A_VL_DIRCRED_RISCO",
            "TAB_I2B_VL_DIRCRED_SEM_RISCO",
            "TAB_I2A3_VL_CRED_INAD",
            "TAB_I2B3_VL_CRED_INAD",
            "TAB_I2A2_VL_CRED_VENC_INAD",
            "TAB_I2B2_VL_CRED_VENC_INAD",
        ):
            if col in tab1.columns:
                tab1[col + "_n"] = to_num(tab1[col])
            else:
                tab1[col + "_n"] = 0.0
        industry["ativo_total"] = float(tab1["TAB_I_VL_ATIVO_n"].sum())
        dc_total = float(
            tab1["TAB_I2A_VL_DIRCRED_RISCO_n"].sum() + tab1["TAB_I2B_VL_DIRCRED_SEM_RISCO_n"].sum()
        )
        inad_vencidos = float(
            tab1["TAB_I2A3_VL_CRED_INAD_n"].sum() + tab1["TAB_I2B3_VL_CRED_INAD_n"].sum()
        )
        a_vencer_com_parcela_inad = float(
            tab1["TAB_I2A2_VL_CRED_VENC_INAD_n"].sum() + tab1["TAB_I2B2_VL_CRED_VENC_INAD_n"].sum()
        )
        industry["carteira_dc"] = dc_total
        industry["dc_inadimplentes"] = inad_vencidos
        industry["dc_a_vencer_com_parcela_inad"] = a_vencer_com_parcela_inad
        industry["inad_pct"] = inad_vencidos / dc_total if dc_total else 0.0

        # Compradores de NPL reportam creditos inadimplentes pelo valor de FACE
        # enquanto a carteira entra pelo valor contabil (ha veiculos com "inad"
        # dezenas de vezes maior que a propria carteira). A metrica ajustada
        # limita a inadimplencia de cada veiculo a sua carteira antes de agregar.
        tab1["dc_veiculo"] = (
            tab1["TAB_I2A_VL_DIRCRED_RISCO_n"] + tab1["TAB_I2B_VL_DIRCRED_SEM_RISCO_n"]
        )
        tab1["inad_veiculo"] = (
            tab1["TAB_I2A3_VL_CRED_INAD_n"] + tab1["TAB_I2B3_VL_CRED_INAD_n"]
        )
        tab1["inad_cap"] = tab1[["inad_veiculo", "dc_veiculo"]].min(axis=1).clip(lower=0.0)
        inad_ajustada = float(tab1["inad_cap"].sum())
        industry["dc_inadimplentes_ajustado"] = inad_ajustada
        industry["inad_pct_ajustada"] = inad_ajustada / dc_total if dc_total else 0.0

        # FIDCs nao padronizados (NP) carregam creditos vencidos por estrategia
        # (NPL, precatorios); a inadimplencia ex-NP e mais representativa do
        # credito performado. Heuristica: razao social contendo "NAO PADRONIZ".
        is_np = (
            tab1["DENOM_SOCIAL"]
            .map(_norm_name)
            .str.contains("NAO PADRONIZ|NÃO PADRONIZ|NAO-PADRONIZ|NÃO-PADRONIZ", regex=True)
        )
        dc_np = float(tab1.loc[is_np, "dc_veiculo"].sum())
        inad_np_cap = float(tab1.loc[is_np, "inad_cap"].sum())
        industry["carteira_dc_np"] = dc_np
        dc_ex_np = dc_total - dc_np
        industry["inad_pct_ajustada_ex_np"] = (
            (inad_ajustada - inad_np_cap) / dc_ex_np if dc_ex_np else 0.0
        )

        tab1["pl_join"] = tab1["cnpj"].map(pl_by_cnpj).fillna(0.0)
        condom = tab1.groupby(tab1["CONDOM"].map(_norm_name))["pl_join"].sum()
        industry["pl_condominio_aberto"] = float(condom.get("ABERTO", 0.0))
        industry["pl_condominio_fechado"] = float(condom.get("FECHADO", 0.0))
        exclusivo = tab1.groupby(tab1["FUNDO_EXCLUSIVO"].map(_norm_name))["pl_join"].sum()
        industry["pl_exclusivo"] = float(exclusivo.get("S", 0.0) + exclusivo.get("SIM", 0.0))

        tab1["admin_cnpj"] = tab1.get("CNPJ_ADMIN", "").map(_strip_digits)
        tab1["admin_nome"] = tab1.get("ADMIN", "").map(_norm_name)
        grouped = tab1.groupby(["admin_cnpj", "admin_nome"], dropna=False).agg(
            pl=("pl_join", "sum"), n_veiculos=("cnpj", "nunique")
        )
        for (admin_cnpj, admin_nome), row in grouped.iterrows():
            admin_rows.append(
                {
                    "competencia": comp,
                    "admin_cnpj": admin_cnpj,
                    "admin_nome": admin_nome,
                    "pl": float(row["pl"]),
                    "n_veiculos": int(row["n_veiculos"]),
                }
            )

    # Tabela II: carteira por segmento
    segments: list[dict] = []
    tab2 = store.read_table(yyyymm, "tab_II")
    if tab2 is not None and not tab2.empty:
        tab2 = tab2.drop_duplicates(subset=["cnpj"], keep="last")
        for col, label in {**SEGMENT_LABELS, **SEGMENT_FIN_SUB_LABELS}.items():
            if col in tab2.columns:
                segments.append(
                    {
                        "competencia": comp,
                        "segmento": label,
                        "nivel": "sub" if col in SEGMENT_FIN_SUB_LABELS else "top",
                        "valor": float(to_num(tab2[col]).sum()),
                    }
                )

    # Tabela X.4: movimentacao de cotas. Ha erros grosseiros de preenchimento
    # (ex.: captacao de R$ 7,25e14 num unico veiculo em 2020-12); descartamos
    # linhas cujo valor supera max(3x PL do veiculo no mes, R$ 2 bi).
    flows: list[dict] = []
    x4 = store.read_table(yyyymm, "tab_X_4")
    if x4 is not None and not x4.empty:
        x4["valor"] = to_num(x4["TAB_X_VL_TOTAL"])
        x4["pl_veiculo"] = x4["cnpj"].map(pl_by_cnpj).fillna(0.0)
        cap = (3.0 * x4["pl_veiculo"]).clip(lower=2e9)
        dropped = x4[x4["valor"] > cap]
        industry["x4_linhas_descartadas"] = int(len(dropped))
        industry["x4_valor_descartado"] = float(dropped["valor"].sum())
        x4 = x4[x4["valor"] <= cap]
        for tp_oper, valor in x4.groupby("TAB_X_TP_OPER")["valor"].sum().items():
            flows.append({"competencia": comp, "tp_oper": str(tp_oper), "valor": float(valor)})
    flow_map = {f["tp_oper"]: f["valor"] for f in flows}
    industry["captacoes"] = flow_map.get("Captações no Mês", 0.0)
    industry["resgates"] = flow_map.get("Resgates no Mês", 0.0)
    industry["amortizacoes"] = flow_map.get("Amortizações", 0.0)
    industry["captacao_liquida"] = (
        industry["captacoes"] - industry["resgates"] - industry["amortizacoes"]
    )

    # Tabela X.1: numero de cotistas (contas por classe/serie)
    x1 = store.read_table(yyyymm, "tab_X_1")
    if x1 is not None and not x1.empty:
        industry["cotistas_total"] = int(to_num(x1["TAB_X_NR_COTST"]).sum())

    # Tabela X.1.1: cotistas por tipo de investidor
    cotistas_tipo: list[dict] = []
    x11 = store.read_table(yyyymm, "tab_X_1_1")
    if x11 is not None and not x11.empty:
        for key, label in COTISTA_TIPO_LABELS.items():
            total = 0.0
            for prefix in ("SENIOR", "SUBORD"):
                col = f"TAB_X_NR_COTST_{prefix}_{key}"
                if col in x11.columns:
                    total += to_num(x11[col]).sum()
            cotistas_tipo.append(
                {"competencia": comp, "tipo_cotista": label, "n_cotistas": int(total)}
            )

    # Tabela X.2: distribuicao senior/subordinada pelo valor das cotas
    # (QT_COTA x VL_COTA). Alguns veiculos reportam valores de cota corrompidos;
    # so entram veiculos cujo valor total de cotas fica entre 0 e 3x o proprio PL.
    x2 = store.read_table(yyyymm, "tab_X_2")
    if x2 is not None and not x2.empty:
        x2["valor"] = to_num(x2["TAB_X_QT_COTA"]) * to_num(x2["TAB_X_VL_COTA"])
        x2["pl_veiculo"] = x2["cnpj"].map(pl_by_cnpj).fillna(0.0)
        total_por_veiculo = x2.groupby("cnpj")["valor"].transform("sum")
        sane = (
            (total_por_veiculo > 0)
            & (x2["pl_veiculo"] > 0)
            & (total_por_veiculo <= 3.0 * x2["pl_veiculo"])
        )
        x2_sane = x2[sane]
        serie = x2_sane["TAB_X_CLASSE_SERIE"].map(_norm_name)
        is_sub = serie.str.contains("SUBORD")
        total_cotas = float(x2_sane["valor"].sum())
        industry["vl_cotas_total"] = total_cotas
        industry["vl_cotas_subordinadas"] = float(x2_sane.loc[is_sub, "valor"].sum())
        industry["subordinacao_pct"] = (
            industry["vl_cotas_subordinadas"] / total_cotas if total_cotas else 0.0
        )
        industry["x2_pl_coberto"] = float(
            x2_sane.drop_duplicates("cnpj")["pl_veiculo"].sum()
        )

    # Tabela VII: recompras e substituicoes no mes
    tab7 = store.read_table(yyyymm, "tab_VII")
    if tab7 is not None and not tab7.empty:
        tab7 = tab7.drop_duplicates(subset=["cnpj"], keep="last")
        if "TAB_VII_D_2_VL_RECOMPRA" in tab7.columns:
            industry["vl_recompras"] = float(to_num(tab7["TAB_VII_D_2_VL_RECOMPRA"]).sum())
        if "TAB_VII_C_2_VL_SUBST" in tab7.columns:
            industry["vl_substituicoes"] = float(to_num(tab7["TAB_VII_C_2_VL_SUBST"]).sum())

    return MonthAggregate(
        competencia=comp,
        industry=industry,
        segments=segments,
        flows=flows,
        cotistas_tipo=cotistas_tipo,
        admin=admin_rows,
    )


def build_universe_snapshot(
    store: RawStore, yyyymm: str, classe_map: pd.DataFrame
) -> pd.DataFrame:
    """Foto por veiculo do ultimo mes: PL, admin, gestor, custodiante, segmento."""
    comp = f"{yyyymm[:4]}-{yyyymm[4:6]}"
    tab4 = store.read_table(yyyymm, "tab_IV")
    tab1 = store.read_table(yyyymm, "tab_I")
    tab2 = store.read_table(yyyymm, "tab_II")
    x1 = store.read_table(yyyymm, "tab_X_1")
    if tab4 is None or tab1 is None:
        return pd.DataFrame()
    tab4 = tab4.drop_duplicates(subset=["cnpj"], keep="last")
    tab1 = tab1.drop_duplicates(subset=["cnpj"], keep="last")
    out = pd.DataFrame(
        {
            "competencia": comp,
            "cnpj": tab4["cnpj"],
            "tp_registro": tab4["tp_registro"],
            "denominacao": tab4["DENOM_SOCIAL"].map(_norm_name),
            "pl": to_num(tab4["TAB_IV_A_VL_PL"]),
        }
    )
    out["is_fic_fidc"] = out["denominacao"].str.contains(FIC_FIDC_PATTERN, na=False)
    slim1 = pd.DataFrame(
        {
            "cnpj": tab1["cnpj"],
            "admin_nome": tab1.get("ADMIN", "").map(_norm_name),
            "admin_cnpj": tab1.get("CNPJ_ADMIN", "").map(_strip_digits),
            "condominio": tab1.get("CONDOM", "").map(_norm_name),
            "exclusivo": tab1.get("FUNDO_EXCLUSIVO", "").map(_norm_name),
            "carteira_dc": to_num(tab1.get("TAB_I2A_VL_DIRCRED_RISCO", pd.Series(dtype=str)))
            + to_num(tab1.get("TAB_I2B_VL_DIRCRED_SEM_RISCO", pd.Series(dtype=str))),
            "dc_inadimplentes": to_num(tab1.get("TAB_I2A3_VL_CRED_INAD", pd.Series(dtype=str)))
            + to_num(tab1.get("TAB_I2B3_VL_CRED_INAD", pd.Series(dtype=str))),
        }
    )
    out = out.merge(slim1, on="cnpj", how="left")
    if tab2 is not None and not tab2.empty:
        tab2 = tab2.drop_duplicates(subset=["cnpj"], keep="last")
        seg_cols = [c for c in SEGMENT_LABELS if c in tab2.columns]
        seg_vals = tab2[seg_cols].apply(to_num)
        main_seg = seg_vals.idxmax(axis=1).map(SEGMENT_LABELS)
        main_seg[seg_vals.max(axis=1) <= 0] = ""
        out = out.merge(
            pd.DataFrame({"cnpj": tab2["cnpj"], "segmento_principal": main_seg}),
            on="cnpj",
            how="left",
        )
    if x1 is not None and not x1.empty:
        x1["n"] = to_num(x1["TAB_X_NR_COTST"])
        out = out.merge(
            x1.groupby("cnpj")["n"].sum().rename("cotistas").reset_index(),
            on="cnpj",
            how="left",
        )
    if not classe_map.empty:
        out = out.merge(
            classe_map.rename(columns={"cnpj_classe": "cnpj"}),
            on="cnpj",
            how="left",
        )
        out["cnpj_fundo"] = out["cnpj_fundo"].fillna(out["cnpj"])
    else:
        out["cnpj_fundo"] = out["cnpj"]
    out["inad_pct"] = (out["dc_inadimplentes"] / out["carteira_dc"]).where(
        out["carteira_dc"] > 0, 0.0
    )
    return out.sort_values("pl", ascending=False).reset_index(drop=True)


def build_prestadores_ranking(universe: pd.DataFrame) -> pd.DataFrame:
    """Ranking de administradores, gestores e custodiantes por PL (foto atual)."""
    frames = []
    specs = [
        ("administrador", "admin_nome", "admin_cnpj", "informe_mensal_tab_I"),
        ("gestor", "gestor_nome", "gestor_cnpj", "cadastro_registro_fundo"),
        ("custodiante", "custodiante_nome", "custodiante_cnpj", "cadastro_registro_classe"),
    ]
    for papel, name_col, cnpj_col, fonte in specs:
        if name_col not in universe.columns:
            continue
        frame = universe.copy()
        frame[name_col] = frame[name_col].fillna("").astype(str)
        frame = frame[frame[name_col].str.strip() != ""]
        grouped = (
            frame.groupby([name_col, cnpj_col], dropna=False)
            .agg(pl=("pl", "sum"), n_veiculos=("cnpj", "nunique"), n_fundos=("cnpj_fundo", "nunique"))
            .reset_index()
            .rename(columns={name_col: "nome", cnpj_col: "cnpj_prestador"})
        )
        total = grouped["pl"].sum()
        grouped["share_pl"] = grouped["pl"] / total if total else 0.0
        grouped["papel"] = papel
        grouped["fonte"] = fonte
        frames.append(grouped.sort_values("pl", ascending=False))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_concentration(admin_monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for comp, group in admin_monthly.groupby("competencia"):
        by_admin = group.groupby("admin_cnpj")["pl"].sum().sort_values(ascending=False)
        total = by_admin.sum()
        if total <= 0:
            continue
        shares = by_admin / total
        rows.append(
            {
                "competencia": comp,
                "n_admins": int((by_admin > 0).sum()),
                "hhi_admin": float((shares**2).sum()),
                "share_top5": float(shares.head(5).sum()),
                "share_top10": float(shares.head(10).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("competencia")


def run_pipeline(args: argparse.Namespace) -> None:
    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    store = RawStore(raw_dir=raw_dir, allow_download=not args.skip_download)

    months = month_range(args.start, args.end)
    industry_rows, segment_rows, flow_rows, cotista_rows, admin_rows = [], [], [], [], []
    processed = []
    for yyyymm in months:
        agg = aggregate_month(store, yyyymm)
        if agg is None:
            print(f"[warn] competencia {yyyymm} indisponivel; ignorada", file=sys.stderr)
            continue
        processed.append(yyyymm)
        industry_rows.append(agg.industry)
        segment_rows.extend(agg.segments)
        flow_rows.extend(agg.flows)
        cotista_rows.extend(agg.cotistas_tipo)
        admin_rows.extend(agg.admin)
        if len(processed) % 12 == 0:
            print(f"[info] processadas {len(processed)} competencias (ate {yyyymm})")

    if not processed:
        raise SystemExit("nenhuma competencia processada; verifique rede/arquivos brutos")

    industry = pd.DataFrame(industry_rows).sort_values("competencia")
    industry.to_csv(output_dir / "industry_monthly.csv", index=False)
    pd.DataFrame(segment_rows).to_csv(output_dir / "segments_monthly.csv", index=False)
    pd.DataFrame(flow_rows).to_csv(output_dir / "flows_monthly.csv", index=False)
    pd.DataFrame(cotista_rows).to_csv(output_dir / "cotistas_tipo_monthly.csv", index=False)
    admin_monthly = pd.DataFrame(admin_rows)
    admin_monthly.to_csv(output_dir / "admin_monthly.csv", index=False)
    build_concentration(admin_monthly).to_csv(
        output_dir / "concentration_monthly.csv", index=False
    )

    classe_map = load_classe_fundo_map(raw_dir, allow_download=not args.skip_download)
    # Foto do universo: ultima competencia "cheia" (a mais recente pode estar em
    # carga no dataset da CVM e viria com PL muito abaixo do mes anterior).
    last_month = args.snapshot_month or processed[-1]
    if not args.snapshot_month and len(industry) >= 2:
        tail = industry.tail(2)["pl_total"].tolist()
        if tail[-1] < 0.7 * tail[-2]:
            last_month = processed[-2]
    universe = build_universe_snapshot(store, last_month, classe_map)
    universe.to_csv(output_dir / "universe_latest.csv", index=False)
    build_prestadores_ranking(universe).to_csv(
        output_dir / "prestadores_latest.csv", index=False
    )

    metadata = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte_informe_mensal": f"{BASE_MONTHLY_URL} (+ HIST/)",
        "fonte_cadastro": REGISTRO_URL,
        "competencia_inicial": processed[0],
        "competencia_final": processed[-1],
        "competencia_snapshot": last_month,
        "n_competencias": len(processed),
        "observacoes": [
            "Unidade de observacao: veiculo reportante (fundo ate a adaptacao a RCVM 175, classe depois).",
            "PL total soma fundos legados e classes; nao ha dupla contagem fundo x classe no dataset.",
            "FIC-FIDC identificados por razao social; PL destacado em pl_fic_fidc (dupla contagem economica potencial).",
            "Cotistas = contas por classe/serie (Tab X.1), nao CPFs/CNPJs unicos.",
            "Captacao/resgate/amortizacao: Tab X.4 (valores de movimentacao de cotas no mes).",
            "Gestor e custodiante vem do cadastro vigente (foto), nao do informe mensal.",
            "Competencias recentes podem estar incompletas (entrega do informe ate 15 dias apos o fechamento; retificacoes ocorrem).",
        ],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] agregados gravados em {output_dir} ({len(processed)} competencias)")

    if args.report:
        render_report(output_dir, Path(args.report_path))
        print(f"[ok] relatorio gravado em {args.report_path}")


# ---------------------------------------------------------------------------
# Relatorio executivo
# ---------------------------------------------------------------------------

def _fmt_bi(value: float) -> str:
    return f"R$ {value / 1e9:,.1f} bi".replace(",", "@").replace(".", ",").replace("@", ".")


def _fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def render_report(data_dir: Path, report_path: Path) -> None:
    industry = pd.read_csv(data_dir / "industry_monthly.csv")
    segments = pd.read_csv(data_dir / "segments_monthly.csv")
    cotistas = pd.read_csv(data_dir / "cotistas_tipo_monthly.csv")
    concentration = pd.read_csv(data_dir / "concentration_monthly.csv")
    prestadores = pd.read_csv(data_dir / "prestadores_latest.csv")
    universe = pd.read_csv(data_dir / "universe_latest.csv")
    metadata = json.loads((data_dir / "metadata.json").read_text(encoding="utf-8"))

    industry = industry.sort_values("competencia").reset_index(drop=True)
    # Ultimo mes cheio = penultima competencia quando a ultima ainda esta em carga
    # (informes chegam ate ~15 dias apos o fechamento e ha retificacoes).
    last = industry.iloc[-1]
    ref = industry.iloc[-2] if len(industry) >= 2 and last["pl_total"] < 0.7 * industry.iloc[-2]["pl_total"] else last
    ref_comp = ref["competencia"]
    ref_year = int(ref_comp[:4])

    def industry_at(comp: str) -> pd.Series | None:
        match = industry[industry["competencia"] == comp]
        return match.iloc[0] if not match.empty else None

    def yoy_series(years_back: int) -> pd.Series | None:
        target = f"{ref_year - years_back}{ref_comp[4:]}"
        return industry_at(target)

    ref_12m = yoy_series(1)
    ref_dez2020 = industry_at("2020-12")
    ref_dez2019 = industry_at("2019-12")

    last12 = industry[industry["competencia"] <= ref_comp].tail(12)
    capt_bruta_12m = last12["captacoes"].sum()
    capt_liq_12m = last12["captacao_liquida"].sum()

    seg_top = (
        segments[(segments["competencia"] == ref_comp) & (segments["nivel"] == "top")]
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )
    seg_fin = (
        segments[(segments["competencia"] == ref_comp) & (segments["nivel"] == "sub")]
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )
    seg_total = seg_top["valor"].sum()

    cot_ref = (
        cotistas[cotistas["competencia"] == ref_comp]
        .sort_values("n_cotistas", ascending=False)
        .reset_index(drop=True)
    )
    conc_ref = concentration[concentration["competencia"] == ref_comp]
    conc_ref = conc_ref.iloc[0] if not conc_ref.empty else None

    def top_table(papel: str, n: int = 15) -> str:
        frame = prestadores[prestadores["papel"] == papel].head(n)
        if frame.empty:
            return "_Sem dados disponiveis._"
        lines = ["| # | Nome | PL | Share | Veiculos |", "|---|------|----|-------|----------|"]
        for idx, row in enumerate(frame.itertuples(), start=1):
            lines.append(
                f"| {idx} | {row.nome} | {_fmt_bi(row.pl)} | {_fmt_pct(row.share_pl)} | {row.n_veiculos} |"
            )
        return "\n".join(lines)

    def seg_table(frame: pd.DataFrame, total: float) -> str:
        lines = ["| Segmento | Carteira | Share |", "|----------|----------|-------|"]
        for row in frame.itertuples():
            share = row.valor / total if total else 0.0
            lines.append(f"| {row.segmento} | {_fmt_bi(row.valor)} | {_fmt_pct(share)} |")
        return "\n".join(lines)

    def cot_table(frame: pd.DataFrame) -> str:
        total = frame["n_cotistas"].sum()
        lines = ["| Tipo de cotista | Contas | Share |", "|-----------------|--------|-------|"]
        for row in frame.itertuples():
            share = row.n_cotistas / total if total else 0.0
            lines.append(f"| {row.tipo_cotista} | {_fmt_int(row.n_cotistas)} | {_fmt_pct(share)} |")
        return "\n".join(lines)

    def evolution_table() -> str:
        marks = ["2013-12", "2015-12", "2017-12", "2019-12", "2020-12", "2021-12",
                 "2022-12", "2023-12", "2024-12", "2025-12", ref_comp]
        lines = [
            "| Competencia | PL | Veiculos | Cotistas (contas) | Captacao liquida 12m |",
            "|-------------|----|----------|-------------------|----------------------|",
        ]
        seen = set()
        for comp in marks:
            if comp in seen:
                continue
            seen.add(comp)
            row = industry_at(comp)
            if row is None:
                continue
            window = industry[industry["competencia"] <= comp].tail(12)
            capt = window["captacao_liquida"].sum()
            cot = row.get("cotistas_total")
            cot_txt = _fmt_int(cot) if pd.notna(cot) else "n/d"
            lines.append(
                f"| {comp} | {_fmt_bi(row['pl_total'])} | {_fmt_int(row['n_veiculos'])} | {cot_txt} | {_fmt_bi(capt)} |"
            )
        return "\n".join(lines)

    n_fundos_unicos = universe["cnpj_fundo"].nunique() if not universe.empty else 0
    pl_nao_fic = ref["pl_total"] - ref.get("pl_fic_fidc", 0.0)
    growth_12m = (ref["pl_total"] / ref_12m["pl_total"] - 1) if ref_12m is not None else None
    growth_2020 = (ref["pl_total"] / ref_dez2020["pl_total"] - 1) if ref_dez2020 is not None else None
    veic_growth_2020 = (
        (ref["n_veiculos"] / ref_dez2020["n_veiculos"] - 1) if ref_dez2020 is not None else None
    )
    pl_2019 = ref_dez2019["pl_total"] if ref_dez2019 is not None else None

    report = f"""# Estudo da industria de FIDCs — base CVM (dados abertos)

**Data-base:** {ref_comp} · **Serie:** {metadata["competencia_inicial"]} a {metadata["competencia_final"]} · **Gerado em:** {metadata["gerado_em_utc"]}

> Relatorio gerado por `scripts/build_fidc_industry_study.py` a partir do dataset
> oficial *FIDC — Documentos: Informe Mensal* (Portal de Dados Abertos da CVM) e do
> cadastro `registro_fundo_classe`. Todos os agregados sao reconstruiveis a partir
> de `data/industry_study/`.

---

## 1. Sumario executivo

- **PL da industria: {_fmt_bi(ref["pl_total"])}** em {ref_comp}, distribuido em
  {_fmt_int(ref["n_veiculos"])} veiculos reportantes ({_fmt_int(ref["n_registros_classe"])} classes
  RCVM 175 + {_fmt_int(ref["n_registros_fundo"])} fundos ainda no regime legado), de
  {_fmt_int(n_fundos_unicos)} fundos unicos.
- **Crescimento:** {"+" + _fmt_pct(growth_12m) if growth_12m is not None else "n/d"} em 12 meses{f"; {'+' + _fmt_pct(growth_2020)} vs dez/2020" if growth_2020 is not None else ""}{f" (PL em dez/2019 era {_fmt_bi(pl_2019)})" if pl_2019 is not None else ""}.
- **Captacao:** {_fmt_bi(capt_bruta_12m)} de captacao bruta e {_fmt_bi(capt_liq_12m)} de
  captacao liquida nos 12 meses ate {ref_comp} (Tab X.4 do informe mensal).
- **Base de investidores:** {_fmt_int(ref.get("cotistas_total", 0))} contas de cotistas
  (conceito de contas por classe/serie, nao CPFs unicos).
- **Numero de veiculos** cresceu {"+" + _fmt_pct(veic_growth_2020) if veic_growth_2020 is not None else "n/d"} desde dez/2020.
- **Inadimplencia ajustada (DC vencidos e nao pagos / carteira, limitada a carteira
  de cada veiculo):** {_fmt_pct(ref.get("inad_pct_ajustada", 0))} em {ref_comp}
  (ex-FIDC NP: {_fmt_pct(ref.get("inad_pct_ajustada_ex_np", 0))}; bruta, com NPL a valor
  de face: {_fmt_pct(ref.get("inad_pct", 0))}).
- **Cotas subordinadas** respondem por {_fmt_pct(ref.get("subordinacao_pct", 0))} do valor
  total de cotas (inclui estruturas mono-classe subordinadas; ver metodologia).
- **Concentracao de administradores:** top 5 = {_fmt_pct(conc_ref["share_top5"]) if conc_ref is not None else "n/d"},
  top 10 = {_fmt_pct(conc_ref["share_top10"]) if conc_ref is not None else "n/d"},
  HHI = {f"{conc_ref['hhi_admin']:.3f}".replace(".", ",") if conc_ref is not None else "n/d"}.
- **FIC-FIDC:** {_fmt_bi(ref.get("pl_fic_fidc", 0.0))} do PL total sao veiculos identificados
  como FIC-FIDC pela razao social — ha dupla contagem economica potencial; PL ex-FIC:
  {_fmt_bi(pl_nao_fic)}.
- **Condominio:** {_fmt_pct(ref.get("pl_condominio_fechado", 0) / ref["pl_total"]) if ref["pl_total"] else "n/d"} do PL em
  condominio fechado; {_fmt_pct(ref.get("pl_condominio_aberto", 0) / ref["pl_total"]) if ref["pl_total"] else "n/d"} aberto.

## 2. Definicao e arcabouco regulatorio

FIDC e o fundo que destina a maior parte do patrimonio a direitos creditorios
(ICVM 356/489, hoje Anexo Normativo II da **Resolucao CVM 175**). Pontos que afetam
diretamente a leitura dos numeros:

1. **RCVM 175 (vigente para FIDCs desde out/2023, adaptacao ao longo de 2024):**
   a unidade regulatoria passou de *fundo* para *fundo -> classe -> subclasse*, com
   CNPJ proprio por classe. No informe mensal, veiculos adaptados reportam por
   classe (`TP_FUNDO_CLASSE = "Classe"`); nao adaptados seguem por fundo.
2. **Acesso ao varejo:** a RCVM 175 permitiu cotas de FIDC para o publico geral
   (antes restritas a investidores qualificados), um dos motores do crescimento
   da base de cotistas desde 2024.
3. **Responsabilidades:** administrador e gestor sao prestadores essenciais;
   custodia, registro/escrituracao e verificacao de lastro seguem regras proprias
   do Anexo II. No dado aberto, o administrador vem no proprio informe mensal;
   gestor e custodiante vem do cadastro.
4. **Informe mensal (fonte deste estudo):** entrega mensal obrigatoria, com
   retificacoes; competencias recentes mudam ate estabilizar.

## 3. Evolucao da industria

{evolution_table()}

Serie mensal completa em `data/industry_study/industry_monthly.csv`
(PL, ativo, carteira, captacoes, resgates, amortizacoes, cotistas, inadimplencia,
subordinacao, recompras, PL aberto/fechado/exclusivo e PL de FIC-FIDC).

## 4. Composicao por tipo de recebivel ({ref_comp})

Classificacao oficial da Tabela II do informe mensal (carteira de direitos
creditorios por segmento economico):

{seg_table(seg_top, seg_total)}

Abertura do segmento **Financeiro**:

{seg_table(seg_fin, seg_fin["valor"].sum())}

## 5. Mapa competitivo de prestadores ({ref_comp})

### 5.1 Administradores (fonte: informe mensal, auditavel mes a mes)

{top_table("administrador")}

### 5.2 Gestores (fonte: cadastro CVM vigente — foto, nao serie historica)

{top_table("gestor")}

### 5.3 Custodiantes (fonte: cadastro CVM `registro_classe` — foto)

{top_table("custodiante")}

Serie historica de concentracao (HHI, top 5, top 10 por administrador) em
`data/industry_study/concentration_monthly.csv`.

## 6. Base de investidores ({ref_comp})

{cot_table(cot_ref)}

Nota: o conceito e **contas por classe/serie** (Tab X.1.1), nao investidores
unicos. O mesmo investidor com posicoes em N classes conta N vezes; por isso este
numero nao bate com "contas" da ANBIMA nem com CPFs unicos da B3.

## 7. Qualidade de carteira e risco ({ref_comp})

- Carteira de direitos creditorios: {_fmt_bi(ref.get("carteira_dc", 0))}.
- **Inadimplencia ajustada: {_fmt_pct(ref.get("inad_pct_ajustada", 0))}**
  ({_fmt_pct(ref.get("inad_pct_ajustada_ex_np", 0))} excluindo FIDCs nao padronizados).
  A leitura "bruta" ({_fmt_pct(ref.get("inad_pct", 0))}) e distorcida por compradores de
  NPL, que reportam creditos vencidos pelo valor de FACE contra carteira a valor
  contabil — ha veiculos com "inadimplencia" superior a propria carteira, dai o
  ajuste que limita a inadimplencia de cada veiculo a sua carteira.
- Creditos a vencer com parcelas em atraso: {_fmt_bi(ref.get("dc_a_vencer_com_parcela_inad", 0))}.
- Recompras de DC no mes: {_fmt_bi(ref.get("vl_recompras", 0))}; substituicoes: {_fmt_bi(ref.get("vl_substituicoes", 0))}.
- Cotas subordinadas / total de cotas: {_fmt_pct(ref.get("subordinacao_pct", 0))}. Atencao:
  o numero inclui fundos inteiramente subordinados (estruturas captivas/mono-classe)
  e depende da nomenclatura das series; nao equivale ao "colchao de subordinacao"
  medio de estruturas com cotas senior.

## 8. Por que os numeros nao batem? (CVM x ANBIMA x Uqbar x midia)

| Causa | Efeito pratico |
|-------|----------------|
| **Universo** | CVM = todos os FIDCs registrados que entregam informe (inclui exclusivos, NP e FIC-FIDC). ANBIMA cobre a base informada a autorregulacao (~90% dos fundos, pelo convenio CVM-ANBIMA de jan/2025). Uqbar consolida securitizacao com metodologia proprietaria. |
| **PL vs AUM** | O PL CVM soma classes e fundos legados; soma inclui FIC-FIDC (dupla contagem economica de {_fmt_bi(ref.get("pl_fic_fidc", 0.0))} na data-base). |
| **Captacao liquida vs emissao** | Captacao liquida (X.4: captacoes - resgates - amortizacoes) nao e "emissoes/ofertas" (ANBIMA) nem "emissoes de mercado primario" (Uqbar). Um FIDC fechado pode emitir muito e amortizar em seguida. |
| **Fundo vs classe** | Pos-RCVM 175 a unidade virou classe. No cadastro CVM, a quase totalidade das classes de FIDC usa o proprio CNPJ do fundo (senior/subordinada viram *subclasses*), entao veiculos reportantes ~ fundos unicos nesta base; contagens de "classes" da ANBIMA seguem outro conceito/universo. |
| **Data-base** | A industria cresce ~2-3% ao mes; comparar nov/2025 com jan/2026 ja distorce. |
| **Contas vs investidores** | Cotistas CVM = contas por classe/serie; ANBIMA reporta contas de outra base; nenhum dos dois e CPF unico. |
| **Competencias em carga** | O ultimo mes do dataset CVM ainda recebe informes e retificacoes por semanas. |

**Numeros de referencia externos** (para reconciliacao; nao recalculados aqui):
ANBIMA reportou PL de R$ 741,1 bi (nov/2025), captacao liquida de R$ 57,6 bi (2025)
e R$ 90,1 bi em emissoes (dez/24-nov/25); Uqbar reportou PL de R$ 767,6 bi (jan/2026)
e emissoes acima de R$ 290 bi (2025). O PL CVM desta base em {ref_comp} e
{_fmt_bi(ref["pl_total"])} ({_fmt_bi(pl_nao_fic)} ex-FIC-FIDC) — acima da ANBIMA, como
esperado pela diferenca de universo.

## 9. Metodologia e reprodutibilidade

- **Fonte:** dataset publico *FIDC — Documentos: Informe Mensal* (CVM), tabelas
  I, II, IV, VII, X.1, X.1.1, X.2 e X.4; cadastro `registro_fundo_classe`.
- **Chave:** `CNPJ_FUNDO` ate a adaptacao a RCVM 175; `TP_FUNDO_CLASSE` +
  `CNPJ_FUNDO_CLASSE` depois. Sem sobreposicao entre fundos e classes no dataset.
- **Dedup:** uma linha por CNPJ por competencia (ultima ocorrencia).
- **Inadimplencia:** (`TAB_I2A3` + `TAB_I2B3`) / (`TAB_I2A` + `TAB_I2B`) — creditos
  vencidos e nao pagos sobre carteira de DC (com e sem aquisicao substancial de
  risco). Na versao **ajustada**, a inadimplencia de cada veiculo e limitada a sua
  propria carteira antes da agregacao (corrige NPL reportado a valor de face).
- **Subordinacao:** soma de `QT_COTA x VL_COTA` das series cujo nome contem
  "subordinada" sobre o total (Tab X.2), considerando apenas veiculos cujo valor
  total de cotas fica entre 0 e 3x o proprio PL (filtro de dados corrompidos).
- **Fluxos (Tab X.4):** linhas com valor acima de max(3x PL do veiculo, R$ 2 bi)
  sao descartadas como erro de preenchimento (valor descartado registrado em
  `x4_valor_descartado`).
- **Limitacoes conhecidas:** gestor/custodiante sao foto do cadastro vigente;
  FIC-FIDC e FIDC-NP identificados por razao social (heuristica); competencias
  recentes sujeitas a revisao; cotistas em base de contas.

Para atualizar: `python scripts/build_fidc_industry_study.py --report`.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", default=".cache/cvm-industry-study")
    parser.add_argument("--output-dir", default="data/industry_study")
    parser.add_argument("--start", default="2013-01", help="competencia inicial AAAA-MM")
    parser.add_argument(
        "--end",
        default=f"{date.today().year}-{date.today().month:02d}",
        help="competencia final AAAA-MM (default: mes corrente)",
    )
    parser.add_argument("--snapshot-month", default="", help="AAAAMM da foto do universo (default: ultima competencia)")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--report", action="store_true", help="gera tambem o relatorio executivo")
    parser.add_argument("--report-path", default="reports/fidc_industry_study.md")
    parser.add_argument("--report-only", action="store_true", help="so renderiza o relatorio a partir dos CSVs existentes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.report_only:
        render_report(Path(args.output_dir), Path(args.report_path))
        print(f"[ok] relatorio gravado em {args.report_path}")
        return
    run_pipeline(args)


if __name__ == "__main__":
    main()
