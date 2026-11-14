"""
Módulo: main.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Orquestador principal de ciclo de vida asíncrono.
             Ejecuta en paralelo la pasarela de alertas (process_queue) y el
             streaming WebSocket con rehidratación correlacionada (stream_validated_ledgers),
             con cierre limpio ante KeyboardInterrupt (Windows y Linux/Docker).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional

from config import Settings, settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dispatchers.alert_queue import AlertQueueDispatcher
from evaluators.rules import (
    audit_vault_access_flags,
    audit_vault_nav_parity,
    evaluate_flcr_solvency_v1_1,
)

logger = logging.getLogger("hermes.main")


def configure_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _extract_node(entry: Any) -> Dict[str, Any]:
    """Extrae el diccionario interno de un resultado RPC/WebSocket XRPL."""
    if not isinstance(entry, dict):
        return {}
    if isinstance(entry.get("node"), dict):
        return entry["node"]
    if isinstance(entry.get("account_data"), dict):
        return entry["account_data"]
    return entry


def evaluate_snapshot_risk(
    vault_raw: Optional[Dict[str, Any]],
    broker_raw: Optional[Dict[str, Any]],
    *,
    ledger_index: Any = None,
) -> List[Dict[str, Any]]:
    """
    Evalúa de forma determinista el estado rehidratado o actualizado de Vault (XLS-65)
    y LoanBroker (XLS-66), devolviendo las alertas a encolar.
    """
    alerts: List[Dict[str, Any]] = []
    vault_node = _extract_node(vault_raw)
    broker_node = _extract_node(broker_raw)

    # 1. Auditoría de Control de Acceso y Paridad NAV (XLS-65 Vault)
    if vault_node:
        if "Flags" in vault_node:
            flags_audit = audit_vault_access_flags(vault_node.get("Flags"))
            logger.debug("Auditoría Flags Bóveda: %s", flags_audit)

        assets = vault_node.get("AssetsTotal", vault_node.get("AssetsAvailable"))
        shares = vault_node.get("SharesTotal")
        if assets is not None and shares is not None:
            nav_audit = audit_vault_nav_parity(assets, shares)
            if nav_audit["parity_status"] in {"IMPAIRED_BELOW_PAR", "ANOMALY_ASSETS_WITHOUT_SHARES"}:
                alerts.append(
                    {
                        "level": "WARNING" if nav_audit["parity_status"] == "IMPAIRED_BELOW_PAR" else "CRITICAL",
                        "source": "XLS65_NAV_PARITY",
                        "ledger_index": ledger_index,
                        "metrics": nav_audit,
                        "message": (
                            f"Anomalía NAV XLS-65 ({nav_audit['parity_status']}): "
                            f"NAV/Share={nav_audit['nav_per_share']} | Ledger={ledger_index}"
                        ),
                    }
                )

    # 2. Auditoría de Solvencia FLCR Cash-Basis V1_1 (XLS-66 LoanBroker)
    if broker_node:
        flc = broker_node.get("CoverAvailable", broker_node.get("FirstLossCapital"))
        principal = broker_node.get("DebtTotal", broker_node.get("PrincipalDebt"))
        if flc is not None and principal is not None:
            realized = broker_node.get("RealizedInterest", 0)
            accrued = broker_node.get("AccruedInterest", 0)
            cover_min = broker_node.get("CoverRateMinimum")

            solvency = evaluate_flcr_solvency_v1_1(
                first_loss_capital=flc,
                principal_debt=principal,
                realized_interest=realized,
                cover_rate_minimum=cover_min,
                accrued_interest=accrued,
            )
            if solvency["status"] in {"CRITICAL_DEEP_FREEZE", "WARNING"}:
                alerts.append(
                    {
                        "level": solvency["status"],
                        "source": "XLS66_FLCR_SOLVENCY",
                        "ledger_index": ledger_index,
                        "metrics": solvency,
                        "message": (
                            f"Alerta Solvencia FLCR ({solvency['status']}): "
                            f"FLCR={solvency['flcr']} vs Min={solvency['cover_rate_minimum']} | "
                            f"EffectiveDebt={solvency['effective_debt']} | Ledger={ledger_index}"
                        ),
                    }
                )

    return alerts


class HermesSentinel:
    """Orquestador asíncrono del centinela Project Hermes."""

    def __init__(
        self,
        *,
        app_settings: Optional[Settings] = None,
        ledger_client: Optional[XRPLedgerClient] = None,
        dispatcher: Optional[AlertQueueDispatcher] = None,
        llm_client: Optional[HermesLLMClient] = None,
    ):
        self.settings = app_settings or settings
        self.ledger_client = ledger_client or XRPLedgerClient(app_settings=self.settings)
        self.dispatcher = dispatcher or AlertQueueDispatcher(app_settings=self.settings)
        self.llm_client = llm_client or HermesLLMClient(app_settings=self.settings)

        self.latest_vault_state: Optional[Dict[str, Any]] = None
        self.latest_broker_state: Optional[Dict[str, Any]] = None

    async def _dispatch_detected_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        for alert in alerts:
            if self.llm_client.is_configured and alert["level"] in {"CRITICAL_DEEP_FREEZE", "CRITICAL"}:
                summary = await self.llm_client.analyze_risk_event_async(
                    alert.get("metrics", alert),
                    thinking_level="high",
                )
                if summary:
                    alert["message"] = f"{alert['message']}\n\n[Gemini 4 Hydrogen]\n{summary}"

            self.dispatcher.enqueue_alert(alert)

    async def handle_rehydrated_state(self, state: Dict[str, Any]) -> None:
        """Callback ejecutado tras cada rehidratación inicial o reconexión WebSocket."""
        self.latest_vault_state = state.get("vault")
        self.latest_broker_state = state.get("loan_broker")

        logger.info(
            "Estado rehidratado (Vault=%s, LoanBroker=%s, BufferedEvents=%d)",
            "OK" if self.latest_vault_state else "NONE",
            "OK" if self.latest_broker_state else "NONE",
            len(state.get("buffered_events", [])),
        )

        alerts = evaluate_snapshot_risk(self.latest_vault_state, self.latest_broker_state, ledger_index="rehydrated")
        await self._dispatch_detected_alerts(alerts)

    async def handle_ledger_event(self, event: Dict[str, Any]) -> None:
        """Callback ejecutado por cada evento validado del stream WebSocket."""
        ledger_index = event.get("ledger_index")
        event_type = event.get("type", "transaction")
        logger.info("Ledger validado recibido | type=%s | ledger_index=%s", event_type, ledger_index)

        # Si el evento trae nodos actualizados inline (ej. transacción o modo Standalone), evaluarlos
        vault_update = event.get("vault") or self.latest_vault_state
        broker_update = event.get("loan_broker") or self.latest_broker_state

        if event.get("vault") or event.get("loan_broker"):
            alerts = evaluate_snapshot_risk(vault_update, broker_update, ledger_index=ledger_index)
            await self._dispatch_detected_alerts(alerts)

    async def run(
        self,
        *,
        stop_event: Optional[asyncio.Event] = None,
        max_reconnects: Optional[int] = None,
    ) -> None:
        """Arranca en paralelo el consumidor de alertas y el stream WebSocket XRPL."""
        halt_event = stop_event or asyncio.Event()

        logger.info(
            "Iniciando Project Hermes | Red=%s (%s) | Gemini=%s",
            self.settings.xrpl_network_mode,
            self.settings.xrpl_ws_url,
            self.settings.gemini_model if self.llm_client.is_configured else "desactivado (sin API key)",
        )

        queue_task = asyncio.create_task(
            self.dispatcher.process_queue(stop_event=halt_event),
            name="hermes-alert-queue",
        )
        stream_task = asyncio.create_task(
            self.ledger_client.stream_validated_ledgers(
                on_event=self.handle_ledger_event,
                on_rehydrated=self.handle_rehydrated_state,
                stop_event=halt_event,
                max_reconnects=max_reconnects,
            ),
            name="hermes-ledger-stream",
        )

        tasks = {queue_task, stream_task}
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for finished in done:
                exc = finished.exception()
                if exc is not None:
                    raise exc
        except asyncio.CancelledError:
            logger.info("Cancelación recibida; deteniendo tareas de Project Hermes...")
            raise
        finally:
            halt_event.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Project Hermes detenido limpiamente.")


def main() -> int:
    configure_logging(settings.log_level)
    sentinel = HermesSentinel()
    try:
        asyncio.run(sentinel.run())
    except KeyboardInterrupt:
        logger.info("Interrupción de usuario (Ctrl+C). Cierre limpio completado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())