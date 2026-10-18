"""Módulo Auditor de Riesgo y Liquidez (XLS-65 / XLS-66)
Basado en especificación: specs/auditor_spec.md
"""
from typing import Dict, Any, Union

def calculate_ltv(outstanding_debt: float, collateral_value: float) -> float:
    """Calcula Loan-to-Value (LTV) como porcentaje.
    LTV = (Deuda Pendiente / Valor del Colateral) * 100
    """
    if collateral_value <= 0:
        return float('inf') if outstanding_debt > 0 else 0.0
    return (outstanding_debt / collateral_value) * 100.0

def calculate_dscr(net_operating_income: float, debt_service: float) -> float:
    """Calcula Debt Service Coverage Ratio (DSCR).
    DSCR = Ingresos Netos Operativos / Servicio de Deuda
    """
    if debt_service <= 0:
        return float('inf') if net_operating_income >= 0 else 0.0
    return net_operating_income / debt_service

def evaluate_health(ltv: float, dscr: float) -> str:
    """Categoriza el estado de salud de la posición:
    - CRÍTICO: LTV > 85% o DSCR < 1.10
    - ESTRÉS: 75% < LTV <= 85% o 1.10 <= DSCR < 1.25
    - SALUDABLE: LTV <= 75% y DSCR >= 1.25
    """
    if ltv > 85.0 or dscr < 1.10:
        return "CRÍTICO"
    if (75.0 < ltv <= 85.0) or (1.10 <= dscr < 1.25):
        return "ESTRÉS"
    if ltv <= 75.0 and dscr >= 1.25:
        return "SALUDABLE"
    return "ESTRÉS"

def audit_position(
    outstanding_debt: float,
    collateral_value: float,
    net_operating_income: float,
    debt_service: float
) -> Dict[str, Any]:
    """Evalúa de forma integral una posición de préstamo / bóveda."""
    ltv = calculate_ltv(outstanding_debt, collateral_value)
    dscr = calculate_dscr(net_operating_income, debt_service)
    status = evaluate_health(ltv, dscr)

    return {
        "status": status,
        "ltv_percent": round(ltv, 4) if ltv != float('inf') else None,
        "dscr": round(dscr, 4) if dscr != float('inf') else None,
        "metrics": {
            "outstanding_debt": outstanding_debt,
            "collateral_value": collateral_value,
            "net_operating_income": net_operating_income,
            "debt_service": debt_service
        }
    }

class HermesAuditor:
    """Clase principal de auditoría para acoplar datos de Vault XLS-65 y Préstamos XLS-66."""
    def __init__(self, vault_data: Dict[str, Any], loan_data: Dict[str, Any]):
        self.vault_data = vault_data
        self.loan_data = loan_data

    def generate_audit_report(self) -> Dict[str, Any]:
        collateral_value = float(self.vault_data.get("collateral_value", 0.0))
        outstanding_debt = float(self.loan_data.get("outstanding_debt", 0.0))
        net_operating_income = float(self.loan_data.get("net_operating_income", 0.0))
        debt_service = float(self.loan_data.get("debt_service", 0.0))

        ltv = calculate_ltv(outstanding_debt, collateral_value)
        dscr = calculate_dscr(net_operating_income, debt_service)
        status = evaluate_health(ltv, dscr)

        return {
            "status": status,
            "ltv_percent": round(ltv, 4) if ltv != float('inf') else "inf",
            "dscr": round(dscr, 4) if dscr != float('inf') else "inf",
            "metrics": {
                "outstanding_debt": outstanding_debt,
                "collateral_value": collateral_value,
                "net_operating_income": net_operating_income,
                "debt_service": debt_service
            }
        }

