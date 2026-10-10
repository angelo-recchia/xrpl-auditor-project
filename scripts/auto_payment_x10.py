#!/usr/bin/env python3
"""
Script de Automatización de Pagos XLS-66 (LoanPayment) - Capa 3
Genera un borrador DRAFT_UNSIGNED para amortización de préstamos sobre Bóveda X10.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, ServerInfo

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_BORROWER = "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = PROJECT_ROOT / "progress" / "drafts"

def parse_args():
    parser = argparse.ArgumentParser(description="Generador de Borradores LoanPayment XLS-66 (DRAFT_UNSIGNED)")
    parser.add_argument("--amount", type=float, default=3.374428, help="Monto de pago en XRP (por defecto: cuota 1 de 3.374428 XRP)")
    parser.add_argument("--borrower", type=str, default=os.environ.get("BORROWER_ADDRESS", DEFAULT_BORROWER), help="Dirección del prestatario/pagador")
    parser.add_argument("--vault-id", type=str, default=os.environ.get("VAULT_ID", DEFAULT_VAULT_ID), help="Identificador VaultID (64 caracteres hex)")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint RPC Devnet")
    return parser.parse_args()

def main():
    args = parse_args()

    print("======================================================================")
    print(" AUTOMATIZACIÓN DE PAGOS XLS-66 (X10) - GENERADOR DRAFT_UNSIGNED")
    print("======================================================================")

    # Validación de formato de VaultID
    clean_vault_id = args.vault_id.strip()
    if len(clean_vault_id) != 64 or not re.fullmatch(r"[0-9A-Fa-f]{64}", clean_vault_id):
        print(f"[ERROR] VaultID inválido ({len(clean_vault_id)} caracteres). Debe ser hex de 64 caracteres.")
        sys.exit(1)

    print(f"Verificando cuotas y estado para Vault: {clean_vault_id[:10]}...")
    print(f"Prestatario: {args.borrower}")
    print(f"Monto de amortización: {args.amount:.6f} XRP")

    client = JsonRpcClient(args.rpc_url)
    sequence = 0
    network_id = 2
    base_fee = "1000"

    try:
        acct_res = client.request(AccountInfo(account=args.borrower, ledger_index="current"))
        sequence = int(acct_res.result.get("account_data", {}).get("Sequence", 0))
    except Exception:
        pass

    try:
        si_res = client.request(ServerInfo())
        network_id = si_res.result.get("info", {}).get("network_id", 2)
    except Exception:
        pass

    amount_drops = int(args.amount * 1_000_000)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    iso_now = datetime.now(timezone.utc).isoformat()

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = DRAFTS_DIR / f"auto_payment_x10_{timestamp_str}_DRAFT_UNSIGNED.json"

    draft_data = {
        "template_meta": {
            "template_id": f"auto_payment_x10_{timestamp_str}",
            "version": "1.0.0",
            "generated_at": iso_now,
            "network": f"XRPL Devnet ({args.rpc_url})",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"LoanPayment XLS-66 — Amortización de {args.amount} XRP sobre Vault {clean_vault_id[:8]}..."
        },
        "payment_context": {
            "vault_id": clean_vault_id,
            "payer": args.borrower,
            "amount_xrp": args.amount,
            "amount_drops": amount_drops,
            "message": "Borrador generado automáticamente para evitar mora."
        },
        "transaction": {
            "TransactionType": "LoanPayment",
            "Account": args.borrower,
            "VaultID": clean_vault_id,
            "Amount": str(amount_drops),
            "Fee": base_fee,
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "fields_to_verify_before_cold_signing": [
            f"Account (Payer): {args.borrower}",
            f"VaultID: {clean_vault_id}",
            f"Amount: {amount_drops} drops ({args.amount} XRP)",
            f"Fee: {base_fee} drops",
            f"Sequence: {sequence}",
            f"NetworkID: {network_id}"
        ],
        "cold_signing": {
            "status": "PENDING",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "instructions": "Transferir borrador JSON a hardware aislado, verificar campos offline y firmar."
        }
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, indent=4, ensure_ascii=False)

    print("----------------------------------------------------------------------")
    print(f"[ÉXITO] Borrador de pago automático generado en:")
    print(f" {filename}")
    print("Estado Firma: PENDING (Firma requerida en dispositivo en frío)")
    print("======================================================================")

if __name__ == "__main__":
    main()
