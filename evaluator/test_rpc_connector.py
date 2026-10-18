"""
Test suite para XRPLRPCConnector en scripts/rpc_connector.py
Valida:
- Manejo de respuestas exitosas para Vault y Loan
- Captura de errores a nivel de protocolo rippled (HTTP 200 con error en payload)
- Captura de excepciones de transporte de red (ConnectionError, Timeout)
- Formato de resúmenes estructurados
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rpc_connector import XRPLRPCConnector


class TestXRPLRPCConnector(unittest.TestCase):
    def setUp(self):
        self.connector = XRPLRPCConnector("https://s.devnet.rippletest.net:51234")

    @patch.object(requests.Session, "post")
    def test_fetch_vault_state_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "result": {
                "status": "success",
                "node": {
                    "LedgerEntryType": "Vault",
                    "Account": "r3MKhgLNG7JfMFVTgBeJeQAzR1Ng4Nx92h",
                    "AssetsTotal": "150000000",
                    "AssetsAvailable": "150000000",
                    "ShareMPTID": "0000000150A0473ED67EC32DF4A1F42BA35CC9882344EF38",
                    "Sequence": 1
                }
            }
        }
        mock_post.return_value = mock_response

        res = self.connector.fetch_vault_state("24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403")

        self.assertTrue(res["success"])
        self.assertFalse(res["error"])
        self.assertEqual(res["ledger_entry_type"], "Vault")
        self.assertEqual(res["vault_summary"]["assets_total"], "150000000")
        self.assertEqual(res["vault_summary"]["account"], "r3MKhgLNG7JfMFVTgBeJeQAzR1Ng4Nx92h")

    @patch.object(requests.Session, "post")
    def test_fetch_loan_state_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "result": {
                "status": "success",
                "node": {
                    "LedgerEntryType": "Loan",
                    "Borrower": "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN",
                    "PrincipalOutstanding": "50000000",
                    "InterestRate": 1000,
                    "MaturityDate": 810000000
                }
            }
        }
        mock_post.return_value = mock_response

        res = self.connector.fetch_loan_state("A1B2C3D4E5F60123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123")

        self.assertTrue(res["success"])
        self.assertEqual(res["ledger_entry_type"], "Loan")
        self.assertEqual(res["loan_summary"]["borrower"], "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN")
        self.assertEqual(res["loan_summary"]["principal_outstanding"], "50000000")

    @patch.object(requests.Session, "post")
    def test_rippled_protocol_error(self, mock_post):
        # Rippled devuelve HTTP 200 pero status error en payload
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "result": {
                "status": "error",
                "error": "entryNotFound",
                "error_code": 33,
                "error_message": "The requested object was not found on the ledger."
            }
        }
        mock_post.return_value = mock_response

        res = self.connector.fetch_vault_state("NON_EXISTENT_HASH")

        self.assertFalse(res["success"])
        self.assertTrue(res["error"])
        self.assertEqual(res["error_type"], "RIPPLED_ERROR")
        self.assertEqual(res["rippled_error"], "entryNotFound")

    @patch.object(requests.Session, "post")
    def test_transport_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        res = self.connector.fetch_ledger_entry_by_index("ANY_HASH")

        self.assertFalse(res["success"])
        self.assertTrue(res["error"])
        self.assertEqual(res["error_type"], "TRANSPORT_ERROR")
        self.assertIn("Fallo de conexión HTTP", res["message"])


if __name__ == "__main__":
    unittest.main()
