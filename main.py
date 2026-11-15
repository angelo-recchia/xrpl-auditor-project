"""
Módulo: main.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66 / LendingProtocolV1_1)
Descripción: Orquestador principal de ciclo de vida asíncrono.
             Ejecuta en paralelo la pasarela de alertas (process_queue) y el
             streaming WebSocket con rehidratación correlacionada, parseo real
             de meta.AffectedNodes (Vault, LoanBroker, RippleState, Loan) y
             cierre limpio ante KeyboardInterrupt (Windows y Linux/Docker).
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
    TRUSTLINE_ANY_FREEZE_MASK,
    TRUSTLINE_DEEP_FREEZE_MASK,
    audit_broker_cover_invariant,
    audit_vault_access_flags,
    audit_vault_nav_parity,
    evaluate_flcr_solvency_v1_1,
)

logger = logging.getLogger("hermes.main")

LSF_LOAN_DEFAULT = 0x00010000
LSF_LOAN_IMPAIRED = 0x00020000


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


def extract_affected_nodes(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae cambios reales de protocolo desde meta.AffectedNodes en transacciones
    validadas de rippled (CreatedNode / ModifiedNode / DeletedNode).
    """
    extracted: Dict[str, Any] = {
        "vault": None,
        "loan_broker": None,
        "frozen_trustlines": [],
        "loan_alerts": [],
    }

    meta = event.get("meta")
    if not isinstance(meta, dict):
        return extracted

    tx_result = meta.get("TransactionResult")
    if tx_result is not None and tx_result != "tesSUCCESS":
        return extracted

    affected = meta.get("AffectedNodes")
    if not isinstance(affected, list):
        return extracted

    for wrapper in affected:
        if not isinstance(wrapper, dict):
            continue

        node_body = None
        for kind in ("ModifiedNode", "CreatedNode", "DeletedNode"):
            if isinstance(wrapper.get(kind), dict):
                node_body = wrapper[kind]
                break
        if not node_body:
            continue

        entry_type = node_body.get("LedgerEntryType")
        fields = node_body.get("FinalFields") or node_body.get("NewFields")
        if not isinstance(fields, dict):
            continue

        if entry_type == "Vault":
            extracted["vault"] = {"node": fields}
        elif entry_type == "LoanBroker":
            extracted["loan_broker"] = {"node": fields}
        elif entry_type == "RippleState":
            flags_int = audit_vault_access_flags(fields.get("Flags", 0))["sanitized_flags"]
            if flags_int & TRUSTLINE_ANY_FREEZE_MASK:
                extracted["frozen_trustlines"].append(
                    {
                        "ledger_index": node_body.get("LedgerIndex"),
                        "flags": flags_int,
                        "is_deep_freeze": bool(flags_int & TRUSTLINE_DEEP_FREEZE_MASK),
                        "low_limit": fields.get("LowLimit"),
                        "high_limit": fields.get("HighLimit"),
                    }
                )
        elif entry_type == "Loan":
            flags_int = audit_vault_access_flags(fields.get("Flags", 0))["sanitized_flags"]
            if flags_int & (LSF_LOAN_DEFAULT | LSF_LOAN_IMPAIRED):
                extracted["loan_alerts"].append(
                    {
                        "ledger_index": node_body.get("LedgerIndex"),
                        "flags": flags_int,
                        "is_default": bool(flags_int & LSF_LOAN_DEFAULT),
                        "is_impaired": bool(flags_int & LSF_LOAN_IMPAIRED),
                    }
                )

    return extracted


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
        shares = vault_node.get("SharesTotal", vault_node.get("OutstandingAmount"))
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
            is_onchain_broker = broker_node.get("LedgerEntryType") == "LoanBroker"

            solvency = evaluate_flcr_solvency_v1_1(
                first_loss_capital=flc,
                principal_debt=principal,
                realized_interest=realized,
                cover_rate_minimum=cover_min,
                accrued_interest=accrued,
                cover_rate_is_tenth_bps=True if is_onchain_broker else None,
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

        # Invariante fixCleanup3_4_0 si se adjunta el saldo de la pseudo-cuenta
        pseudo_balance = broker_node.get("PseudoAccountBalance")
        if flc is not None and pseudo_balance is not None:
            inv = audit_broker_cover_invariant(flc, pseudo_balance)
            if not inv["is_valid"]:
                alerts.append(
                    {
                        "level": "CRITICAL",
                        "source": "XLS66_COVER_INVARIANT",
                        "ledger_index": ledger_index,
                        "metrics": inv,
                        "message": (
                            f"Desajuste fixCleanup3_4_0 en CoverAvailable: "
                            f"Cover={inv['cover_available']} vs Pseudo={inv['pseudo_account_balance']} | "
                            f"Ledger={ledger_index}"
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
            if self.llm_client.is_configured and alert["level"] in {"CRITICAL_DEEP_FREEZE", "CRITICAL", "HIGH_RISK"}:
                summary = await self.llm_client.analyze_risk_event_async(
                    alert.get("metrics", alert),
                    thinking_level="high",
                )
                if summary:
                    alert["message"] = f"{alert['message']}\n\n[Gemini 4 Hydrogen]\n{summary}"

            self.dispatcher.enqueue_alert(alert)

    async def handle_rehydrated_state(self, state: Dict[str, Any]) -> None:
        """Callback ejecutado tras cada rehidratación inicial o refresco de LedgerEntry."""
        if state.get("vault") is not None:
            self.latest_vault_state = state.get("vault")
        if state.get("loan_broker") is not None:
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
        """
        Callback ejecutado por cada evento validado del stream WebSocket.
        Soporta transacciones reales (meta.AffectedNodes) y payloads inline de test.
        """
        ledger_index = event.get("ledger_index")
        event_type = event.get("type", "transaction")
        logger.info("Ledger validado recibido | type=%s | ledger_index=%s", event_type, ledger_index)

        affected = extract_affected_nodes(event)
        vault_update = event.get("vault") or affected.get("vault")
        broker_update = event.get("loan_broker") or affected.get("loan_broker")

        alerts: List[Dict[str, Any]] = []

        if vault_update is not None or broker_update is not None:
            if vault_update is not None:
                self.latest_vault_state = vault_update
            if broker_update is not None:
                self.latest_broker_state = broker_update
            alerts.extend(
                evaluate_snapshot_risk(
                    self.latest_vault_state,
                    self.latest_broker_state,
                    ledger_index=ledger_index,
                )
            )

        for tl in affected.get("frozen_trustlines", []):
            kind = "DEEP_FREEZE" if tl["is_deep_freeze"] else "FREEZE"
            alerts.append(
                {
                    "level": "HIGH_RISK",
                    "source": f"XRPL_TRUSTLINE_{kind}",
                    "ledger_index": ledger_index,
                    "metrics": tl,
                    "message": (
                        f"TrustLine en {kind} detectada en AffectedNodes: "
                        f"LedgerIndex={tl['ledger_index']} Flags={hex(tl['flags'])} | Ledger={ledger_index}"
                    ),
                }
            )

        for loan in affected.get("loan_alerts", []):
            status_tag = "DEFAULT" if loan["is_default"] else "IMPAIRED"
            alerts.append(
                {
                    "level": "CRITICAL" if loan["is_default"] else "WARNING",
                    "source": f"XLS66_LOAN_{status_tag}",
                    "ledger_index": ledger_index,
                    "metrics": loan,
                    "message": (
                        f"Evento Loan XLS-66 ({status_tag}): "
                        f"LedgerIndex={loan['ledger_index']} Flags={hex(loan['flags'])} | Ledger={ledger_index}"
                    ),
                }
            )

        if alerts:
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
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
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