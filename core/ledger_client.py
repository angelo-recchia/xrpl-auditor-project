"""
Módulo: core/ledger_client.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Cliente híbrido RPC/WebSocket agnóstico de red con rehidratación
             correlacionada por JSON-RPC id (101 Vault / 102 LoanBroker),
             filtrado de ledgers validados y reconexión con backoff exponencial.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.core.addresscodec import is_valid_classic_address
from xrpl.models.requests import AccountInfo, LedgerEntry

from config import Settings, settings

logger = logging.getLogger(__name__)

LedgerEventHandler = Callable[[Dict[str, Any]], Awaitable[Any] | Any]


def _build_xrpl_lookup_command(req_id: int, target_id: str) -> Dict[str, Any]:
    """
    Construye el comando JSON-RPC adecuado según el formato del identificador:
      - Dirección clásica ('r...') -> account_info
      - Índice de LedgerEntry (64 hex) -> ledger_entry
    """
    cleaned = target_id.strip()
    if is_valid_classic_address(cleaned):
        return {
            "id": req_id,
            "command": "account_info",
            "account": cleaned,
            "ledger_index": "validated",
        }
    return {
        "id": req_id,
        "command": "ledger_entry",
        "index": cleaned,
        "ledger_index": "validated",
    }


def is_validated_ledger_event(message: Dict[str, Any]) -> bool:
    """Filtra exclusivamente eventos de ledger validados o transacciones validadas."""
    if message.get("type") == "ledgerClosed":
        return True
    return message.get("validated") is True


class XRPLedgerClient:
    """Cliente institucional XRPL para lectura puntual RPC y streaming WebSocket 24/7."""

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        app_settings: Optional[Settings] = None,
    ):
        cfg = app_settings or settings
        self.settings = cfg
        self.rpc_url = rpc_url or cfg.xrpl_rpc_url
        self.ws_url = ws_url or cfg.xrpl_ws_url
        self.client = AsyncJsonRpcClient(self.rpc_url)

    # ------------------------------------------------------------------
    # Consultas puntuales JSON-RPC HTTP (compatibilidad con scripts previos)
    # ------------------------------------------------------------------

    async def get_account_status(self, account_address: str) -> Dict[str, Any]:
        """Consulta el estado, saldo y secuencia de una cuenta en el Ledger validado."""
        if not is_valid_classic_address(account_address):
            raise ValueError(f"Dirección XRPL inválida (checksum/formato): {account_address}")

        request = AccountInfo(
            account=account_address,
            ledger_index="validated",
        )
        response = await self.client.request(request)
        if not response.is_successful():
            err = response.result.get("error_message", response.result.get("error"))
            raise RuntimeError(f"Error RPC Ledger: {err}")
        return response.result

    async def get_vault_raw_data(self, vault_id: str) -> Dict[str, Any]:
        """Consulta directa al LedgerEntry de una bóveda XLS-65 sin pasar por UI."""
        request = LedgerEntry(
            index=vault_id,
            ledger_index="validated",
        )
        response = await self.client.request(request)
        if not response.is_successful():
            err = response.result.get("error_message", response.result.get("error"))
            raise RuntimeError(f"Bóveda no encontrada o error RPC: {err}")
        return response.result

    # ------------------------------------------------------------------
    # Rehidratación correlacionada por ID y streaming WebSocket resiliente
    # ------------------------------------------------------------------

    async def rehydrate_state(
        self,
        ws: Any,
        vault_id: Optional[str] = None,
        loan_broker_id: Optional[str] = None,
        *,
        timeout: Optional[float] = None,
        raise_on_rpc_error: bool = False,
    ) -> Dict[str, Any]:
        """
        Rehidrata el estado inicial de Vault (id=101) y LoanBroker (id=102)
        correlacionando estrictamente cada respuesta JSON-RPC por su campo 'id'
        y aislando cualquier trama de streaming que llegue desalineada.
        """
        target_vault = vault_id if vault_id is not None else self.settings.vault_account_id
        target_broker = loan_broker_id if loan_broker_id is not None else self.settings.loan_broker_id
        req_timeout = timeout if timeout is not None else self.settings.rpc_request_timeout

        vault_req_id = self.settings.rpc_vault_req_id
        broker_req_id = self.settings.rpc_loan_broker_req_id

        pending: Dict[int, str] = {}
        if target_vault:
            pending[vault_req_id] = "vault"
            await ws.send(json.dumps(_build_xrpl_lookup_command(vault_req_id, target_vault)))
        if target_broker:
            pending[broker_req_id] = "loan_broker"
            await ws.send(json.dumps(_build_xrpl_lookup_command(broker_req_id, target_broker)))

        state: Dict[str, Any] = {
            "vault": None,
            "loan_broker": None,
            "buffered_events": [],
            "errors": {},
        }

        if not pending:
            return state

        loop = asyncio.get_running_loop()
        deadline = loop.time() + req_timeout

        while pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                missing = ", ".join(f"{name}(id={rid})" for rid, name in pending.items())
                raise TimeoutError(f"Timeout durante rehidratación JSON-RPC esperando: {missing}")

            raw_frame = await asyncio.wait_for(ws.recv(), timeout=remaining)
            message = json.loads(raw_frame) if isinstance(raw_frame, (str, bytes)) else raw_frame

            if not isinstance(message, dict):
                continue

            msg_id = message.get("id")
            if msg_id in pending:
                key = pending.pop(msg_id)
                if message.get("status") == "error" or "error" in message:
                    err_info = message.get("error_message") or message.get("error")
                    if raise_on_rpc_error:
                        raise RuntimeError(f"Error RPC en rehidratación de {key} (id={msg_id}): {err_info}")
                    state["errors"][key] = err_info
                else:
                    state[key] = message.get("result", message)
            else:
                # Aislar tramas asíncronas (ej. ledgerClosed temprano) sin mezclarlas con RPC
                if is_validated_ledger_event(message):
                    state["buffered_events"].append(message)

        return state

    async def subscribe_streams(
        self,
        ws: Any,
        accounts: Optional[list[str]] = None,
        *,
        sub_req_id: int = 103,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Suscribe el socket al stream de ledgers validados (y cuentas objetivo si aplica)."""
        payload: Dict[str, Any] = {
            "id": sub_req_id,
            "command": "subscribe",
            "streams": ["ledger"],
        }
        if accounts:
            payload["accounts"] = accounts

        await ws.send(json.dumps(payload))

        req_timeout = timeout if timeout is not None else self.settings.rpc_request_timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + req_timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("Timeout esperando confirmación de suscripción WebSocket.")

            raw_frame = await asyncio.wait_for(ws.recv(), timeout=remaining)
            message = json.loads(raw_frame) if isinstance(raw_frame, (str, bytes)) else raw_frame
            if isinstance(message, dict) and message.get("id") == sub_req_id:
                if message.get("status") == "error" or "error" in message:
                    raise RuntimeError(f"Error al suscribir stream XRPL: {message.get('error_message', message.get('error'))}")
                return message.get("result", message)

    async def stream_validated_ledgers(
        self,
        on_event: Optional[LedgerEventHandler] = None,
        *,
        on_rehydrated: Optional[Callable[[Dict[str, Any]], Awaitable[Any] | Any]] = None,
        stop_event: Optional[asyncio.Event] = None,
        max_reconnects: Optional[int] = None,
    ) -> None:
        """
        Bucle de escucha WebSocket 24/7 con rehidratación en cada reconexión,
        filtrado estricto de eventos validados y backoff exponencial ante caídas.
        """
        delay = self.settings.ws_reconnect_initial_delay
        max_delay = self.settings.ws_reconnect_max_delay
        factor = self.settings.ws_reconnect_backoff_factor
        attempts = 0

        accounts_to_watch = [
            addr
            for addr in (self.settings.vault_account_id, self.settings.loan_broker_id)
            if addr and is_valid_classic_address(addr)
        ]

        while not (stop_event and stop_event.is_set()):
            try:
                logger.info("Conectando WebSocket XRPL (%s): %s", self.settings.xrpl_network_mode, self.ws_url)
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    rehydrated = await self.rehydrate_state(ws)
                    if on_rehydrated is not None:
                        res = on_rehydrated(rehydrated)
                        if inspect.isawaitable(res):
                            await res

                    # Procesar eventos validados que hubieran llegado durante la rehidratación
                    for buffered in rehydrated.get("buffered_events", []):
                        if on_event is not None:
                            res = on_event(buffered)
                            if inspect.isawaitable(res):
                                await res

                    await self.subscribe_streams(ws, accounts=accounts_to_watch or None)

                    # Conexión estable: reiniciar contador y backoff
                    delay = self.settings.ws_reconnect_initial_delay
                    attempts = 0
                    logger.info("Stream XRPL validado activo en %s", self.ws_url)

                    while not (stop_event and stop_event.is_set()):
                        try:
                            raw_frame = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue

                        message = json.loads(raw_frame) if isinstance(raw_frame, (str, bytes)) else raw_frame
                        if isinstance(message, dict) and is_validated_ledger_event(message):
                            if on_event is not None:
                                res = on_event(message)
                                if inspect.isawaitable(res):
                                    await res

            except asyncio.CancelledError:
                logger.info("Stream XRPL cancelado ordenadamente.")
                raise
            except (ConnectionClosed, WebSocketException, OSError, TimeoutError, RuntimeError) as exc:
                attempts += 1
                logger.warning("Desconexión/Error en WebSocket XRPL (%s): %s", type(exc).__name__, exc)

                if max_reconnects is not None and attempts > max_reconnects:
                    raise RuntimeError(f"Se superó el máximo de reconexiones ({max_reconnects}).") from exc

                if stop_event and stop_event.is_set():
                    break

                logger.info("Reintentando conexión XRPL en %.1f segundos...", delay)
                try:
                    if stop_event:
                        await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    else:
                        await asyncio.sleep(delay)
                except asyncio.TimeoutError:
                    pass

                delay = min(delay * factor, max_delay)


async def main() -> None:
    """Prueba rápida de conectividad RPC + configuración activa."""
    ledger = XRPLedgerClient()
    print(f"Conectando al nodo XRPL ({ledger.settings.xrpl_network_mode}: {ledger.rpc_url})...")
    test_account = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
    try:
        info = await ledger.get_account_status(test_account)
        account_data = info.get("account_data", {})
        print("Conexión directa exitosa:")
        print(f"  Account:  {account_data.get('Account')}")
        print(f"  Balance:  {int(account_data.get('Balance', 0)) / 1_000_000:,.6f} XRP")
        print(f"  Ledger:   {info.get('ledger_index')}")
    except Exception as e:
        print(f"Error de conexión: {e}")


if __name__ == "__main__":
    asyncio.run(main())