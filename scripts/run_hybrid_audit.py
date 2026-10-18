import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from browser.engine import HermesBrowserEngine
from evaluator.rules import XLS65VaultEvaluator, XLS66LendingEvaluator

async def run_hybrid_audit(dapp_url="https://devnet.xrpl.org"):
    print("[*] ==================================================")
    print("[*] SIMULACION DE ESTRES: AUDITORIA HIBRIDA CRITICA")
    print("[*] ==================================================")
    
    # 1. Hermes Fuera: Valores simulados en zona de riesgo CRÍTICO
    vault_data = XLS65VaultEvaluator.evaluate_vault(
        total_assets=10000.0, 
        total_shares=9500.0, 
        available_liquidity=300.0  # Liquidez del 3% (< 5% -> CRÍTICO)
    )
    
    lending_data = XLS66LendingEvaluator.evaluate_position(
        borrowed_amount=9000.0, 
        collateral_value=10000.0,  # LTV = 90% (>= 85% -> CRÍTICO)
        debt_service=1000.0, 
        cash_flow=900.0            # DSCR < 1.0 -> CRÍTICO
    )
    
    ledger_audit_data = {
        "node_target": "Devnet",
        "account": "rHb9CAJWyB4rJ91RWn96DkukG4bwdyTh",
        "xls65_vault_evaluation": vault_data,
        "xls66_lending_evaluation": lending_data,
        "overall_health": "CRÍTICO" if vault_data["vault_health"] == "CRÍTICO" or lending_data["health_status"] == "CRÍTICO" else "SALUDABLE"
    }
    
    print(f"[!] [Alerta Hermes Fuera] Métricas de estrés detectadas:")
    print(f"    - Bóveda XLS-65 Estado: {vault_data['vault_health']} (Liquidez: {vault_data['liquidity_ratio']})")
    print(f"    - Préstamo XLS-66 Estado: {lending_data['health_status']} (LTV: {lending_data['ltv']}, DSCR: {lending_data['dscr']})")

    # 2. Hermes Dentro: Inspección Visual en dApp
    print("[*] [Hermes Dentro] Verificando interfaz bajo estrés...")
    engine = HermesBrowserEngine(headless=True)
    
    # Navegamos y capturamos evidencia visual
    browser_result = await engine.inspect_vault_ui(dapp_url)
    
    # 3. Consolidación de Reporte Zero-Trust con Alerta
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hybrid_report = {
        "timestamp": timestamp,
        "architecture": "Hybrid Hermes (Fuera + Dentro) - Stress Test",
        "ledger_metrics": ledger_audit_data,
        "browser_audit": browser_result
    }
    
    drafts_dir = PROJECT_ROOT / "progress" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    report_filename = drafts_dir / f"hybrid_audit_stress_{timestamp}.json"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        json.dump(hybrid_report, f, indent=2)
        
    print(f"[!] Simulación de estrés completada. Informe de alerta guardado en: {report_filename}")
    print("[*] ==================================================")

if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://devnet.xrpl.org"
    asyncio.run(run_hybrid_audit(target_url))
