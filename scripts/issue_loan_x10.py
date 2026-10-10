#!/usr/bin/env python3
"""
Script de Emisión de Préstamos XLS-66 sobre Bóveda X10 - Capa 3
Genera un borrador DRAFT_UNSIGNED listo para cold-signing tras verificar liquidez en Devnet.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import LedgerEntry, AccountObjects, AccountInfo, ServerInfo

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_OPERATOR = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
DEFAULT_BORROWER = "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = PROJECT_ROOT / "progress" / "drafts"

def parse_args():
    parser = argparse.ArgumentParser(description="Emisión de Préstamos XLS-66 sobre Bóveda X10 (DRAFT_UNSIGNED)")
    parser.add_argument("--amount", type=float, required=True, help="Monto del préstamo en XRP")
    parser.add_argument("--payments", type=int, required=True, help="Número de cuotas / pagos")
    parser.add_argument("--interest", type=float, required=True, help="Tasa de interés anual en porcentaje (ej. 5.0)")
    parser.add_argument("--borrower", type=str, default=os.environ.get("BORROWER_ADDRESS", DEFAULT_BORROWER), help="Dirección del prestatario")
    parser.add_argument("--vault-id", type=str, default=os.environ.get("VAULT_ID", DEFAULT_VAULT_ID), help="Identificador VaultID")
    parser.add_argument("--operator", type=str, default=os.environ.get("VAULT_OWNER", DEFAULT_OPERATOR), help="Dirección del operador de la bóveda")
    parser.add_argument("--duration-days", type=int, default=None, help="Duración total en días (por defecto: payments * 30)")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint JSON-RPC Devnet")
    return parser.parse_args()

def calculate_schedule(principal_drops: int, annual_rate_bps: int, payments: int, duration_days: int):
    duration_hours = duration_days * 24
    total_interest_drops = int(principal_drops * (annual_rate_bps / 10000.0) * (duration_hours / (365 * 24)))
    total_repay_drops = principal_drops + total_interest_drops

    schedule = []
    p_per_pay = principal_drops // payments
    i_per_pay = total_interest_drops // payments

    for idx in range(1, payments + 1):
        p_amt = p_per_pay if idx < payments else principal_drops - (p_per_pay * (payments - 1))
        i_amt = i_per_pay if idx < payments else total_interest_drops - (i_per_pay * (payments - 1))
        schedule.append({
            "payment_index": idx,
            "principal_drops": p_amt,
            "interest_drops": i_amt,
            "total_drops": p_amt + i_amt,
            "principal_xrp": round(p_amt / 1_000_000, 6),
            "interest_xrp": round(i_amt / 1_000_000, 6),
            "total_xrp": round((p_amt + i_amt) / 1_000_000, 6)
        })

    return {
        "duration_days": duration_days,
        "duration_hours": duration_hours,
        "total_interest_drops": total_interest_drops,
        "total_repay_drops": total_repay_drops,
        "schedule": schedule
    }

def main():
    args = parse_args()
    duration_days = args.duration_days if args.duration_days is not None else max(args.payments * 30, 30)

    principal_drops = int(args.amount * 1_000_000)
    annual_rate_bps = int(round(args.interest * 100))

    client = JsonRpcClient(args.rpc_url)

    # 1. Consulta Bóveda en Devnet
    try:
        vault_res = client.request(LedgerEntry(index=args.vault_id, ledger_index="current"))
        vault_node = vault_res.result.get("node", {})
    except Exception as e:
        print(f"[ERROR] Error al consultar Bóveda en Devnet: {e}")
        sys.exit(1)

    if not vault_node:
        print(f"[ERROR] No se encontró la Bóveda con ID {args.vault_id}")
        sys.exit(1)

    assets_total_drops = int(vault_node.get("AssetsTotal", 0))
    assets_avail_drops = int(vault_node.get("AssetsAvailable", 0))

    # 2. Consultar AccountObjects para obtener estado de LoanBroker existente
    debt_total_drops = 0
    try:
        obj_res = client.request(AccountObjects(account=args.operator, ledger_index="current"))
        for obj in obj_res.result.get("account_objects", []):
            if obj.get("LedgerEntryType") == "LoanBroker" and obj.get("VaultID") == args.vault_id:
                debt_total_drops = int(obj.get("DebtTotal", 0))
                break
    except Exception:
        pass

    # 3. Consultar AccountInfo y ServerInfo para metadatos de transacción
    sequence = 0
    try:
        acct_res = client.request(AccountInfo(account=args.operator, ledger_index="current"))
        sequence = int(acct_res.result.get("account_data", {}).get("Sequence", 0))
    except Exception:
        pass

    network_id = 2
    base_fee = "1000"
    try:
        si_res = client.request(ServerInfo())
        info = si_res.result.get("info", {})
        network_id = info.get("network_id", 2)
    except Exception:
        pass

    # 4. Verificación de liquidez y límites
    avail_after_drops = assets_avail_drops - principal_drops
    debt_after_drops = debt_total_drops + principal_drops
    ltv_after_bps = int((debt_after_drops / assets_total_drops) * 10000) if assets_total_drops > 0 else 10000

    within_capacity = avail_after_drops >= 0
    within_ltv = ltv_after_bps <= 8000

    status = "SALUDABLE" if (within_capacity and within_ltv) else ("ESTRÉS" if within_capacity else "CRÍTICO")

    if not within_capacity:
        print(f"[CRÍTICO] Capacidad insuficiente en Bóveda X10.")
        print(f"Disponible: {assets_avail_drops / 1_000_000:.6f} XRP | Solicitado: {args.amount:.6f} XRP")
        sys.exit(1)

    # 5. Cálculo del plan de amortización
    plan = calculate_schedule(principal_drops, annual_rate_bps, args.payments, duration_days)

    timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 6. Generación del borrador DRAFT_UNSIGNED
    draft = {
        "template_meta": {
            "template_id": f"loan_create_x10_{timestamp_str}",
            "version": "1.0.0",
            "generated_at": iso_now,
            "network": f"XRPL Devnet ({args.rpc_url})",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"LoanCreate XLS-66 — Bóveda Cold storage X10 ({args.amount} XRP a {args.payments} pagos, {args.interest}% anual)"
        },
        "vault_context": {
            "VaultID": args.vault_id,
            "VaultAccount": vault_node.get("Account"),
            "VaultOperator": args.operator,
            "AssetsTotal_drops": assets_total_drops,
            "AssetsAvailable_drops": assets_avail_drops,
            "DebtTotal_drops": debt_total_drops,
            "liquidity_status_before": "SALUDABLE"
        },
        "loan_terms": {
            "borrower": args.borrower,
            "principal_xrp": args.amount,
            "principal_drops": principal_drops,
            "annual_rate_bps": annual_rate_bps,
            "annual_rate_pct": args.interest,
            "payments_count": args.payments,
            "duration_days": duration_days,
            "duration_hours": plan["duration_hours"],
            "amortization": "linear",
            "total_interest_drops": plan["total_interest_drops"],
            "total_interest_xrp": round(plan["total_interest_drops"] / 1_000_000, 6),
            "total_repay_drops": plan["total_repay_drops"],
            "total_repay_xrp": round(plan["total_repay_drops"] / 1_000_000, 6),
            "repayment_schedule": plan["schedule"]
        },
        "liquidity_validation": {
            "within_capacity": within_capacity,
            "within_ltv": within_ltv,
            "available_after_drops": avail_after_drops,
            "available_after_xrp": round(avail_after_drops / 1_000_000, 6),
            "debt_after_drops": debt_after_drops,
            "debt_after_xrp": round(debt_after_drops / 1_000_000, 6),
            "ltv_after_bps": ltv_after_bps,
            "ltv_after_pct": round(ltv_after_bps / 100.0, 2),
            "status_after": status
        },
        "transaction": {
            "TransactionType": "LoanCreate",
            "Account": args.operator,
            "Borrower": args.borrower,
            "VaultID": args.vault_id,
            "Principal": str(principal_drops),
            "InterestRateBps": annual_rate_bps,
            "LoanDurationHours": plan["duration_hours"],
            "PaymentCount": args.payments,
            "Amortization": "linear",
            "DayCountConvention": "actual/365",
            "Fee": base_fee,
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "fields_to_verify_before_cold_signing": [
            f"Account: {args.operator}",
            f"Borrower: {args.borrower}",
            f"VaultID: {args.vault_id}",
            f"Principal: {principal_drops} drops ({args.amount} XRP)",
            f"InterestRateBps: {annual_rate_bps} ({args.interest}% anual)",
            f"PaymentCount: {args.payments}",
            f"LoanDurationHours: {plan['duration_hours']} horas ({duration_days} días)",
            f"Fee: {base_fee} drops",
            f"Sequence: {sequence}",
            f"NetworkID: {network_id}"
        ],
        "cold_signing": {
            "status": "PENDING",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "instructions": "Transferir borrador JSON a dispositivo en frío aislado, verificar campos en hardware y firmar offline."
        }
    }

    # Guardar en ./progress/drafts/
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"loan_create_x10_{timestamp_str}_DRAFT_UNSIGNED.json"
    filepath = DRAFTS_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    # 7. Resumen en consola
    print("======================================================================")
    print(" XLS-66 LOAN CREATE - BORRADOR GENERADO (DRAFT_UNSIGNED)")
    print("======================================================================")
    print(f"Bóveda Origen:       Cold storage X10 ({args.vault_id[:16]}...)")
    print(f"Operador (Account):  {args.operator}")
    print(f"Prestatario:         {args.borrower}")
    print(f"Principal Préstamo:  {args.amount:.6f} XRP ({principal_drops} drops)")
    print(f"Tasa de Interés:     {args.interest:.2f}% anual ({annual_rate_bps} bps)")
    print(f"Cuotas / Pagos:      {args.payments} pagos (amortización lineal)")
    print(f"Duración Total:      {duration_days} días ({plan['duration_hours']} horas)")
    print(f"Interés Total:       {plan['total_interest_drops'] / 1_000_000:.6f} XRP ({plan['total_interest_drops']} drops)")
    print(f"Total a Devolver:    {plan['total_repay_drops'] / 1_000_000:.6f} XRP")
    print("----------------------------------------------------------------------")
    print(" CALENDARIO DE AMORTIZACIÓN:")
    for pay in plan["schedule"]:
        print(f"  Cuota {pay['payment_index']}: Principal={pay['principal_xrp']:.6f} XRP | Interés={pay['interest_xrp']:.6f} XRP | Total={pay['total_xrp']:.6f} XRP")
    print("----------------------------------------------------------------------")
    print(" IMPACTO EN LIQUIDEZ (XLS-65):")
    print(f"  Disponible previo:   {assets_avail_drops / 1_000_000:.6f} XRP")
    print(f"  Disponible tras op:  {avail_after_drops / 1_000_000:.6f} XRP")
    print(f"  LTV resultante:      {ltv_after_bps / 100:.2f}% ({ltv_after_bps} bps)")
    print(f"  Estado de Bóveda:    {status}")
    print("----------------------------------------------------------------------")
    print(f" Archivo Borrador:   {filepath}")
    print(" Estado Firma:       PENDING (Firma aislada requerida en hardware)")
    print("======================================================================")

if __name__ == "__main__":
    main()
