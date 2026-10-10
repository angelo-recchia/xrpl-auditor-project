#!/usr/bin/env python3
"""
Script de Depósito con Regular Key Delegada - Capa 3
Genera el borrador DRAFT_UNSIGNED para depósito delegado en la Bóveda XLS-65.
Cumple estrictamente con el protocolo Zero-Trust: NO firma en caliente ni maneja semillas.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, ServerInfo

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_MASTER = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = PROJECT_ROOT / "progress" / "drafts"
CONFIG_FILE = PROJECT_ROOT / "progress" / "config" / "delegation_registry.json"

def parse_args():
    parser = argparse.ArgumentParser(description="Generador de Borrador de Depósito Delegado (DRAFT_UNSIGNED)")
    parser.add_argument("--amount", type=float, default=100.0, help="Monto de XRP a depositar (default 100.0)")
    parser.add_argument("--master", type=str, default=os.environ.get("MASTER_ACCOUNT", DEFAULT_MASTER), help="Cuenta principal dueña de fondos")
    parser.add_argument("--vault-id", type=str, default=os.environ.get("VAULT_ID", DEFAULT_VAULT_ID), help="Identificador VaultID (64 hex)")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint RPC Devnet")
    return parser.parse_args()

def main():
    args = parse_args()
    print("======================================================================")
    print(" BORRADOR DE DEPÓSITO CON REGULAR KEY DELEGADA (ZERO-TRUST)")
    print("======================================================================")

    registered_delegate = None
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                registered_delegate = cdata.get("authorized_regular_key")
        except Exception:
            pass

    client = JsonRpcClient(args.rpc_url)

    # 1. Comprobar si la RegularKey está autorizada en el Ledger
    try:
        acct_res = client.request(AccountInfo(account=args.master, ledger_index="current"))
        acct_data = acct_res.result.get("account_data", {})
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al RPC de Devnet: {e}")
        sys.exit(1)

    active_regular_key = acct_data.get("RegularKey")

    if not active_regular_key:
        print("[ESTADO] PENDIENTE DE ACTIVACIÓN EN LEDGER:")
        print(f"La cuenta {args.master} aún no tiene autorizada una Regular Key en Devnet.")
        print(f"Genere primero el borrador SetRegularKey ejecutando:")
        print("  python scripts/setup_regular_key.py")
        print("======================================================================")
        sys.exit(0)

    print(f"Cuenta Principal (Master):  {args.master}")
    print(f"Clave Delegada en Ledger:   {active_regular_key}")
    if registered_delegate and registered_delegate != active_regular_key:
        print(f"[AVISO] Discrepancia con registro local ({registered_delegate}). Usando clave de ledger.")
    print("----------------------------------------------------------------------")

    sequence = int(acct_data.get("Sequence", 0))
    network_id = 2
    try:
        si_res = client.request(ServerInfo())
        network_id = si_res.result.get("info", {}).get("network_id", 2)
    except Exception:
        pass

    amount_drops = int(args.amount * 1_000_000)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    iso_now = datetime.now(timezone.utc).isoformat()

    # 2. Construir transacción VaultDeposit para firma delegada en frío
    draft = {
        "template_meta": {
            "template_id": f"delegated_vault_deposit_{timestamp_str}",
            "version": "2.0.0",
            "generated_at": iso_now,
            "network": f"XRPL Devnet ({args.rpc_url})",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"VaultDeposit XLS-65 — Depósito delegado de {args.amount} XRP firmado por RegularKey"
        },
        "delegation_context": {
            "master_account": args.master,
            "signing_regular_key": active_regular_key,
            "vault_id": args.vault_id
        },
        "transaction": {
            "TransactionType": "VaultDeposit",
            "Account": args.master,
            "VaultID": args.vault_id,
            "Amount": str(amount_drops),
            "Fee": "1000",
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "cold_signing": {
            "status": "PENDING_REGULAR_KEY_SIGNATURE",
            "device": "Ledger Nano S Plus / Tangem / Xaman (cuenta RegularKey)",
            "instructions": (
                "Firmar esta transacción utilizando la clave privada correspondiente a la RegularKey autorizada "
                f"({active_regular_key}). NUNCA firmar en caliente."
            )
        }
    }

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = DRAFTS_DIR / f"delegated_vault_deposit_x10_{timestamp_str}_DRAFT_UNSIGNED.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    print(f"[ÉXITO] Borrador generado en:")
    print(f" {filename}")
    print("----------------------------------------------------------------------")
    print("INSTRUCCIONES DE TRANSMISIÓN:")
    print(" 1. Firma este archivo con tu hardware wallet configurado para la RegularKey.")
    print(" 2. Envía el blob hexadecimal firmado ejecutando:")
    print("    python scripts/submit_signed_blob.py <TX_BLOB_HEX>")
    print("======================================================================")

if __name__ == "__main__":
    main()
