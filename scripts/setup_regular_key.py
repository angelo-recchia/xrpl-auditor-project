#!/usr/bin/env python3
"""
Script de Configuración de Regular Key Delegada - Capa 3
Genera el borrador SetRegularKey DRAFT_UNSIGNED para autorización en frío en XRPL Devnet.
Cumple estrictamente con el protocolo Zero-Trust: NO almacena ni maneja semillas privadas.
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
DEFAULT_MASTER = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
DEFAULT_DELEGATE = "rMaKA3J9m6tbJ2ziHDTDPbTNGaCKSqeSjs"

# Ruta canónica absoluta a progress/drafts
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = PROJECT_ROOT / "progress" / "drafts"

def parse_args():
    parser = argparse.ArgumentParser(description="Configuración de Regular Key Delegada (Flujo DRAFT_UNSIGNED)")
    parser.add_argument("--master", type=str, default=os.environ.get("MASTER_ACCOUNT", DEFAULT_MASTER), help="Cuenta principal a delegar")
    parser.add_argument("--regular-key", type=str, default=os.environ.get("REGULAR_KEY_ADDRESS", DEFAULT_DELEGATE), help="Dirección XRPL pública de la Regular Key a autorizar")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint RPC Devnet")
    return parser.parse_args()

def main():
    args = parse_args()
    client = JsonRpcClient(args.rpc_url)

    if not args.regular_key.startswith("r"):
        print(f"[ERROR] Dirección de RegularKey inválida: {args.regular_key}")
        sys.exit(1)

    if args.master == args.regular_key:
        print("[ERROR] La RegularKey no puede ser idéntica a la cuenta principal.")
        sys.exit(1)

    print("======================================================================")
    print(" CONFIGURACIÓN DE REGULAR KEY DELEGADA (FLUX ZERO-TRUST COLD SIGNING)")
    print("======================================================================")
    print(f"Cuenta Principal (Master): {args.master}")
    print(f"Clave Delegada (Pública):  {args.regular_key}")
    print(f"Endpoint RPC:              {args.rpc_url}")
    print("----------------------------------------------------------------------")

    # 1. Consultar estado y secuencia de la cuenta principal
    try:
        acct_res = client.request(AccountInfo(account=args.master, ledger_index="current"))
        acct_data = acct_res.result.get("account_data", {})
    except Exception as e:
        print(f"[ERROR] Error al consultar cuenta en Devnet: {e}")
        sys.exit(1)

    if not acct_data:
        print(f"[ERROR] Cuenta principal {args.master} no encontrada en Devnet.")
        sys.exit(1)

    sequence = int(acct_data.get("Sequence", 0))

    network_id = 2
    try:
        si_res = client.request(ServerInfo())
        network_id = si_res.result.get("info", {}).get("network_id", 2)
    except Exception:
        pass

    # 2. Guardar metadata pública de delegación (SIN claves privadas)
    delegation_meta = {
        "master_account": args.master,
        "authorized_regular_key": args.regular_key,
        "network": f"XRPL Devnet (NetworkID: {network_id})",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "AWAITING_MASTER_COLD_SIGNATURE"
    }
    config_dir = PROJECT_ROOT / "progress" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    meta_path = config_dir / "delegation_registry.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(delegation_meta, f, indent=2)

    print(f"[OK] Registro público de delegación actualizado: {meta_path}")
    print("----------------------------------------------------------------------")

    # 3. Generar borrador DRAFT_UNSIGNED para SetRegularKey
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    draft = {
        "template_meta": {
            "template_id": f"set_regular_key_{timestamp_str}",
            "version": "2.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "network": f"XRPL Devnet ({args.rpc_url})",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"SetRegularKey — Autorizar a {args.regular_key} como clave delegada"
        },
        "delegation_info": {
            "master_account": args.master,
            "authorized_regular_key": args.regular_key,
            "security_policy": "STRICT_COLD_SIGNING_ZERO_TRUST"
        },
        "transaction": {
            "TransactionType": "SetRegularKey",
            "Account": args.master,
            "RegularKey": args.regular_key,
            "Fee": "1000",
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "cold_signing": {
            "status": "PENDING_MASTER_KEY_SIGNATURE",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "instructions": "Firmar este payload UNA SOLA VEZ con la clave maestra física. Tras ser validada en el ledger, la RegularKey estará autorizada en el Ledger para firmar transacciones de forma aislada."
        }
    }

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft_file = DRAFTS_DIR / f"set_regular_key_{timestamp_str}_DRAFT_UNSIGNED.json"
    with open(draft_file, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    print(" BORRADOR DE DELEGACIÓN GENERADO (FIRMA ÚNICA EN FRÍO):")
    print(f"  Archivo: {draft_file}")
    print("======================================================================")

if __name__ == "__main__":
    main()
