#!/usr/bin/env python3
"""
Script de Depósito en Bóveda XLS-65 (VaultDeposit) - Capa 3
Genera un borrador DRAFT_UNSIGNED para depósito en frío en la Bóveda X10 y consulta información contable.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, AccountObjects, LedgerEntry, ServerInfo

DEFAULT_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_DEPOSITOR = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = PROJECT_ROOT / "progress" / "drafts"

def parse_args():
    parser = argparse.ArgumentParser(description="Generador de Borrador XLS-65 VaultDeposit (DRAFT_UNSIGNED)")
    parser.add_argument("--amount", type=float, default=100.0, help="Cantidad de XRP a depositar (por defecto 100.0)")
    parser.add_argument("--depositor", type=str, default=os.environ.get("DEPOSITOR_ADDRESS", DEFAULT_DEPOSITOR), help="Dirección del depositante")
    parser.add_argument("--vault-id", type=str, default=os.environ.get("VAULT_ID", DEFAULT_VAULT_ID), help="Identificador VaultID (64 hex)")
    parser.add_argument("--rpc-url", type=str, default=os.environ.get("XRPL_RPC_URL", DEFAULT_RPC), help="Endpoint RPC Devnet")
    parser.add_argument("--wallet-info", action="store_true", help="Muestra información contable y balances de la cartera depositante")
    parser.add_argument("--execute", action="store_true", help="Intento de ejecución directa (Bloqueado por protocolo de seguridad en frío)")
    parser.add_argument("--devnet-bypass", action="store_true", help="Intento de bypass de seguridad (Terminantemente denegado)")
    return parser.parse_args()

def show_wallet_info(client: JsonRpcClient, account: str, vault_id: str):
    print("======================================================================")
    print(" INFORMACIÓN DE CARTERA DEPOSITANTE (DEVNET)")
    print("======================================================================")
    print(f"Dirección Evaluada: {account}")
    print(f"Bóveda Vinculada:   {vault_id[:16]}...")
    print("----------------------------------------------------------------------")

    # 1. Consulta de cuenta
    try:
        acct_res = client.request(AccountInfo(account=account, ledger_index="current"))
    except Exception as e:
        print(f"[ERROR] Error al conectar con nodo RPC: {e}")
        return

    acct_data = acct_res.result.get("account_data")
    if not acct_data:
        err = acct_res.result.get("error", "actNotFound")
        msg = acct_res.result.get("error_message", "Cuenta no inicializada en el ledger.")
        print(f"[ESTADO] Cuenta NO activa en Devnet ({err}): {msg}")
        print("Sugerencia: Financiar la cuenta desde el faucet de Devnet o usar cuenta activa.")
        print("======================================================================")
        return

    balance_drops = int(acct_data.get("Balance", 0))
    balance_xrp = balance_drops / 1_000_000
    owner_count = acct_data.get("OwnerCount", 0)
    sequence = acct_data.get("Sequence", 0)

    # Reserva en Devnet: 10 XRP base + 2 XRP por cada objeto de cuenta (OwnerCount)
    reserve_drops = 10_000_000 + (owner_count * 2_000_000)
    reserve_xrp = reserve_drops / 1_000_000
    spendable_xrp = max(0.0, balance_xrp - reserve_xrp)

    print(" BALANCES Y ESTADO:")
    print(f"  - Saldo Total:        {balance_xrp:,.6f} XRP ({balance_drops:,} drops)")
    print(f"  - Reserva del Ledger:  {reserve_xrp:,.6f} XRP (Base 10 XRP + {owner_count} objetos)")
    print(f"  - Saldo Disponible:   {spendable_xrp:,.6f} XRP (Fondos libres para depósito)")
    print(f"  - Secuencia Actual:   {sequence}")
    print("----------------------------------------------------------------------")

    # 2. Consulta de objetos asociados (MPToken / Shares)
    mpt_shares = []
    try:
        obj_res = client.request(AccountObjects(account=account, ledger_index="current"))
        for obj in obj_res.result.get("account_objects", []):
            if obj.get("LedgerEntryType") == "MPToken":
                mpt_shares.append(obj)
    except Exception:
        pass

    print(f" ACCIONES / SHARES (MPToken): {len(mpt_shares)} tokens de bóveda en cartera")
    for s in mpt_shares:
        print(f"  - IssuanceID: {s.get('MPTokenIssuanceID')} | Balance: {s.get('MPTAmount', 'N/A')}")

    print("----------------------------------------------------------------------")
    dep_cap = "SÍ" if spendable_xrp >= 100.0 else "NO (Requiere saldo libre suficiente)"
    print(f" Capacidad para depósito de 100 XRP: {dep_cap}")
    print("======================================================================")

def main():
    args = parse_args()
    client = JsonRpcClient(args.rpc_url)

    clean_vault_id = args.vault_id.strip()
    if len(clean_vault_id) != 64 or not re.fullmatch(r"[0-9A-Fa-f]{64}", clean_vault_id):
        print(f"[ERROR] VaultID inválido ({len(clean_vault_id)} caracteres). Debe ser hex de 64 caracteres.")
        sys.exit(1)

    # RECHAZO ESTRICTO DE BYPASS
    if args.devnet_bypass:
        print("======================================================================")
        print(" [BLOQUEO DE SEGURIDAD] INTENTO DE BYPASS DENEGADO")
        print("======================================================================")
        print(" Error de Seguridad: SEC_ERR_BYPASS_ATTEMPT_DENIED")
        print(" Razón: La política de seguridad prohíbe terminantemente cualquier bypass de firma en frío.")
        print(" Este entorno opera bajo principio Zero-Trust hacia seeds privadas.")
        print(" Ninguna transacción puede ser firmada ni enviada en caliente bajo ninguna condición.")
        print("======================================================================")
        sys.exit(1)

    if args.wallet_info:
        show_wallet_info(client, args.depositor, clean_vault_id)
        return

    if args.execute:
        print("======================================================================")
        print(" [AVISO DE SEGURIDAD] POLÍTICA STRICT COLD-SIGNING")
        print("======================================================================")
        print(" Bloqueo de seguridad: Hermes Agent NO procesa claves privadas ni firma en caliente.")
        print(" La bandera --execute no realiza envíos directos a la red para prevenir exposición de claves.")
        print(" En su lugar, se genera el borrador DRAFT_UNSIGNED para firma aislada en hardware wallet.")
        print("======================================================================")

    print("======================================================================")
    print(" XLS-65 VAULT DEPOSIT - GENERADOR DRAFT_UNSIGNED")
    print("======================================================================")
    print(f"Bóveda Destino: {clean_vault_id}")
    print(f"Depositante:    {args.depositor}")
    print(f"Monto Depósito: {args.amount:.6f} XRP")
    print("----------------------------------------------------------------------")

    # 1. Consultar estado previo de la Bóveda
    try:
        v_res = client.request(LedgerEntry(index=clean_vault_id, ledger_index="current"))
        vault_node = v_res.result.get("node", {})
    except Exception as e:
        print(f"[ERROR] Error al consultar Bóveda en Devnet: {e}")
        sys.exit(1)

    if not vault_node:
        print(f"[ERROR] No se encontró la Bóveda con ID {clean_vault_id}")
        sys.exit(1)

    assets_total_prev = int(vault_node.get("AssetsTotal", 0))
    assets_avail_prev = int(vault_node.get("AssetsAvailable", 0))
    deposit_drops = int(args.amount * 1_000_000)

    # 2. Consultar secuencia de cuenta y datos de red
    sequence = 0
    try:
        acct_res = client.request(AccountInfo(account=args.depositor, ledger_index="current"))
        sequence = int(acct_res.result.get("account_data", {}).get("Sequence", 0))
    except Exception:
        pass

    network_id = 2
    base_fee = "1000"
    try:
        si_res = client.request(ServerInfo())
        network_id = si_res.result.get("info", {}).get("network_id", 2)
    except Exception:
        pass

    # 3. Métricas proyectadas
    assets_total_post = assets_total_prev + deposit_drops
    assets_avail_post = assets_avail_prev + deposit_drops

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    iso_now = datetime.now(timezone.utc).isoformat()

    # 4. Estructura del Borrador sin firmar
    draft = {
        "template_meta": {
            "template_id": f"vault_deposit_x10_{timestamp_str}",
            "version": "1.0.0",
            "generated_at": iso_now,
            "network": f"XRPL Devnet ({args.rpc_url})",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"VaultDeposit XLS-65 — Depósito de {args.amount} XRP en Bóveda X10"
        },
        "vault_context": {
            "VaultID": clean_vault_id,
            "VaultAccount": vault_node.get("Account"),
            "ShareMPTID": vault_node.get("ShareMPTID"),
            "AssetsTotal_before_xrp": assets_total_prev / 1_000_000,
            "AssetsTotal_after_xrp": assets_total_post / 1_000_000,
            "AssetsAvailable_before_xrp": assets_avail_prev / 1_000_000,
            "AssetsAvailable_after_xrp": assets_avail_post / 1_000_000
        },
        "transaction": {
            "TransactionType": "VaultDeposit",
            "Account": args.depositor,
            "VaultID": clean_vault_id,
            "Amount": str(deposit_drops),
            "Fee": base_fee,
            "Sequence": sequence,
            "NetworkID": network_id
        },
        "fields_to_verify_before_cold_signing": [
            f"TransactionType: VaultDeposit",
            f"Account: {args.depositor}",
            f"VaultID: {clean_vault_id}",
            f"Amount: {deposit_drops} drops ({args.amount} XRP)",
            f"Fee: {base_fee} drops",
            f"Sequence: {sequence}",
            f"NetworkID: {network_id}"
        ],
        "cold_signing": {
            "status": "PENDING",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "instructions": "Transferir borrador JSON a dispositivo de firma en frío, verificar campos en pantalla y firmar offline."
        }
    }

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = DRAFTS_DIR / f"vault_deposit_x10_{timestamp_str}_DRAFT_UNSIGNED.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    print(" IMPACTO PROYECTADO EN BÓVEDA X10:")
    print(f"  - Custodiado previo:    {assets_total_prev / 1_000_000:,.6f} XRP")
    print(f"  - Custodiado posterior: {assets_total_post / 1_000_000:,.6f} XRP (+{args.amount:.6f} XRP)")
    print(f"  - Disponible posterior: {assets_avail_post / 1_000_000:,.6f} XRP")
    print(f"  - Acciones ShareMPT:    {vault_node.get('ShareMPTID')}")
    print("----------------------------------------------------------------------")
    print(f"[ÉXITO] Borrador generado en:")
    print(f" {filename}")
    print("Estado Firma: PENDING (Firma obligatoria en frío en hardware)")
    print("======================================================================")

if __name__ == "__main__":
    main()
