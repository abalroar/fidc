from __future__ import annotations

from pathlib import Path
import unittest

from services.fundonet_parser import parse_informe_mensal_xml


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fundonet_822193.xml"


class ParseInformeMensalXmlTests(unittest.TestCase):
    def test_parse_real_xml_extracts_metadata_scalars_and_lists(self) -> None:
        parsed = parse_informe_mensal_xml(FIXTURE_PATH.read_bytes(), doc_id=822193)

        self.assertEqual("12/2024", parsed.metadata["competencia_xml"])
        self.assertEqual("6.1", parsed.metadata["xml_version"])
        self.assertFalse(parsed.scalar_df.empty)
        self.assertFalse(parsed.list_df.empty)
        self.assertIn("DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB", parsed.scalar_df["tag_path"].tolist())
        self.assertIn(
            "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/LISTA_CEDENT_CRED_EXISTE/CEDENT_CRED_EXISTE",
            parsed.list_df["list_group_path"].tolist(),
        )

    def test_parse_real_xml_handles_comma_dot_and_negative_values(self) -> None:
        parsed = parse_informe_mensal_xml(FIXTURE_PATH.read_bytes(), doc_id=822193)

        disponibilidades = parsed.scalar_df.loc[
            parsed.scalar_df["tag_path"] == "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB"
        ].iloc[0]
        valor_cota = parsed.scalar_df.loc[
            parsed.scalar_df["tag_path"]
            == "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR/VL_COTAS"
        ].iloc[0]
        percentual_apurado = parsed.scalar_df.loc[
            parsed.scalar_df["tag_path"]
            == "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SENIOR/PR_APURADA"
        ].iloc[0]
        outro_dicred = parsed.scalar_df.loc[
            parsed.scalar_df["tag_path"] == "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VALORES_MOB/VL_OUTRO_DICRED"
        ].iloc[0]

        self.assertEqual("30761196,40", disponibilidades["valor_raw"])
        self.assertAlmostEqual(30761196.40, float(disponibilidades["valor_num"]))
        self.assertEqual("1205.78565646", valor_cota["valor_raw"])
        self.assertAlmostEqual(1205.78565646, float(valor_cota["valor_num"]))
        self.assertEqual("1.16", percentual_apurado["valor_raw"])
        self.assertAlmostEqual(1.16, float(percentual_apurado["valor_num"]))
        self.assertEqual("-273275,10", outro_dicred["valor_raw"])
        self.assertAlmostEqual(-273275.10, float(outro_dicred["valor_num"]))


if __name__ == "__main__":
    unittest.main()
