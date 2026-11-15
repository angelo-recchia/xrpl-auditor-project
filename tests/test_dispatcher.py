"""
Suite QA determinista para dispatchers/alert_queue.py, core/ledger_client.py y main.py.
Valida Dropping Policy, Circuit Breaker Half-Open, formato HTML seguro en Telegram,
correlación JSON-RPC (101/102), re-sondeo 64-hex (201/202) y parseo de meta.AffectedNodes.
"""

import asyncio
import json
import pytest

from config import load_settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dispatchers.alert_queue import (
    AlertQueueDispatcher,
    CircuitBreaker,
    CircuitState,
)
from evaluators.rules import LSF_LOW_DEEP_FREEZE
from main import LSF_LOAN_DEFAULT, HermesSentinel, extract_affected_nodes


class TestCircuitBreaker:
    def test_full_recovery_cycle_closed_open_half_open_closed(self):
        now = [100.0]
        cb = CircuitBreaker(failure_threshold=3, cooldown_period=30.0, clock=lambda: now[0])

        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        now[0] = 129.9
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        now[0] = 130.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True
        assert cb.allow_request() is False

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.allow_request() is True

    def test_half_open_failure_reopens_circuit_for_new_cooldown(self):
        now = [0.0]
        cb = CircuitBreaker(failure_threshold=2, cooldown_period=30.0, clock=lambda: now[0])

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        now[0] = 30.0
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        now[0] = 59.0
        assert cb.allow_request() is False
        now[0] = 60.0
        assert cb.allow_request() is True


class TestAlertQueueDispatcher:
    def test_dropping_policy_protects_bounded_queue_and_logs_critical(self, tmp_path):
        emergency_log = tmp_path / "emergency_halt.log"
        dispatcher = AlertQueueDispatcher(
            max_size=2,
            emergency_log_path=emergency_log,
        )

        assert dispatcher.enqueue_alert({"level": "INFO", "message": "msg1"}) is True
        assert dispatcher.enqueue_alert({"level": "INFO", "message": "msg2"}) is True
        assert dispatcher.enqueue_alert({"level": "CRITICAL", "message": "msg3"}) is False

        assert dispatcher.enqueued_count == 2
        assert dispatcher.dropped_count == 1
        assert emergency_log.exists()
        assert "Dropping Policy" in emergency_log.read_text(encoding="utf-8")

    def test_telegram_payload_uses_safe_html_and_escapes_underscores_and_markdown(self):
        dispatcher = AlertQueueDispatcher(max_size=5)
        payload = dispatcher._build_telegram_payload(
            {
                "level": "CRITICAL_DEEP_FREEZE",
                "message": "**Alerta** <Vault_1> & XLS66_FLCR_SOLVENCY",
            }
        )
        assert payload["parse_mode"] == "HTML"
        assert "<b>[HERMES SENTINEL - NIVEL: CRITICAL_DEEP_FREEZE]</b>" in payload["text"]
        assert "&lt;Vault_1&gt; &amp; XLS66_FLCR_SOLVENCY" in payload["text"]

    @pytest.mark.asyncio
    async def test_process_queue_circuit_breaker_recovery_and_shutdown(self, tmp_path):
        now = [0.0]
        attempts = []
        should_succeed = [False]

        async def flaky_sender(alert):
            attempts.append(alert["message"])
            return should_succeed[0]

        dispatcher = AlertQueueDispatcher(
            max_size=10,
            failure_threshold=2,
            cooldown_period=30.0,
            sender=flaky_sender,
            clock=lambda: now[0],
            emergency_log_path=tmp_path / "emergency_halt.log",
        )

        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a1"}) is False
        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a2"}) is False
        assert dispatcher.circuit_breaker.state == CircuitState.OPEN

        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a3"}) is False
        assert len(attempts) == 2
        assert dispatcher.circuit_rejected_count == 1

        now[0] = 30.0
        should_succeed[0] = True

        stop_event = asyncio.Event()
        consumer_task = asyncio.create_task(dispatcher.process_queue(stop_event=stop_event))
        dispatcher.enqueue_alert({"level": "CRITICAL", "message": "a4_recovered"})

        await asyncio.wait_for(dispatcher.queue.join(), timeout=2.0)
        stop_event.set()
        await asyncio.wait_for(consumer_task, timeout=2.0)

        assert dispatcher.circuit_breaker.state