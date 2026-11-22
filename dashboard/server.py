"""
Módulo: dashboard/server.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66 / LendingProtocolV1_1)
Descripción: Servidor HTTP asíncrono estrictamente de solo lectura sobre aiohttp.web.
             Expone /health, /api/status, /metrics (Prometheus) y / (UI oscura).
             No modifica estado ni expone secretos/credenciales de entorno.
"""

from __future__ import annotations

import inspect
import math
import time
from decimal import Decimal
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiohttp import web

StateProvider = Callable[[], Dict[str, Any] | Awaitable[Dict[str, Any]]]
ClockFn = Callable[[], float]

STARTUP_GRACE_SECONDS = 15.0

_STATUS_SEVERITY_ORDER: Dict[str, int] = {
    "HEALTHY": 0,
    "WARNING": 1,
    "HIGH_RISK": 2,
    "CRITICAL": 3,
    "CRITICAL_DEEP_FREEZE": 4,
}

_CIRCUIT_BREAKER_NUMERIC: Dict[str, int] = {
    "CLOSED": 0,
    "HALF_OPEN": 1,
    "OPEN": 2,
}


def _json_safe(value: Any) -> Any:
    """Convierte valores Decimal/Enum a tipos seguros para serialización JSON."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _as_finite_float(value: Any) -> Optional[float]:
    """Convierte un valor numérico a float finito para Prometheus; devuelve None si no aplica."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return num if math.isfinite(num) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        num = float(value)
        return num if math.isfinite(num) else None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            num = float(cleaned)
        except ValueError:
            return None
        return num if math.isfinite(num) else None
    return None


def _as_non_negative_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


def _normalize_global_status(state: Dict[str, Any], recent_alerts: List[Dict[str, Any]]) -> str:
    explicit = state.get("global_status") or state.get("status")
    if isinstance(explicit, str):
        normalized = explicit.strip().upper()
        if normalized in _STATUS_SEVERITY_ORDER:
            return normalized

    best = "HEALTHY"
    best_rank = 0

    vault = state.get("vault") if isinstance(state.get("vault"), dict) else {}
    broker = state.get("loan_broker") if isinstance(state.get("loan_broker"), dict) else {}
    candidates: List[Any] = [
        vault.get("loss_status"),
        broker.get("status"),
    ]
    if vault.get("parity_status") == "IMPAIRED_BELOW_PAR":
        candidates.append("WARNING")
    elif vault.get("parity_status") == "ANOMALY_ASSETS_WITHOUT_SHARES":
        candidates.append("CRITICAL")

    for alert in recent_alerts:
        candidates.append(alert.get("level"))

    for cand in candidates:
        if isinstance(cand, str):
            norm = cand.strip().upper()
            rank = _STATUS_SEVERITY_ORDER.get(norm, -1)
            if rank > best_rank:
                best_rank = rank
                best = norm
    return best


