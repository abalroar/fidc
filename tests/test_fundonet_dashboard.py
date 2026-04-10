from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from services.fundonet_dashboard import build_dashboard_data


class FundonetDashboardTests(unittest.TestCase):
    def test_build_dashboard_data_computes_summary_returns_and_event_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_fixture_csvs(workspace)

            dashboard = build_dashboard_data(
                wide_csv_path=workspace / "informes_wide.csv",
                listas_csv_path=workspace / "estruturas_lista.csv",
                docs_csv_path=workspace / "documentos_filtrados.csv",
            )

        self.assertEqual("01/2026", dashboard.latest_competencia)
        self.assertAlmostEqual(20_500.0, dashboard.summary["pl_total"] or 0.0)
        self.assertAlmostEqual(48.7804878, dashboard.summary["subordinacao_pct"] or 0.0, places=5)
        self.assertIsNone(dashboard.summary["direitos_creditorios"])
        self.assertIsNone(dashboard.summary["alocacao_pct"])
        self.assertEqual("12/2025", dashboard.composition_latest_df["competencia"].iloc[0])
        self.assertAlmostEqual(2_000.0, dashboard.summary["emissao_mes"] or 0.0)
        self.assertAlmostEqual(500.0, dashboard.summary["amortizacao_mes"] or 0.0)
        self.assertEqual(2, len(dashboard.event_history_df))

        senior_row = dashboard.return_summary_df[dashboard.return_summary_df["label"] == "Série 1"].iloc[0]
        self.assertAlmostEqual(2.0, senior_row["retorno_mes_pct"], places=6)
        self.assertAlmostEqual(2.0, senior_row["retorno_ano_pct"], places=6)
        self.assertAlmostEqual(3.02, senior_row["retorno_12m_pct"], places=2)

    def test_build_dashboard_data_exposes_fund_header_information(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_fixture_csvs(workspace)

            dashboard = build_dashboard_data(
                wide_csv_path=workspace / "informes_wide.csv",
                listas_csv_path=workspace / "estruturas_lista.csv",
                docs_csv_path=workspace / "documentos_filtrados.csv",
            )

        self.assertEqual("12345678000190", dashboard.fund_info["cnpj_fundo"])
        self.assertEqual("Teste FIDC RL", dashboard.fund_info["nome_fundo"])
        self.assertEqual("FECHADO", dashboard.fund_info["condominio"])
        self.assertEqual("12/2025 a 01/2026", dashboard.fund_info["periodo_analisado"])

    @staticmethod
    def _write_fixture_csvs(workspace: Path) -> None:
        wide_rows = [
            {
                "bloco": "CAB_INFORM",
                "sub_bloco": "",
                "tag": "NR_CNPJ_FUNDO",
                "tag_path": "DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO",
                "descricao": "CNPJ fundo",
                "12/2025": "12345678000190",
                "01/2026": "12345678000190",
            },
            {
                "bloco": "CAB_INFORM",
                "sub_bloco": "",
                "tag": "NR_CNPJ_CLASSE",
                "tag_path": "DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE",
                "descricao": "CNPJ classe",
                "12/2025": "12345678000190",
                "01/2026": "12345678000190",
            },
            {
                "bloco": "CAB_INFORM",
                "sub_bloco": "",
                "tag": "NR_CNPJ_ADM",
                "tag_path": "DOC_ARQ/CAB_INFORM/NR_CNPJ_ADM",
                "descricao": "CNPJ administrador",
                "12/2025": "99887766000155",
                "01/2026": "99887766000155",
            },
            {
                "bloco": "CAB_INFORM",
                "sub_bloco": "",
                "tag": "TP_CONDOMINIO",
                "tag_path": "DOC_ARQ/CAB_INFORM/TP_CONDOMINIO",
                "descricao": "Condomínio",
                "12/2025": "FECHADO",
                "01/2026": "FECHADO",
            },
            {
                "bloco": "CAB_INFORM",
                "sub_bloco": "",
                "tag": "CLASS_UNICA",
                "tag_path": "DOC_ARQ/CAB_INFORM/CLASS_UNICA",
                "descricao": "Classe única",
                "12/2025": "SIM",
                "01/2026": "SIM",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR",
                "tag": "SERIE",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR/SERIE",
                "descricao": "Série",
                "12/2025": "Série 1",
                "01/2026": "Série 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR",
                "tag": "QT_COTAS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR/QT_COTAS",
                "descricao": "Qt cotas",
                "12/2025": "100",
                "01/2026": "100",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR",
                "tag": "VL_COTAS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR/VL_COTAS",
                "descricao": "Vl cotas",
                "12/2025": "100",
                "01/2026": "105",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD",
                "tag": "TIPO",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/TIPO",
                "descricao": "Tipo",
                "12/2025": "Subordinada 1",
                "01/2026": "Subordinada 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD",
                "tag": "QT_COTAS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/QT_COTAS",
                "descricao": "Qt cotas",
                "12/2025": "500",
                "01/2026": "500",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD",
                "tag": "VL_COTAS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/VL_COTAS",
                "descricao": "Vl cotas",
                "12/2025": "18",
                "01/2026": "20",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "RENT_MES/RENT_CLASSE_SENIOR",
                "tag": "SERIE",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SENIOR/SERIE",
                "descricao": "Série",
                "12/2025": "Série 1",
                "01/2026": "Série 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "RENT_MES/RENT_CLASSE_SENIOR",
                "tag": "PR_APURADA",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SENIOR/PR_APURADA",
                "descricao": "Retorno",
                "12/2025": "1.00",
                "01/2026": "2.00",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "RENT_MES/RENT_CLASSE_SUBORD",
                "tag": "TIPO",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SUBORD/TIPO",
                "descricao": "Tipo",
                "12/2025": "Subordinada 1",
                "01/2026": "Subordinada 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "RENT_MES/RENT_CLASSE_SUBORD",
                "tag": "PR_APURADA",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SUBORD/PR_APURADA",
                "descricao": "Retorno",
                "12/2025": "0.50",
                "01/2026": "1.00",
            },
            {
                "bloco": "APLIC_ATIVO",
                "sub_bloco": "",
                "tag": "VL_SOM_APLIC_ATIVO",
                "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_SOM_APLIC_ATIVO",
                "descricao": "Ativos",
                "12/2025": "20000",
                "01/2026": "21000",
            },
            {
                "bloco": "APLIC_ATIVO",
                "sub_bloco": "",
                "tag": "VL_CARTEIRA",
                "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_CARTEIRA",
                "descricao": "Carteira",
                "12/2025": "15000",
                "01/2026": "18000",
            },
            {
                "bloco": "APLIC_ATIVO",
                "sub_bloco": "CRED_EXISTE",
                "tag": "VL_CRED_EXISTE_VENC_ADIMPL",
                "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_VENC_ADIMPL",
                "descricao": "Direitos",
                "12/2025": "12000",
                "01/2026": "0",
            },
            {
                "bloco": "APLIC_ATIVO",
                "sub_bloco": "CRED_EXISTE",
                "tag": "VL_CRED_TOTAL_VENC_INAD",
                "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_TOTAL_VENC_INAD",
                "descricao": "Inadimplência",
                "12/2025": "300",
                "01/2026": "0",
            },
            {
                "bloco": "APLIC_ATIVO",
                "sub_bloco": "CRED_EXISTE",
                "tag": "VL_PROVIS_REDUC_RECUP",
                "tag_path": "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_PROVIS_REDUC_RECUP",
                "descricao": "Provisão",
                "12/2025": "100",
                "01/2026": "0",
            },
            {
                "bloco": "NEGOC_DICRED_MES",
                "sub_bloco": "AQUISICOES",
                "tag": "VL_DICRED_AQUIS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/NEGOC_DICRED_MES/AQUISICOES/VL_DICRED_AQUIS",
                "descricao": "Aquisições",
                "12/2025": "1000",
                "01/2026": "800",
            },
            {
                "bloco": "NEGOC_DICRED_MES",
                "sub_bloco": "DICRED_MES_ALIEN",
                "tag": "VL_DICRED_ALIEN",
                "tag_path": "DOC_ARQ/LISTA_INFORM/NEGOC_DICRED_MES/DICRED_MES_ALIEN/VL_DICRED_ALIEN",
                "descricao": "Alienações",
                "12/2025": "200",
                "01/2026": "100",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "LIQUIDEZ",
                "tag": "VL_ATIV_LIQDEZ",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ",
                "descricao": "Liquidez",
                "12/2025": "500",
                "01/2026": "600",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "LIQUIDEZ",
                "tag": "VL_ATIV_LIQDEZ_30",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_30",
                "descricao": "Liquidez 30",
                "12/2025": "300",
                "01/2026": "350",
            },
            {
                "bloco": "COMPMT_DICRED_AQUIS",
                "sub_bloco": "",
                "tag": "VL_PRAZO_VENC_30",
                "tag_path": "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_30",
                "descricao": "Prazo 30",
                "12/2025": "2000",
                "01/2026": "0",
            },
            {
                "bloco": "COMPMT_DICRED_AQUIS",
                "sub_bloco": "",
                "tag": "VL_INAD_VENC_30",
                "tag_path": "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_30",
                "descricao": "Inad 30",
                "12/2025": "100",
                "01/2026": "0",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD",
                "tag": "TIPO",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD/TIPO",
                "descricao": "Tipo",
                "12/2025": "Subordinada 1",
                "01/2026": "Subordinada 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD",
                "tag": "VL_TOTAL",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD/VL_TOTAL",
                "descricao": "Emissão",
                "12/2025": "0",
                "01/2026": "2000",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD",
                "tag": "QT_COTAS",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD/QT_COTAS",
                "descricao": "Qt emissão",
                "12/2025": "0",
                "01/2026": "100",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR",
                "tag": "SERIE",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR/SERIE",
                "descricao": "Série",
                "12/2025": "Série 1",
                "01/2026": "Série 1",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR",
                "tag": "VL_TOTAL",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR/VL_TOTAL",
                "descricao": "Amortização",
                "12/2025": "0",
                "01/2026": "500",
            },
            {
                "bloco": "OUTRAS_INFORM",
                "sub_bloco": "CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR",
                "tag": "VL_COTA",
                "tag_path": "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR/VL_COTA",
                "descricao": "Amortização/cota",
                "12/2025": "0",
                "01/2026": "5",
            },
        ]
        pd.DataFrame(wide_rows).to_csv(workspace / "informes_wide.csv", index=False)

        listas_columns = [
            "competencia",
            "list_group_path",
            "list_index",
            "tag",
            "valor_excel",
        ]
        pd.DataFrame(columns=listas_columns).to_csv(workspace / "estruturas_lista.csv", index=False)

        docs_rows = [
            {
                "documento_id": "1",
                "competencia": "12/2025",
                "data_entrega": "20/01/2026 09:00",
                "fundo_ou_classe": "Classe",
                "nome_fundo": "Teste FIDC RL",
                "processamento": "ok",
            },
            {
                "documento_id": "2",
                "competencia": "01/2026",
                "data_entrega": "20/02/2026 09:00",
                "fundo_ou_classe": "Classe",
                "nome_fundo": "Teste FIDC RL",
                "processamento": "ok",
            },
        ]
        pd.DataFrame(docs_rows).to_csv(workspace / "documentos_filtrados.csv", index=False)


if __name__ == "__main__":
    unittest.main()
