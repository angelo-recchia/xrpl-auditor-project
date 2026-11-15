"""
Módulo: dispatchers/alert_queue.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Cola asíncrona limitada (Dropping Policy) y Circuit Breaker con
             recuperación Half-Open tras cooldown. Envío seguro a Telegram
             con parse_mode="HTML" + html.escape para evitar fallos HTTP 400
             por guiones bajos (_) o Markdown de LLM.
"""

from __future__ import annotations

import asyncio
import html
import inspect
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp

from config import Settings, settings

logger = logging.getLogger(__name__)

QUEUE_MAX_SIZE = settings.alert_queue_max_size
COOLDOWN_PERIOD = settings.circuit_breaker_cooldown_seconds

AlertSender = Callable[[Dict[str, Any]], Awaitable[bool] | bool]
ClockFn = Callable[[], float]

CRITICAL_LEVELS = frozenset({"CRITICAL", "ROJO", "CRITICAL_DEEP_FREEZE", "HIGH_RISK"})


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Máquina de estados de resiliencia: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_period: float = 30.0,
        clock: ClockFn = time.monotonic,
    ):
        if failure_threshold <= 0:
            raise ValueError("failure_threshold debe ser mayor que 0.")
        if cooldown_period <= 0:
            raise ValueError("cooldown_period debe ser mayor que 0.")

        self.failure_threshold = failure_threshold
        self.cooldown_period = cooldown_period
        self._clock = clock

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: Optional[float] = None
        self._half_open_probe_in_flight: bool = False

    @property
    def state(self) -> CircuitState:
        """Devuelve el estado actual evaluando si expiró el cooldown de OPEN."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if (self._clock() - self._opened_at) >= self.cooldown_period:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def allow_request(self) -> bool:
        """
        Indica si el circuito permite intentar un envío.
        En HALF_OPEN solo autoriza un único envío de prueba (probe) simultáneo.
        """
        current = self.state
        if current == CircuitState.CLOSED:
            return True

        if current == CircuitState.HALF_OPEN:
            if self._state == CircuitState.OPEN:
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_in_flight = False
                logger.info("Circuit Breaker pasó a HALF_OPEN tras cooldown. Probando recuperación...")

            if not self._half_open_probe_in_flight:
                self._half_open_probe_in_flight = True
                return True
            return False

        return False

    def record_success(self) -> None:
        """Registra un envío exitoso: cierra el circuito y limpia el contador de fallos."""
        prev = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
        self._half_open_probe_in_flight = False
        if prev != CircuitState.CLOSED:
            logger.info("Circuit Breaker recuperado: %s -> CLOSED.", prev.value)

    def record_failure(self) -> None:
        """Registra un fallo: abre el circuito si se alcanza el umbral o falla el probe HALF_OPEN."""
        self._half_open_probe_in_flight = False
        current = self.state

        if current == CircuitState.HALF_OPEN or self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._failure_count = self.failure_threshold
            logger.warning("Fallo en probe HALF_OPEN. Circuit Breaker reabierto (OPEN) durante %.1fs.", self.cooldown_period)
            return

        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            logger.error(
                "Circuit Breaker ABIERTO (OPEN) tras %d fallos consecutivos. Cooldown: %.1fs.",
                self._failure_count,
                self.cooldown_period,
            )


class AlertQueueDispatcher:
    """
    Cola asíncrona limitada con Dropping Policy y Circuit Breaker Half-Open.
    """

    def __init__(
        self,
        *,
        app_settings: Optional[Settings] = None,
        max_size: Optional[int] = None,
        failure_threshold: Optional[int] = None,
        cooldown_period: Optional[float] = None,
        sender: Optional[AlertSender] = None,
        clock: ClockFn = time.monotonic,
        emergency_log_path: Optional[Path] = None,
    ):
        cfg = app_settings or settings
        self.settings = cfg

        q_size = max_size if max_size is not None else cfg.alert_queue_max_size
        f_thresh = failure_threshold if failure_threshold is not None else cfg.circuit_breaker_failure_threshold
        c_period = cooldown_period if cooldown_period is not None else cfg.circuit_breaker_cooldown_seconds

        if q_size <= 0:
            raise ValueError("max_size debe ser mayor que 0.")

        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=q_size)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=f_thresh,
            cooldown_period=c_period,
            clock=clock,
        )
        self._sender = sender or self._default_async_sender
        self.emergency_log_path = emergency_log_path or (
            Path(__file__).resolve().parent.parent / "progress" / "emergency_halt.log"
        )

        # Métricas observables para QA y telemetría
        self.enqueued_count: int = 0
        self.dropped_count: int = 0
        self.sent_count: int = 0
        self.failed_count: int = 0
        self.circuit_rejected_count: int = 0

    def enqueue_alert(self, alert: Dict[str, Any]) -> bool:
        """
        Encola una alerta sin bloquear el bucle de ingesta.
        Aplica Dropping Policy si la cola alcanzó max_size.
        """
        try:
            self.queue.put_nowait(alert)
            self.enqueued_count += 1
            return True
        except asyncio.QueueFull:
            self.dropped_count += 1
            logger.warning(
                "Cola de alertas llena (maxsize=%d). Dropping Policy aplicada (total descartadas=%d).",
                self.queue.maxsize,
                self.dropped_count,
            )
            self._write_emergency_fallback(alert, "Cola de alertas llena (Dropping Policy)")
            return False

    async def dispatch_one(self, alert: Dict[str, Any]) -> bool:
        """Intenta despachar una alerta respetando el estado del Circuit Breaker."""
        if not self.circuit_breaker.allow_request():
            self.circuit_rejected_count += 1
            logger.warning("Alerta retenida por Circuit Breaker OPEN (rechazadas=%d).", self.circuit_rejected_count)
            self._write_emergency_fallback(alert, "Circuit Breaker OPEN")
            return False

        try:
            result = self._sender(alert)
            success = bool(await result) if inspect.isawaitable(result) else bool(result)
        except Exception as exc:
            logger.warning("Excepción enviando alerta: %s", exc)
            success = False

        if success:
            self.circuit_breaker.record_success()
            self.sent_count += 1
            return True

        self.circuit_breaker.record_failure()
        self.failed_count += 1
        self._write_emergency_fallback(alert, "Fallo en transporte de salida")
        return False

    async def process_queue(self, stop_event: Optional[asyncio.Event] = None) -> None:
        """
        Consumidor asíncrono continuo de la cola de alertas.
        Soporta cierre ordenado mediante stop_event o asyncio.CancelledError.
        """
        logger.info(
            "Pasarela de alertas iniciada (maxsize=%d, cooldown=%.1fs).",
            self.queue.maxsize,
            self.circuit_breaker.cooldown_period,
        )
        try:
            while True:
                if stop_event and stop_event.is_set() and self.queue.empty():
                    break

                try:
                    alert = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                try:
                    await self.dispatch_one(alert)
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            logger.info("Consumidor de alertas cancelado ordenadamente.")
            raise

    def _build_telegram_payload(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construye payload HTML seguro para Telegram Bot API:
        evita HTTP 400 por guiones bajos (_) o Markdown de LLM y respeta límite 4096 chars.
        """
        raw_level = str(alert.get("level", "INFO")).upper()
        raw_message = str(alert.get("message", ""))[:3800]
        level = html.escape(raw_level, quote=False)
        message = html.escape(raw_message, quote=False)
        return {
            "chat_id": self.settings.telegram_chat_id,
            "text": f"<b>[HERMES SENTINEL - NIVEL: {level}]</b>\n\n{message}",
            "parse_mode": "HTML",
        }

    async def _default_async_sender(self, alert: Dict[str, Any]) -> bool:
        """Transporte asíncrono por defecto (Telegram Bot API o Webhook)."""
        level = str(alert.get("level", "INFO")).upper()
        message = str(alert.get("message", ""))

        if self.settings.has_telegram_channel:
            url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
            payload = self._build_telegram_payload(alert)
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    err_body = await resp.text()
                    logger.warning("Telegram rechazó el envío (HTTP %d): %s", resp.status, err_body)
                    return False

        if self.settings.alert_webhook_url:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.settings.alert_webhook_url, json=alert) as resp:
                    return 200 <= resp.status < 300

        # Sin canal externo configurado: registrar localmente sin disparar falsos fallos de red
        logger.info("[ALERTA LOCAL - %s] %s", level, message)
        return True

    def _write_emergency_fallback(self, alert: Dict[str, Any], reason: str) -> None:
        """Persiste alertas críticas en progress/emergency_halt.log ante fallos externos."""
        level = str(alert.get("level", "INFO")).upper()
        if level not in CRITICAL_LEVELS:
            return

        self.emergency_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        entry = (
            f"====================================================\n"
            f"TIMESTAMP (UTC): {timestamp}\n"
            f"NIVEL: {level}\n"
            f"MOTIVO FALLBACK: {reason}\n"
            f"MENSAJE: {alert.get('message', '')}\n"
            f"====================================================\n\n"
        )
        with open(self.emergency_log_path, "a", encoding="utf-8") as f:
            f.write(entry)