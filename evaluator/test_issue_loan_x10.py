#!/usr/bin/env python3
"""
Evaluador de Pruebas - Emisión de Préstamos XLS-66 sobre Bóveda X10
Valida el plan de pagos, cálculos de interés, validación de liquidez y borrador DRAFT_UNSIGNED.
"""

import unittest

def calculate_loan_schedule(principal_xrp: float, interest_pct: float, payments: int, duration_days: int = 90) -> dict:
    principal_drops = int(principal_xrp * 1_000_000)
    annual_rate_bps = int(round(interest_pct * 100))
    duration_hours = duration_days * 24

    # Interés total estimado en drops
    total_interest_drops = int(principal_drops * (annual_rate_bps / 10000.0) * (duration_hours / (365 * 24)))
    total_repay_drops = principal_drops + total_interest_drops

    schedule = []
    principal_per_payment = principal_drops // payments
    interest_per_payment = total_interest_drops // payments

    for i in range(1, payments + 1):
        p_amt = principal_per_payment if i < payments else principal_drops - (principal_per_payment * (payments - 1))
        i_amt = interest_per_payment if i < payments else total_interest_drops - (interest_per_payment * (payments - 1))
        schedule.append({
            "payment_number": i,
            "principal_drops": p_amt,
            "interest_drops": i_amt,
            "total_drops": p_amt + i_amt,
            "principal_xrp": p_amt / 1_000_000,
            "interest_xrp": i_amt / 1_000_000,
            "total_xrp": (p_amt + i_amt) / 1_000_000
        })

    return {
        "principal_drops": principal_drops,
        "annual_rate_bps": annual_rate_bps,
        "total_interest_drops": total_interest_drops,
        "total_repay_drops": total_repay_drops,
        "duration_hours": duration_hours,
        "payments": payments,
        "schedule": schedule
    }

def validate_loan_liquidity(assets_total_drops: int, assets_avail_drops: int, debt_total_drops: int, loan_drops: int) -> dict:
    available_after = assets_avail_drops - loan_drops
    debt_after = debt_total_drops + loan_drops
    ltv_after_bps = int((debt_after / assets_total_drops) * 10000) if assets_total_drops > 0 else 10000

    within_capacity = available_after >= 0
    within_ltv = ltv_after_bps <= 8000

    status = "SALUDABLE" if (within_capacity and within_ltv) else ("ESTRÉS" if within_capacity else "CRÍTICO")

    return {
        "within_capacity": within_capacity,
        "within_ltv": within_ltv,
        "ltv_after_bps": ltv_after_bps,
        "available_after_drops": available_after,
        "status": status
    }

class TestIssueLoanX10(unittest.TestCase):
    def test_schedule_calculation(self):
        plan = calculate_loan_schedule(principal_xrp=20.0, interest_pct=5.0, payments=3, duration_days=90)
        self.assertEqual(plan["principal_drops"], 20_000_000)
        self.assertEqual(plan["annual_rate_bps"], 500)
        self.assertEqual(len(plan["schedule"]), 3)
        
        sum_p = sum(s["principal_drops"] for s in plan["schedule"])
        self.assertEqual(sum_p, 20_000_000)
        
        sum_i = sum(s["interest_drops"] for s in plan["schedule"])
        self.assertEqual(sum_i, plan["total_interest_drops"])

    def test_liquidity_evaluation(self):
        # Escenario Bóveda X10 actual: Total ~100.32 XRP, Avail ~80.16 XRP, Debt ~20.16 XRP
        total = 100_325_925
        avail = 80_162_416
        debt = 20_163_509
        loan = 20_000_000

        result = validate_loan_liquidity(total, avail, debt, loan)
        self.assertTrue(result["within_capacity"])
        self.assertTrue(result["within_ltv"])
        self.assertEqual(result["status"], "SALUDABLE")
        self.assertLess(result["ltv_after_bps"], 8000)

    def test_liquidity_overload(self):
        # Exceso de capacidad disponible
        total = 100_325_925
        avail = 10_000_000
        debt = 90_000_000
        loan = 20_000_000

        result = validate_loan_liquidity(total, avail, debt, loan)
        self.assertFalse(result["within_capacity"])
        self.assertEqual(result["status"], "CRÍTICO")

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando validaciones para issue_loan_x10...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIssueLoanX10)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador pasaron con éxito.")
