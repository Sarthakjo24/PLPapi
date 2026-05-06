from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_env_alias_and_docs_urls_are_normalized(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ENV": "prod",
                "DOCS_URL": "docs",
                "REDOC_URL": "redoc",
                "OPENAPI_URL": "openapi.json",
            },
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.environment, "prod")
        self.assertEqual(settings.docs_url, "/docs")
        self.assertEqual(settings.redoc_url, "/redoc")
        self.assertEqual(settings.openapi_url, "/openapi.json")

    def test_cors_origins_support_json_and_csv_inputs(self) -> None:
        json_settings = Settings(
            _env_file=None,
            environment="dev",
            cors_origins='["https://app.example.com", "https://admin.example.com"]',
        )
        csv_settings = Settings(
            _env_file=None,
            environment="dev",
            cors_origins="https://app.example.com, https://admin.example.com",
        )

        expected = ["https://app.example.com", "https://admin.example.com"]
        self.assertEqual(json_settings.cors_origins, expected)
        self.assertEqual(csv_settings.cors_origins, expected)

    def test_validate_runtime_rejects_placeholder_prod_secrets(self) -> None:
        settings = Settings(_env_file=None, ENV="prod")
        with self.assertRaises(RuntimeError):
            settings.validate_runtime()
