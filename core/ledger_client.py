"""
Módulo: core/ledger_client.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Cliente híbrido RPC/WebSocket agnóstico de red con rehidratación
             correlacionada por JSON-RPC id (101 Vault / 102 LoanBroker),
             descubrimiento de pseudo-cuentas, re-sondeo de LedgerEntry 64-hex
             en ledgers validados y reconexión con backoff exponencial.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.core.addresscodec import is_valid_classic_address
from xrpl.models.requests import AccountInfo, LedgerEntry

from config import Settings, settings

logger = logging.getLogger(__name__)

LedgerEventHandler = Callable[[Dict[str, Any]], Awaitable[Any] | Any]

REFRESH_VAULT_OFFSET = 100  # 101 + 100 = 201
REFRESH_BROKER_OFFSET = 100  # 102 + 100 = 202
MPT_ISSUANCE_OFFSET = 50  # 101 + 50 = 151 (rehidratación), 201 + 50 = 251 (refresco)


def _inject_mpt_outstanding_amount(snapshot: Dict[str, Any]) -> None:
    """Si existe mpt_issuance con OutstandingAmount y vault.node, inyecta OutstandingAmount en vault.node."""
    vault = snapshot.get("vault")
    mpt = snapshot.get("mpt_issuance")
    if not isinstance(vault, dict) or not isinstance(mpt, dict):
        return
    vault_node = vault.get("node")
    mpt_node = mpt.get("node") if isinstance(mpt.get("node"), dict) else mpt
    if not isinstance(vault_node, dict) or not isinstance(mpt_node, dict):
        return
    outstanding = mpt_node.get("OutstandingAmount")
    if outstanding is not None:
        vault_node["OutstandingAmount"] = outstanding


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


def _extract_account_from_result(result: Any) -> Optional[str]:
    """Extrae la dirección clásica Account de un resultado Vault/LoanBroker/AccountInfo."""
    if not isinstance(result, dict):
        return None
    for container_key in ("node", "account_data"):
        inner = result.get(container_key)
        if isinstance(inner, dict):
            account = inner.get("Account")
            if isinstance(account, str) and is_valid_classic_address(account):
                return account
    account = result.get("Account")
    if isinstance(account, str) and is_valid_classic_address(account):
        return account
    return None


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
            "mpt_issuance": None,
            "buffered_events": [],
            "errors": {},
            "discovered_accounts": [],
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
                    result = message.get("result", message)
                    state[key] = result
                    discovered = _extract_account_from_result(result)
                    if discovered and discovered not in state["discovered_accounts"]:
                        state["discovered_accounts"].append(discovered)

                    if key == "vault" and isinstance(result, dict) and isinstance(result.get("node"), dict):
                        vault_node = result["node"]
                        share_mpt_id = vault_node.get("ShareMPTID")
                        if (
                            isinstance(share_mpt_id, str)
                            and share_mpt_id.strip()
                            and vault_node.get("OutstandingAmount") is None
                        ):
                            mpt_req_id = vault_req_id + MPT_ISSUANCE_OFFSET
                            if mpt_req_id not in pending:
                                pending[mpt_req_id] = "mpt_issuance"
                                await ws.send(
                                    json.dumps(
                                        {
                                            "id": mpt_req_id,
                                            "command": "ledger_entry",
                                            "mpt_issuance": share_mpt_id.strip(),
                                            "ledger_index": "validated",
                                        }
                                    )
                                )
                    _inject_mpt_outstanding_amount(state)
            else:
                # Aislar tramas asíncronas (ej. ledgerClosed temprano) sin mezclarlas con RPC
                if is_validated_ledger_event(message):
                    state["buffered_events"].append(message)

        return state

    async def subscribe_streams(
        self,
        ws: Any,
        accounts: Optional[List[str]] = None,
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

    async def request_ledger_refresh(
        self,
        ws: Any,
        pending_refresh: Dict[int, str],
        share_mpt_id: Optional[str] = None,
    ) -> None:
        """
        Solicita de forma no bloqueante el refresco de Vault y/o LoanBroker (64-hex o clásico)
        cuando llega un ledgerClosed y no hay refrescos previos en vuelo.
        """
        refresh_vault_id = self.settings.rpc_vault_req_id + REFRESH_VAULT_OFFSET
        refresh_broker_id = self.settings.rpc_loan_broker_req_id + REFRESH_BROKER_OFFSET
        refresh_mpt_id = refresh_vault_id + MPT_ISSUANCE_OFFSET

        if self.settings.vault_account_id and refresh_vault_id not in pending_refresh:
            pending_refresh[refresh_vault_id] = "vault"
            await ws.send(json.dumps(_build_xrpl_lookup_command(refresh_vault_id, self.settings.vault_account_id)))

        if (
            isinstance(share_mpt_id, str)
            and share_mpt_id.strip()
            and refresh_mpt_id not in pending_refresh
        ):
            pending_refresh[refresh_mpt_id] = "mpt_issuance"
            await ws.send(
                json.dumps(
                    {
                        "id": refresh_mpt_id,
                        "command": "ledger_entry",
                        "mpt_issuance": share_mpt_id.strip(),
                        "ledger_index": "validated",
                    }
                )
            )

        if self.settings.loan_broker_id and refresh_broker_id not in pending_refresh:
            pending_refresh[refresh_broker_id] = "loan_broker"
            await ws.send(json.dumps(_build_xrpl_lookup_command(refresh_broker_id, self.settings.loan_broker_id)))

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
        suscripción a cuentas descubiertas, re-sondeo no bloqueante para IDs 64-hex
        en ledgerClosed y backoff exponencial ante caídas.
        """
        delay = self.settings.ws_reconnect_initial_delay
        max_delay = self.settings.ws_reconnect_max_delay
        factor = self.settings.ws_reconnect_backoff_factor
        attempts = 0

        base_accounts: List[str] = [
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

                    # Combinar cuentas configuradas + pseudo-cuentas descubiertas en rehidratación
                    accounts_to_watch = list(dict.fromkeys(base_accounts + rehydrated.get("discovered_accounts", [])))

                    for buffered in rehydrated.get("buffered_events", []):
                        if on_event is not None:
                            res = on_event(buffered)
                            if inspect.isawaitable(res):
                                await res

                    await self.subscribe_streams(ws, accounts=accounts_to_watch or None)

                    delay = self.settings.ws_reconnect_initial_delay
                    attempts = 0
                    logger.info("Stream XRPL validado activo en %s (cuentas=%d)", self.ws_url, len(accounts_to_watch))

                    pending_refresh: Dict[int, str] = {}
                    known_share_mpt_id: Optional[str] = None
                    if isinstance(rehydrated.get("vault"), dict) and isinstance(rehydrated["vault"].get("node"), dict):
                        raw_mpt = rehydrated["vault"]["node"].get("ShareMPTID")
                        if isinstance(raw_mpt, str) and raw_mpt.strip():
                            known_share_mpt_id = raw_mpt.strip()

                    refresh_snapshot: Dict[str, Any] = {
                        "vault": rehydrated.get("vault"),
                        "loan_broker": rehydrated.get("loan_broker"),
                        "mpt_issuance": rehydrated.get("mpt_issuance"),
                        "buffered_events": [],
                        "errors": {},
                    }

                    while not (stop_event and stop_event.is_set()):
                        try:
                            raw_frame = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue

                        message = json.loads(raw_frame) if isinstance(raw_frame, (str, bytes)) else raw_frame
                        if not isinstance(message, dict):
                            continue

                        msg_id = message.get("id")
                        if msg_id in pending_refresh:
                            key = pending_refresh.pop(msg_id)
                            if message.get("status") != "error" and "error" not in message:
                                result = message.get("result", message)
                                refresh_snapshot[key] = result
                                if key == "vault" and isinstance(result, dict) and isinstance(result.get("node"), dict):
                                    raw_mpt = result["node"].get("ShareMPTID")
                                    if isinstance(raw_mpt, str) and raw_mpt.strip():
                                        known_share_mpt_id = raw_mpt.strip()
                            _inject_mpt_outstanding_amount(refresh_snapshot)
                            if not pending_refresh and on_rehydrated is not None:
                                res = on_rehydrated(dict(refresh_snapshot))
                                if inspect.isawaitable(res):
                                    await res
                            continue

                        if is_validated_ledger_event(message):
                            if on_event is not None:
                                res = on_event(message)
                                if inspect.isawaitable(res):
                                    await res

                            # Si hay objetivos configurados (p. ej. LedgerEntry 64-hex), refrescar estado tras ledgerClosed
                            if message.get("type") == "ledgerClosed" and (
                                self.settings.vault_account_id or self.settings.loan_broker_id
                            ):
                                await self.request_ledger_refresh(
                                    ws,
                                    pending_refresh,
                                    share_mpt_id=known_share_mpt_id,
                                )

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