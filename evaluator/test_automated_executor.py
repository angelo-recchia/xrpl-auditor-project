#!/usr/bin/env python3
"""
Evaluador de Pruebas - Ejecutor con Regular Key Delegada
Valida la comprobación de activación en ledger de la RegularKey antes del envío.
"""

import unittest

def verify_regular_key_active(account_data: dict, expected_regular_key: str) -> dict:
    if not account_data:
        return {"authorized": False, "reason": "Cuenta no encontrada"}

    actual_key = account_data.get("RegularKey")
    if not actual_key:
        return {
            "authorized": False,
            "reason": "La cuenta principal no tiene ninguna RegularKey autorizada en el ledger. Firme el borrador SetRegularKey en frío."
        }
    if actual_key != expected_regular_key:
        return {
            "authorized": False,
            "reason": f"RegularKey configurada ({actual_key}) no coincide con la clave delegada del bot ({expected_regular_key})."
        }

    return {"authorized": True, "reason": "RegularKey autorizada y activa en el ledger."}

class TestAutomatedExecutor(unittest.TestCase):
    def test_key_not_set(self):
        acct_data = {"Account": "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj", "Balance": "1000000"}
        res = verify_regular_key_active(acct_data, "rM4WxXqGDmhzW2v7jKftgY1UycqXNdoWab")
        self.assertFalse(res["authorized"])
        self.assertIn("Firme el borrador SetRegularKey", res["reason"])

    def test_key_active(self):
        acct_data = {
            "Account": "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj",
            "RegularKey": "rM4WxXqGDmhzW2v7jKftgY1UycqXNdoWab"
        }
        res = verify_regular_key_active(acct_data, "rM4WxXqGDmhzW2v7jKftgY1UycqXNdoWab")
        self.assertTrue(res["authorized"])

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para automated_executor...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAutomatedExecutor)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para automated_executor fueron exitosas.")
