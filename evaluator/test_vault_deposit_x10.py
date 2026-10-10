#!/usr/bin/env python3
"""
Evaluador de Pruebas - Depósito en Bóveda XLS-65 (VaultDeposit)
Valida la estructura del borrador, cálculo de métricas post-depósito, inspección de cartera y guardia de seguridad ante --execute y --devnet-bypass.
"""

import unittest

def build_vault_deposit_draft(depositor_account: str, vault_id: str, amount_xrp: float, sequence: int = 1, fee_drops: str = "1000", network_id: int = 2) -> dict:
    if not depositor_account.startswith("r"):
        raise ValueError("Cuenta depositante inválida")
    if len(vault_id) != 64:
        raise ValueError("VaultID debe ser de 64 caracteres hex")

    amount_drops = int(amount_xrp * 1_000_000)
    return {
        "template_meta": {
            "template_id": "test_deposit",
            "version": "1.0.0",
            "network": "XRPL Devnet",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"VaultDeposit XLS-65 — Depósito de {amount_xrp} XRP"
        },
        "transaction": {
            "TransactionType": "VaultDeposit",
            "Account": depositor_account,
            "VaultID": vault_id,
            "Amount": str(amount_drops),
            "Fee": fee_drops,
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "cold_signing": {
            "status": "PENDING",
            "device": "Ledger Nano S Plus / Tangem / Xaman"
        }
    }

def format_wallet_metrics(account_data: dict) -> dict:
    if not account_data:
        return {"active": False, "balance_xrp": 0.0, "spendable_xrp": 0.0, "sequence": 0}
    bal_drops = int(account_data.get("Balance", 0))
    bal_xrp = bal_drops / 1_000_000
    spendable = max(0.0, bal_xrp - 10.0) # Reserva base 10 XRP
    return {
        "active": True,
        "balance_xrp": round(bal_xrp, 6),
        "spendable_xrp": round(spendable, 6),
        "sequence": int(account_data.get("Sequence", 0))
    }

def check_execute_security_guard(execute_flag: bool, bypass_flag: bool = False) -> dict:
    if bypass_flag:
        return {
            "blocked": True,
            "rejection_code": "SEC_ERR_BYPASS_ATTEMPT_DENIED",
            "reason": "VIOLACIÓN DE POLÍTICA: Intentos de bypass o evasión de controles en frío están terminantemente bloqueados. Las claves privadas jamás se exponen en este entorno."
        }
    if execute_flag:
        return {
            "blocked": True,
            "rejection_code": "SEC_STRICT_COLD_SIGNING",
            "reason": "POLÍTICA DE SEGURIDAD: La firma en caliente y envío directo están deshabilitados. Toda transacción debe firmarse en frío mediante hardware wallet (Ledger / Tangem / Xaman)."
        }
    return {"blocked": False, "reason": None}

class TestVaultDepositX10(unittest.TestCase):
    def test_draft_structure(self):
        vault_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
        depositor = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
        draft = build_vault_deposit_draft(depositor, vault_id, 100.0)

        self.assertEqual(draft["transaction"]["TransactionType"], "VaultDeposit")
        self.assertEqual(draft["transaction"]["Amount"], "100000000")
        self.assertEqual(draft["transaction"]["VaultID"], vault_id)
        self.assertEqual(draft["transaction"]["Account"], depositor)
        self.assertEqual(draft["template_meta"]["status"], "DRAFT_UNSIGNED")
        self.assertEqual(draft["cold_signing"]["status"], "PENDING")

    def test_invalid_account(self):
        vault_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
        with self.assertRaises(ValueError):
            build_vault_deposit_draft("invalid_address", vault_id, 100.0)

    def test_wallet_metrics(self):
        mock_data = {"Balance": "394803286", "Sequence": 3597359}
        metrics = format_wallet_metrics(mock_data)
        self.assertTrue(metrics["active"])
        self.assertAlmostEqual(metrics["balance_xrp"], 394.803286, places=5)
        self.assertAlmostEqual(metrics["spendable_xrp"], 384.803286, places=5)
        self.assertEqual(metrics["sequence"], 3597359)

    def test_security_guard(self):
        res = check_execute_security_guard(True)
        self.assertTrue(res["blocked"])
        self.assertIn("POLÍTICA DE SEGURIDAD", res["reason"])

    def test_bypass_guard(self):
        res = check_execute_security_guard(True, bypass_flag=True)
        self.assertTrue(res["blocked"])
        self.assertEqual(res["rejection_code"], "SEC_ERR_BYPASS_ATTEMPT_DENIED")

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para vault_deposit_x10...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVaultDepositX10)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para vault_deposit_x10 fueron exitosas.")
