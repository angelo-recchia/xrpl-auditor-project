from decimal import Decimal
import os
import yaml

# Re-exportar para compatibilidad operativa
from evaluator.rules import HermesRiskEngine, XLS65VaultEvaluator

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'parameters.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def evaluate_vault_risk(flcr: float, borrower_shares: dict) -> dict:
    """
    Motor de evaluación de riesgo de grado institucional para XLS-66 (Project Hermes).
    Implementa doble capa defensiva (Sistémica + Granular) con aritmética escalada.
    """
    # Blindaje aritmético: escalado base 10^5 para evitar errores de coma flotante IEEE 754
    flcr_scaled = int(Decimal(str(flcr)) * 100000)
    min_flcr_scaled = 10000   # 10.0% Umbral crítico global (ROJO)
    warning_flcr_scaled = 12000 # 12.0% Umbral de advertencia (AMARILLO)
    
    risk_level = "VERDE"
    freeze_credit_required = False
    restricted_borrowers = []
    concentration_violations = []
    recommended_action = "Monitoreo estándar. Sin riesgo aparente."

    # Capa 1: Riesgo Sistémico (FLCR Global)
    if flcr_scaled <= min_flcr_scaled:
        risk_level = "ROJO"
        freeze_credit_required = True
        recommended_action = "CRÍTICO: Perforación del Límite de seguridad. Disparar FREEZE_CREDIT y transacción multi-sig de emergencia."
    elif flcr_scaled <= warning_flcr_scaled:
        risk_level = "AMARILLO"
        recommended_action = "Desviación leve. Incrementar frecuencia de sondeo."

    # Capa 2: Riesgo Granular / Concentración por Prestatario (Límite estricto 20%)
    concentration_limit = 0.20
    for borrower, share in borrower_shares.items():
        # Blindaje de valores flotantes en shares
        if Decimal(str(share)) > Decimal(str(concentration_limit)):
            restricted_borrowers.append(borrower)
            concentration_violations.append(
                f"Prestatario {borrower} excede la cuota permitida ({float(share)*100:.1f}% > {concentration_limit*100:.1f}%)"
            )

    if restricted_borrowers and risk_level != "ROJO":
        recommended_action += " [ACCIÓN PARCIAL: Bloqueo de nuevos tramos para prestatarios infractores]."

    return {
        "flcr_actual": flcr,
        "risk_level": risk_level,
        "freeze_credit_required": freeze_credit_required,
        "restricted_borrowers": restricted_borrowers,
        "recommended_action": recommended_action,
        "concentration_violations": concentration_violations
    }


def check_broker_freeze_status(broker_account_data: dict) -> dict:
    """
    Regla 1: Congelación del Broker.
    Evalúa si la pseudo-cuenta del Broker o su Owner están en Freeze/DeepFreeze.
    """
    is_pseudo_frozen = broker_account_data.get("FreezeState", 0) > 0
    is_owner_deep_frozen = broker_account_data.get("OwnerDeepFreeze", False)

    if is_pseudo_frozen or is_owner_deep_frozen:
        return {
            "status": "CRITICAL_ALERT",
            "code": "BROKER_FROZEN",
            "action_required": "HALT_NEW_DEPOSITS",
            "details": "El Broker o su propietario están congelados por el emisor del activo."
        }
    return {"status": "HEALTHY"}


def check_borrower_freeze_risk(loan_data: dict, borrower_account_flags: int) -> dict:
    """
    Regla 2: Impago Inminente por Prestatario Congelado.
    Detecta si un prestatario con un préstamo activo ha sufrido un DeepFreeze.
    """
    DEEP_FREEZE_FLAG = 0x00800000  # Máscara de bit según especificación XRPL
    is_borrower_frozen = bool(borrower_account_flags & DEEP_FREEZE_FLAG)

    if is_borrower_frozen and loan_data.get("status") == "ACTIVE":
        return {
            "status": "HIGH_RISK",
            "code": "BORROWER_DEEP_FROZEN",
            "action_required": "FLAG_IMPAIRMENT_IMMINENT",
            "details": "El prestatario no podrá ejecutar LoanPay. Riesgo de default forzado."
        }
    return {"status": "HEALTHY"}


def check_flcr_fee_redirection(broker_state: dict) -> dict:
    """
    Regla 3: Auditoría de Redirección de Comisiones.
    Si el Broker está en DeepFreeze, verifica que las comisiones se estén 
    acumulando correctamente como First-Loss Capital suplementario.
    """
    if broker_state.get("OwnerDeepFreeze", False):
        if not broker_state.get("FeesRedirectedToFLCR", True):
            return {
                "status": "CRITICAL_ALERT",
                "code": "FLCR_REDIRECTION_FAILURE",
                "details": "Desviación detectada: Las comisiones no se están sumando al First-Loss Capital."
            }
    return {"status": "HEALTHY"}
