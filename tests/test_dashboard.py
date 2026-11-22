"""
Suite QA determinista para dashboard/server.py (HermesDashboardServer).
Verifica /health (200 y 503 en shutdown/stale), /api/status (JSON sin secretos),
/metrics (formato Prometheus 0.0.4) y / (HTML oscuro seguro sin ** ni ⚙️).
"""

from decimal import Decimal
import aiohttp
import pytest

from dashboard.server import HermesDashboardServer


def _sample_state(*, stream_connected: bool = True, is_shutting_down: bool = False, last_ledger_age: float = 1.0):
    return {
        "stream_connected": stream_connected,
        "is_shutting_down": is_shutting_down,
        "last_ledger_index": 22360050,
        "last_ledger_age": last_ledger_age,
        "network": "testnet",
        "network_mode": "testnet",
        "gemini_api_key": "SUPER_SECRET_DO_NOT_EXPOSE",
        "telegram_bot_token": "BOT_SECRET_DO_NOT_EXPOSE",
        "vault": {
            "object_id": "A" * 64,
            "nav_per_share": Decimal("1.000000"),
            "parity_status": "AT_PAR",
            "loss_unrealized": Decimal("50"),
            "loss_ratio": Decimal("0.050000"),
            "loss_status": "WARNING",
            "access_mode": "PERMISSIONED",
            "secondary_market_mode": "NON_TRANSFERABLE",
            "is_permissioned": True,
            "is_share_transferable": False,
            "scale": 6,
        },
        "loan_broker": {
            "object_id": "B" * 64,
            "status": "HEALTHY",
            "flcr": Decimal("0.150000"),
            "cover_rate_minimum": Decimal("0.10000"),
            "effective_debt": Decimal("100"),
            "first_loss_capital": Decimal("15"),
        },
        "dispatcher": {
            "circuit_breaker_state": "CLOSED",
            "queue_size": 0,
            "enqueued_count": 3,
            "sent_count": 3,
            "failed_count": 0,
            "dropped_count": 0,
            "circuit_rejected_count": 0,
        },
        "llm": {
            "model": "gemini-4-hydrogen",
            "configured": False,
            "cost_estimate": "0 Tokens / $0.00 USD",
        },
        "recent_alerts": [
            {
                "timestamp": "2026-11-22T12:00:00+00:00",
                "level": "WARNING",
                "source": "XLS65_UNREALIZED_LOSS",
                "object_id": "A" * 64,
                "ledger_index": 22360050,
                "message": "Pérdida no realizada detectada <script>alert(1)</script>",
            }
        ],
    }


@pytest.mark.asyncio
async def test_dashboard_server_endpoints_and_security():
    now = [100.0]
    state = _sample_state(stream_connected=True, is_shutting_down=False, last_ledger_age=1.0)

    server = HermesDashboardServer(
        state_provider=lambda: state,
        host="127.0.0.1",
        port=0,
        stale_seconds=60.0,
        clock=lambda: now[0],
    )
    await server.start()
    try:
        assert server.bound_port > 0
        base_url = f"http://127.0.0.1:{server.bound_port}"

        async with aiohttp.ClientSession() as session:
            # 1. GET /health -> 200 cuando conectado
            async with session.get(f"{base_url}/health") as resp:
                assert resp.status == 200
                health_json = await resp.json()
                assert health_json["status"] == "ok"
                assert health_json["stream_connected"] is True

            # 2. GET /health -> 503 cuando is_shutting_down=True
            state["is_shutting_down"] = True
            async with session.get(f"{base_url}/health") as resp:
                assert resp.status == 503
                health_down = await resp.json()
                assert health_down["status"] == "unhealthy"
                assert health_down["shutting_down"] is True

            # 3. GET /health -> 503 cuando stale (fuera de ventana de arranque de 15s)
            state["is_shutting_down"] = False
            state["stream_connected"] = False
            state["last_ledger_age"] = 120.0
            now[0] = 130.0
            async with session.get(f"{base_url}/health") as resp:
                assert resp.status == 503
                health_stale = await resp.json()
                assert health_stale["status"] == "unhealthy"

            # Restaurar conexión para el resto de comprobaciones
            state["stream_connected"] = True
            state["last_ledger_age"] = 2.0

            # 4. GET /api/status -> JSON limpio sin secretos
            async with session.get(f"{base_url}/api/status") as resp:
                assert resp.status == 200
                raw_text = await resp.text()
                assert "SUPER_SECRET_DO_NOT_EXPOSE" not in raw_text
                assert "BOT_SECRET_DO_NOT_EXPOSE" not in raw_text
                assert "gemini_api_key" not in raw_text
                assert "telegram_bot_token" not in raw_text

                status_json = await resp.json()
                assert status_json["status"] == "WARNING"
                assert status_json["network"] == "testnet"
                assert status_json["last_ledger_index"] == 22360050
                assert status_json["vault"]["nav_per_share"] == "1.000000"
                assert status_json["vault"]["loss_unrealized"] == "50"
                assert status_json["vault"]["access_mode"] == "PERMISSIONED"
                assert status_json["vault"]["secondary_market_mode"] == "NON_TRANSFERABLE"
                assert status_json["loan_broker"]["flcr"] == "0.150000"
                assert status_json["loan_broker"]["cover_rate_minimum"] == "0.10000"
                assert status_json["loan_broker"]["effective_debt"] == "100"
                assert status_json["dispatcher"]["circuit_breaker_state"] == "CLOSED"
                assert status_json["dispatcher"]["sent_count"] == 3
                assert status_json["dispatcher"]["dropped_count"] == 0
                assert status_json["llm"]["model"] == "gemini-4-hydrogen"
                assert status_json["llm"]["configured"] is False
                assert status_json["llm"]["cost_estimate"] == "0 Tokens / $0.00 USD"
                assert len(status_json["recent_alerts"]) == 1

            # 5. GET /metrics -> formato Prometheus 0.0.4
            async with session.get(f"{base_url}/metrics") as resp:
                assert resp.status == 200
                content_type = resp.headers.get("Content-Type", "")
                assert "text/plain" in content_type
                assert "version=0.0.4" in content_type
                metrics_text = await resp.text()
                for expected_line in (
                    "# TYPE hermes_up gauge",
                    "hermes_up 1",
                    "hermes_last_ledger_index 22360050",
                    "hermes_flcr_ratio 0.15",
                    "hermes_nav_per_share 1.0",
                    "hermes_loss_unrealized 50.0",
                    "hermes_alerts_enqueued_total 3",
                    "hermes_alerts_sent_total 3",
                    "hermes_alerts_failed_total 0",
                    "hermes_alerts_dropped_total 0",
                    "hermes_circuit_breaker_state 0",
                ):
                    assert expected_line in metrics_text

            # 6. GET / -> HTML oscuro institucional sin ** literales ni ⚙️
            async with session.get(f"{base_url}/") as resp:
                assert resp.status == 200
                assert "text/html" in resp.headers.get("Content-Type", "")
                html_text = await resp.text()
                assert "**" not in html_text
                assert "⚙️" not in html_text
                assert "escapeHtml" in html_text
                assert 'fetch("/api/status"' in html_text
                assert "🟢 Datos en Tiempo Real (Solo Lectura)" in html_text
                assert 'href="/health"' in html_text
                assert 'href="/api/status"' in html_text
                assert 'href="/metrics"' in html_text
    finally:
        await server.stop()
