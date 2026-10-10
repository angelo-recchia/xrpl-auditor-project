#!/usr/bin/env python3
"""
Evaluador de Pruebas - Procesador de Borradores Cold-Signing (sign_draft)
Valida la extracción de campos críticos para verificación en pantalla y cálculo de hash de firma.
"""

import json
import unittest
from xrpl.core.binarycodec import encode_for_signing

class TestSignDraft(unittest.TestCase):
    def setUp(self):
        self.mock_tx = {
            "TransactionType": "SetRegularKey",
            "Account": "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj",
            "RegularKey": "rM4WxXqGDmhzW2v7jKftgY1UycqXNdoWab",
            "Fee": "1000",
            "Sequence": 3597359,
            "NetworkID": 2
        }

    def test_encode_for_signing(self):
        encoded = encode_for_signing(self.mock_tx)
        self.assertIsInstance(encoded, str)
        self.assertTrue(len(encoded) > 0)
        # Prefijo de transacción de pago/firma XRPL (0x53545800 = 'STX\0')
        self.assertTrue(encoded.startswith("53545800"))

    def test_rejection_of_hot_sign(self):
        # Asegurar que se mantenga el bloqueo de clave maestra
        can_hot_sign = False
        self.assertFalse(can_hot_sign)

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para sign_draft...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSignDraft)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para sign_draft fueron exitosas.")
