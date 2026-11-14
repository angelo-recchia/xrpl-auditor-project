"""
Suite QA determinista para evaluators/rules.py (XLS-65 / XLS-66).
Valida aritmética Decimal (ROUND_DOWN), contabilidad cash-basis V1_1,
guardas de división por cero, saneamiento de flags y paridad NAV.
"""

from decimal import Decimal
import pytest

from evaluators.rules import (
    audit_vault_access_flags,
    audit_vault_nav_parity,
    check_borrower_freeze_risk,
    evaluate_flcr_solvency_v1_1,
)


class TestFLCRSolvencyV11:
    def test_cash_basis_ignores_accrued_interest(self):
        """EffectiveDebt solo suma Principal + RealizedInterest; AccruedInterest se ignora."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="12",
            principal_debt="100",
            realized_interest="0",
            cover_rate_minimum="0.10",
            accrued_interest="5000",  # No cobrado -> ignorado en V1_1
        )
        assert res["effective_debt"] == Decimal("100")
        assert res["flcr"] == Decimal("0.120000")
        assert res["status"] == "HEALTHY"
        assert res["accounting_basis"] == "CASH_BASIS_V1_1"

    def test_realized_interest_included_in_effective_debt(self):
        """Los intereses realizados sí aumentan EffectiveDebt y pueden disparar WARNING."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="12",
            principal_debt="100",
            realized_interest="10",  # EffectiveDebt = 110 -> FLCR = 0.109090
            cover_rate_minimum="0.10",
        )
        assert res["effective_debt"] == Decimal("110")
        assert res["flcr"] == Decimal("0.109090")
        assert res["status"] == "WARNING"

    def test_critical_deep_freeze_below_minimum(self):
        """FLCR < CoverRateMinimum activa CRITICAL_DEEP_FREEZE."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="9.9999",
            principal_debt="100",
            realized_interest="0",
            cover_rate_minimum="0.10",
        )
        assert res["flcr"] == Decimal("0.099999")
        assert res["status"] == "CRITICAL_DEEP_FREEZE"

    def test_round_down_conservative_precision(self):
        """Verifica truncamiento ROUND_DOWN (nunca redondear al alza la solvencia)."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="11.9999999",
            principal_debt="100",
            realized_interest="0",
            cover_rate_minimum="0.10",
        )
        assert res["flcr"] == Decimal("0.119999")
        assert res["status"] == "WARNING"

    def test_zero_debt_returns_infinity_and_healthy(self):
        """Guarda de división por cero: DebtTotal == 0 -> Infinity y HEALTHY."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="50",
            principal_debt="0",
            realized_interest="0",
            cover_rate_minimum="0.10",
        )
        assert res["flcr"] == Decimal("Infinity")
        assert res["status"] == "HEALTHY"

    def test_rejects_negative_or_boolean_inputs(self):
        with pytest.raises(ValueError):
            evaluate_flcr_solvency_v1_1("-1", "100")
        with pytest.raises(TypeError):
            evaluate_flcr_solvency_v1_1(True, "100")


class TestVaultAccessFlags:
    @pytest.mark.parametrize(
        "raw_flags,expected_mode,expected_type,expected_perm",
        [
            (1, "PERMISSIONED", "RESTRICTED_VAULT", True),
            ("1", "PERMISSIONED", "RESTRICTED_VAULT", True),
            ("0x0001", "PERMISSIONED", "RESTRICTED_VAULT", True),
            (" 0x00010001 ", "PERMISSIONED", "RESTRICTED_VAULT", True),
            (0, "OPEN", "STANDARD_VAULT", False),
            ("0x0000", "OPEN", "STANDARD_VAULT", False),
            (0x0002, "OPEN", "STANDARD_VAULT", False),
            (None, "OPEN", "STANDARD_VAULT", False),
        ],
    )
    def test_flag_sanitization_and_bitmask(self, raw_flags, expected_mode, expected_type, expected_perm):
        res = audit_vault_access_flags(raw_flags)
        assert res["is_permissioned"] is expected_perm
        assert res["access_mode"] == expected_mode
        assert res["vault_type"] == expected_type

    def test_invalid_flag_types_raise_cleanly(self):
        with pytest.raises(ValueError):
            audit_vault_access_flags("not_hex")
        with pytest.raises(TypeError):
            audit_vault_access_flags(True)
        with pytest.raises(TypeError):
            audit_vault_access_flags(1.5)

    def test_borrower_freeze_accepts_hex_string_flags(self):
        res = check_borrower_freeze_risk({"status": "ACTIVE"}, "0x00800000")
        assert res["status"] == "HIGH_RISK"
        assert res["code"] == "BORROWER_DEEP_FROZEN"


class TestVaultNAVParity:
    def test_zero_shares_returns_par_1_000000(self):
        res = audit_vault_nav_parity("0", "0")
        assert res["nav_per_share"] == Decimal("1.000000")
        assert res["parity_status"] == "AT_PAR"

    def test_zero_shares_with_positive_assets_flags_anomaly(self):
        res = audit_vault_nav_parity("250", "0")
        assert res["nav_per_share"] == Decimal("1.000000")
        assert res["parity_status"] == "ANOMALY_ASSETS_WITHOUT_SHARES"

    def test_nav_truncates_round_down_to_six_decimals(self):
        res = audit_vault_nav_parity("10", "3")
        assert res["nav_per_share"] == Decimal("3.333333")
        assert res["parity_status"] == "ABOVE_PAR_ACCRETIVE"

    def test_impaired_nav_below_par(self):
        res = audit_vault_nav_parity("99.9999999", "100")
        assert res["nav_per_share"] == Decimal("0.999999")
        assert res["parity_status"] == "IMPAIRED_BELOW_PAR"