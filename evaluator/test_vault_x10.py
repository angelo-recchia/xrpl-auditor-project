#!/usr/bin/env python3
"""
Evaluador de Pruebas - Consulta y Análisis de Bóveda X10 (XLS-65 / XLS-66)
Valida la lógica de decodificación, cálculo de métricas y evaluación de liquidez.
"""

import json
import unittest

def parse_vault_data(hex_str: str) -> dict:
    if not hex_str:
        return {}
    try:
        raw = bytes.fromhex(hex_str).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {"raw": hex_str}

def evaluate_vault_metrics(vault_node: dict, loan_broker_node: dict = None) -> dict:
    assets_total_drops = int(vault_node.get("AssetsTotal", 0))
    assets_avail_drops = int(vault_node.get("AssetsAvailable", 0))
    assets_total_xrp = assets_total_drops / 1_000_000
    assets_avail_xrp = assets_avail_drops / 1_000_000
    locked_xrp = assets_total_xrp - assets_avail_xrp

    metadata = parse_vault_data(vault_node.get("Data", ""))
    
    debt_total_xrp = 0.0
    if loan_broker_node:
        debt_total_drops = int(loan_broker_node.get("DebtTotal", 0))
        debt_total_xrp = debt_total_drops / 1_000_000

    utilization_rate = (locked_xrp / assets_total_xrp * 100) if assets_total_xrp > 0 else 0.0

    status = "SALUDABLE"
    if utilization_rate > 90.0 or assets_avail_xrp <= 0:
        status = "CRÍTICO"
    elif utilization_rate > 75.0:
        status = "ESTRÉS"

    return {
        "vault_id": vault_node.get("index"),
        "name": metadata.get("n", "Desconocido"),
        "website": metadata.get("w", "N/A"),
        "total_xrp": assets_total_xrp,
        "available_xrp": assets_avail_xrp,
        "locked_xrp": locked_xrp,
        "debt_total_xrp": debt_total_xrp,
        "utilization_pct": round(utilization_rate, 2),
        "status": status,
        "share_mptid": vault_node.get("ShareMPTID"),
        "withdrawal_policy": vault_node.get("WithdrawalPolicy")
    }

class TestVaultX10(unittest.TestCase):
    def setUp(self):
        self.mock_vault_node = {
            "index": "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403",
            "LedgerEntryType": "Vault",
            "Owner": "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj",
            "Account": "r3MKhgLNG7JfMFVTgBeJeQAzR1Ng4Nx92h",
            "Asset": {"currency": "XRP"},
            "AssetsTotal": "100325925",
            "AssetsAvailable": "80162416",
            "Data": "7B226E223A22436F6C642073746F726167652058313020286D79207072696D6572205661756C742028424F5645444129222C2277223A22676F6F676C652E636F6D227D",
            "ShareMPTID": "0000000150A0473ED67EC32DF4A1F42BA35CC9882344EF38",
            "WithdrawalPolicy": 1
        }
        self.mock_broker_node = {
            "LedgerEntryType": "LoanBroker",
            "VaultID": "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403",
            "DebtTotal": "20163509",
            "DebtMaximum": "5000000000",
            "CoverAvailable": "10000000"
        }

    def test_metadata_decoding(self):
        parsed = parse_vault_data(self.mock_vault_node["Data"])
        self.assertIn("n", parsed)
        self.assertTrue("Cold storage X10" in parsed["n"])
        self.assertEqual(parsed.get("w"), "google.com")

    def test_metrics_calculation(self):
        metrics = evaluate_vault_metrics(self.mock_vault_node, self.mock_broker_node)
        self.assertAlmostEqual(metrics["total_xrp"], 100.325925, places=5)
        self.assertAlmostEqual(metrics["available_xrp"], 80.162416, places=5)
        self.assertAlmostEqual(metrics["locked_xrp"], 20.163509, places=5)
        self.assertAlmostEqual(metrics["debt_total_xrp"], 20.163509, places=5)
        self.assertEqual(metrics["status"], "SALUDABLE")
        self.assertEqual(metrics["withdrawal_policy"], 1)

    def test_stress_and_critical_states(self):
        stressed_vault = dict(self.mock_vault_node, AssetsAvailable="20000000") # 80% locked
        metrics_stress = evaluate_vault_metrics(stressed_vault)
        self.assertEqual(metrics_stress["status"], "ESTRÉS")

        critical_vault = dict(self.mock_vault_node, AssetsAvailable="0") # 100% locked
        metrics_critical = evaluate_vault_metrics(critical_vault)
        self.assertEqual(metrics_critical["status"], "CRÍTICO")

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas unitarias para Bóveda X10...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVaultX10)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para Bóveda X10 fueron exitosas.")
