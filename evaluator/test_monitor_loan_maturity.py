#!/usr/bin/env python3
"""
Evaluador de Pruebas - Monitor de Vencimiento de Préstamos XLS-66
Valida la conversión de timestamps Ripple Epoch, clasificación de estados y alertas de vencimiento.
"""

from datetime import datetime, timezone
import unittest

RIPPLE_EPOCH = 946684800

def ripple_to_datetime(ripple_seconds: int) -> datetime:
    return datetime.fromtimestamp(ripple_seconds + RIPPLE_EPOCH, tz=timezone.utc)

def evaluate_loan_maturity(loan: dict, now_dt: datetime) -> dict:
    due_dt = ripple_to_datetime(loan["NextPaymentDueDate"])
    grace_seconds = loan.get("GracePeriod", 604800)
    grace_dt = datetime.fromtimestamp(loan["NextPaymentDueDate"] + RIPPLE_EPOCH + grace_seconds, tz=timezone.utc)

    if now_dt < due_dt:
        status = "AL_DIA"
        days_diff = (due_dt - now_dt).total_seconds() / 86400
    elif now_dt < grace_dt:
        status = "EN_GRACIA"
        days_diff = (grace_dt - now_dt).total_seconds() / 86400
    else:
        status = "MORA"
        days_diff = (now_dt - due_dt).total_seconds() / 86400

    return {
        "loan_seq": loan.get("LoanSequence"),
        "due_date_iso": due_dt.isoformat(),
        "status": status,
        "days_diff": round(days_diff, 2)
    }

class TestMonitorLoanMaturity(unittest.TestCase):
    def setUp(self):
        self.mock_loan = {
            "LoanSequence": 1,
            "NextPaymentDueDate": 844955680, # 2026-10-10T13:54:40+00:00
            "GracePeriod": 604800 # 7 days -> 2026-10-17T13:54:40+00:00
        }

    def test_al_dia(self):
        # 1 de Octubre 2026
        now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        eval_res = evaluate_loan_maturity(self.mock_loan, now)
        self.assertEqual(eval_res["status"], "AL_DIA")
        self.assertGreater(eval_res["days_diff"], 0)

    def test_en_gracia(self):
        # 12 de Octubre 2026 (dentro del periodo de gracia de 7 días)
        now = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)
        eval_res = evaluate_loan_maturity(self.mock_loan, now)
        self.assertEqual(eval_res["status"], "EN_GRACIA")

    def test_mora(self):
        # 20 de Octubre 2026 (fuera del periodo de gracia)
        now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        eval_res = evaluate_loan_maturity(self.mock_loan, now)
        self.assertEqual(eval_res["status"], "MORA")

if __name__ == "__main__":
    print("[EVALUATOR] Ejecutando pruebas para monitor_loan_maturity...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMonitorLoanMaturity)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        exit(1)
    print("[PASS] Todas las pruebas del evaluador para monitor_loan_maturity fueron exitosas.")
