#!/usr/bin/env python3
"""
Evaluador de Pruebas - Envío de Blobs Firmados (submit_signed_blob)
Valida la validación sintáctica del blob hexadecimal antes de la transmisión.
"""

import re
import unittest

def validate_blob_syntax(blob_hex: str) -> bool:
    if not blob_hex or len(blob_hex) < 32:
        return False
    return bool(re.fullmatch(r"[0-9A-Fa-f]+", blob_hex))

class TestSubmitSignedBlob(unittest.TestCase):
    def test_valid_blob(self):
        self.assertTrue(validate_blob_syntax("120000240036E42F6140000000000F4240"))

    def test_invalid_blob(self):
        self.assertFalse(validate_blob_syntax("xyz123"))
        self.assertFalse(validate_blob_syntax(""))

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para submit_signed_blob...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSubmitSignedBlob)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para submit_signed_blob fueron exitosas.")
