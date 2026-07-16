from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib import error

from services.portfolio_store import (
    GitHubPortfolioStore,
    PortfolioFund,
    PortfolioRecord,
    build_portfolio_store,
    portfolio_basket_signature,
    resolve_portfolio_store_config,
)


class _FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return None


class PortfolioStoreTests(unittest.TestCase):
    def test_portfolio_basket_signature_is_order_insensitive(self) -> None:
        funds_a = (
            PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
            PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
        )
        funds_b = (
            PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
            PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
        )

        self.assertEqual(
            portfolio_basket_signature(funds_a),
            portfolio_basket_signature(funds_b),
        )

    def test_local_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = build_portfolio_store(
                resolve_portfolio_store_config(
                    secrets_mapping={"local_portfolios_path": str(Path(tmp_dir) / "portfolios.json")}
                )
            )
            stored = store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-1",
                    name="Carteira Teste",
                    funds=(
                        PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),
                        PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),
                    ),
                    created_at="2026-04-14T12:00:00Z",
                    updated_at="2026-04-14T12:00:00Z",
                )
            )

            portfolios = store.list_portfolios()
            self.assertEqual(1, len(portfolios))
            self.assertEqual("Carteira Teste", portfolios[0].name)
            self.assertEqual("portfolio-1", stored.id)

            store.delete_portfolio("portfolio-1")
            self.assertEqual([], store.list_portfolios())

    def test_local_store_persists_multiple_portfolios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = build_portfolio_store(
                resolve_portfolio_store_config(
                    secrets_mapping={"local_portfolios_path": str(Path(tmp_dir) / "portfolios.json")}
                )
            )
            store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-1",
                    name="Carteira A",
                    funds=(PortfolioFund(cnpj="12345678000199", display_name="FIDC A"),),
                    created_at="2026-04-14T12:00:00Z",
                    updated_at="2026-04-14T12:00:00Z",
                )
            )
            store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-2",
                    name="Carteira B",
                    funds=(PortfolioFund(cnpj="22345678000199", display_name="FIDC B"),),
                    created_at="2026-04-14T12:05:00Z",
                    updated_at="2026-04-14T12:05:00Z",
                )
            )

            portfolios = store.list_portfolios()

        self.assertEqual(2, len(portfolios))
        self.assertEqual({"Carteira A", "Carteira B"}, {portfolio.name for portfolio in portfolios})

    def test_local_store_seeds_missing_cache_and_preserves_every_existing_portfolio_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            seed_path = root / "portfolios.json"
            local_path = root / ".cache" / "portfolios.local.json"
            seed_payload = {
                "schema_version": 1,
                "portfolios": [
                    {
                        "id": "portfolio-a",
                        "name": "Carteira A",
                        "funds": [{"cnpj": "12345678000199", "display_name": "FIDC A"}],
                        "created_at": "2026-04-14T12:00:00Z",
                        "updated_at": "2026-04-14T12:00:00Z",
                        "notes": "",
                    },
                    {
                        "id": "portfolio-b",
                        "name": "Carteira B",
                        "funds": [{"cnpj": "22345678000199", "display_name": "FIDC B"}],
                        "created_at": "2026-04-14T12:00:00Z",
                        "updated_at": "2026-04-14T12:00:00Z",
                        "notes": "",
                    },
                ],
            }
            seed_text = json.dumps(seed_payload, ensure_ascii=False, indent=2)
            seed_path.write_text(seed_text, encoding="utf-8")
            store = build_portfolio_store(
                resolve_portfolio_store_config(
                    secrets_mapping={
                        "local_portfolios_path": str(local_path),
                        "local_portfolios_seed_path": str(seed_path),
                    }
                )
            )

            self.assertEqual({"Carteira A", "Carteira B"}, {item.name for item in store.list_portfolios()})
            self.assertFalse(local_path.exists())

            store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-c",
                    name="Carteira C",
                    funds=(PortfolioFund(cnpj="32345678000199", display_name="FIDC C"),),
                    created_at="2026-04-14T12:05:00Z",
                    updated_at="2026-04-14T12:05:00Z",
                )
            )

            self.assertTrue(local_path.exists())
            self.assertEqual(
                {"Carteira A", "Carteira B", "Carteira C"},
                {item.name for item in store.list_portfolios()},
            )
            self.assertEqual(seed_text, seed_path.read_text(encoding="utf-8"))
            self.assertEqual([], list(local_path.parent.glob(f".{local_path.name}.*.tmp")))

    def test_local_store_keeps_existing_local_file_authoritative_over_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            seed_path = root / "portfolios.json"
            local_path = root / ".cache" / "portfolios.local.json"
            local_path.parent.mkdir(parents=True)
            seed_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "portfolios": [
                            {
                                "id": "seed",
                                "name": "Carteira Seed",
                                "funds": [{"cnpj": "12345678000199", "display_name": "Seed"}],
                                "created_at": "2026-04-14T12:00:00Z",
                                "updated_at": "2026-04-14T12:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            local_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "portfolios": [
                            {
                                "id": "local",
                                "name": "Carteira Local",
                                "funds": [{"cnpj": "22345678000199", "display_name": "Local"}],
                                "created_at": "2026-04-14T12:00:00Z",
                                "updated_at": "2026-04-14T12:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = build_portfolio_store(
                resolve_portfolio_store_config(
                    secrets_mapping={
                        "local_portfolios_path": str(local_path),
                        "local_portfolios_seed_path": str(seed_path),
                    }
                )
            )

            self.assertEqual(["Carteira Local"], [item.name for item in store.list_portfolios()])

    def test_local_store_rejects_duplicate_name_and_same_basket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = build_portfolio_store(
                resolve_portfolio_store_config(
                    secrets_mapping={"local_portfolios_path": str(Path(tmp_dir) / "portfolios.json")}
                )
            )
            store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-1",
                    name="MELI (FIDCs Mercado Crédito 0, I e II)",
                    funds=(
                        PortfolioFund(cnpj="33254370000104", display_name="FIDC A"),
                        PortfolioFund(cnpj="37511828000114", display_name="FIDC B"),
                        PortfolioFund(cnpj="41970012000126", display_name="FIDC C"),
                    ),
                    created_at="2026-04-14T12:00:00Z",
                    updated_at="2026-04-14T12:00:00Z",
                )
            )

            with self.assertRaisesRegex(ValueError, "seleção idêntica"):
                store.save_portfolio(
                    PortfolioRecord(
                        id="portfolio-2",
                        name="MELI (FIDCs Mercado Crédito 0, I e II)",
                        funds=(
                            PortfolioFund(cnpj="41970012000126", display_name="FIDC C"),
                            PortfolioFund(cnpj="37511828000114", display_name="FIDC B"),
                            PortfolioFund(cnpj="33254370000104", display_name="FIDC A"),
                        ),
                        created_at="2026-04-14T12:05:00Z",
                        updated_at="2026-04-14T12:05:00Z",
                    )
                )

    def test_resolve_config_prefers_github_when_repo_and_token_exist(self) -> None:
        config = resolve_portfolio_store_config(
            secrets_mapping={
                "github_repo": "abalroar/fidc",
                "github_branch": "main",
                "github_portfolios_path": "state/portfolios.json",
                "github_token": "token",
            }
        )

        self.assertEqual("github", config.backend)
        self.assertEqual("abalroar/fidc", config.repo)
        self.assertEqual("state/portfolios.json", config.path)

    def test_default_local_config_uses_versioned_portfolios_as_seed(self) -> None:
        config = resolve_portfolio_store_config(secrets_mapping={}, environ={})

        self.assertEqual("local", config.backend)
        self.assertEqual(".cache/portfolios.local.json", config.local_path)
        self.assertEqual("portfolios.json", config.local_seed_path)

    def test_custom_local_path_requires_explicit_seed(self) -> None:
        config = resolve_portfolio_store_config(
            secrets_mapping={"local_portfolios_path": "/tmp/custom-portfolios.json"},
            environ={},
        )

        self.assertEqual("local", config.backend)
        self.assertIsNone(config.local_seed_path)

    def test_github_store_reads_and_writes_contents_api(self) -> None:
        encoded = base64.b64encode(
            json.dumps({"schema_version": 1, "portfolios": []}).encode("utf-8")
        ).decode("utf-8")
        requests_seen = []

        def fake_urlopen(req, timeout=20):  # noqa: ANN001
            requests_seen.append(req)
            if req.get_method() == "GET":
                return _FakeResponse({"content": encoded, "sha": "sha-123"})
            return _FakeResponse({})

        store = GitHubPortfolioStore(
            repo="abalroar/fidc",
            branch="main",
            path="portfolios.json",
            token="token",
        )

        with patch("services.portfolio_store.request.urlopen", side_effect=fake_urlopen):
            stored = store.save_portfolio(
                PortfolioRecord(
                    id="portfolio-2",
                    name="Carteira GitHub",
                    funds=(PortfolioFund(cnpj="32345678000199", display_name="FIDC GH"),),
                    created_at="2026-04-14T12:00:00Z",
                    updated_at="2026-04-14T12:00:00Z",
                )
            )

        self.assertEqual("Carteira GitHub", stored.name)
        self.assertEqual(2, len(requests_seen))
        self.assertEqual("GET", requests_seen[0].get_method())
        self.assertEqual("PUT", requests_seen[1].get_method())

    def test_github_delete_retries_write_conflict(self) -> None:
        payload = {
            "schema_version": 1,
            "portfolios": [
                {
                    "id": "portfolio-1",
                    "name": "Carteira GitHub",
                    "funds": [{"cnpj": "32345678000199", "display_name": "FIDC GH"}],
                    "created_at": "2026-04-14T12:00:00Z",
                    "updated_at": "2026-04-14T12:00:00Z",
                    "notes": "",
                }
            ],
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        requests_seen = []
        put_attempts = 0

        def fake_urlopen(req, timeout=20):  # noqa: ANN001
            nonlocal put_attempts
            requests_seen.append(req)
            if req.get_method() == "GET":
                return _FakeResponse({"content": encoded, "sha": "sha-123"})
            put_attempts += 1
            if put_attempts == 1:
                raise error.HTTPError(req.full_url, 409, "Conflict", hdrs=None, fp=None)
            written = json.loads(req.data.decode("utf-8"))
            decoded = json.loads(base64.b64decode(written["content"]).decode("utf-8"))
            self.assertEqual([], decoded["portfolios"])
            return _FakeResponse({})

        store = GitHubPortfolioStore(
            repo="abalroar/fidc",
            branch="main",
            path="portfolios.json",
            token="token",
        )

        with patch("services.portfolio_store.request.urlopen", side_effect=fake_urlopen):
            store.delete_portfolio("portfolio-1")

        self.assertEqual(4, len(requests_seen))
        self.assertEqual(["GET", "PUT", "GET", "PUT"], [request.get_method() for request in requests_seen])


if __name__ == "__main__":
    unittest.main()
