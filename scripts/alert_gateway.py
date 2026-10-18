"""
Módulo: scripts/alert_gateway.py
Proyecto: Hermes (XRPL XLS-65/66)
Descripción: Pasarela de notificaciones y alertas institucionales (Telegram Gateway).
             Permite el envío pasivo y seguro de reportes de auditoría y centinela.
"""

from typing import Any, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class TelegramAlertGateway:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10):
        """
        Inicializa la pasarela de alertas de Telegram.
        """
        self.bot_token = bot_token.strip() if bot_token else ""
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.timeout = timeout

        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def send_alert(self, message: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
        """
        Envía un mensaje de alerta formateado a través del bot de Telegram.
        Si el token es un placeholder o la red no responde, registra el reporte en consola
        y retorna el estado sin interrumpir la ejecución del sistema.
        """
        print("\n[TelegramAlertGateway] Enviando reporte de auditoría:")
        print("-" * 50)
        print(message)
        print("-" * 50)

        # Validación de token placeholder / no configurado
        if not self.bot_token or "***" in self.bot_token or not self.chat_id:
            msg = "Token de bot o chat_id no configurado o contiene placeholders (***). Envío omitido."
            print(f"[TelegramAlertGateway] [AVISO] {msg}")
            return {
                "success": False,
                "sent": False,
                "message": msg
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp_data = resp.json()
            if resp.status_code == 200 and resp_data.get("ok"):
                print("[TelegramAlertGateway] [OK] Alerta entregada exitosamente en Telegram.")
                return {
                    "success": True,
                    "sent": True,
                    "result": resp_data.get("result")
                }
            else:
                error_desc = resp_data.get("description", resp.text)
                print(f"[TelegramAlertGateway] [ERROR] Telegram API: {error_desc}")
                return {
                    "success": False,
                    "sent": False,
                    "status_code": resp.status_code,
                    "message": error_desc
                }
        except Exception as e:
            print(f"[TelegramAlertGateway] [EXCEPCIÓN] Fallo de conexión con Telegram: {str(e)}")
            return {
                "success": False,
                "sent": False,
                "message": str(e)
            }
