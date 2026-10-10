#!/usr/bin/env python3
"""
Script de Envío de Blobs Firmados a XRPL Devnet - Capa 3
Transmite el blob hexadecimal firmado en frío al RPC de Devnet.
"""

import argparse
import os
import re
import sys
import httpx

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"

def parse_args():
    parser = argparse.ArgumentParser(description="Envío de Blob Firmado a XRPL Devnet")
    parser.add_argument("tx_blob", type=str, help="Blob hexadecimal firmado devuelto por hardware wallet")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint RPC Devnet")
    return parser.parse_args()

def main():
    args = parse_args()
    blob = args.tx_blob.strip()

    if not re.fullmatch(r"[0-9A-Fa-f]+", blob) or len(blob) < 32:
        print("[ERROR] El blob proporcionado no es un formato hexadecimal válido.")
        sys.exit(1)

    print("======================================================================")
    print(" TRANSMISIÓN DE TRANSACCIÓN FIRMADA A XRPL DEVNET")
    print("======================================================================")
    print(f"Endpoint RPC: {args.rpc_url}")
    print(f"Longitud Blob: {len(blob)} caracteres hex")
    print("----------------------------------------------------------------------")

    payload = {
        "method": "submit",
        "params": [{"tx_blob": blob}]
    }

    try:
        res = httpx.post(args.rpc_url, json=payload, timeout=15.0)
        res_json = res.json()
    except Exception as e:
        print(f"[ERROR] Error al conectar con nodo RPC: {e}")
        sys.exit(1)

    result = res_json.get("result", {})
    engine_result = result.get("engine_result")
    engine_msg = result.get("engine_result_message")
    tx_hash = result.get("tx_json", {}).get("hash")

    print(f"Resultado del Motor:  {engine_result}")
    print(f"Mensaje:              {engine_msg}")
    print(f"Hash de Transacción:  {tx_hash}")
    print("======================================================================")

    if engine_result == "tesSUCCESS":
        print("[ÉXITO] Transacción validada e introducida en el ledger de Devnet.")
    else:
        print(f"[AVISO] Estado devuelto: {engine_result}")

if __name__ == "__main__":
    main()
