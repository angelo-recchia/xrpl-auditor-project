"""
Suite QA determinista para dispatchers/alert_queue.py y rehidratación JSON-RPC.
Valida Dropping Policy, máquina de estados Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN -> CLOSED),
cierre ordenado del consumidor asíncrono y correlación estricta por ID (101 / 102).
"""

import asyncio
import json
import pytest

from core.ledger_client import XRPLedgerClient
from dispatchers.alert_queue import (
    AlertQueueDispatcher,
    CircuitBreaker,
    CircuitState,
)


class TestCircuitBreaker:
    def test_full_recovery_cycle_closed_open_half_open_closed(self):
        now = [100.0]
        cb = CircuitBreaker(failure_threshold=3, cooldown_period=30.0, clock=lambda: now[0])

        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

        # 3 fallos consecutivos abren el circuito
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        # Antes de 30s sigue bloqueado
        now[0] = 129.9
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        # A los 30s pasa a HALF_OPEN y solo permite 1 probe simultáneo
        now[0] = 130.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True
        assert cb.allow_request() is False

        # Si el probe triunfa, se cierra y resetea fallos
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

        # Falla el probe -> vuelve a OPEN durante otros 30s
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

        # 2 fallos -> abre el circuito
        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a1"}) is False
        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a2"}) is False
        assert dispatcher.circuit_breaker.state == CircuitState.OPEN

        # 3.er envío bloqueado sin llamar al sender
        assert await dispatcher.dispatch_one({"level": "CRITICAL", "message": "a3"}) is False
        assert len(attempts) == 2
        assert dispatcher.circuit_rejected_count == 1

        # Avanzamos reloj 30s y recuperamos el transporte
        now[0] = 30.0
        should_succeed[0] = True

        stop_event = asyncio.Event()
        consumer_task = asyncio.create_task(dispatcher.process_queue(stop_event=stop_event))
        dispatcher.enqueue_alert({"level": "CRITICAL", "message": "a4_recovered"})

        await asyncio.wait_for(dispatcher.queue.join(), timeout=2.0)
        stop_event.set()
        await asyncio.wait_for(consumer_task, timeout=2.0)

        assert dispatcher.circuit_breaker.state == CircuitState.CLOSED
        assert dispatcher.sent_count == 1
        assert attempts[-1] == "a4_recovered"


class TestLedgerRehydrationCorrelation:
    @pytest.mark.asyncio
    async def test_rehydrate_state_handles_out_of_order_and_stream_noise(self):
        client = XRPLedgerClient()
        frames = [
            json.dumps({"type": "ledgerClosed", "ledger_index": 1001}),
            json.dumps({"id": 102, "status": "success", "result": {"node": {"LedgerEntryType": "LoanBroker"}}}),
            json.dumps({"type": "ledgerClosed", "ledger_index": 1002}),
            json.dumps({"id": 101, "status": "success", "result": {"node": {"LedgerEntryType": "Vault"}}}),
        ]
        sent = []

        class MockWS:
            async def send(self, msg):
                sent.append(json.loads(msg))

            async def recv(self):
                return frames.pop(0)

        state = await client.rehydrate_state(MockWS(), "A" * 64, "B" * 64)

        assert [m["id"] for m in sent] == [101, 102]
        assert state["vault"]["node"]["LedgerEntryType"] == "Vault"
        assert state["loan_broker"]["node"]["LedgerEntryType"] == "LoanBroker"
        assert [e["ledger_index"] for e in state["buffered_events"]] == [1001, 1002]