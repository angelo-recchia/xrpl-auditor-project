import json
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.requests import LedgerEntry, AccountInfo
from xrpl.core.addresscodec import is_valid_classic_address

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "networks.json"

class XRPLedgerClient:
    def __init__(self, rpc_url: Optional[str] = None, ws_url: Optional[str] = None):
        if not rpc_url or not ws_url:
            if CONFIG_PATH.exists():
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        cfg = json.load(f).get("devnet", {})
                        rpc_url = rpc_url or cfg.get("rpc", "https://s.devnet.rippletest.net:51234")
                        ws_url = ws_url or cfg.get("websocket", "wss://s.devnet.rippletest.net:51233")
                except Exception:
                    rpc_url = rpc_url or "https://s.devnet.rippletest.net:51234"
                    ws_url = ws_url or "wss://s.devnet.rippletest.net:51233"
            else:
                rpc_url = rpc_url or "https://s.devnet.rippletest.net:51234"
                ws_url = ws_url or "wss://s.devnet.rippletest.net:51233"

        self.rpc_url = rpc_url
        self.ws_url = ws_url
        self.client = AsyncJsonRpcClient(self.rpc_url)

    async def get_account_status(self, account_address: str) -> Dict[str, Any]:
        """Consulta el estado, saldo y secuencia de una cuenta en el Ledger."""
        if not is_valid_classic_address(account_address):
            raise ValueError(f"Direccion XRPL invalida (checksum/formato): {account_address}")

        request = AccountInfo(
            account=account_address,
            ledger_index="validated"
        )
        response = await self.client.request(request)
        if not response.is_successful():
            raise RuntimeError(f"Error RPC Ledger: {response.result.get('error_message', response.result.get('error'))}")
        return response.result

    async def get_vault_raw_data(self, vault_id: str) -> Dict[str, Any]:
        """
        Consulta la entrada del Ledger para obtener los datos crudos de una bóveda (XLS-65)
        sin pasar por ninguna interfaz web.
        """
        request = LedgerEntry(
            index=vault_id,
            ledger_index="validated"
        )
        response = await self.client.request(request)
        if not response.is_successful():
            raise RuntimeError(f"Boveda no encontrada o error RPC: {response.result.get('error_message', response.result.get('error'))}")
        return response.result

# Prueba rápida de conexión
async def main():
    ledger = XRPLedgerClient()
    print(f"Conectando al nodo XRPL Devnet ({ledger.rpc_url})...")
    test_account = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
    try:
        info = await ledger.get_account_status(test_account)
        account_data = info.get("account_data", {})
        print("Conexion directa exitosa. Respuesta del Ledger:")
        print(f"  Account:  {account_data.get('Account')}")
        print(f"  Balance:  {int(account_data.get('Balance', 0)) / 1_000_000:,.6f} XRP")
        print(f"  Sequence: {account_data.get('Sequence')}")
        print(f"  Ledger:   {info.get('ledger_index')}")
    except Exception as e:
        print(f"Error de conexion: {e}")

if __name__ == "__main__":
    asyncio.run(main())
