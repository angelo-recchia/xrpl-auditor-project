#!/usr/bin/env python3
"""
Evaluador de Pruebas - Automatización de Pagos XLS-66 (LoanPayment)
Valida la estructura del borrador, longitud y formato del VaultID, y campos requeridos para cold-signing.
"""

import json
import re
import unittest

def validate_vault_id(vault_id: str) -> bool:
    if not vault_id or len(vault_id) != 64:
        return False
    return bool(re.fullmatch(r"[0-9A-Fa-f]{64}", vault_id))

def generate_payment_draft(vault_id: str, borrower: str, amount_xrp: float, fee_drops: str = "1000", sequence: int = 1, network_id: int = 2) -> dict:
    if not validate_vault_id(vault_id):
        raise ValueError(f"VaultID inválido: debe ser hex de 64 caracteres, recibido len={len(vault_id)}")

    amount_drops = int(amount_xrp * 1_000_000)
    return {
        "template_meta": {
            "template_id": "auto_payment_x10_test",
            "version": "1.0.0",
            "network": "XRPL Devnet",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"LoanPayment XLS-66 — Amortización de {amount_xrp} XRP"
        },
        "payment_context": {
            "vault_id": vault_id,
            "payer": borrower,
            "amount_xrp": amount_xrp,
            "amount_drops": amount_drops
        },
        "transaction": {
            "TransactionType": "LoanPayment",
            "Account": borrower,
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

class TestAutoPaymentX10(unittest.TestCase):
    def test_vault_id_validation(self):
        valid_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
        invalid_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C781D08099B403" # 66 chars
        self.assertTrue(validate_vault_id(valid_id))
        self.assertFalse(validate_vault_id(invalid_id))
        self.assertFalse(validate_vault_id("not_hex"))

    def test_payment_draft_generation(self):
        valid_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
        draft = generate_payment_draft(valid_id, "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN", 3.374428)
        self.assertEqual(draft["transaction"]["TransactionType"], "LoanPayment")
        self.assertEqual(draft["transaction"]["VaultID"], valid_id)
        self.assertEqual(draft["template_meta"]["status"], "DRAFT_UNSIGNED")
        self.assertEqual(draft["cold_signing"]["status"], "PENDING")

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para auto_payment_x10...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAutoPaymentX10)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para auto_payment_x10 fueron exitosas.")
