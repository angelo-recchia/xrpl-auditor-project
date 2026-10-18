"""Test suite para el módulo core/auditor.py
Verifica cumplimiento con specs/auditor_spec.md
"""
import unittest
import sys
from pathlib import Path

# Agregar raíz al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.auditor import calculate_ltv, calculate_dscr, evaluate_health, audit_position

class TestAuditor(unittest.TestCase):
    def test_ltv_calculation(self):
        # 50,000 deuda sobre 100,000 colateral = 50%
        self.assertEqual(calculate_ltv(50000, 100000), 50.0)
        # 80,000 deuda sobre 100,000 colateral = 80%
        self.assertEqual(calculate_ltv(80000, 100000), 80.0)
        # Sin colateral
        self.assertEqual(calculate_ltv(1000, 0), float('inf'))
        self.assertEqual(calculate_ltv(0, 0), 0.0)

    def test_dscr_calculation(self):
        # 15,000 ingresos sobre 10,000 servicio = 1.5
        self.assertEqual(calculate_dscr(15000, 10000), 1.5)
        # 11,500 ingresos sobre 10,000 servicio = 1.15
        self.assertAlmostEqual(calculate_dscr(11500, 10000), 1.15)
        # Servicio 0
        self.assertEqual(calculate_dscr(1000, 0), float('inf'))

    def test_health_evaluation_saludable(self):
        # LTV <= 75% y DSCR >= 1.25
        self.assertEqual(evaluate_health(70.0, 1.30), "SALUDABLE")
        self.assertEqual(evaluate_health(75.0, 1.25), "SALUDABLE")

    def test_health_evaluation_estres(self):
        # 75% < LTV <= 85% y DSCR saludable
        self.assertEqual(evaluate_health(80.0, 1.30), "ESTRÉS")
        # LTV saludable pero 1.10 <= DSCR < 1.25
        self.assertEqual(evaluate_health(60.0, 1.15), "ESTRÉS")
        # Ambos en rango estrés
        self.assertEqual(evaluate_health(82.0, 1.20), "ESTRÉS")

    def test_health_evaluation_critico(self):
        # LTV > 85%
        self.assertEqual(evaluate_health(86.0, 1.50), "CRÍTICO")
        # DSCR < 1.10
        self.assertEqual(evaluate_health(50.0, 1.05), "CRÍTICO")
        # Ambos críticos
        self.assertEqual(evaluate_health(90.0, 0.90), "CRÍTICO")

    def test_audit_position_full(self):
        report = audit_position(
            outstanding_debt=60000,
            collateral_value=100000,
            net_operating_income=15000,
            debt_service=10000
        )
        self.assertEqual(report["status"], "SALUDABLE")
        self.assertEqual(report["ltv_percent"], 60.0)
        self.assertEqual(report["dscr"], 1.5)

if __name__ == "__main__":
    unittest.main()
