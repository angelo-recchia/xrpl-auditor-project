import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluators.rules import (
    evaluate_vault_risk,
    check_broker_freeze_status,
    check_borrower_freeze_risk,
    check_flcr_fee_redirection
)
from core.notifier import send_telegram_alert

async def evaluate_and_dispatch(s: dict) -> dict:
    result = evaluate_vault_risk(s["flcr"], s["shares"])
    print(f"[{s['name']}]")
    print(f"  -> FLCR Auditado: {s['flcr']*100:.1f}%")
    print(f"  -> Nivel de Riesgo: {result['risk_level']}")
    print(f"  -> Freeze Credit Requerido: {result['freeze_credit_required']}")
    print(f"  -> Prestatarios Restringidos: {result['restricted_borrowers']}")
    print(f"  -> Acción Recomendada: {result['recommended_action']}")

    # Disparo condicional de alerta push a Telegram ante colapso crítico
    if result['freeze_credit_required']:
        alert_msg = (
            f"*ALERTA CRÍTICA DE BÓVEDA XLS-66*\n"
            f"• Nivel: *{result['risk_level']}*\n"
            f"• FLCR Actual: *{s['flcr']*100:.1f}%*\n"
            f"• Acción: Ejecución inmediata de `FREEZE_CREDIT` y multi-sig de emergencia."
        )
        print(f"  -> [TELEGRAM] Disparando alerta push al chat ID configurado...")
        success = await send_telegram_alert(alert_msg)
        if success:
            print(f"  -> [TELEGRAM] Alerta despachada con éxito.")
        else:
            print(f"  -> [TELEGRAM] Aviso: No se pudo enviar (verifique .env o tokens).")
    return result

def run_st01():
    """ST-01: Salud Óptima (FLCR 22%, sin concentraciones excesivas)."""
    s = {"name": "Escenario 1: Salud Óptima (ST-01)", "flcr": 0.22, "shares": {"rBorrower1": 0.10, "rBorrower2": 0.12}}
    return asyncio.run(evaluate_and_dispatch(s))

def run_st02():
    """ST-02: Desviación Leve (FLCR 14%, concentración moderada)."""
    s = {"name": "Escenario 2: Desviación Leve (ST-02)", "flcr": 0.14, "shares": {"rBorrower1": 0.15, "rBorrower2": 0.10}}
    return asyncio.run(evaluate_and_dispatch(s))

def run_st03():
    """ST-03: Estrés Moderado + Concentración (FLCR 11%, rBorrower1 25%)."""
    s = {"name": "Escenario 3: Estrés Moderado + Concentración (ST-03)", "flcr": 0.11, "shares": {"rBorrower1": 0.25, "rBorrower2": 0.05}}
    return asyncio.run(evaluate_and_dispatch(s))

def run_st04():
    """ST-04: Colapso Sistémico + Infracción (FLCR 6.5%, Freeze Credit + Multi-sig)."""
    s = {"name": "Escenario 4: Colapso Sistémico (ROJO) + Infracción (ST-04)", "flcr": 0.065, "shares": {"rBorrower1": 0.28, "rBorrower2": 0.22}}
    return asyncio.run(evaluate_and_dispatch(s))

def run_st05():
    """ST-05: Cascada de Contagio Multiusuario y Deep Freeze (FLCR 1.0%, Default Masivo Alpha+Beta)."""
    s = {
        "name": "Escenario 5: Cascada de Contagio Multiusuario y Deep Freeze (ST-05)",
        "flcr": 0.010,
        "shares": {"rBorrowerAlpha": 0.40, "rBorrowerBeta": 0.35, "rBorrowerGamma": 0.05}
    }
    return asyncio.run(evaluate_and_dispatch(s))

async def evaluate_borrower_deep_freeze():
    loan_data = {"loan_id": "LOAN_XLS66_ALPHA_99", "status": "ACTIVE", "amount_xrp": 75000.0}
    DEEP_FREEZE_FLAG = 0x00800000
    borrower_flags = DEEP_FREEZE_FLAG
    
    print("[Escenario 6: Impago Inminente por DeepFreeze en Prestatario (ST-06)]")
    result = check_borrower_freeze_risk(loan_data, borrower_flags)
    print(f"  -> Estado del Préstamo: {loan_data['status']}")
    print(f"  -> Flags de Cuenta Prestatario: {hex(borrower_flags)}")
    print(f"  -> Diagnóstico Sentinel: {result['status']} ({result.get('code', 'OK')})")
    print(f"  -> Acción Requerida: {result.get('action_required', 'NONE')}")
    print(f"  -> Detalles: {result.get('details', 'Sin anomalías.')}")

    if result.get("status") in ["HIGH_RISK", "CRITICAL_ALERT"]:
        alert_msg = (
            f"*ALERTA DEFENSIVA XLS-66: PRESTATARIO EN DEEP FREEZE*\n"
            f"• Préstamo: `{loan_data['loan_id']}`\n"
            f"• Código: *{result.get('code')}*\n"
            f"• Acción: `{result.get('action_required')}` — Imposibilidad de ejecutar `LoanPay`."
        )
        print(f"  -> [TELEGRAM] Disparando alerta preventiva al operador...")
        success = await send_telegram_alert(alert_msg, level="HIGH_RISK")
        if success:
            print(f"  -> [TELEGRAM] Alerta despachada con éxito.")
        else:
            print(f"  -> [TELEGRAM] Aviso: No se pudo enviar (verifique .env o tokens).")
    return result

