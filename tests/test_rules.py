"""
Suite QA determinista para evaluators/rules.py (XLS-65 / XLS-66 / LendingProtocolV1_1).
Valida aritmética Decimal (ROUND_DOWN), contabilidad cash-basis V1_1,
normalización 1/10th bps, máscaras reales de rippled (0x00010000 / DeepFreeze 0x02000000),
bóvedas closed-ended (buffer 60s), Scale e invariante fixCleanup3_4_0.
"""

from decimal import Decimal
import pytest

from evaluators.rules import (
    LSF_HIGH_DEEP_FREEZE,
    LSF_HIGH_FREEZE,
    LSF_LOW_DEEP_FREEZE,
    LSF_VAULT_PRIVATE,
    LSF_VAULT_SHARE_NON_TRANSFERABLE,
    audit_broker_cover_invariant,
    audit_closed_ended_vault_v1_1,
    audit_vault_access_flags,
    audit_vault_nav_parity,
    audit_vault_unrealized_loss,
    check_borrower_freeze_risk,
    evaluate_flcr_solvency_v1_1,
    normalize_cover_rate,
    scale_vault_amount,
)


class TestFLCRSolvencyV11:
    def test_cash_basis_ignores_accrued_interest(self):
        """EffectiveDebt solo suma Principal + RealizedInterest; AccruedInterest se ignora."""
        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="12",
            principal_debt="100",
            realized_interest="0",
            cover_rate_minimum="0.10",
            accrued_interest="5000",
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
            realized_interest="10",
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

    def test_cover_rate_minimum_tenth_bps_normalization(self):
        """10000 en 1/10th bps on-chain equivale a 10% (Decimal 0.10000)."""
        assert normalize_cover_rate(10000, is_tenth_bps=True) == Decimal("0.10000")
        assert normalize_cover_rate("0.10") == Decimal("0.10")

        res = evaluate_flcr_solvency_v1_1(
            first_loss_capital="9",
            principal_debt="100",
            cover_rate_minimum=10000,
            cover_rate_is_tenth_bps=True,
        )
        assert res["cover_rate_minimum"] == Decimal("0.10000")
        assert res["status"] == "CRITICAL_DEEP_FREEZE"

    def test_rejects_negative_or_boolean_inputs(self):
        with pytest.raises(ValueError):
            evaluate_flcr_solvency_v1_1("-1", "100")
        with pytest.raises(TypeError):
            evaluate_flcr_solvency_v1_1(True, "100")


class TestVaultAccessFlags:
    @pytest.mark.parametrize(
        "raw_flags,expected_mode,expected_type,expected_perm",
        [
            (LSF_VAULT_PRIVATE, "PERMISSIONED", "RESTRICTED_VAULT", True),
            ("65536", "PERMISSIONED", "RESTRICTED_VAULT", True),
            ("0x00010000", "PERMISSIONED", "RESTRICTED_VAULT", True),
            (" 0x00010001 ", "PERMISSIONED", "RESTRICTED_VAULT", True),
            (0, "OPEN", "STANDARD_VAULT", False),
            ("0x0000", "OPEN", "STANDARD_VAULT", False),
            ("0x0001", "OPEN", "STANDARD_VAULT", False),
            (None, "OPEN", "STANDARD_VAULT", False),
        ],
    )
    def test_flag_sanitization_and_official_vault_private_bitmask(
        self, raw_flags, expected_mode, expected_type, expected_perm
    ):
        res = audit_vault_access_flags(raw_flags)
        assert res["is_permissioned"] is expected_perm
        assert res["access_mode"] == expected_mode
        assert res["vault_type"] == expected_type

    def test_custom_permissioned_mask_override(self):
        res = audit_vault_access_flags("0x0001", permissioned_mask=0x0001)
        assert res["is_permissioned"] is True

    def test_invalid_flag_types_raise_cleanly(self):
        with pytest.raises(ValueError):
            audit_vault_access_flags("not_hex")
        with pytest.raises(TypeError):
            audit_vault_access_flags(True)
        with pytest.raises(TypeError):
            audit_vault_access_flags(1.5)

    def test_borrower_freeze_and_deep_freeze_masks(self):
        classic = check_borrower_freeze_risk({"status": "ACTIVE"}, hex(LSF_HIGH_FREEZE))
        assert classic["status"] == "HIGH_RISK"
        assert classic["freeze_kind"] == "FREEZE"

        deep_low = check_borrower_freeze_risk({"status": "ACTIVE"}, LSF_LOW_DEEP_FREEZE)
        assert deep_low["status"] == "HIGH_RISK"
        assert deep_low["freeze_kind"] == "DEEP_FREEZE"

        deep_high = check_borrower_freeze_risk({"status": "ACTIVE"}, hex(LSF_HIGH_DEEP_FREEZE))
        assert deep_high["status"] == "HIGH_RISK"
        assert deep_high["freeze_kind"] == "DEEP_FREEZE"


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


