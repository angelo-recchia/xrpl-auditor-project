#!/usr/bin/env python3
"""
Script de Procesamiento de Borradores y Firma en Frío (sign_draft) - Capa 3
Prepara y formatea el payload de firma física en Ledger / Tangem / Xaman.
"""

import argparse
import hashlib
import json
import os
import sys
from xrpl.core.binarycodec import encode_for_signing

def parse_args():
    parser = argparse.ArgumentParser(description="Procesador de Borradores para Firma en Frío (Xaman / Ledger)")
    parser.add_argument("draft_file", type=str, help="Ruta al archivo DRAFT_UNSIGNED.json")
    parser.add_argument("--devnet-sign", action="store_true", help="Solicitud de firma en Devnet")
    return parser.parse_args()

def main():
    args = parse_args()

    if not os.path.exists(args.draft_file):
        print(f"[ERROR] Archivo no encontrado: {args.draft_file}")
        sys.exit(1)

    with open(args.draft_file, "r", encoding="utf-8") as f:
        draft = json.load(f)

    tx = draft.get("transaction")
    if not tx:
        print("[ERROR] El borrador no contiene el objeto 'transaction'.")
        sys.exit(1)

    account = tx.get("Account")

    print("======================================================================")
    print(" PROCESAMIENTO DE BORRADOR PARA FIRMA EN FRÍO (HARDWARE / XAMAN)")
    print("======================================================================")
    print(f"Archivo Borrador: {os.path.abspath(args.draft_file)}")
    print(f"Tipo Operación:   {tx.get('TransactionType')}")
    print(f"Cuenta Firmante:  {account}")
    print("----------------------------------------------------------------------")

    # Serialización canónica para firma
    binary_for_signing = encode_for_signing(tx)
    # Hash SHA-512 Half de XRPL para verificación de firma
    hasher = hashlib.sha512(bytes.fromhex(binary_for_signing)).digest()
    signing_hash = hasher[:32].hex().upper()

    print(" CAMPOS A VERIFICAR EN LA PANTALLA DE TU HARDWARE WALLET:")
    for k, v in tx.items():
        print(f"  - {k:20}: {v}")

    print("----------------------------------------------------------------------")
    print(f" Signing Hash (SHA-512 Half): {signing_hash}")
    print("----------------------------------------------------------------------")

    if args.devnet_sign:
        print(" [AVISO DE SEGURIDAD STRICT COLD-SIGNING]")
        print(f" La clave maestra de {account} reside EXCLUSIVAMENTE en tu hardware (Ledger/Xaman).")
        print(" Hermes Agent no posee ni solicita tu semilla; la firma no puede realizarse en caliente.")
        print("----------------------------------------------------------------------")
        print(" INSTRUCCIONES PARA COMPLETAR LA FIRMA:")
        print(" 1. En Xaman (con red configurada en Devnet) o Ledger:")
        print("    Importa o aprueba la transacción descrita arriba.")
        print(" 2. Obtén el 'tx_blob' firmado generado por tu dispositivo.")
        print(" 3. Envía el blob firmado a Devnet ejecutando:")
        print("    python scripts/submit_signed_blob.py <TX_BLOB_HEX>")
        print("======================================================================")

if __name__ == "__main__":
    main()
