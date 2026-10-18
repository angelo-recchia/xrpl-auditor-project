import asyncio
import json
import sys
from pathlib import Path

# Asegurar importación de core si se ejecuta directamente
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ledger_client import XRPLedgerClient
from core.auditor import HermesAuditor

async def main():
    ledger = XRPLedgerClient()
    # Dirección Genesis de Devnet (corregido checksum/typo si aplica)
    test_account = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
    
    print(f"[*] Conectando al nodo para auditar la cuenta: {test_account}")
    info = await ledger.get_account_status(test_account)
    account_data = info.get("account_data", {})
    
    balance_drops = int(account_data.get("Balance", 0))
    balance_xrp = balance_drops / 1_000_000
    print(f"[+] Balance real obtenido del Ledger: {balance_xrp:,.6f} XRP")
    
    # Vinculamos el balance real del colateral con un modelo de préstamo de prueba
    vault_data = {"collateral_value": balance_xrp}
    loan_data = {
        "outstanding_debt": 2500.0, 
        "net_operating_income": 1200.0, 
        "debt_service": 800.0
    }
    
    auditor = HermesAuditor(vault_data, loan_data)
    report = auditor.generate_audit_report()
    
    print("\n[=] INFORME DE AUDITORÍA EN VIVO:")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