class TestSeniorProtocolRulesV11:
    def test_closed_ended_vault_phases_and_60s_buffer(self):
        vault = {"VaultKind": 1, "LEVersion": 1, "SubscriptionDate": 1000, "RedemptionDate": 2000}

        pre = audit_closed_ended_vault_v1_1(vault, current_ripple_time=900)
        assert pre["phase"] == "PRE_SUBSCRIPTION"
        assert pre["loan_broker_permitted"] is True
        assert pre["status"] == "HEALTHY"

        ok_loan = audit_closed_ended_vault_v1_1(
            vault, current_ripple_time=1500, loan_final_payment_ripple_time=1940
        )
        assert ok_loan["phase"] == "ACTIVE_LOCKED"
        assert ok_loan["buffer_violation"] is False
        assert ok_loan["status"] == "HEALTHY"

        bad_loan = audit_closed_ended_vault_v1_1(
            vault, current_ripple_time=1500, loan_final_payment_ripple_time=1950
        )
        assert bad_loan["buffer_violation"] is True
        assert bad_loan["status"] == "MATURITY_BUFFER_VIOLATION"

        red = audit_closed_ended_vault_v1_1(vault, current_ripple_time=2000)
        assert red["phase"] == "REDEMPTION_WINDOW"

        open_ended = audit_closed_ended_vault_v1_1({"VaultKind": 0}, current_ripple_time=1500)
        assert open_ended["status"] == "INVALID_OPEN_ENDED_FOR_V1_1"
        assert open_ended["loan_broker_permitted"] is False

    def test_scale_vault_amount_trustline_vs_xrp_mpt(self):
        assert scale_vault_amount("1.5", 6) == Decimal("1500000.0")
        assert scale_vault_amount("100", 6, is_xrp_or_mpt=True) == Decimal("100")

    def test_broker_cover_invariant_fixcleanup340(self):
        ok = audit_broker_cover_invariant("500", "500")
        assert ok["is_valid"] is True
        assert ok["status"] == "HEALTHY"

        bad = audit_broker_cover_invariant("500", "450")
        assert bad["is_valid"] is False
        assert bad["status"] == "COVER_INVARIANT_MISMATCH"
        assert bad["discrepancy"] == Decimal("50")


class TestVaultShareTransferabilityScaleAndLoss:
    def test_non_transferable_flag_and_secondary_market_mode(self):
        assert LSF_VAULT_SHARE_NON_TRANSFERABLE == 0x00020000

        transferable = audit_vault_access_flags(LSF_VAULT_PRIVATE)
        assert transferable["is_permissioned"] is True
        assert transferable["is_share_transferable"] is True
        assert transferable["secondary_market_mode"] == "TRANSFERABLE"

        non_transferable = audit_vault_access_flags(
            LSF_VAULT_PRIVATE | LSF_VAULT_SHARE_NON_TRANSFERABLE
        )
        assert non_transferable["is_permissioned"] is True
        assert non_transferable["is_share_transferable"] is False
        assert non_transferable["secondary_market_mode"] == "NON_TRANSFERABLE"

    def test_nav_parity_with_scale_and_invalid_scale_validation(self):
        res = audit_vault_nav_parity(
            "10000",
            "10000000000",
            scale=6,
            shares_are_scaled=True,
        )
        assert res["nav_per_share"] == Decimal("1.000000")
        assert res["parity_status"] == "AT_PAR"
        assert res["effective_shares"] == Decimal("10000")
        assert res["scale"] == 6

        with pytest.raises(TypeError):
            audit_vault_nav_parity("100", "100", scale=True)
        with pytest.raises(TypeError):
            audit_vault_nav_parity("100", "100", scale=False)
        with pytest.raises(ValueError):
            audit_vault_nav_parity("100", "100", scale=-1)
        with pytest.raises(ValueError):
            audit_vault_nav_parity("100", "100", scale=19)

    def test_audit_vault_unrealized_loss_statuses_and_ratios(self):
        healthy = audit_vault_unrealized_loss("0", "1000")
        assert healthy["status"] == "HEALTHY"
        assert healthy["loss_ratio"] == Decimal("0.000000")

        warning = audit_vault_unrealized_loss("50", "1000")
        assert warning["status"] == "WARNING"
        assert warning["loss_ratio"] == Decimal("0.050000")

        critical = audit_vault_unrealized_loss("1000", "1000")
        assert critical["status"] == "CRITICAL"
        assert critical["loss_ratio"] == Decimal("1.000000")

        with pytest.raises(ValueError):
            audit_vault_unrealized_loss("-1", "1000")