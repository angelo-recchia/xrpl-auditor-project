"""
Módulo: evaluators/rules.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66 / LendingProtocolV1_1)
Descripción: Núcleo matemático determinista con aritmética Decimal (ROUND_DOWN),
             contabilidad cash-basis V1_1, máscaras reales de rippled (lsfVaultPrivate
             0x00010000, XLS-77d DeepFreeze 0x02000000/0x04000000), normalización
             1/10th bps de CoverRateMinimum, bóvedas closed-ended (60s buffer) e
             invariante fixCleanup3_4_0.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any

import yaml

from config import settings
from evaluator.rules import HermesRiskEngine, XLS65VaultEvaluator

NumberLike = Decimal | int | float | str

# Máscaras oficiales de LedgerEntry en rippled (XLS-0065 / XLS-77d)
LSF_VAULT_PRIVATE = 0x00010000
LSF_LOW_FREEZE = 0x00400000
LSF_HIGH_FREEZE = 0x00800000
LSF_LOW_DEEP_FREEZE = 0x02000000
LSF_HIGH_DEEP_FREEZE = 0x04000000

TRUSTLINE_FREEZE_MASK = LSF_LOW_FREEZE | LSF_HIGH_FREEZE
TRUSTLINE_DEEP_FREEZE_MASK = LSF_LOW_DEEP_FREEZE | LSF_HIGH_DEEP_FREEZE
TRUSTLINE_ANY_FREEZE_MASK = TRUSTLINE_FREEZE_MASK | TRUSTLINE_DEEP_FREEZE_MASK

# Alias retrocompatible para scripts previos
DEEP_FREEZE_FLAG = LSF_HIGH_FREEZE

TENTH_BPS_FACTOR = Decimal("0.00001")  # 1 unit = 1/10 bps = 0.001% = 0.00001
MAX_COVER_RATE_TENTH_BPS = Decimal("100000")  # 100%
LOAN_REDEMPTION_BUFFER_SECONDS = 60  # PR #8151 (kLoanRedemptionBuffer)
DEFAULT_NAV_QUANTIZER = Decimal("0.000001")


def _to_decimal(value: NumberLike, field_name: str) -> Decimal:
    """Convierte entradas numéricas heterogéneas a Decimal finito sin errores IEEE 754."""
    if isinstance(value, bool):
        raise TypeError(f"El campo '{field_name}' no acepta booleanos.")

    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise ValueError(f"Valor numérico inválido en '{field_name}': {value!r}") from exc

    if not dec.is_finite():
        raise ValueError(f"El campo '{field_name}' debe ser finito, recibido: {value!r}")
    return dec


def _sanitize_flags(raw_flags: int | str | None, field_name: str = "Flags") -> int:
    """
    Sanea el campo Flags de objetos XRPL soportando enteros y cadenas hexadecimales
    (ej. 65536, '0x00010000', None -> 0) evitando TypeError en operaciones bit a bit.
    """
    if raw_flags is None:
        return 0
    if isinstance(raw_flags, bool):
        raise TypeError(f"El campo '{field_name}' no acepta booleanos.")
    if isinstance(raw_flags, int):
        if raw_flags < 0:
            raise ValueError(f"El campo '{field_name}' no puede ser negativo: {raw_flags}")
        return raw_flags
    if isinstance(raw_flags, str):
        cleaned = raw_flags.strip()
        if not cleaned:
            raise ValueError(f"El campo '{field_name}' no puede ser una cadena vacía.")
        try:
            parsed = int(cleaned, 0)
        except ValueError as exc:
            raise ValueError(f"Cadena de flags inválida en '{field_name}': {raw_flags!r}") from exc
        if parsed < 0:
            raise ValueError(f"El campo '{field_name}' no puede ser negativo: {parsed}")
        return parsed

    raise TypeError(
        f"Tipo no soportado para '{field_name}': {type(raw_flags).__name__}. "
        "Se esperaba int, str hexadecimal o None."
    )


def normalize_cover_rate(
    raw_cover_rate: NumberLike,
    *,
    is_tenth_bps: bool | None = None,
) -> Decimal:
    """
    Normaliza CoverRateMinimum a ratio Decimal [0, 1].
    En XLS-66 on-chain, LoanBroker.CoverRateMinimum es uint32 en 1/10th bps (0..100000),
    donde 10000 = 10% = Decimal('0.10').

    Si is_tenth_bps es None, valores > 1 se interpretan automáticamente como 1/10th bps.
    Para campos procedentes de un LoanBroker on-chain, pasar is_tenth_bps=True explícitamente.
    """
    dec = _to_decimal(raw_cover_rate, "cover_rate_minimum")
    if dec < Decimal("0"):
        raise ValueError("cover_rate_minimum no puede ser negativo.")

    use_tenth_bps = (dec > Decimal("1")) if is_tenth_bps is None else is_tenth_bps
    if use_tenth_bps:
        if dec > MAX_COVER_RATE_TENTH_BPS:
            raise ValueError(f"CoverRateMinimum en 1/10th bps excede 100000 (100%): {dec}")
        return (dec * TENTH_BPS_FACTOR).quantize(Decimal("0.00001"), rounding=ROUND_DOWN)

    if dec > Decimal("1"):
        raise ValueError(f"Ratio cover_rate_minimum fuera de rango [0, 1]: {dec}")
    return dec


def evaluate_flcr_solvency_v1_1(
    first_loss_capital: NumberLike,
    principal_debt: NumberLike,
    realized_interest: NumberLike = Decimal("0"),
    cover_rate_minimum: NumberLike | None = None,
    *,
    accrued_interest: NumberLike = Decimal("0"),
    warning_multiplier: NumberLike | None = None,
    quantizer: Decimal | None = None,
    cover_rate_is_tenth_bps: bool | None = None,
) -> dict[str, Any]:
    """
    Regla 1 (XLS-66 LendingProtocolV1_1): Solvencia de Primera Pérdida bajo criterio de caja.

    EffectiveDebt = PrincipalDebt + RealizedInterest
    (accrued_interest no cobrado se ignora explícitamente según especificación V1_1).
    """
    _ = _to_decimal(accrued_interest, "accrued_interest")

    flc_dec = _to_decimal(first_loss_capital, "first_loss_capital")
    principal_dec = _to_decimal(principal_debt, "principal_debt")
    realized_dec = _to_decimal(realized_interest, "realized_interest")

    min_rate_dec = (
        normalize_cover_rate(cover_rate_minimum, is_tenth_bps=cover_rate_is_tenth_bps)
        if cover_rate_minimum is not None
        else settings.flcr_base
    )
    mult_dec = (
        _to_decimal(warning_multiplier, "warning_multiplier")
        if warning_multiplier is not None
        else settings.flcr_warning_multiplier
    )
    step = quantizer if quantizer is not None else settings.nav_quantizer

    if flc_dec < Decimal("0"):
        raise ValueError("first_loss_capital no puede ser negativo.")
    if principal_dec < Decimal("0") or realized_dec < Decimal("0"):
        raise ValueError("principal_debt y realized_interest no pueden ser negativos.")
    if min_rate_dec < Decimal("0"):
        raise ValueError("cover_rate_minimum no puede ser negativo.")
    if mult_dec < Decimal("1.00"):
        raise ValueError("warning_multiplier debe ser >= 1.00.")

    effective_debt = principal_dec + realized_dec
    warning_buffer = (min_rate_dec * mult_dec).quantize(step, rounding=ROUND_DOWN)

    if effective_debt == Decimal("0"):
        return {
            "status": "HEALTHY",
            "flcr": Decimal("Infinity"),
            "effective_debt": effective_debt,
            "first_loss_capital": flc_dec,
            "cover_rate_minimum": min_rate_dec,
            "warning_buffer": warning_buffer,
            "accounting_basis": "CASH_BASIS_V1_1",
        }

    flcr = (flc_dec / effective_debt).quantize(step, rounding=ROUND_DOWN)

    if flcr < min_rate_dec:
        status = "CRITICAL_DEEP_FREEZE"
    elif flcr < warning_buffer:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "flcr": flcr,
        "effective_debt": effective_debt,
        "first_loss_capital": flc_dec,
        "cover_rate_minimum": min_rate_dec,
        "warning_buffer": warning_buffer,
        "accounting_basis": "CASH_BASIS_V1_1",
    }


def audit_vault_access_flags(
    vault_flags: int | str | None,
    *,
    permissioned_mask: int | None = None,
) -> dict[str, Any]:
    """
    Regla 2 (XLS-65): Control de acceso de bóveda mediante lsfVaultPrivate (0x00010000).
    Soporta enteros y cadenas hexadecimales (ej. '0x00010000').
    """
    sanitized = _sanitize_flags(vault_flags, field_name="vault_flags")
    mask = permissioned_mask if permissioned_mask is not None else settings.vault_permissioned_mask
    is_permissioned = bool(sanitized & mask)

    return {
        "raw_flags": vault_flags,
        "sanitized_flags": sanitized,
        "mask_applied": hex(mask),
        "is_permissioned": is_permissioned,
        "access_mode": "PERMISSIONED" if is_permissioned else "OPEN",
        "vault_type": "RESTRICTED_VAULT" if is_permissioned else "STANDARD_VAULT",
    }


def audit_vault_nav_parity(
    vault_assets: NumberLike,
    outstanding_shares: NumberLike,
    *,
    quantizer: Decimal | None = None,
) -> dict[str, Any]:
    """
    Regla 3 (XLS-65): Paridad de Valor Liquidativo (NAV per Share).
    Trunca a 6 decimales (0.000001) con ROUND_DOWN.
    Si OutstandingShares == 0, devuelve 1.000000.
    """
    assets_dec = _to_decimal(vault_assets, "vault_assets")
    shares_dec = _to_decimal(outstanding_shares, "outstanding_shares")
    step = quantizer if quantizer is not None else settings.nav_quantizer

    if assets_dec < Decimal("0") or shares_dec < Decimal("0"):
        raise ValueError("vault_assets y outstanding_shares no pueden ser negativos.")

    par_value = Decimal("1.000000").quantize(step, rounding=ROUND_DOWN)

    if shares_dec == Decimal("0"):
        parity_status = "ANOMALY_ASSETS_WITHOUT_SHARES" if assets_dec > Decimal("0") else "AT_PAR"
        return {
            "nav_per_share": par_value,
            "vault_assets": assets_dec,
            "outstanding_shares": shares_dec,
            "parity_status": parity_status,
        }

    nav_per_share = (assets_dec / shares_dec).quantize(step, rounding=ROUND_DOWN)

    if nav_per_share < par_value:
        parity_status = "IMPAIRED_BELOW_PAR"
    elif nav_per_share == par_value:
        parity_status = "AT_PAR"
    else:
        parity_status = "ABOVE_PAR_ACCRETIVE"

    return {
        "nav_per_share": nav_per_share,
        "vault_assets": assets_dec,
        "outstanding_shares": shares_dec,
        "parity_status": parity_status,
    }


def audit_closed_ended_vault_v1_1(
    vault_node: dict[str, Any],
    current_ripple_time: int,
    *,
    loan_final_payment_ripple_time: int | None = None,
) -> dict[str, Any]:
    """
    Auditoría de ciclo de vida para bóvedas Closed-Ended bajo LendingProtocolV1_1:
      - VaultKind == 1 (Closed-Ended) obligatorio para asociar LoanBroker.
      - Fases según SubscriptionDate y RedemptionDate (segundos desde Ripple Epoch).
      - Buffer obligatorio >= 60s entre último vencimiento de préstamo y RedemptionDate.
    """
    vault_kind = vault_node.get("VaultKind")
    le_version = vault_node.get("LEVersion")
    sub_date = vault_node.get("SubscriptionDate")
    red_date = vault_node.get("RedemptionDate")

    if vault_kind is None:
        return {
            "status": "OPEN_ENDED_UNVERIFIED",
            "vault_kind": None,
            "le_version": le_version,
            "phase": "UNKNOWN",
            "loan_broker_permitted": False,
        }

    is_closed_ended = int(vault_kind) == 1
    if not is_closed_ended:
        return {
            "status": "INVALID_OPEN_ENDED_FOR_V1_1",
            "vault_kind": int(vault_kind),
            "le_version": le_version,
            "phase": "OPEN_ENDED",
            "loan_broker_permitted": False,
        }

    phase = "ACTIVE_LOCKED"
    if sub_date is not None and current_ripple_time < int(sub_date):
        phase = "PRE_SUBSCRIPTION"
    elif red_date is not None and current_ripple_time >= int(red_date):
        phase = "REDEMPTION_WINDOW"

    buffer_violation = False
    if red_date is not None and loan_final_payment_ripple_time is not None:
        latest_allowed = int(red_date) - LOAN_REDEMPTION_BUFFER_SECONDS
        if int(loan_final_payment_ripple_time) > latest_allowed:
            buffer_violation = True

    status = "MATURITY_BUFFER_VIOLATION" if buffer_violation else "HEALTHY"
    return {
        "status": status,
        "vault_kind": int(vault_kind),
        "le_version": le_version,
        "phase": phase,
        "loan_broker_permitted": True,
        "buffer_seconds": LOAN_REDEMPTION_BUFFER_SECONDS,
        "buffer_violation": buffer_violation,
    }


def scale_vault_amount(
    raw_amount: NumberLike,
    scale: int = 0,
    *,
    is_xrp_or_mpt: bool = False,
) -> Decimal:
    """
    Convierte un monto de activo usando el factor 10^Scale de XLS-65.
    Para XRP y MPTs, Scale es fijo en 0. Para trustline tokens, Scale está en [0, 18].
    """
    amount_dec = _to_decimal(raw_amount, "raw_amount")
    if amount_dec < Decimal("0"):
        raise ValueError("raw_amount no puede ser negativo.")

    effective_scale = 0 if is_xrp_or_mpt else int(scale)
    if not (0 <= effective_scale <= 18):
        raise ValueError(f"Scale fuera de rango permitido [0, 18]: {effective_scale}")

    return amount_dec * (Decimal(10) ** effective_scale)


def audit_broker_cover_invariant(
    cover_available: NumberLike,
    pseudo_account_balance: NumberLike,
    *,
    tolerance: NumberLike = Decimal("0"),
) -> dict[str, Any]:
    """
    Invariante fixCleanup3_4_0: verifica que LoanBroker.CoverAvailable coincida
    con los activos reales mantenidos en la pseudo-cuenta asociada del Broker.
    """
    cover_dec = _to_decimal(cover_available, "cover_available")
    balance_dec = _to_decimal(pseudo_account_balance, "pseudo_account_balance")
    tol_dec = _to_decimal(tolerance, "tolerance")

    if cover_dec < Decimal("0") or balance_dec < Decimal("0") or tol_dec < Decimal("0"):
        raise ValueError("Los montos del invariante CoverAvailable no pueden ser negativos.")

    discrepancy = abs(cover_dec - balance_dec)
    is_valid = discrepancy <= tol_dec

    return {
        "status": "HEALTHY" if is_valid else "COVER_INVARIANT_MISMATCH",
        "is_valid": is_valid,
        "cover_available": cover_dec,
        "pseudo_account_balance": balance_dec,
        "discrepancy": discrepancy,
    }


# ==============================================================================
# Capa de compatibilidad operativa con scripts y tests previos de Project Hermes
# ==============================================================================

def load_config() -> dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "parameters.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_vault_risk(flcr: NumberLike, borrower_shares: dict[str, NumberLike]) -> dict[str, Any]:
    """
    Motor de evaluación de riesgo institucional para XLS-66 (Project Hermes).
    Implementa doble capa defensiva (Sistémica + Granular) con aritmética Decimal.
    """
    flcr_dec = _to_decimal(flcr, "flcr")
    min_flcr = settings.flcr_base
    warning_flcr = min_flcr * settings.flcr_warning_multiplier
    concentration_limit = settings.max_borrower_share

    risk_level = "VERDE"
    freeze_credit_required = False
    restricted_borrowers: list[str] = []
    concentration_violations: list[str] = []
    recommended_action = "Monitoreo estándar. Sin riesgo aparente."

    if flcr_dec <= min_flcr:
        risk_level = "ROJO"
        freeze_credit_required = True
        recommended_action = (
            "CRÍTICO: Perforación del Límite de seguridad. "
            "Disparar FREEZE_CREDIT y transacción multi-sig de emergencia."
        )
    elif flcr_dec <= warning_flcr:
        risk_level = "AMARILLO"
        recommended_action = "Desviación leve. Incrementar frecuencia de sondeo."

    for borrower, share in borrower_shares.items():
        share_dec = _to_decimal(share, f"share[{borrower}]")
        if share_dec > concentration_limit:
            restricted_borrowers.append(borrower)
            concentration_violations.append(
                f"Prestatario {borrower} excede la cuota permitida "
                f"({float(share_dec) * 100:.1f}% > {float(concentration_limit) * 100:.1f}%)"
            )

    if restricted_borrowers and risk_level != "ROJO":
        recommended_action += " [ACCIÓN PARCIAL: Bloqueo de nuevos tramos para prestatarios infractores]."

    return {
        "flcr_actual": float(flcr_dec),
        "risk_level": risk_level,
        "freeze_credit_required": freeze_credit_required,
        "restricted_borrowers": restricted_borrowers,
        "recommended_action": recommended_action,
        "concentration_violations": concentration_violations,
    }


def check_broker_freeze_status(broker_account_data: dict[str, Any]) -> dict[str, Any]:
    """Evalúa si la pseudo-cuenta del Broker o su Owner están en Freeze/DeepFreeze."""
    is_pseudo_frozen = _sanitize_flags(broker_account_data.get("FreezeState", 0), "FreezeState") > 0
    is_owner_deep_frozen = bool(broker_account_data.get("OwnerDeepFreeze", False))

    if is_pseudo_frozen or is_owner_deep_frozen:
        return {
            "status": "CRITICAL_ALERT",
            "code": "BROKER_FROZEN",
            "action_required": "HALT_NEW_DEPOSITS",
            "details": "El Broker o su propietario están congelados por el emisor del activo.",
        }
    return {"status": "HEALTHY"}


def check_borrower_freeze_risk(loan_data: dict[str, Any], borrower_account_flags: int | str | None) -> dict[str, Any]:
    """
    Detecta si una TrustLine/prestatario con préstamo activo sufrió Freeze clásico
    (0x00400000 / 0x00800000) o XLS-77d DeepFreeze (0x02000000 / 0x04000000).
    """
    sanitized_flags = _sanitize_flags(borrower_account_flags, "borrower_account_flags")
    is_deep_frozen = bool(sanitized_flags & TRUSTLINE_DEEP_FREEZE_MASK)
    is_frozen = bool(sanitized_flags & TRUSTLINE_ANY_FREEZE_MASK)

    if is_frozen and loan_data.get("status") == "ACTIVE":
        return {
            "status": "HIGH_RISK",
            "code": "BORROWER_DEEP_FROZEN",
            "freeze_kind": "DEEP_FREEZE" if is_deep_frozen else "FREEZE",
            "action_required": "FLAG_IMPAIRMENT_IMMINENT",
            "details": "El prestatario no podrá ejecutar LoanPay. Riesgo de default forzado.",
        }
    return {"status": "HEALTHY"}


def check_flcr_fee_redirection(broker_state: dict[str, Any]) -> dict[str, Any]:
    """Verifica acumulación de comisiones como First-Loss Capital suplementario."""
    if broker_state.get("OwnerDeepFreeze", False):
        if not broker_state.get("FeesRedirectedToFLCR", True):
            return {
                "status": "CRITICAL_ALERT",
                "code": "FLCR_REDIRECTION_FAILURE",
                "details": "Desviación detectada: Las comisiones no se están sumando al First-Loss Capital.",
            }
    return {"status": "HEALTHY"}


__all__ = [
    "LSF_VAULT_PRIVATE",
    "LSF_LOW_FREEZE",
    "LSF_HIGH_FREEZE",
    "LSF_LOW_DEEP_FREEZE",
    "LSF_HIGH_DEEP_FREEZE",
    "TRUSTLINE_FREEZE_MASK",
    "TRUSTLINE_DEEP_FREEZE_MASK",
    "TRUSTLINE_ANY_FREEZE_MASK",
    "DEEP_FREEZE_FLAG",
    "LOAN_REDEMPTION_BUFFER_SECONDS",
    "HermesRiskEngine",
    "XLS65VaultEvaluator",
    "normalize_cover_rate",
    "evaluate_flcr_solvency_v1_1",
    "audit_vault_access_flags",
    "audit_vault_nav_parity",
    "audit_closed_ended_vault_v1_1",
    "scale_vault_amount",
    "audit_broker_cover_invariant",
    "load_config",
    "evaluate_vault_risk",
    "check_broker_freeze_status",
    "check_borrower_freeze_risk",
    "check_flcr_fee_redirection",
]