#!/usr/bin/env python3
"""
Script de Auditoría e Interacción - Capa 3
Consulta el estado de la Bóveda XLS-65 X10 y su LoanBroker XLS-66 asociado en XRPL Devnet.
"""

import json
import os
import sys
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import LedgerEntry, AccountObjects

DEFAULT_DEVNET_RPC = "https://s.devnet.rippletest.net:51234"
DEFAULT_VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
DEFAULT_VAULT_OWNER = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"

def decode_hex_data(hex_str: str) -> dict:
    if not hex_str:
        return {}
    try:
        raw_text = bytes.fromhex(hex_str).decode("utf-8")
        return json.loads(raw_text)
    except Exception:
        return {"raw": hex_str}

def check_vault_status():
    rpc_url = os.environ.get("XRPL_RPC_URL", DEFAULT_DEVNET_RPC)
    vault_id = os.environ.get("VAULT_ID", DEFAULT_VAULT_ID)
    vault_owner = os.environ.get("VAULT_OWNER", DEFAULT_VAULT_OWNER)

    print("======================================================================")
    print(" XRPL DEVNET - ESTADO DE BÓVEDA XLS-65 / XLS-66 (X10)")
    print("======================================================================")
    print(f"Endpoint RPC:  {rpc_url}")
    print(f"VaultID:       {vault_id}")
    print(f"Cuenta Owner:  {vault_owner}")
    print("----------------------------------------------------------------------")

    client = JsonRpcClient(rpc_url)

    # 1. Consulta del objeto Vault
    try:
        req = LedgerEntry(index=vault_id, ledger_index="current")
        res = client.request(req)
        vault_node = res.result.get("node", {})
    except Exception as e:
        print(f"[ERROR] No se pudo obtener la entrada de ledger de la bóveda: {e}")
        sys.exit(1)

    if not vault_node:
        print("[ERROR] Bóveda no encontrada en el ledger.")
        sys.exit(1)

    # Decodificación de metadatos
    data_hex = vault_node.get("Data", "")
    metadata = decode_hex_data(data_hex)
    vault_name = metadata.get("n", "Cold storage X10")
    vault_web = metadata.get("w", "N/A")

    # Activos y balances
    asset_info = vault_node.get("Asset", {})
    currency = asset_info.get("currency", "XRP")
    assets_total_drops = int(vault_node.get("AssetsTotal", 0))
    assets_avail_drops = int(vault_node.get("AssetsAvailable", 0))

    assets_total_xrp = assets_total_drops / 1_000_000
    assets_avail_xrp = assets_avail_drops / 1_000_000
    locked_xrp = assets_total_xrp - assets_avail_xrp

    # 2. Consulta de objetos asociados (LoanBroker / MPToken)
    broker_node = None
    mpt_node = None
    try:
        obj_req = AccountObjects(account=vault_owner, ledger_index="current")
        obj_res = client.request(obj_req)
        account_objects = obj_res.result.get("account_objects", [])
        for obj in account_objects:
            if obj.get("LedgerEntryType") == "LoanBroker" and obj.get("VaultID") == vault_id:
                broker_node = obj
            elif obj.get("LedgerEntryType") == "MPToken" and obj.get("MPTokenIssuanceID") == vault_node.get("ShareMPTID"):
                mpt_node = obj
    except Exception as e:
        print(f"[AVISO] No se pudieron consultar objetos vinculados de la cuenta: {e}")

    # Métricas de liquidez
    utilization_rate = (locked_xrp / assets_total_xrp * 100) if assets_total_xrp > 0 else 0.0
    status = "SALUDABLE"
    if utilization_rate > 90.0 or assets_avail_xrp <= 0:
        status = "CRÍTICO"
    elif utilization_rate > 75.0:
        status = "ESTRÉS"

    # Presentación de resultados
    print(f"Nombre Bóveda:       {vault_name}")
    print(f"Sitio Web / Ref:     {vault_web}")
    print(f"Cuenta Técnica:      {vault_node.get('Account')}")
    print(f"Moneda Activo:       {currency}")
    print(f"Política de Retiro:  {vault_node.get('WithdrawalPolicy')} (1 = FCFS)")
    print(f"Share MPT ID:        {vault_node.get('ShareMPTID')}")
    print("----------------------------------------------------------------------")
    print(" BALANCES Y LIQUIDEZ:")
    print(f"  - Total Custodiado: {assets_total_xrp:,.6f} {currency} ({assets_total_drops} drops)")
    print(f"  - Disponible:       {assets_avail_xrp:,.6f} {currency} ({assets_avail_drops} drops)")
    print(f"  - Bloqueado:        {locked_xrp:,.6f} {currency}")
    print(f"  - Tasa Utilización: {utilization_rate:.2f}%")
    print(f"  - Estado Liquidez:  {status}")

    if broker_node:
        debt_total_drops = int(broker_node.get("DebtTotal", 0))
        debt_max_drops = int(broker_node.get("DebtMaximum", 0))
        cover_drops = int(broker_node.get("CoverAvailable", 0))
        loan_seq = broker_node.get("LoanSequence", 0)
        mgmt_fee = broker_node.get("ManagementFeeRate", 0)

        print("----------------------------------------------------------------------")
        print(" XLS-66 LOAN BROKER ASOCIADO:")
        print(f"  - Deuda Total Activa: {debt_total_drops / 1_000_000:,.6f} {currency} ({debt_total_drops} drops)")
        print(f"  - Deuda Máxima:       {debt_max_drops / 1_000_000:,.6f} {currency}")
        print(f"  - Cobertura Disp.:    {cover_drops / 1_000_000:,.6f} {currency}")
        print(f"  - Secuencia Préstamo: {loan_seq}")
        print(f"  - Management Fee:     {mgmt_fee} bps ({mgmt_fee / 100:.2f}%)")

    print("======================================================================")
    print(f" Consulta finalizada con éxito. Ledger Index: {res.result.get('ledger_current_index')}")
    print("======================================================================")

if __name__ == "__main__":
    check_vault_status()