def _sanitize_alerts(raw_alerts: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_alerts, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for item in raw_alerts[:25]:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "timestamp": _json_safe(item.get("timestamp")),
                "level": str(item.get("level") or "INFO").upper(),
                "source": str(item.get("source") or "UNKNOWN"),
                "object_id": _json_safe(item.get("object_id")),
                "ledger_index": _json_safe(item.get("ledger_index")),
                "message": str(item.get("message") or ""),
            }
        )
    return cleaned


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Hermes — Monitor Institucional XRPL XLS-65 / XLS-66</title>
  <style>
    :root {
      --bg: #070b14;
      --surface: #0f172a;
      --surface-alt: #162033;
      --border: #1e293b;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --ok: #22c55e;
      --warn: #f59e0b;
      --crit: #ef4444;
      --accent: #38bdf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 20px 80px;
    }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 24px;
    }
    .brand h1 {
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: 0.02em;
    }
    .brand p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.875rem;
    }
    .badge {
      display: inline-block;
      padding: 6px 12px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      border: 1px solid var(--border);
      background: var(--surface);
    }
    .badge-HEALTHY { color: var(--ok); border-color: rgba(34, 197, 94, 0.4); background: rgba(34, 197, 94, 0.1); }
    .badge-WARNING { color: var(--warn); border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.1); }
    .badge-CRITICAL, .badge-CRITICAL_DEEP_FREEZE, .badge-HIGH_RISK {
      color: var(--crit); border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.12);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }
    .card h2 {
      margin: 0 0 12px;
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--accent);
    }
    .kv {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0;
      border-bottom: 1px solid rgba(30, 41, 59, 0.65);
      font-size: 0.88rem;
    }
    .kv:last-child { border-bottom: none; }
    .kv .k { color: var(--muted); }
    .kv .v { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-align: right; word-break: break-all; }
    .alerts-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }
    .alerts-card h2 {
      margin: 0 0 12px;
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--accent);
    }
    .alert-item {
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 8px;
      font-size: 0.85rem;
    }
    .alert-item:last-child { margin-bottom: 0; }
    .alert-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 0.78rem;
    }
    .empty { color: var(--muted); font-size: 0.88rem; }
    footer.statusbar {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      background: #050811;
      border-top: 1px solid var(--border);
      padding: 10px 20px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      font-size: 0.82rem;
      color: var(--muted);
    }
    footer.statusbar a {
      color: var(--accent);
      text-decoration: none;
      margin-left: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    footer.statusbar a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1>Project Hermes Sentinel</h1>
        <p>Monitor institucional de riesgo XRPL XLS-65 / XLS-66 (Solo Lectura)</p>
      </div>
      <div id="global-badge" class="badge badge-HEALTHY">CARGANDO...</div>
    </header>

    <div class="grid">
      <section class="card">
        <h2>Red y Ledger</h2>
        <div id="panel-network"></div>
      </section>
      <section class="card">
        <h2>Bóveda XLS-65</h2>
        <div id="panel-vault"></div>
      </section>
      <section class="card">
        <h2>LoanBroker XLS-66</h2>
        <div id="panel-broker"></div>
      </section>
      <section class="card">
        <h2>Pasarela y LLM</h2>
        <div id="panel-ops"></div>
      </section>
    </div>

    <section class="alerts-card">
      <h2>Alertas Recientes</h2>
      <div id="panel-alerts" class="empty">Consultando estado...</div>
    </section>
  </div>

  <footer class="statusbar">
    <div>🟢 Datos en Tiempo Real (Solo Lectura) · <span id="last-sync">sincronizando...</span></div>
    <div>
      Endpoints:
      <a href="/health">/health</a>
      <a href="/api/status">/api/status</a>
      <a href="/metrics">/metrics</a>
    </div>
  </footer>

  <script>
    function escapeHtml(value) {
      if (value === null || value === undefined) return "—";
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function renderRows(rows) {
      return rows.map(function (pair) {
        return '<div class="kv"><span class="k">' + escapeHtml(pair[0]) +
          '</span><span class="v">' + escapeHtml(pair[1]) + '</span></div>';
      }).join("");
    }

    function renderStatus(data) {
      var status = String(data.status || "HEALTHY").toUpperCase();
      var badge = document.getElementById("global-badge");
      badge.textContent = status;
      badge.className = "badge badge-" + status.replace(/[^A-Z0-9_]/g, "");

      document.getElementById("panel-network").innerHTML = renderRows([
        ["Red", data.network || "unknown"],
        ["Modo", data.network_mode || "unknown"],
        ["Stream WS", data.stream_connected ? "CONECTADO" : "DESCONECTADO"],
        ["Último Ledger", data.last_ledger_index]
      ]);

      var vault = data.vault || {};
      document.getElementById("panel-vault").innerHTML = renderRows([
        ["NAV / Share", vault.nav_per_share],
        ["Paridad", vault.parity_status],
        ["LossUnrealized", vault.loss_unrealized],
        ["Acceso", vault.access_mode],
        ["Mercado Secundario", vault.secondary_market_mode]
      ]);

      var broker = data.loan_broker || {};
      document.getElementById("panel-broker").innerHTML = renderRows([
        ["Estado", broker.status],
        ["FLCR", broker.flcr],
        ["CoverRateMinimum", broker.cover_rate_minimum],
        ["EffectiveDebt", broker.effective_debt]
      ]);

      var disp = data.dispatcher || {};
      var llm = data.llm || {};
      document.getElementById("panel-ops").innerHTML = renderRows([
        ["Circuit Breaker", disp.circuit_breaker_state],
        ["Cola / Enviadas / Drops", [disp.queue_size, disp.sent_count, disp.dropped_count].join(" / ")],
        ["Modelo LLM", llm.model + (llm.configured ? " (activo)" : " (inactivo)")],
        ["Coste LLM", llm.cost_estimate]
      ]);

      var alerts = Array.isArray(data.recent_alerts) ? data.recent_alerts : [];
      var alertsEl = document.getElementById("panel-alerts");
      if (alerts.length === 0) {
        alertsEl.innerHTML = '<div class="empty">Sin alertas activas ni recientes.</div>';
      } else {
        alertsEl.innerHTML = alerts.map(function (a) {
          return '<div class="alert-item">' +
            '<div class="alert-meta">' +
              '<span class="badge badge-' + escapeHtml(String(a.level || "INFO").replace(/[^A-Z0-9_]/g, "")) + '">' + escapeHtml(a.level) + '</span>' +
              '<span>' + escapeHtml(a.source) + '</span>' +
              '<span>ID: ' + escapeHtml(a.object_id) + '</span>' +
              '<span>Ledger: ' + escapeHtml(a.ledger_index) + '</span>' +
            '</div>' +
            '<div>' + escapeHtml(a.message) + '</div>' +
          '</div>';
        }).join("");
      }

      document.getElementById("last-sync").textContent = "actualizado " + new Date().toLocaleTimeString();
    }

    async function refreshStatus() {
      try {
        var resp = await fetch("/api/status", { cache: "no-store" });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        var data = await resp.json();
        renderStatus(data);
      } catch (err) {
        document.getElementById("last-sync").textContent = "error de lectura (" + err.message + ")";
      }
    }

    refreshStatus();
    setInterval(refreshStatus, 3000);
  </script>
</body>
</html>
"""


class HermesDashboardServer:
    """Servidor HTTP de solo lectura para observabilidad operacional de Project Hermes."""

    def __init__(
        self,
        state_provider: StateProvider,
        host: str = "127.0.0.1",
        port: int = 8080,
        stale_seconds: float = 60.0,
        clock: ClockFn = time.monotonic,
    ) -> None:
        if not callable(state_provider):
            raise TypeError("state_provider debe ser invocable (callable).")
        if isinstance(port, bool) or not isinstance(port, int) or not (0 <= port <= 65535):
            raise ValueError(f"port debe estar en [0, 65535], recibido: {port!r}")
        if stale_seconds <= 0:
            raise ValueError("stale_seconds debe ser mayor que 0.")

        self._state_provider = state_provider
        self.host = host
        self.port = port
        self.stale_seconds = float(stale_seconds)
        self._clock = clock

        self._started_at: float = float(self._clock())
        self._shutting_down: bool = False
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    @property
    def bound_port(self) -> int:
        """Devuelve el puerto real asignado por el SO (útil cuando port=0)."""
        if self._site is not None and getattr(self._site, "_server", None) is not None:
            sockets = getattr(self._site._server, "sockets", None) or []
            if sockets:
                return int(sockets[0].getsockname()[1])
        return self.port

    async def _read_state(self) -> Dict[str, Any]:
        raw = self._state_provider()
        if inspect.isawaitable(raw):
            raw = await raw
        return raw if isinstance(raw, dict) else {}

    def _compute_health(self, state: Dict[str, Any]) -> Dict[str, Any]:
        now = float(self._clock())
        uptime = max(0.0, now - self._started_at)
        stream_connected = bool(state.get("stream_connected", False))
        shutting_down = self._shutting_down or bool(state.get("is_shutting_down", False))

        raw_age = state.get("last_ledger_age")
        if raw_age is not None and not isinstance(raw_age, bool):
            try:
                last_ledger_age: Optional[float] = max(0.0, float(raw_age))
            except (TypeError, ValueError):
                last_ledger_age = None
        elif state.get("last_ledger_at") is not None:
            try:
                last_ledger_age = max(0.0, now - float(state["last_ledger_at"]))
            except (TypeError, ValueError):
                last_ledger_age = None
        else:
            last_ledger_age = None

        is_healthy = (not shutting_down) and (
            stream_connected
            or uptime <= STARTUP_GRACE_SECONDS
            or (last_ledger_age is not None and last_ledger_age <= self.stale_seconds)
        )
        return {
            "is_healthy": is_healthy,
            "shutting_down": shutting_down,
            "stream_connected": stream_connected,
            "uptime_seconds": round(uptime, 3),
            "last_ledger_age": round(last_ledger_age, 3) if last_ledger_age is not None else None,
            "stale_seconds": self.stale_seconds,
            "last_ledger_index": _json_safe(state.get("last_ledger_index")),
        }

    def _build_status_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        vault_in = state.get("vault") if isinstance(state.get("vault"), dict) else {}
        broker_in = state.get("loan_broker") if isinstance(state.get("loan_broker"), dict) else {}
        disp_in = state.get("dispatcher") if isinstance(state.get("dispatcher"), dict) else {}
        llm_in = state.get("llm") if isinstance(state.get("llm"), dict) else {}
        recent_alerts = _sanitize_alerts(state.get("recent_alerts"))

        raw_cb = disp_in.get("circuit_breaker_state", "CLOSED")
        cb_state = raw_cb.value if isinstance(raw_cb, Enum) else str(raw_cb or "CLOSED").upper()

        health = self._compute_health(state)

        return {
            "status": _normalize_global_status(state, recent_alerts),
            "network": str(state.get("network") or state.get("xrpl_network") or "unknown"),
            "network_mode": str(state.get("network_mode") or state.get("xrpl_network_mode") or "unknown"),
            "stream_connected": health["stream_connected"],
            "last_ledger_index": health["last_ledger_index"],
            "last_ledger_age": health["last_ledger_age"],
            "vault": {
                "object_id": _json_safe(vault_in.get("object_id")),
                "nav_per_share": _json_safe(vault_in.get("nav_per_share")),
                "parity_status": _json_safe(vault_in.get("parity_status")),
                "loss_unrealized": _json_safe(vault_in.get("loss_unrealized")),
                "loss_ratio": _json_safe(vault_in.get("loss_ratio")),
                "loss_status": _json_safe(vault_in.get("loss_status")),
                "access_mode": _json_safe(vault_in.get("access_mode")),
                "secondary_market_mode": _json_safe(vault_in.get("secondary_market_mode")),
                "is_permissioned": vault_in.get("is_permissioned"),
                "is_share_transferable": vault_in.get("is_share_transferable"),
                "scale": vault_in.get("scale"),
            },
            "loan_broker": {
                "object_id": _json_safe(broker_in.get("object_id")),
                "status": _json_safe(broker_in.get("status")),
                "flcr": _json_safe(broker_in.get("flcr")),
                "cover_rate_minimum": _json_safe(broker_in.get("cover_rate_minimum")),
                "effective_debt": _json_safe(broker_in.get("effective_debt")),
                "first_loss_capital": _json_safe(broker_in.get("first_loss_capital")),
            },
            "dispatcher": {
                "circuit_breaker_state": cb_state,
                "queue_size": _as_non_negative_int(disp_in.get("queue_size")),
                "enqueued_count": _as_non_negative_int(disp_in.get("enqueued_count")),
                "sent_count": _as_non_negative_int(disp_in.get("sent_count")),
                "failed_count": _as_non_negative_int(disp_in.get("failed_count")),
                "dropped_count": _as_non_negative_int(disp_in.get("dropped_count")),
                "circuit_rejected_count": _as_non_negative_int(disp_in.get("circuit_rejected_count")),
            },
            "llm": {
                "model": str(llm_in.get("model") or "gemini-4-hydrogen"),
                "configured": bool(llm_in.get("configured", False)),
                "cost_estimate": str(llm_in.get("cost_estimate") or llm_in.get("cost") or "0 Tokens / $0.00 USD"),
            },
            "recent_alerts": recent_alerts,
        }

    async def handle_health(self, request: web.Request) -> web.Response:
        state = await self._read_state()
        health = self._compute_health(state)
        is_healthy = health.pop("is_healthy")
        body = {
            "status": "ok" if is_healthy else "unhealthy",
            **health,
        }
        return web.json_response(body, status=200 if is_healthy else 503)

    async def handle_api_status(self, request: web.Request) -> web.Response:
        state = await self._read_state()
        return web.json_response(self._build_status_payload(state), status=200)

    async def handle_metrics(self, request: web.Request) -> web.Response:
        state = await self._read_state()
        health = self._compute_health(state)
        status_payload = self._build_status_payload(state)

        vault = status_payload["vault"]
        broker = status_payload["loan_broker"]
        disp = status_payload["dispatcher"]

        hermes_up = 1 if health["is_healthy"] else 0
        ledger_num = _as_finite_float(status_payload["last_ledger_index"])
        flcr_num = _as_finite_float(broker.get("flcr"))
        nav_num = _as_finite_float(vault.get("nav_per_share"))
        loss_num = _as_finite_float(vault.get("loss_unrealized"))
        cb_num = _CIRCUIT_BREAKER_NUMERIC.get(disp["circuit_breaker_state"], 0)

        lines: List[str] = [
            "# HELP hermes_up Whether Hermes Sentinel is healthy (1=up, 0=unhealthy).",
            "# TYPE hermes_up gauge",
            f"hermes_up {hermes_up}",
            "# HELP hermes_last_ledger_index Last validated XRPL ledger index observed.",
            "# TYPE hermes_last_ledger_index gauge",
            f"hermes_last_ledger_index {int(ledger_num) if ledger_num is not None else 0}",
        ]

        if flcr_num is not None:
            lines.extend(
                [
                    "# HELP hermes_flcr_ratio Current XLS-66 First-Loss Capital Ratio.",
                    "# TYPE hermes_flcr_ratio gauge",
                    f"hermes_flcr_ratio {flcr_num}",
                ]
            )
        if nav_num is not None:
            lines.extend(
                [
                    "# HELP hermes_nav_per_share Current XLS-65 Vault NAV per share.",
                    "# TYPE hermes_nav_per_share gauge",
                    f"hermes_nav_per_share {nav_num}",
                ]
            )
        if loss_num is not None:
            lines.extend(
                [
                    "# HELP hermes_loss_unrealized Current XLS-65 Vault LossUnrealized.",
                    "# TYPE hermes_loss_unrealized gauge",
                    f"hermes_loss_unrealized {loss_num}",
                ]
            )

        lines.extend(
            [
                "# HELP hermes_alerts_enqueued_total Total alerts enqueued in dispatcher.",
                "# TYPE hermes_alerts_enqueued_total counter",
                f"hermes_alerts_enqueued_total {disp['enqueued_count']}",
                "# HELP hermes_alerts_sent_total Total alerts dispatched successfully.",
                "# TYPE hermes_alerts_sent_total counter",
                f"hermes_alerts_sent_total {disp['sent_count']}",
                "# HELP hermes_alerts_failed_total Total alerts failed during dispatch.",
                "# TYPE hermes_alerts_failed_total counter",
                f"hermes_alerts_failed_total {disp['failed_count']}",
                "# HELP hermes_alerts_dropped_total Total alerts dropped due to full queue.",
                "# TYPE hermes_alerts_dropped_total counter",
                f"hermes_alerts_dropped_total {disp['dropped_count']}",
                "# HELP hermes_circuit_breaker_state Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN).",
                "# TYPE hermes_circuit_breaker_state gauge",
                f"hermes_circuit_breaker_state {cb_num}",
            ]
        )

        body = "\n".join(lines) + "\n"
        return web.Response(
            body=body.encode("utf-8"),
            status=200,
            headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
        )

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(
            body=_DASHBOARD_HTML.encode("utf-8"),
            status=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    async def start(self) -> None:
        """Arranca el servidor HTTP solo-lectura sobre AppRunner y TCPSite."""
        if self._runner is not None:
            return
        self._shutting_down = False
        self._started_at = float(self._clock())

        app = web.Application()
        app.router.add_get("/health", self.handle_health)
        app.router.add_get("/api/status", self.handle_api_status)
        app.router.add_get("/metrics", self.handle_metrics)
        app.router.add_get("/", self.handle_index)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    async def stop(self) -> None:
        """Detiene el servidor HTTP de forma ordenada."""
        self._shutting_down = True
        if self._runner is not None:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
