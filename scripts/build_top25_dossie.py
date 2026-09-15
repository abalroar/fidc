"""Dossiê estruturado dos Top 25 FIDCs.

Cruza o snapshot do Toma Conta (Top 25 por PL) com o **Informe Mensal Estruturado
da CVM** (fonte universal: todo FIDC entrega) e com as leituras de regulamento já
existentes (cedentes/sacados nomeados). Para cada fundo extrai o máximo de dado
estruturado possível:

- identidade (admin/gestor consolidado, custodiante, condomínio, classe única)
- tipo de recebível / segmento
- estrutura de cotas: nº de classes/séries e subordinação (% subordinada)
- cedentes: nº total (Tab VII) e maiores com % (Tab I) + nomeados (regulamento)
- sacados/devedores: perfil de risco SCR (AA–C x D–H) + nomeados (regulamento)
- cotistas por tipo de investidor (Tab X_1_1) e institucionais
- emissões: nº de séries, ofertas por ano, safra e ano de início
- origem: quando/como surgiu (primeira oferta, última leitura de regulamento)

Saídas:
  reports/top25_fidc_dossie.csv     (uma linha por fundo)
  reports/top25_fidc_dossie.md      (dossiê narrativo por fundo)

Uso: python scripts/build_top25_dossie.py [--competencia 2026-05] [--top 25]
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.conglomerados import resolve  # noqa: E402

CVM_URL = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_{ym}.zip"
CACHE = ROOT / ".cache" / "cvm-ime"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# rótulos legíveis dos segmentos de investidor (Tab X_1_1)
INVESTIDOR = {
    "PF": "Pessoa física", "PJ_NAO_FINANC": "PJ não financeira", "BANCO": "Banco",
    "CORRETORA_DISTRIB": "Corretora/distribuidora", "PJ_FINANC": "PJ financeira",
    "INVNR": "Investidor não residente", "EAPC": "Prev. aberta (EAPC)",
    "EFPC": "Prev. fechada (EFPC)", "RPPS": "Regime próprio (RPPS)", "SEGUR": "Seguradora",
    "CAPITALIZ": "Capitalização", "COTA_FIDC": "Cotas de FIDC", "FII": "FII",
    "OUTRO_FI": "Outros fundos", "CLUBE": "Clube", "OUTRO": "Outros",
}
INSTITUCIONAIS = {"EAPC", "EFPC", "RPPS", "SEGUR", "CAPITALIZ"}


def _num(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except Exception:
        try:
            return float(s)
        except Exception:
            return 0.0


def _num_dot(s):
    """Campos da CVM com ponto decimal."""
    try:
        return float(s)
    except Exception:
        return 0.0


def download_ime(ym: str) -> zipfile.ZipFile:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"inf_mensal_fidc_{ym}.zip"
    if not dest.exists() or dest.stat().st_size < 1000:
        url = CVM_URL.format(ym=ym)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as resp:
                    dest.write_bytes(resp.read())
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
    return zipfile.ZipFile(dest)


def load_tab(z: zipfile.ZipFile, tab: str, ym: str) -> pd.DataFrame:
    name = f"inf_mensal_fidc_tab_{tab}_{ym}.csv"
    df = pd.read_csv(io.StringIO(z.read(name).decode("latin-1")), sep=";", dtype=str)
    df["root"] = df["CNPJ_FUNDO_CLASSE"].str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    return df


def _grp(nome, cnpj):
    return resolve(nome, cnpj)[0]


def build(competencia: str, topn: int, industry_dir: Path) -> tuple[pd.DataFrame, str]:
    ym = competencia.replace("-", "")
    snap = pd.read_csv(industry_dir / "industry_fund_snapshot.csv.gz")
    snap["pl"] = pd.to_numeric(snap["pl"], errors="coerce").fillna(0.0)
    snap["cotistas"] = pd.to_numeric(snap.get("cotistas"), errors="coerce")
    top = snap.sort_values("pl", ascending=False).head(topn).copy()
    top["c14"] = top["cnpj_fundo"].map(lambda x: str(int(x)).zfill(14))
    top["root"] = top["c14"].str[:8]

    z = download_ime(ym)
    tI = load_tab(z, "I", ym)
    tVII = load_tab(z, "VII", ym)
    tX = load_tab(z, "X", ym)
    tX1 = load_tab(z, "X_1", ym)
    tX11 = load_tab(z, "X_1_1", ym)
    tX2 = load_tab(z, "X_2", ym)

    # leituras de regulamento (cedentes/sacados nomeados)
    ced_struct = pd.read_csv(industry_dir / "cedentes_structured.csv.gz")
    ced_struct["root"] = ced_struct["cnpj_fundo"].map(lambda x: str(int(x)).zfill(14)[:8] if pd.notna(x) else "")

    seg_all = [c.replace("TAB_X_NR_COTST_SENIOR_", "") for c in tX11.columns if c.startswith("TAB_X_NR_COTST_SENIOR_")]

    rows = []
    dossie_md = [f"# Dossiê dos Top {topn} FIDCs — anatomia documental\n",
                 f"Competência {competencia}. Fonte: Informe Mensal Estruturado (CVM) + leituras de regulamento (Toma Conta).\n"]

    for _, r in top.iterrows():
        root = r["root"]; nome = str(r["nome_exibicao"])
        I = tI[tI["root"] == root]; VII = tVII[tVII["root"] == root]
        X = tX[tX["root"] == root]; X1 = tX1[tX1["root"] == root]
        X11 = tX11[tX11["root"] == root]; X2 = tX2[tX2["root"] == root]

        # estrutura
        n_classes = X1["TAB_X_CLASSE_SERIE"].nunique() if "TAB_X_CLASSE_SERIE" in X1 and len(X1) else len(X1)
        # subordinação a partir de X_2 (PL por classe = QT_COTA * VL_COTA)
        pl_sub = pl_tot = 0.0
        if len(X2):
            for _, cr in X2.iterrows():
                plc = _num_dot(cr.get("TAB_X_QT_COTA")) * _num_dot(cr.get("TAB_X_VL_COTA"))
                pl_tot += plc
                if "subordinada" in str(cr.get("TAB_X_CLASSE_SERIE", "")).lower():
                    pl_sub += plc
        sub_pct = (pl_sub / pl_tot * 100) if pl_tot else float("nan")

        # cedentes: identificados no Tab I (CNPJ + %, ponto decimal), somando entre classes
        ced_map = {}
        for _, rr in I.iterrows():
            for i in range(1, 10):
                cc = rr.get(f"TAB_I2A12_CPF_CNPJ_CEDENTE_{i}"); pr = rr.get(f"TAB_I2A12_PR_CEDENTE_{i}")
                cc = str(cc).strip() if cc else ""
                if cc and cc != "nan":
                    ced_map[cc] = max(ced_map.get(cc, 0.0), _num_dot(pr))
        top_ced = sorted(ced_map.items(), key=lambda x: -x[1])
        n_ced_id = len(top_ced)
        top_ced_pct = top_ced[0][1] if top_ced else float("nan")
        top3_ced_pct = round(sum(p for _, p in top_ced[:3]), 1) if top_ced else float("nan")
        maior_ced_lbl = ""
        if top_ced:
            grp = _grp(None, top_ced[0][0])
            maior_ced_lbl = grp if grp and not grp[0].isdigit() else ("CNPJ " + top_ced[0][0][:8])

        # carteira: qualidade do recebível (% vencido/inadimplente e judicial) — Tab I
        cart = _num_dot((I.iloc[0].get("TAB_I2A_VL_DIRCRED_RISCO") if len(I) else 0)) or 0.0
        venc_inad = jud = 0.0
        if len(I):
            rr = I.iloc[0]
            for f in ("TAB_I2A2_VL_CRED_VENC_INAD", "TAB_I2A3_VL_CRED_INAD"):
                venc_inad += _num_dot(rr.get(f))
            jud = _num_dot(rr.get("TAB_I2A8_VL_CRED_ACAO_JUDIC"))
        pct_inad = round(venc_inad / cart * 100, 1) if cart else float("nan")
        pct_jud = round(jud / cart * 100, 1) if cart else float("nan")

        # sacados/devedores: perfil de risco SCR (Tab X) AA..H
        scr = {g: _num_dot(X.iloc[0].get(f"TAB_X_SCR_RISCO_DEVEDOR_{g}")) if len(X) else 0.0
               for g in ["AA", "A", "B", "C", "D", "E", "F", "G", "H"]}
        scr_tot = sum(scr.values())
        scr_perf = (scr["AA"] + scr["A"] + scr["B"] + scr["C"]) / scr_tot * 100 if scr_tot else float("nan")

        # setor de cedente/sacado (leitura de regulamento, quando há)
        cs = ced_struct[ced_struct["root"] == root]
        setor_ced = " · ".join(sorted(set(cs[cs["tipo_participante"] == "cedente/originador"]["setor"].dropna()))[:2])
        setor_sac = " · ".join(sorted(set(cs[cs["tipo_participante"] == "sacado/devedor"]["setor"].dropna()))[:2])

        # cotistas por tipo de investidor
        seg_tot = {}
        for g in seg_all:
            v = 0
            for pref in ("SENIOR", "SUBORD"):
                col = f"TAB_X_NR_COTST_{pref}_{g}"
                if col in X11:
                    v += sum(int(_num(x)) for x in X11[col])
            if v > 0:
                seg_tot[INVESTIDOR.get(g, g)] = v
        n_cot = sum(seg_tot.values())
        top_seg = sorted(seg_tot.items(), key=lambda x: -x[1])[:3]
        n_inst = sum(v for g, v in seg_tot.items() if g in {INVESTIDOR[k] for k in INSTITUCIONAIS})

        row = {
            "#": len(rows) + 1,
            "fundo": nome[:70],
            "pl_bi": round(r["pl"] / 1e9, 2),
            "gestor": _grp(r.get("gestor_nome"), r.get("gestor_cnpj")),
            "admin": _grp(r.get("admin_nome"), r.get("admin_cnpj")),
            "custodiante": str(r.get("custodiante_nome", ""))[:30],
            "segmento": r.get("segmento_principal", ""),
            "condominio": r.get("condominio", ""),
            "classe_unica": r.get("exclusivo", ""),
            "n_classes_series": int(n_classes),
            "subordinacao_%": None if pd.isna(sub_pct) else round(sub_pct, 1),
            "n_cedentes_identificados": int(n_ced_id),
            "maior_cedente_%": None if pd.isna(top_ced_pct) else round(top_ced_pct, 1),
            "top3_cedentes_%": None if pd.isna(top3_ced_pct) else top3_ced_pct,
            "maior_cedente": maior_ced_lbl,
            "setor_cedente": setor_ced,
            "setor_sacado": setor_sac,
            "pct_vencido_inad": None if pd.isna(pct_inad) else pct_inad,
            "pct_judicial": None if pd.isna(pct_jud) else pct_jud,
            "sacado_perform_%": None if pd.isna(scr_perf) else round(scr_perf, 1),
            "n_cotistas": int(n_cot),
            "top_investidores": " · ".join(f"{k} ({v})" for k, v in top_seg),
            "n_cotistas_institucionais": int(n_inst),
            "n_ofertas_24_25_26": int(sum(_num(r.get(c, 0)) for c in ("offers_2024", "offers_2025", "offers_2026"))),
            "ano_1a_oferta": "" if pd.isna(r.get("first_offer_year")) else str(int(r.get("first_offer_year"))),
            "safra": r.get("emission_cohort", ""),
            "ultima_leitura_regulamento": r.get("latest_regulamento_date", ""),
        }
        rows.append(row)

        # dossiê narrativo
        dossie_md.append(f"\n## {row['#']}. {nome[:80]}  ·  R$ {row['pl_bi']:.1f} bi")
        dossie_md.append(f"- **Gestor/Admin/Custódia:** {row['gestor']} / {row['admin']} / {row['custodiante']}")
        dossie_md.append(f"- **Tipo:** {row['segmento']} · condomínio {row['condominio']} · classe única {row['classe_unica']}")
        dossie_md.append(f"- **Estrutura:** {row['n_classes_series']} classes/séries · subordinação "
                         f"{row['subordinacao_%'] if row['subordinacao_%'] is not None else 'n/d'}%")
        dossie_md.append(f"- **Cedentes:** {row['n_cedentes_identificados']} identificados · maior "
                         f"{row['maior_cedente_%'] if row['maior_cedente_%'] is not None else 'n/d'}%"
                         + (f" ({row['maior_cedente']})" if row['maior_cedente'] else "")
                         + (f" · top-3 {row['top3_cedentes_%']}%" if row['top3_cedentes_%'] is not None else "")
                         + (f" · setor: {row['setor_cedente']}" if row['setor_cedente'] else ""))
        dossie_md.append(f"- **Recebível:** {row['pct_vencido_inad'] if row['pct_vencido_inad'] is not None else 'n/d'}% vencido/inad · "
                         f"{row['pct_judicial'] if row['pct_judicial'] is not None else 'n/d'}% judicial · "
                         f"devedores {row['sacado_perform_%'] if row['sacado_perform_%'] is not None else 'n/d'}% AA–C"
                         + (f" · setor sacado: {row['setor_sacado']}" if row['setor_sacado'] else ""))
        dossie_md.append(f"- **Cotistas:** {row['n_cotistas']} · perfil: {row['top_investidores']} · institucionais: {row['n_cotistas_institucionais']}")
        dossie_md.append(f"- **Emissões/origem:** {row['n_ofertas_24_25_26']} ofertas 24–26 · 1ª oferta {row['ano_1a_oferta']} · safra {row['safra']}")

    df = pd.DataFrame(rows)
    return df, "\n".join(dossie_md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--competencia", default=None, help="YYYY-MM (default: do snapshot)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args()
    snap = pd.read_csv(args.industry_dir / "industry_fund_snapshot.csv.gz")
    comp = args.competencia or str(snap["competencia"].dropna().iloc[0])
    df, md = build(comp, args.top, args.industry_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "top25_fidc_dossie.csv"
    md_path = args.out / "top25_fidc_dossie.md"
    df.to_csv(csv_path, index=False)
    md_path.write_text(md, encoding="utf-8")
    print(f"[ok] {csv_path} ({len(df)} fundos)")
    print(f"[ok] {md_path}")
    # resumo de cobertura
    print(f"[cobertura] cedentes id: {(df['n_cedentes_identificados']>0).sum()}/{len(df)} · subord: {df['subordinacao_%'].notna().sum()}/{len(df)} · cotistas: {(df['n_cotistas']>0).sum()}/{len(df)}")


if __name__ == "__main__":
    main()
