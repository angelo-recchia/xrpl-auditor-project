import asyncio
import sys
import os

from core.ledger_client import XRPLedgerClient
from evaluators.rules import evaluate_vault_risk
from actions.multisig_builder import create_emergency_multisig_payload
from telemetry.crypto_anchor import sign_telemetry_report
from core.notifier import send_telegram_alert

async def run_full_sentinel_audit():
    print("=== PROYECTO HERMES: INICIANDO AUDITORÍA EN VIVO (DEVNET) ===")
    
    ledger = XRPLedgerClient()
    vault_account = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
    
    try:
        account_info = await ledger.get_account_status(vault_account)
        balance_xrp = int(account_info.get('account_data', {}).get('Balance', 0)) / 1_000_000
        flcr_actual = 0.075  # Simulación de escenario crítico sobre datos reales
        borrower_shares = {'rBorrower1': 0.15, 'rBorrower2': 0.25}
        
        risk_result = evaluate_vault_risk(flcr_actual, borrower_shares)
        
        # Generar borrador de emergencia en Zona Roja
        if risk_result['risk_level'] == "ROJO":
            print("\n[!] ESTADO CRÍTICO DETECTADO: Disparando protocolo de mitigación...")
            payload = create_emergency_multisig_payload(vault_account, action_type="FREEZE_CREDIT")
            print(payload)
            
            # Disparo de alerta push por Telegram
            alert_msg = f"*ALERTA CRÍTICA - BÓVEDA EN ZONA ROJA*\nCuenta: `{vault_account}`\nFLCR: {flcr_actual*100}%\nAcción: FREEZE_CREDIT emitido."
            await send_telegram_alert(alert_msg)

        report_data = {
            "vault": vault_account,
            "balance_xrp": balance_xrp,
            "flcr": flcr_actual,
            "risk_level": risk_result['risk_level'],
            "violations": risk_result['concentration_violations']
        }
        signed_report = sign_telemetry_report(report_data)
        print(f"[+] Certificado Generado: {signed_report['telemetry_hash']}")
        
    except Exception as e:
        print(f"[!] Error en la auditoría: {e}")

    print("=== AUDITORÍA FINALIZADA ===")

if __name__ == "__main__":
    asyncio.run(run_full_sentinel_audit())
