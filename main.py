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
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from config import Settings, settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dashboard.server import HermesDashboardServer
from dispatchers.alert_queue import AlertQueueDispatcher
from evaluators.rules import (
    TRUSTLINE_ANY_FREEZE_MASK,
    TRUSTLINE_DEEP_FREEZE_MASK,
    audit_broker_cover_invariant,
    audit_vault_access_flags,
    audit_vault_nav_parity,
    audit_vault_unrealized_loss,
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


def _extract_object_id(raw_entry: Optional[Dict[str, Any]], fallback: str) -> str:
    """Obtiene el identificador canónico del objeto XRPL (LedgerIndex/index/Account)."""
    if not isinstance(raw_entry, dict):
        return fallback
    for key in ("ledger_index", "index"):
        val = raw_entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    node = _extract_node(raw_entry)
    for key in ("LedgerIndex", "index", "Account"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _matches_configured_id(node_ledger_index: Any, configured_id: Optional[str]) -> bool:
    """Filtra por LedgerIndex cuando HERMES_VAULT_ID / HERMES_LOAN_BROKER_ID está configurado."""
    if not configured_id or not configured_id.strip():
        return True
    if not isinstance(node_ledger_index, str) or not node_ledger_index.strip():
        return False
    return node_ledger_index.strip().upper() == configured_id.strip().upper()


def extract_affected_nodes(
    event: Dict[str, Any],
    *,
    vault_id: Optional[str] = None,
    loan_broker_id: Optional[str] = None,
    app_settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Extrae cambios reales de protocolo desde meta.AffectedNodes en transacciones
    validadas de rippled (CreatedNode / ModifiedNode / DeletedNode).
    Almacena listas de Vault y LoanBroker con su LedgerIndex y filtra si
    HERMES_VAULT_ID / HERMES_LOAN_BROKER_ID están configurados en settings.
    """
    cfg = app_settings or settings
    target_vault_id = vault_id if vault_id is not None else cfg.vault_account_id
    target_broker_id = loan_broker_id if loan_broker_id is not None else cfg.loan_broker_id

    extracted: Dict[str, Any] = {
        "vaults": [],
        "loan_brokers": [],
        "vault": None,
        "loan_broker": None,
        "frozen_trustlines": [],
        "cleared_trustlines": [],
        "loan_alerts": [],
        "cleared_loans": [],
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
        node_ledger_index = node_body.get("LedgerIndex")
        fields = node_body.get("FinalFields") or node_body.get("NewFields")
        if not isinstance(fields, dict):
            continue

        if entry_type == "Vault":
            if _matches_configured_id(node_ledger_index, target_vault_id):
                extracted["vaults"].append({"ledger_index": node_ledger_index, "node": fields})
        elif entry_type == "LoanBroker":
            if _matches_configured_id(node_ledger_index, target_broker_id):
                extracted["loan_brokers"].append({"ledger_index": node_ledger_index, "node": fields})
        elif entry_type == "RippleState":
            flags_int = audit_vault_access_flags(fields.get("Flags", 0))["sanitized_flags"]
            if flags_int & TRUSTLINE_ANY_FREEZE_MASK:
                extracted["frozen_trustlines"].append(
                    {
                        "ledger_index": node_ledger_index,
                        "flags": flags_int,
                        "is_deep_freeze": bool(flags_int & TRUSTLINE_DEEP_FREEZE_MASK),
                        "low_limit": fields.get("LowLimit"),
                        "high_limit": fields.get("HighLimit"),
                    }
                )
            elif node_ledger_index:
                extracted["cleared_trustlines"].append(node_ledger_index)
        elif entry_type == "Loan":
            flags_int = audit_vault_access_flags(fields.get("Flags", 0))["sanitized_flags"]
            if flags_int & (LSF_LOAN_DEFAULT | LSF_LOAN_IMPAIRED):
                extracted["loan_alerts"].append(
                    {
                        "ledger_index": node_ledger_index,
                        "flags": flags_int,
                        "is_default": bool(flags_int & LSF_LOAN_DEFAULT),
                        "is_impaired": bool(flags_int & LSF_LOAN_IMPAIRED),
                    }
                )
            elif node_ledger_index:
                extracted["cleared_loans"].append(node_ledger_index)

    if extracted["vaults"]:
        extracted["vault"] = extracted["vaults"][-1]
    if extracted["loan_brokers"]:
        extracted["loan_broker"] = extracted["loan_brokers"][-1]

    return extracted


def evaluate_snapshot_risk(
    vault_raw: Optional[Dict[str, Any]],
    broker_raw: Optional[Dict[str, Any]],
    *,
    ledger_index: Any = None,
    healthy_keys_out: Optional[List[Tuple[str, str]]] = None,
    metrics_out: Optional[Dict[str, Any]] = None,
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
        vault_object_id = _extract_object_id(vault_raw, "vault")
        vault_metrics: Dict[str, Any] = {"object_id": vault_object_id}
        if "Flags" in vault_node:
            flags_audit = audit_vault_access_flags(vault_node.get("Flags"))
            logger.debug("Auditoría Flags Bóveda: %s", flags_audit)
            vault_metrics.update(
                {
                    "access_mode": flags_audit["access_mode"],
                    "is_permissioned": flags_audit["is_permissioned"],
                    "is_share_transferable": flags_audit["is_share_transferable"],
                    "secondary_market_mode": flags_audit["secondary_market_mode"],
                }
            )

        assets = vault_node.get("AssetsTotal", vault_node.get("AssetsAvailable"))
        shares = vault_node.get("SharesTotal", vault_node.get("OutstandingAmount"))
        if assets is not None and shares is not None:
            vault_scale = int(vault_node.get("Scale") or 0)
            shares_are_scaled = bool(
                vault_node.get(
                    "SharesAreScaled",
                    "SharesTotal" not in vault_node and "OutstandingAmount" in vault_node,
                )
            )
            nav_audit = audit_vault_nav_parity(
                assets,
                shares,
                scale=vault_scale,
                shares_are_scaled=shares_are_scaled,
            )
            vault_metrics.update(
                {
                    "nav_per_share": nav_audit["nav_per_share"],
                    "parity_status": nav_audit["parity_status"],
                    "scale": nav_audit["scale"],
                }
            )
            if nav_audit["parity_status"] in {"IMPAIRED_BELOW_PAR", "ANOMALY_ASSETS_WITHOUT_SHARES"}:
                alerts.append(
                    {
                        "level": "WARNING" if nav_audit["parity_status"] == "IMPAIRED_BELOW_PAR" else "CRITICAL",
                        "source": "XLS65_NAV_PARITY",
                        "object_id": vault_object_id,
                        "ledger_index": ledger_index,
                        "metrics": nav_audit,
                        "message": (
                            f"Anomalía NAV XLS-65 ({nav_audit['parity_status']}): "
                            f"NAV/Share={nav_audit['nav_per_share']} | Ledger={ledger_index}"
                        ),
                    }
                )
            elif healthy_keys_out is not None:
                healthy_keys_out.append(("XLS65_NAV_PARITY", vault_object_id))

        has_assets_field = "AssetsTotal" in vault_node or "AssetsAvailable" in vault_node
        if has_assets_field or vault_node.get("LossUnrealized") is not None:
            loss_raw = vault_node.get("LossUnrealized")
            if loss_raw is None:
                loss_raw = 0
            loss_audit = audit_vault_unrealized_loss(loss_raw, assets)
            vault_metrics.update(
                {
                    "loss_unrealized": loss_audit["loss_unrealized"],
                    "loss_ratio": loss_audit["loss_ratio"],
                    "loss_status": loss_audit["status"],
                }
            )
            if loss_audit["status"] in {"WARNING", "CRITICAL"}:
                alerts.append(
                    {
                        "level": loss_audit["status"],
                        "source": "XLS65_UNREALIZED_LOSS",
                        "object_id": vault_object_id,
                        "ledger_index": ledger_index,
                        "metrics": loss_audit,
                        "message": (
                            f"Pérdida no realizada XLS-65 ({loss_audit['status']}): "
                            f"LossUnrealized={loss_audit['loss_unrealized']} | "
                            f"LossRatio={loss_audit['loss_ratio']} | Ledger={ledger_index}"
                        ),
                    }
                )
            elif loss_audit["status"] == "HEALTHY" and healthy_keys_out is not None:
                healthy_keys_out.append(("XLS65_UNREALIZED_LOSS", vault_object_id))

        if metrics_out is not None:
            metrics_out["vault"] = vault_metrics

    # 2. Auditoría de Solvencia FLCR Cash-Basis V1_1 (XLS-66 LoanBroker)
    if broker_node:
        broker_object_id = _extract_object_id(broker_raw, "loan_broker")
        broker_metrics: Dict[str, Any] = {"object_id": broker_object_id}
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
            broker_metrics.update(
                {
                    "status": solvency["status"],
                    "flcr": solvency["flcr"],
                    "cover_rate_minimum": solvency["cover_rate_minimum"],
                    "effective_debt": solvency["effective_debt"],
                    "first_loss_capital": solvency["first_loss_capital"],
                }
            )
            if solvency["status"] in {"CRITICAL_DEEP_FREEZE", "WARNING"}:
                alerts.append(
                    {
                        "level": solvency["status"],
                        "source": "XLS66_FLCR_SOLVENCY",
                        "object_id": broker_object_id,
                        "ledger_index": ledger_index,
                        "metrics": solvency,
                        "message": (
                            f"Alerta Solvencia FLCR ({solvency['status']}): "
                            f"FLCR={solvency['flcr']} vs Min={solvency['cover_rate_minimum']} | "
                            f"EffectiveDebt={solvency['effective_debt']} | Ledger={ledger_index}"
                        ),
                    }
                )
            elif healthy_keys_out is not None:
                healthy_keys_out.append(("XLS66_FLCR_SOLVENCY", broker_object_id))

        # Invariante fixCleanup3_4_0 si se adjunta el saldo de la pseudo-cuenta
        pseudo_balance = broker_node.get("PseudoAccountBalance")
        if flc is not None and pseudo_balance is not None:
            inv = audit_broker_cover_invariant(flc, pseudo_balance)
            if not inv["is_valid"]:
                alerts.append(
                    {
                        "level": "CRITICAL",
                        "source": "XLS66_COVER_INVARIANT",
                        "object_id": broker_object_id,
                        "ledger_index": ledger_index,
                        "metrics": inv,
                        "message": (
                            f"Desajuste fixCleanup3_4_0 en CoverAvailable: "
                            f"Cover={inv['cover_available']} vs Pseudo={inv['pseudo_account_balance']} | "
                            f"Ledger={ledger_index}"
                        ),
                    }
                )
            elif healthy_keys_out is not None:
                healthy_keys_out.append(("XLS66_COVER_INVARIANT", broker_object_id))

        if metrics_out is not None:
            metrics_out["loan_broker"] = broker_metrics

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
        alert_cooldown_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if alert_cooldown_seconds < 0:
            raise ValueError("alert_cooldown_seconds no puede ser negativo.")

        self.settings = app_settings or settings
        self.ledger_client = ledger_client or XRPLedgerClient(app_settings=self.settings)
        self.dispatcher = dispatcher or AlertQueueDispatcher(app_settings=self.settings)
        self.llm_client = llm_client or HermesLLMClient(app_settings=self.settings)
        self.alert_cooldown_seconds = float(alert_cooldown_seconds)
        self._clock = clock

        self.latest_vault_state: Optional[Dict[str, Any]] = None
        self.latest_broker_state: Optional[Dict[str, Any]] = None
        self._active_alerts: Dict[Tuple[str, str], Tuple[str, float]] = {}

        # Telemetría en memoria para dashboard HTTP solo-lectura
        self.started_at: float = float(self._clock())
        self.stream_connected: bool = False
        self.is_shutting_down: bool = False
        self.last_ledger_index: Any = None
        self.last_ledger_at: Optional[float] = None
        self.last_updated_utc: Optional[str] = None
        self.latest_vault_metrics: Dict[str, Any] = {}
        self.latest_broker_metrics: Dict[str, Any] = {}
        self.recent_alerts: Deque[Dict[str, Any]] = deque(maxlen=25)
        self.llm_calls_count: int = 0
        self.dashboard_server: Optional[HermesDashboardServer] = None

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """Devuelve una instantánea de solo lectura sin exponer secretos de configuración."""
        return {
            "started_at": self.started_at,
            "stream_connected": self.stream_connected,
            "is_shutting_down": self.is_shutting_down,
            "last_ledger_index": self.last_ledger_index,
            "last_ledger_at": self.last_ledger_at,
            "last_updated_utc": self.last_updated_utc,
            "network": self.settings.xrpl_network,
            "network_mode": self.settings.xrpl_network_mode,
            "vault": dict(self.latest_vault_metrics),
            "loan_broker": dict(self.latest_broker_metrics),
            "dispatcher": {
                "circuit_breaker_state": self.dispatcher.circuit_breaker.state.value,
                "queue_size": self.dispatcher.queue.qsize(),
                "enqueued_count": self.dispatcher.enqueued_count,
                "sent_count": self.dispatcher.sent_count,
                "failed_count": self.dispatcher.failed_count,
                "dropped_count": self.dispatcher.dropped_count,
                "circuit_rejected_count": self.dispatcher.circuit_rejected_count,
            },
            "llm": {
                "model": self.settings.gemini_model,
                "configured": self.llm_client.is_configured,
                "calls_count": self.llm_calls_count,
                "cost_estimate": f"Core 0 Tokens (IA: {self.llm_calls_count} llamadas)",
            },
            "recent_alerts": list(self.recent_alerts),
        }

    def _alert_dedup_key(self, alert: Dict[str, Any]) -> Tuple[str, str]:
        source = str(alert.get("source") or "UNKNOWN")
        obj_key = alert.get("object_id") or alert.get("ledger_index") or "global"
        return (source, str(obj_key))

    def _clear_healthy_alerts(self, keys: List[Tuple[str, str]]) -> None:
        for key in keys:
            self._active_alerts.pop((str(key[0]), str(key[1])), None)

    def _should_emit_alert(self, alert: Dict[str, Any]) -> bool:
        key = self._alert_dedup_key(alert)
        level = str(alert.get("level") or "INFO")
        now = self._clock()
        prev = self._active_alerts.get(key)

        if prev is None:
            self._active_alerts[key] = (level, now)
            return True

        prev_level, last_emitted = prev
        if level != prev_level or (now - last_emitted) >= self.alert_cooldown_seconds:
            self._active_alerts[key] = (level, now)
            return True

        return False

    async def _dispatch_detected_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        for alert in alerts:
            if not self._should_emit_alert(alert):
                logger.debug(
                    "Alerta suprimida por deduplicación/cooldown: key=%s level=%s",
                    self._alert_dedup_key(alert),
                    alert.get("level"),
                )
                continue
            if self.llm_client.is_configured and alert["level"] in {"CRITICAL_DEEP_FREEZE", "CRITICAL", "HIGH_RISK"}:
                self.llm_calls_count += 1
                summary = await self.llm_client.analyze_risk_event_async(
                    alert.get("metrics", alert),
                    thinking_level="high",
                )
                if summary:
                    alert["message"] = f"{alert['message']}\n\n[Gemini 4 Hydrogen]\n{summary}"

            self.recent_alerts.appendleft(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": str(alert.get("level") or "INFO").upper(),
                    "source": str(alert.get("source") or "UNKNOWN"),
                    "object_id": alert.get("object_id"),
                    "ledger_index": alert.get("ledger_index"),
                    "message": str(alert.get("message") or ""),
                }
            )
            self.dispatcher.enqueue_alert(alert)

    async def handle_rehydrated_state(self, state: Dict[str, Any]) -> None:
        """Callback ejecutado tras cada rehidratación inicial o refresco de LedgerEntry."""
        if state.get("vault") is not None:
            self.latest_vault_state = state.get("vault")
        if state.get("loan_broker") is not None:
            self.latest_broker_state = state.get("loan_broker")

        self.stream_connected = True
        if state.get("ledger_index") is not None:
            self.last_ledger_index = state.get("ledger_index")
        self.last_ledger_at = float(self._clock())
        self.last_updated_utc = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Estado rehidratado (Vault=%s, LoanBroker=%s, BufferedEvents=%d)",
            "OK" if self.latest_vault_state else "NONE",
            "OK" if self.latest_broker_state else "NONE",
            len(state.get("buffered_events", [])),
        )

        healthy_keys: List[Tuple[str, str]] = []
        snapshot_metrics: Dict[str, Any] = {}
        alerts = evaluate_snapshot_risk(
            self.latest_vault_state,
            self.latest_broker_state,
            ledger_index="rehydrated",
            healthy_keys_out=healthy_keys,
            metrics_out=snapshot_metrics,
        )
        if "vault" in snapshot_metrics:
            self.latest_vault_metrics = snapshot_metrics["vault"]
        if "loan_broker" in snapshot_metrics:
            self.latest_broker_metrics = snapshot_metrics["loan_broker"]

        self._clear_healthy_alerts(healthy_keys)
        await self._dispatch_detected_alerts(alerts)

    async def handle_ledger_event(self, event: Dict[str, Any]) -> None:
        """
        Callback ejecutado por cada evento validado del stream WebSocket.
        Soporta transacciones reales (meta.AffectedNodes) y payloads inline de test.
        """
        ledger_index = event.get("ledger_index")
        event_type = event.get("type", "transaction")
        logger.info("Ledger validado recibido | type=%s | ledger_index=%s", event_type, ledger_index)

        self.stream_connected = True
        if ledger_index is not None:
            self.last_ledger_index = ledger_index
        self.last_ledger_at = float(self._clock())
        self.last_updated_utc = datetime.now(timezone.utc).isoformat()

        affected = extract_affected_nodes(event, app_settings=self.settings)
        inline_vault = event.get("vault")
        inline_broker = event.get("loan_broker")
        vault_updates: List[Dict[str, Any]] = [inline_vault] if inline_vault is not None else affected["vaults"]
        broker_updates: List[Dict[str, Any]] = [inline_broker] if inline_broker is not None else affected["loan_brokers"]

        alerts: List[Dict[str, Any]] = []
        healthy_keys: List[Tuple[str, str]] = []

        if vault_updates or broker_updates:
            if vault_updates:
                self.latest_vault_state = vault_updates[-1]
            if broker_updates:
                self.latest_broker_state = broker_updates[-1]

            eval_vaults = vault_updates if vault_updates else (
                [self.latest_vault_state] if self.latest_vault_state is not None else []
            )
            eval_brokers = broker_updates if broker_updates else (
                [self.latest_broker_state] if self.latest_broker_state is not None else []
            )

            for v_entry in eval_vaults:
                v_metrics: Dict[str, Any] = {}
                alerts.extend(
                    evaluate_snapshot_risk(
                        v_entry,
                        None,
                        ledger_index=ledger_index,
                        healthy_keys_out=healthy_keys,
                        metrics_out=v_metrics,
                    )
                )
                if "vault" in v_metrics:
                    self.latest_vault_metrics = v_metrics["vault"]
            for b_entry in eval_brokers:
                b_metrics: Dict[str, Any] = {}
                alerts.extend(
                    evaluate_snapshot_risk(
                        None,
                        b_entry,
                        ledger_index=ledger_index,
                        healthy_keys_out=healthy_keys,
                        metrics_out=b_metrics,
                    )
                )
                if "loan_broker" in b_metrics:
                    self.latest_broker_metrics = b_metrics["loan_broker"]

        for lid in affected.get("cleared_trustlines", []):
            healthy_keys.append(("XRPL_TRUSTLINE_FREEZE", str(lid)))
            healthy_keys.append(("XRPL_TRUSTLINE_DEEP_FREEZE", str(lid)))

        for tl in affected.get("frozen_trustlines", []):
            kind = "DEEP_FREEZE" if tl["is_deep_freeze"] else "FREEZE"
            other_kind = "FREEZE" if tl["is_deep_freeze"] else "DEEP_FREEZE"
            tl_id = tl.get("ledger_index") or "trustline"
            healthy_keys.append((f"XRPL_TRUSTLINE_{other_kind}", str(tl_id)))
            alerts.append(
                {
                    "level": "HIGH_RISK",
                    "source": f"XRPL_TRUSTLINE_{kind}",
                    "object_id": str(tl_id),
                    "ledger_index": ledger_index,
                    "metrics": tl,
                    "message": (
                        f"TrustLine en {kind} detectada en AffectedNodes: "
                        f"LedgerIndex={tl['ledger_index']} Flags={hex(tl['flags'])} | Ledger={ledger_index}"
                    ),
                }
            )

        for lid in affected.get("cleared_loans", []):
            healthy_keys.append(("XLS66_LOAN_DEFAULT", str(lid)))
            healthy_keys.append(("XLS66_LOAN_IMPAIRED", str(lid)))

        for loan in affected.get("loan_alerts", []):
            status_tag = "DEFAULT" if loan["is_default"] else "IMPAIRED"
            other_tag = "IMPAIRED" if loan["is_default"] else "DEFAULT"
            loan_id = loan.get("ledger_index") or "loan"
            healthy_keys.append((f"XLS66_LOAN_{other_tag}", str(loan_id)))
            alerts.append(
                {
                    "level": "CRITICAL" if loan["is_default"] else "WARNING",
                    "source": f"XLS66_LOAN_{status_tag}",
                    "object_id": str(loan_id),
                    "ledger_index": ledger_index,
                    "metrics": loan,
                    "message": (
                        f"Evento Loan XLS-66 ({status_tag}): "
                        f"LedgerIndex={loan['ledger_index']} Flags={hex(loan['flags'])} | Ledger={ledger_index}"
                    ),
                }
            )

        self._clear_healthy_alerts(healthy_keys)
        if alerts:
            await self._dispatch_detected_alerts(alerts)

    async def run(
        self,
        *,
        stop_event: Optional[asyncio.Event] = None,
        max_reconnects: Optional[int] = None,
        start_dashboard: Optional[bool] = None,
    ) -> None:
        """Arranca en paralelo el consumidor de alertas, el dashboard solo-lectura y el stream WebSocket XRPL."""
        halt_event = stop_event or asyncio.Event()
        self.is_shutting_down = False
        use_dashboard = self.settings.dashboard_enabled if start_dashboard is None else bool(start_dashboard)

        logger.info(
            "Iniciando Project Hermes | Red=%s (%s) | Gemini=%s",
            self.settings.xrpl_network_mode,
            self.settings.xrpl_ws_url,
            self.settings.gemini_model if self.llm_client.is_configured else "desactivado (sin API key)",
        )

        dashboard_server: Optional[HermesDashboardServer] = None
        tasks: set[asyncio.Task[Any]] = set()
        try:
            if use_dashboard:
                candidate = HermesDashboardServer(
                    state_provider=self.get_dashboard_snapshot,
                    host=self.settings.dashboard_host,
                    port=self.settings.dashboard_port,
                    stale_seconds=self.settings.dashboard_stale_seconds,
                    clock=self._clock,
                )
                try:
                    await candidate.start()
                    dashboard_server = candidate
                    self.dashboard_server = candidate
                    logger.info(
                        "Dashboard solo-lectura activo en http://%s:%d",
                        candidate.host,
                        candidate.bound_port,
                    )
                except OSError as exc:
                    logger.warning(
                        "No se pudo iniciar el dashboard HTTP en %s:%d (%s). El centinela continuará sin dashboard.",
                        self.settings.dashboard_host,
                        self.settings.dashboard_port,
                        exc,
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
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for finished in done:
                exc = finished.exception()
                if exc is not None:
                    raise exc
        except asyncio.CancelledError:
            logger.info("Cancelación recibida; deteniendo tareas de Project Hermes...")
            raise
        finally:
            self.is_shutting_down = True
            self.stream_connected = False
            halt_event.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if dashboard_server is not None:
                await dashboard_server.stop()
                self.dashboard_server = None
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