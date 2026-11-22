"""
Módulo de Configuración Global de Project Hermes (XRPL XLS-65 / XLS-66).

Centraliza la lectura dinámica de variables de entorno (.env), config/networks.json
y config/parameters.yaml, validando invariantes antes de iniciar los sockets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent
NETWORKS_PATH = CONFIG_DIR / "networks.json"
PARAMETERS_PATH = CONFIG_DIR / "parameters.yaml"

ThinkingLevel = Literal["low", "high"]
NetworkMode = Literal["devnet", "testnet", "mainnet", "standalone", "custom"]

VALID_THINKING_LEVELS: frozenset[str] = frozenset({"low", "high"})
VALID_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _get_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    if raw is None:
        return default
    cleaned = raw.strip()
    return cleaned if cleaned else default


def _get_optional_str(key: str) -> str | None:
    raw = os.getenv(key)
    if raw is None:
        return None
    cleaned = raw.strip()
    return cleaned if cleaned else None


def _get_int(key: str, default: int) -> int:
    raw = _get_optional_str(key)
    if raw is None:
        return default
    try:
        return int(raw, 0)  # Soporta enteros y hexadecimales (ej. 0x00010000)
    except ValueError as exc:
        raise ValueError(f"Variable '{key}' inválida (se esperaba entero): {raw!r}") from exc


def _get_float(key: str, default: float) -> float:
    raw = _get_optional_str(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Variable '{key}' inválida (se esperaba float): {raw!r}") from exc


def _get_bool(key: str, default: bool) -> bool:
    raw = _get_optional_str(key)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Variable '{key}' inválida (se esperaba booleano): {raw!r}")


def _get_decimal(key: str, default: str | float | int) -> Decimal:
    raw = _get_optional_str(key)
    value = raw if raw is not None else str(default)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Variable '{key}' inválida (se esperaba Decimal): {value!r}") from exc


def _load_networks() -> dict[str, Any]:
    if not NETWORKS_PATH.exists():
        return {}
    with open(NETWORKS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _load_parameters() -> dict[str, Any]:
    if not PARAMETERS_PATH.exists() or yaml is None:
        return {}
    with open(PARAMETERS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _infer_network_mode(ws_url: str, configured_network: str) -> NetworkMode:
    lowered = ws_url.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered or "rippled" in lowered or "xrpld" in lowered:
        return "standalone"
    if "altnet" in lowered or "testnet" in lowered:
        return "testnet"
    if "devnet" in lowered:
        return "devnet"
    if "xrplcluster.com" in lowered or "s1.ripple.com" in lowered or "s2.ripple.com" in lowered:
        return "mainnet"
    if configured_network in {"devnet", "testnet", "mainnet", "standalone"}:
        return configured_network  # type: ignore[return-value]
    return "custom"


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuración global inmutable de Project Hermes."""

    # --- Entorno y Logging ---
    app_env: str
    log_level: str

    # --- Red XRPL (Híbrida: Testnet / Devnet / Standalone Docker) ---
    xrpl_network: str
    xrpl_ws_url: str
    xrpl_rpc_url: str
    xrpl_network_mode: NetworkMode
    vault_account_id: str | None
    loan_broker_id: str | None

    # --- Correlación JSON-RPC y Reconexión WebSocket ---
    rpc_vault_req_id: int
    rpc_loan_broker_req_id: int
    rpc_request_timeout: float
    ws_reconnect_initial_delay: float
    ws_reconnect_max_delay: float
    ws_reconnect_backoff_factor: float

    # --- Reglas Financieras XLS-65 / XLS-66 ---
    flcr_base: Decimal
    flcr_warning_multiplier: Decimal
    max_borrower_share: Decimal
    max_concentration_hhi: Decimal
    nav_quantizer: Decimal
    vault_permissioned_mask: int

    # --- Pasarela de Alertas y Circuit Breaker ---
    alert_queue_max_size: int
    circuit_breaker_failure_threshold: int
    circuit_breaker_cooldown_seconds: float
    telegram_bot_token: str | None = field(repr=False)
    telegram_chat_id: str | None
    alert_webhook_url: str | None = field(repr=False)

    # --- Motor Agéntico (Gemini 4 Hydrogen) ---
    gemini_api_key: str | None = field(repr=False)
    gemini_model: str
    gemini_thinking_level: ThinkingLevel
    gemini_temperature: float

    # --- Dashboard Solo Lectura ---
    dashboard_enabled: bool = True
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8080
    dashboard_stale_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not (self.xrpl_ws_url.startswith("ws://") or self.xrpl_ws_url.startswith("wss://")):
            raise ValueError(f"XRPL_WS_URL debe iniciar con ws:// o wss://, recibido: {self.xrpl_ws_url!r}")

        if not (self.xrpl_rpc_url.startswith("http://") or self.xrpl_rpc_url.startswith("https://")):
            raise ValueError(f"XRPL_RPC_URL debe iniciar con http:// o https://, recibido: {self.xrpl_rpc_url!r}")

        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL inválido: {self.log_level!r}")

        if self.rpc_vault_req_id == self.rpc_loan_broker_req_id:
            raise ValueError("RPC_VAULT_REQ_ID y RPC_LOAN_BROKER_REQ_ID deben ser distintos.")

        if self.rpc_request_timeout <= 0:
            raise ValueError("RPC_REQUEST_TIMEOUT debe ser mayor que 0.")

        if self.ws_reconnect_initial_delay <= 0 or self.ws_reconnect_max_delay < self.ws_reconnect_initial_delay:
            raise ValueError("Parámetros de backoff WebSocket inconsistentes.")

        if self.ws_reconnect_backoff_factor < 1.0:
            raise ValueError("WS_RECONNECT_BACKOFF_FACTOR debe ser >= 1.0.")

        if self.flcr_warning_multiplier < Decimal("1.00"):
            raise ValueError("FLCR_WARNING_MULTIPLIER debe ser >= 1.00.")

        if self.nav_quantizer <= Decimal("0"):
            raise ValueError("NAV_QUANTIZER debe ser positivo.")

        if self.alert_queue_max_size <= 0:
            raise ValueError("ALERT_QUEUE_MAX_SIZE debe ser mayor que 0.")

        if self.circuit_breaker_failure_threshold <= 0:
            raise ValueError("CIRCUIT_BREAKER_FAILURE_THRESHOLD debe ser mayor que 0.")

        if self.circuit_breaker_cooldown_seconds <= 0:
            raise ValueError("CIRCUIT_BREAKER_COOLDOWN_SECONDS debe ser mayor que 0.")

        if self.gemini_thinking_level not in VALID_THINKING_LEVELS:
            raise ValueError(
                f"GEMINI_THINKING_LEVEL inválido: {self.gemini_thinking_level!r}. "
                f"Permitidos: {sorted(VALID_THINKING_LEVELS)}"
            )

        if not (0.0 <= self.gemini_temperature <= 2.0):
            raise ValueError("GEMINI_TEMPERATURE debe estar entre 0.0 y 2.0.")

        if not (0 <= self.dashboard_port <= 65535):
            raise ValueError("DASHBOARD_PORT debe estar entre 0 y 65535.")

        if self.dashboard_stale_seconds <= 0:
            raise ValueError("DASHBOARD_STALE_SECONDS debe ser mayor que 0.")

    @property
    def is_standalone(self) -> bool:
        """Indica si opera contra un nodo local Docker (xrpld -a --start)."""
        return self.xrpl_network_mode == "standalone"

    @property
    def has_gemini_credentials(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_telegram_channel(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_settings(env_path: str | Path | None = None, *, override: bool = False) -> Settings:
    """Carga configuración dinámica combinando .env, networks.json y parameters.yaml."""
    target_env = Path(env_path) if env_path else (PROJECT_ROOT / ".env")
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=override)

    networks_cfg = _load_networks()
    params_cfg = _load_parameters()

    xrpl_network = _get_str("XRPL_NETWORK", "testnet").lower()
    net_entry = networks_cfg.get(xrpl_network, {})

    default_ws = net_entry.get("websocket", "wss://s.altnet.rippletest.net:51233")
    default_rpc = net_entry.get("rpc", "https://s.altnet.rippletest.net:51234")

    ws_url = _get_str("XRPL_WS_URL", default_ws)
    rpc_url = _get_str("XRPL_RPC_URL", default_rpc)
    network_mode = _infer_network_mode(ws_url, xrpl_network)

    # Si XRPL_WS_URL apunta a localhost/xrpld y no se forzó XRPL_RPC_URL, alinear RPC local
    if network_mode == "standalone" and not _get_optional_str("XRPL_RPC_URL"):
        standalone_rpc = networks_cfg.get("standalone", {}).get("rpc", "http://localhost:5005")
        rpc_url = standalone_rpc

    thinking_level = _get_str("GEMINI_THINKING_LEVEL", "low").lower()
    log_level = _get_str("LOG_LEVEL", "INFO").upper()

    return Settings(
        app_env=_get_str("APP_ENV", "development").lower(),
        log_level=log_level,
        xrpl_network=xrpl_network,
        xrpl_ws_url=ws_url,
        xrpl_rpc_url=rpc_url,
        xrpl_network_mode=network_mode,
        vault_account_id=_get_optional_str("HERMES_VAULT_ID"),
        loan_broker_id=_get_optional_str("HERMES_LOAN_BROKER_ID"),
        rpc_vault_req_id=_get_int("RPC_VAULT_REQ_ID", 101),
        rpc_loan_broker_req_id=_get_int("RPC_LOAN_BROKER_REQ_ID", 102),
        rpc_request_timeout=_get_float("RPC_REQUEST_TIMEOUT", 10.0),
        ws_reconnect_initial_delay=_get_float("WS_RECONNECT_INITIAL_DELAY", 1.0),
        ws_reconnect_max_delay=_get_float("WS_RECONNECT_MAX_DELAY", 60.0),
        ws_reconnect_backoff_factor=_get_float("WS_RECONNECT_BACKOFF_FACTOR", 2.0),
        flcr_base=_get_decimal("FLCR_BASE", params_cfg.get("flcr_base", "0.10")),
        flcr_warning_multiplier=_get_decimal("FLCR_WARNING_MULTIPLIER", "1.20"),
        max_borrower_share=_get_decimal("MAX_BORROWER_SHARE", params_cfg.get("max_borrower_share", "0.20")),
        max_concentration_hhi=_get_decimal("MAX_CONCENTRATION_HHI", params_cfg.get("max_concentration_hhi", "0.25")),
        nav_quantizer=_get_decimal("NAV_QUANTIZER", "0.000001"),
        vault_permissioned_mask=_get_int("VAULT_PERMISSIONED_MASK", 0x00010000),
        alert_queue_max_size=_get_int("ALERT_QUEUE_MAX_SIZE", 1000),
        circuit_breaker_failure_threshold=_get_int("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5),
        circuit_breaker_cooldown_seconds=_get_float("CIRCUIT_BREAKER_COOLDOWN_SECONDS", 30.0),
        telegram_bot_token=_get_optional_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get_optional_str("TELEGRAM_CHAT_ID"),
        alert_webhook_url=_get_optional_str("ALERT_WEBHOOK_URL"),
        gemini_api_key=_get_optional_str("GEMINI_API_KEY"),
        gemini_model=_get_str("GEMINI_MODEL", "gemini-4-hydrogen"),
        gemini_thinking_level=thinking_level,  # type: ignore[arg-type]
        gemini_temperature=_get_float("GEMINI_TEMPERATURE", 0.1),
        dashboard_enabled=_get_bool("DASHBOARD_ENABLED", True),
        dashboard_host=_get_str("DASHBOARD_HOST", "127.0.0.1"),
        dashboard_port=_get_int("DASHBOARD_PORT", 8080),
        dashboard_stale_seconds=_get_float("DASHBOARD_STALE_SECONDS", 60.0),
    )


settings = load_settings()