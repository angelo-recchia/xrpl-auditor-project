"""
Test suite para HermesRiskEngine en evaluator/rules.py
Valida:
- Restricciones de invariantes y manejo de errores
- Capacidad máxima de bóveda (FLC)
- Concentración agregada por prestatario
- FLCR en tiempo real (incluyendo pasivos cero)
"""
import unittest
import sys
from pathlib import Path
from decimal import Decimal

# Agregar raíz al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluator.rules import HermesRiskEngine


class TestHermesRiskEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HermesRiskEngine(min_coverage_ratio=0.20, max_concentration_ratio=0.10)

    def test_invariants_validation(self):
        # Ratio fuera de rango o cero
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio=0.0, max_concentration_ratio=0.10)
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio=-0.1, max_concentration_ratio=0.10)
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio=1.5, max_concentration_ratio=0.10)
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio=0.20, max_concentration_ratio=0.0)
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio=0.20, max_concentration_ratio=1.2)
        with self.assertRaises(ValueError):
            HermesRiskEngine(min_coverage_ratio="invalido", max_concentration_ratio=0.10)

    def test_calculate_max_vault_capacity(self):
        # FLC 20,000 / 0.20 = 100,000
        capacity = self.engine.calculate_max_vault_capacity(20000)
        self.assertEqual(capacity, Decimal('100000'))

    def test_check_vault_capacity_limit(self):
        # Dentro de límite
        res_ok = self.engine.check_vault_capacity_limit(flc=20000, total_deposits=95000)
        self.assertTrue(res_ok["is_safe"])
        self.assertEqual(res_ok["status"], "OK")

        # Excedido
        res_over = self.engine.check_vault_capacity_limit(flc=20000, total_deposits=105000)
        self.assertFalse(res_over["is_safe"])
        self.assertIn("ALERTA", res_over["status"])

    def test_check_borrower_concentration_aggregated(self):
        # Capacidad 100,000 * 0.10 = 10,000 max
        # Existente 5,000 + Nuevo 4,000 = 9,000 (Cumple)
        res_ok = self.engine.check_borrower_concentration_aggregated(
            max_capacity=100000, existing_borrower_debt=5000, new_loan_request=4000
        )
        self.assertTrue(res_ok["is_compliant"])
        self.assertEqual(res_ok["total_aggregated_debt"], 9000.0)

        # Existente 5,000 + Nuevo 6,000 = 11,000 (No cumple)
        res_over = self.engine.check_borrower_concentration_aggregated(
            max_capacity=100000, existing_borrower_debt=5000, new_loan_request=6000
        )
        self.assertFalse(res_over["is_compliant"])
        self.assertEqual(res_over["total_aggregated_debt"], 11000.0)
        self.assertIn("ALERTA CRÍTICA", res_over["status"])

    def test_evaluate_real_flcr(self):
        # Caso pasivo cero
        zero_res = self.engine.evaluate_real_flcr(flc_actual=10000, total_depositors_active=0)
        self.assertEqual(zero_res["flcr_real"], 1.0)
        self.assertIn("Sin pasivo activo", zero_res["health_status"])

        # Caso saludable: 25,000 / 100,000 = 0.25 >= 0.20
        healthy_res = self.engine.evaluate_real_flcr(flc_actual=25000, total_depositors_active=100000)
        self.assertEqual(healthy_res["flcr_real"], 0.25)
        self.assertEqual(healthy_res["health_status"], "Bóveda de Riesgo Controlado")

        # Caso insolvencia/inseguro: 15,000 / 100,000 = 0.15 < 0.20
        unhealthy_res = self.engine.evaluate_real_flcr(flc_actual=15000, total_depositors_active=100000)
        self.assertEqual(unhealthy_res["flcr_real"], 0.15)
        self.assertEqual(unhealthy_res["health_status"], "Alerta Roja de Insolvencia")


if __name__ == "__main__":
    unittest.main()