def run_st06():
    """ST-06: Impago Inminente por DeepFreeze de Prestatario (Regla 2: Flag 0x00800000)."""
    return asyncio.run(evaluate_borrower_deep_freeze())

async def evaluate_broker_freeze():
    broker_data = {
        "broker_account": "rBrokerPseudoAccount12345",
        "FreezeState": 1,
        "OwnerDeepFreeze": True
    }
    print("[Escenario 7: Congelación Institucional del Broker XLS-65 (ST-07)]")
    result = check_broker_freeze_status(broker_data)
    print(f"  -> Broker Account: {broker_data['broker_account']}")
    print(f"  -> FreezeState: {broker_data['FreezeState']}, OwnerDeepFreeze: {broker_data['OwnerDeepFreeze']}")
    print(f"  -> Diagnóstico Sentinel: {result['status']} ({result.get('code', 'OK')})")
    print(f"  -> Acción Requerida: {result.get('action_required', 'NONE')}")
    print(f"  -> Detalles: {result.get('details', 'Sin anomalías.')}")

    if result.get("status") in ["HIGH_RISK", "CRITICAL_ALERT"]:
        alert_msg = (
            f"*ALERTA CRÍTICA XLS-65: BROKER CONGELADO*\n"
            f"• Broker: `{broker_data['broker_account']}`\n"
            f"• Código: *{result.get('code')}*\n"
            f"• Acción: `{result.get('action_required')}` — Bloqueo preventivo de nuevos depósitos."
        )
        print(f"  -> [TELEGRAM] Disparando alerta crítica al operador...")
        success = await send_telegram_alert(alert_msg, level="CRITICAL")
        if success:
            print(f"  -> [TELEGRAM] Alerta despachada con éxito.")
        else:
            print(f"  -> [TELEGRAM] Aviso: No se pudo enviar (verifique .env o tokens).")
    return result

def run_st07():
    """ST-07: Congelación del Broker XLS-65 (Regla 1: HALT_NEW_DEPOSITS)."""
    return asyncio.run(evaluate_broker_freeze())

async def evaluate_fee_redirection():
    broker_state = {
        "broker_account": "rBrokerPseudoAccount12345",
        "OwnerDeepFreeze": True,
        "FeesRedirectedToFLCR": False
    }
    print("[Escenario 8: Auditoría de Redirección de Comisiones FLC (ST-08)]")
    result = check_flcr_fee_redirection(broker_state)
    print(f"  -> Broker Account: {broker_state['broker_account']}")
    print(f"  -> OwnerDeepFreeze: {broker_state['OwnerDeepFreeze']}")
    print(f"  -> FeesRedirectedToFLCR: {broker_state['FeesRedirectedToFLCR']}")
    print(f"  -> Diagnóstico Sentinel: {result['status']} ({result.get('code', 'OK')})")
    print(f"  -> Detalles: {result.get('details', 'Sin anomalías.')}")

    if result.get("status") in ["HIGH_RISK", "CRITICAL_ALERT"]:
        alert_msg = (
            f"*ALERTA CRÍTICA XLS-65: FALLO EN REDIRECCIÓN DE COMISIONES*\n"
            f"• Broker: `{broker_state['broker_account']}`\n"
            f"• Código: *{result.get('code')}*\n"
            f"• Detalle: `{result.get('details')}`"
        )
        print(f"  -> [TELEGRAM] Disparando alerta crítica al operador...")
        success = await send_telegram_alert(alert_msg, level="CRITICAL")
        if success:
            print(f"  -> [TELEGRAM] Alerta despachada con éxito.")
        else:
            print(f"  -> [TELEGRAM] Aviso: No se pudo enviar (verifique .env o tokens).")
    return result

def run_st08():
    """ST-08: Fallo en Redirección de Comisiones a First-Loss Capital (Regla 3)."""
    return asyncio.run(evaluate_fee_redirection())

async def run_stress_matrix():
    scenarios = [
        {"name": "Escenario 1: Salud Óptima (ST-01)", "flcr": 0.22, "shares": {"rBorrower1": 0.10, "rBorrower2": 0.12}},
        {"name": "Escenario 2: Desviación Leve (ST-02)", "flcr": 0.14, "shares": {"rBorrower1": 0.15, "rBorrower2": 0.10}},
        {"name": "Escenario 3: Estrés Moderado + Concentración (ST-03)", "flcr": 0.11, "shares": {"rBorrower1": 0.25, "rBorrower2": 0.05}},
        {"name": "Escenario 4: Colapso Sistémico (ROJO) + Infracción (ST-04)", "flcr": 0.065, "shares": {"rBorrower1": 0.28, "rBorrower2": 0.22}}
    ]

    print('=== EJECUTANDO MATRIZ DE ESTRÉS INSTITUCIONAL + TELEGRAM DISPATCH ===\n')
    for s in scenarios:
        await evaluate_and_dispatch(s)
        print('-' * 60)

if __name__ == '__main__':
    asyncio.run(run_stress_matrix())
