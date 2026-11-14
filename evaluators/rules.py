"""
Módulo: evaluators/rules.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Núcleo matemático determinista con aritmética Decimal (ROUND_DOWN),
             contabilidad cash-basis V1_1, saneamiento de flags XRPL y reglas
             de riesgo sistémico y granular.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any

import yaml

from config import settings
from evaluator.rules import HermesRiskEngine, XLS65VaultEvaluator

NumberLike = Decimal | int | float | str

DEEP_FREEZE_FLAG = 0x00800000
DEFAULT_NAV_QUANTIZER = Decimal("0.000001")
DEFAULT_PERMISSIONED_MASK = 0x0001


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
    (ej. 1, '1', '0x0001', None -> 0) evitando TypeError en operaciones bit a bit.
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


def evaluate_flcr_solvency_v1_1(
    first_loss_capital: NumberLike,
    principal_debt: NumberLike,
    realized_interest: NumberLike = Decimal("0"),
    cover_rate_minimum: NumberLike | None = None,
    *,
    accrued_interest: NumberLike = Decimal("0"),
    warning_multiplier: NumberLike | None = None,
    quantizer: Decimal | None = None,
) -> dict[str, Any]:
    """
    Regla 1 (XLS-66 LendingProtocolV1_1): Solvencia de Primera Pérdida bajo criterio de caja.

    EffectiveDebt = PrincipalDebt + RealizedInterest
    (accrued_interest no cobrado se ignora explícitamente según especificación V1_1).

    Umbrales:
      - FLCR < CoverRateMinimum                -> CRITICAL_DEEP_FREEZE
      - FLCR < CoverRateMinimum * 1.20         -> WARNING
      - FLCR >= CoverRateMinimum * 1.20        -> HEALTHY
      - EffectiveDebt == 0                     -> FLCR = Infinity, HEALTHY
    """
    # Se valida que accrued_interest sea numérico por trazabilidad, pero NO entra en EffectiveDebt
    _ = _to_decimal(accrued_interest, "accrued_interest")

    flc_dec = _to_decimal(first_loss_capital, "first_loss_capital")
    principal_dec = _to_decimal(principal_debt, "principal_debt")
    realized_dec = _to_decimal(realized_interest, "realized_interest")

    min_rate_dec = (
        _to_decimal(cover_rate_minimum, "cover_rate_minimum")
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
    if min_rate_dec <= Decimal("0"):
        raise ValueError("cover_rate_minimum debe ser mayor que 0.")
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
    Regla 2 (XLS-65): Control de acceso de bóveda mediante máscara bit a bit (& 0x0001).
    Soporta enteros y cadenas hexadecimales (ej. '0x0001').
    """
    sanitized = _sanitize_flags(vault_flags, field_name="vault_flags")
    mask = permissioned_mask if permissioned_mask is not None else settings.vault_permissioned_mask
    is_permissioned = bool(sanitized & mask)

    return {
        "raw_flags": vault_flags,
        "sanitized_flags": sanitized,
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


# ==============================================================================
# Capa de compatibilidad operativa con scripts y tests previos de Project Hermes
# ==============================================================================

def load_config() -> dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "parameters.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_vault_risk(flcr: NumberLike, borrower_shares: dict[str, NumberLike]) -> dict[str, Any]:
    """
    Motor de evaluación de riesgo de grado institucional para XLS-66 (Project Hermes).
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

    # Capa 1: Riesgo Sistémico (FLCR Global)
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

    # Capa 2: Riesgo Granular / Concentración por Prestatario
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
    """
    Regla: Congelación del Broker.
    Evalúa si la pseudo-cuenta del Broker o su Owner están en Freeze/DeepFreeze.
    """
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
    Regla: Impago Inminente por Prestatario Congelado.
    Detecta si un prestatario con un préstamo activo ha sufrido un DeepFreeze (0x00800000).
    """
    sanitized_flags = _sanitize_flags(borrower_account_flags, "borrower_account_flags")
    is_borrower_frozen = bool(sanitized_flags & DEEP_FREEZE_FLAG)

    if is_borrower_frozen and loan_data.get("status") == "ACTIVE":
        return {
            "status": "HIGH_RISK",
            "code": "BORROWER_DEEP_FROZEN",
            "action_required": "FLAG_IMPAIRMENT_IMMINENT",
            "details": "El prestatario no podrá ejecutar LoanPay. Riesgo de default forzado.",
        }
    return {"status": "HEALTHY"}


def check_flcr_fee_redirection(broker_state: dict[str, Any]) -> dict[str, Any]:
    """
    Regla: Auditoría de Redirección de Comisiones.
    Si el Broker está en DeepFreeze, verifica que las comisiones se estén
    acumulando correctamente como First-Loss Capital suplementario.
    """
    if broker_state.get("OwnerDeepFreeze", False):
        if not broker_state.get("FeesRedirectedToFLCR", True):
            return {
                "status": "CRITICAL_ALERT",
                "code": "FLCR_REDIRECTION_FAILURE",
                "details": "Desviación detectada: Las comisiones no se están sumando al First-Loss Capital.",
            }
    return {"status": "HEALTHY"}


__all__ = [
    "DEEP_FREEZE_FLAG",
    "HermesRiskEngine",
    "XLS65VaultEvaluator",
    "evaluate_flcr_solvency_v1_1",
    "audit_vault_access_flags",
    "audit_vault_nav_parity",
    "load_config",
    "evaluate_vault_risk",
    "check_broker_freeze_status",
    "check_borrower_freeze_risk",
    "check_flcr_fee_redirection",
]