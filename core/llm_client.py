"""
Módulo: core/llm_client.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66)
Descripción: Conector oficial para Gemini 4 Hydrogen (google-genai) con
             temperature=0.1 y control dinámico de ThinkingConfig ('low' | 'high').
             Opera de forma opcional/resiliente sin bloquear el centinela determinista.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Literal, Optional

from google import genai
from google.genai import types

from config import Settings, settings

logger = logging.getLogger(__name__)

ThinkingLevel = Literal["low", "high"]

HERMES_SYSTEM_INSTRUCTION = (
    "Eres el analista institucional de riesgo de Project Hermes para bóvedas XRPL XLS-65 "
    "y préstamos XLS-66 (LendingProtocolV1_1). Resume métricas deterministas con precisión "
    "técnica, sin inventar cifras y priorizando acciones de mitigación (DeepFreeze / Halt)."
)


class HermesLLMClient:
    """Cliente agéntico unificado sobre Gemini 4 Hydrogen (gemini-4-hydrogen)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_settings: Optional[Settings] = None,
        client: Any = None,
    ):
        self.settings = app_settings or settings
        self.api_key = api_key if api_key is not None else self.settings.gemini_api_key
        self._client = client

        if self._client is None and self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def is_configured(self) -> bool:
        """Indica si existe clave GEMINI_API_KEY o cliente inyectado operativo."""
        return self._client is not None

    def _build_config(self, thinking_level: Optional[ThinkingLevel] = None) -> types.GenerateContentConfig:
        level = (thinking_level or self.settings.gemini_thinking_level).lower()
        if level not in {"low", "high"}:
            raise ValueError(f"thinking_level inválido: {level!r}. Use 'low' o 'high'.")

        return types.GenerateContentConfig(
            temperature=self.settings.gemini_temperature,
            system_instruction=HERMES_SYSTEM_INSTRUCTION,
            thinking_config=types.ThinkingConfig(thinking_level=level),
        )

    def analyze_risk_event(
        self,
        audit_payload: Dict[str, Any],
        *,
        thinking_level: Optional[ThinkingLevel] = None,
    ) -> str:
        """Genera un resumen ejecutivo síncrono para un evento de riesgo evaluado."""
        if not self.is_configured:
            raise EnvironmentError(
                "GEMINI_API_KEY no configurada en .env. "
                "Configúrala para habilitar análisis con Gemini 4 Hydrogen."
            )

        prompt = (
            "Analiza el siguiente evento determinista XLS-65/XLS-66 y entrega un "
            "diagnóstico breve (máx. 4 líneas) con acción operativa recomendada:\n\n"
            f"{json.dumps(audit_payload, default=str, ensure_ascii=False, indent=2)}"
        )

        response = self._client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=self._build_config(thinking_level),
        )
        return (response.text or "").strip()

    async def analyze_risk_event_async(
        self,
        audit_payload: Dict[str, Any],
        *,
        thinking_level: Optional[ThinkingLevel] = None,
    ) -> Optional[str]:
        """
        Ejecuta análisis asíncrono sin bloquear el bucle WebSocket.
        Si no hay GEMINI_API_KEY configurada, devuelve None sin interrumpir el centinela.
        """
        if not self.is_configured:
            return None

        try:
            return await asyncio.to_thread(
                self.analyze_risk_event,
                audit_payload,
                thinking_level=thinking_level,
            )
        except Exception as exc:
            logger.warning("Fallo no bloqueante consultando Gemini 4 Hydrogen: %s", exc)
            return None