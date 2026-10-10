#!/usr/bin/env python3
"""
Evaluador de Pruebas - Configuración de Regular Key Delegada
Valida la estructura del payload SetRegularKey y la separación estricta entre clave maestra y delegada.
"""

import unittest

def build_set_regular_key_draft(master_account: str, regular_key_account: str, sequence: int = 1, fee_drops: str = "1000", network_id: int = 2) -> dict:
    if not master_account.startswith("r") or not regular_key_account.startswith("r"):
        raise ValueError("Direcciones XRPL inválidas")
    if master_account == regular_key_account:
        raise ValueError("La RegularKey no puede ser idéntica a la cuenta principal")

    return {
        "template_meta": {
            "template_id": "test_set_regular_key",
            "version": "1.0.0",
            "network": "XRPL Devnet",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"SetRegularKey — Delegación de firma para automatizaciones Devnet a {regular_key_account}"
        },
        "transaction": {
            "TransactionType": "SetRegularKey",
            "Account": master_account,
            "RegularKey": regular_key_account,
            "Fee": fee_drops,
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "cold_signing": {
            "status": "PENDING_MASTER_KEY_SIGNATURE",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "note": "Firmar UNA SOLA VEZ con la clave maestra en frío para habilitar la delegación."
        }
    }

class TestRegularKey(unittest.TestCase):
    def test_draft_structure(self):
        master = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
        regular = "rMaKA3J9m6tbJ2ziHDTDPbTNGaCKSqeSjs"
        draft = build_set_regular_key_draft(master, regular, sequence=3597359)

        self.assertEqual(draft["transaction"]["TransactionType"], "SetRegularKey")
        self.assertEqual(draft["transaction"]["Account"], master)
        self.assertEqual(draft["transaction"]["RegularKey"], regular)
        self.assertEqual(draft["cold_signing"]["status"], "PENDING_MASTER_KEY_SIGNATURE")

    def test_identical_addresses_rejected(self):
        master = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
        with self.assertRaises(ValueError):
            build_set_regular_key_draft(master, master)

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para regular_key...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRegularKey)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para regular_key fueron exitosas.")
