"""
Test suite para TelegramAlertGateway en scripts/alert_gateway.py
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.alert_gateway import TelegramAlertGateway


class TestTelegramAlertGateway(unittest.TestCase):
    def test_placeholder_token_skips_request(self):
        gateway = TelegramAlertGateway(bot_token="12345:***", chat_id="6439172775")
        res = gateway.send_alert("Test alert")
        self.assertFalse(res["success"])
        self.assertFalse(res["sent"])
        self.assertIn("placeholders", res["message"])

    def test_empty_chat_id_skips_request(self):
        gateway = TelegramAlertGateway(bot_token="12345:ABCDEF", chat_id="")
        res = gateway.send_alert("Test alert")
        self.assertFalse(res["success"])
        self.assertFalse(res["sent"])

    @patch.object(requests.Session, "post")
    def test_successful_alert(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 999}}
        mock_post.return_value = mock_resp

        gateway = TelegramAlertGateway(bot_token="12345:ABC_VALID_TOKEN", chat_id="6439172775")
        res = gateway.send_alert("Alerta exitosa")

        self.assertTrue(res["success"])
        self.assertTrue(res["sent"])
        self.assertEqual(res["result"]["message_id"], 999)

    @patch.object(requests.Session, "post")
    def test_transport_error_handled(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Network down")

        gateway = TelegramAlertGateway(bot_token="12345:ABC_VALID_TOKEN", chat_id="6439172775")
        res = gateway.send_alert("Alerta con red caída")

        self.assertFalse(res["success"])
        self.assertFalse(res["sent"])
        self.assertIn("Network down", res["message"])


if __name__ == "__main__":
    unittest.main()
