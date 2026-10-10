#!/usr/bin/env python3
"""
Script de Monitoreo Diario de Vencimiento de Préstamos XLS-66 - Capa 3
Monitorea la fecha exacta de vencimiento y estado de cobro de préstamos en la Bóveda X10.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountObjects

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_OWNER = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
RIPPLE_EPOCH = 946684800

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROGRESS_DIR = PROJECT_ROOT / "progress"

def ripple_to_datetime(ripple_sec: int) -> datetime:
    return datetime.fromtimestamp(ripple_sec + RIPPLE_EPOCH, tz=timezone.utc)

def run_maturity_check():
    rpc_url = os.environ.get("XRPL_RPC_URL", DEFAULT_RPC)
    vault_id = os.environ.get("VAULT_ID", DEFAULT_VAULT_ID)
    owner = os.environ.get("VAULT_OWNER", DEFAULT_OWNER)

    now = datetime.now(timezone.utc)
    print("======================================================================")
    print(" MONITOR DIARIO DE VENCIMIENTO XLS-66 (BÓVEDA X10)")
    print("======================================================================")
    print(f"Fecha/Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"VaultID:           {vault_id}")
    print(f"Endpoint RPC:      {rpc_url}")
    print("----------------------------------------------------------------------")

    client = JsonRpcClient(rpc_url)

    # 1. Encontrar LoanBroker de la bóveda
    broker_obj = None
    try:
        res = client.request(AccountObjects(account=owner, ledger_index="current"))
        for obj in res.result.get("account_objects", []):
            if obj.get("LedgerEntryType") == "LoanBroker" and obj.get("VaultID") == vault_id:
                broker_obj = obj
                break
    except Exception as e:
        print(f"[ERROR] No se pudo consultar la cuenta del propietario: {e}")
        sys.exit(1)

    if not broker_obj:
        print("[AVISO] No se encontró LoanBroker vinculado a la bóveda (sin préstamos activos).")
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = PROGRESS_DIR / "loan_maturity_status.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": now.isoformat(),
                "vault_id": vault_id,
                "has_alerts": False,
                "status": "NO_BROKER_OR_LOANS",
                "loans": []
            }, f, indent=2)
        return

    broker_account = broker_obj.get("Account")
    broker_id = broker_obj.get("index")
    print(f"LoanBroker Account: {broker_account}")
    print(f"LoanBroker ID:      {broker_id}")
    print("----------------------------------------------------------------------")

    # 2. Consultar préstamos activos
    loans = []
    try:
        b_res = client.request(AccountObjects(account=broker_account, ledger_index="current"))
        for obj in b_res.result.get("account_objects", []):
            if obj.get("LedgerEntryType") == "Loan" and obj.get("LoanBrokerID") == broker_id:
                loans.append(obj)
    except Exception as e:
        print(f"[ERROR] No se pudieron consultar préstamos del broker: {e}")
        sys.exit(1)

    if not loans:
        print("[INFO] No hay préstamos activos registrados en el LoanBroker.")
        return

    print(f"Préstamos activos encontrados: {len(loans)}")
    print("----------------------------------------------------------------------")

    report_list = []
    has_alerts = False

    for loan in loans:
        seq = loan.get("LoanSequence")
        borrower = loan.get("Borrower")
        total_out_drops = int(loan.get("TotalValueOutstanding", 0))
        principal_out_drops = int(loan.get("PrincipalOutstanding", 0))
        payments_remaining = loan.get("PaymentRemaining", 0)
        due_ripple = loan.get("NextPaymentDueDate", 0)
        due_dt = ripple_to_datetime(due_ripple)
        grace_sec = loan.get("GracePeriod", 604800)
        grace_dt = datetime.fromtimestamp(due_ripple + RIPPLE_EPOCH + grace_sec, tz=timezone.utc)

        if now < due_dt:
            status = "AL DÍA"
            days_left = (due_dt - now).total_seconds() / 86400
            time_msg = f"Vence en {days_left:.1f} días"
        elif now < grace_dt:
            status = "PERIODO DE GRACIA"
            days_grace_left = (grace_dt - now).total_seconds() / 86400
            time_msg = f"En gracia: expira en {days_grace_left:.1f} días"
            has_alerts = True
        else:
            status = "MORA / DEFAULT RISK"
            days_overdue = (now - due_dt).total_seconds() / 86400
            time_msg = f"VENCIDO hace {days_overdue:.1f} días"
            has_alerts = True

        print(f" PRÉSTAMO #{seq}:")
        print(f"  - Prestatario:           {borrower}")
        print(f"  - Deuda Pendiente:       {total_out_drops / 1_000_000:,.6f} XRP (Principal: {principal_out_drops / 1_000_000:,.6f} XRP)")
        print(f"  - Cuotas Restantes:      {payments_remaining}")
        print(f"  - Fecha Próximo Pago:    {due_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  - Límite Periodo Gracia: {grace_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  - Estado de Cobro:       [{status}] ({time_msg})")
        print("  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")

        report_list.append({
            "loan_sequence": seq,
            "borrower": borrower,
            "total_outstanding_xrp": total_out_drops / 1_000_000,
            "payments_remaining": payments_remaining,
            "next_due_date_iso": due_dt.isoformat(),
            "grace_limit_iso": grace_dt.isoformat(),
            "status": status,
            "time_msg": time_msg
        })

    # Guardar reporte de seguimiento
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = PROGRESS_DIR / "loan_maturity_status.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.isoformat(),
            "vault_id": vault_id,
            "has_alerts": has_alerts,
            "loans": report_list
        }, f, indent=2)

    print(f"Registro de estado actualizado en: {report_path.resolve()}")
    print("======================================================================")

if __name__ == "__main__":
    run_maturity_check()
