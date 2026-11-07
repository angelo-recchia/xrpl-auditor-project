import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluators.rules import evaluate_vault_risk
from core.notifier import send_telegram_alert

async def run_stress_matrix():
    scenarios = [
        {"name": "Escenario 1: Salud Óptima", "flcr": 0.22, "shares": {"rBorrower1": 0.10, "rBorrower2": 0.12}},
        {"name": "Escenario 2: Desviación Leve", "flcr": 0.14, "shares": {"rBorrower1": 0.15, "rBorrower2": 0.10}},
        {"name": "Escenario 3: Estrés Moderado + Concentración", "flcr": 0.11, "shares": {"rBorrower1": 0.25, "rBorrower2": 0.05}},
        {"name": "Escenario 4: Colapso Sistémico (ROJO) + Infracción", "flcr": 0.065, "shares": {"rBorrower1": 0.28, "rBorrower2": 0.22}}
    ]

    print('=== EJECUTANDO MATRIZ DE ESTRÉS INSTITUCIONAL + TELEGRAM DISPATCH ===\n')
    for s in scenarios:
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

        print('-' * 60)

if __name__ == '__main__':
    asyncio.run(run_stress_matrix())
