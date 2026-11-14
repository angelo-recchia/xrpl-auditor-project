import os
import time
import requests
from pathlib import Path
from decimal import Decimal

# Intentar cargar dotenv si está disponible para asegurar lectura automática del .env local
try:
    from dotenv import load_dotenv
    # Buscar el archivo .env en la raíz del proyecto
    env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass  # Si no está instalado, se confía en las variables de entorno del sistema

class TelegramDispatcher:
    def __init__(self, strict_mode: bool = True):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        # Capa 1: Validación estricta de arranque (Fail-Fast)
        if not self.token or not self.chat_id:
            error_msg = (
                "[FATAL] Credenciales de Telegram (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) "
                "no encontradas en el entorno ni en el archivo .env."
            )
            if strict_mode:
                raise EnvironmentError(error_msg)
            else:
                print(f"[!] {error_msg} Las alertas vía Telegram están DESACTIVADAS.")
                self.active = False
        else:
            self.active = True
            self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def dispatch_alert(self, level: str, message: str, max_retries: int = 3) -> bool:
        """
        Despacha una alerta crítica con reintentos exponenciales y fallback local de emergencia.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": f"🚨 [HERMES SENTINEL — NIVEL: {level.upper()}] 🚨\n\n{message}",
            "parse_mode": "Markdown"
        }

        if not self.active:
            self._trigger_emergency_fallback(level, message, "Telegram no inicializado (Credenciales ausentes)")
            return False

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(self.api_url, json=payload, timeout=5)
                if response.status_code == 200:
                    print(f"[TELEGRAM] Alerta de nivel {level} despachada con éxito.")
                    return True
                else:
                    print(f"[TELEGRAM] Intento {attempt}/{max_retries} fallido. Código HTTP: {response.status_code}")
            except Exception as e:
                print(f"[TELEGRAM] Error de red en intento {attempt}/{max_retries}: {e}")
            
            # Espera exponencial antes del siguiente reintento
            time.sleep(2 ** attempt)

        # Si se agotan los reintentos, activar protocolo de emergencia local
        self._trigger_emergency_fallback(level, message, "Agotados los reintentos de conexión con la API de Telegram")
        return False

    def _trigger_emergency_fallback(self, level: str, message: str, reason: str):
        """
        Escribe de forma síncrona y atómica un registro de parada de emergencia local 
        si la red o Telegram fallan durante una condición crítica (ej. Rojo).
        """
        log_dir = Path("progress")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "emergency_halt.log"
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        log_entry = (
            f"====================================================\n"
            f"TIMESTAMP (UTC): {timestamp}\n"
            f"ESTADO CRÍTICO: NIVEL {level.upper()}\n"
            f"FALLO DE DESPACHO: {reason}\n"
            f"MENSAJE ORIGINAL:\n{message}\n"
            f"ACCIÓN DEL SISTEMA: Bloqueo preventivo local activado.\n"
            f"====================================================\n\n"
        )
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        print(f"[CRITICAL] Fallo de pasarela registrado en persistencia local: {log_file}")
