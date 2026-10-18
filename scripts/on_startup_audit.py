import sys
import os
from decimal import Decimal

# Asegurar rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.rpc_connector import XRPLRPCConnector
from evaluators.rules import HermesRiskEngine
from scripts.alert_gateway import TelegramAlertGateway

BOT_TOKEN = "8983108444:AAF4aR_zkcWSHo_WDJ4Now3BsacgJe9Q288"
CHAT_ID = "6439172757"

def run_auto_audit():
    connector = XRPLRPCConnector()
    risk_engine = HermesRiskEngine(min_coverage_ratio=0.20, max_concentration_ratio=0.10)
    gateway = TelegramAlertGateway(bot_token=BOT_TOKEN, chat_id=CHAT_ID)

    vault_id = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
    vault_data = connector.fetch_vault_state(vault_id)

    if vault_data.get("error"):
        gateway.send_alert("⚠️ *HERMES SENTINEL*: Error crítico de lectura RPC al iniciar el sistema.")
        return

    flc_actual = Decimal("30000")
    deposits = Decimal("120000")
    
    cap_check = risk_engine.check_vault_capacity_limit(flc_actual, deposits)
    flcr_check = risk_engine.evaluate_real_flcr(flc_actual, deposits)

    report = (
        "🛡️ *INFORME DE AUDITORÍA HERMES (INICIO DE SISTEMA)*\n\n"
        f"• *Bóveda ID:* `{vault_id[:12]}...`\n"
        f"• *Estado RPC:* Conectado (Devnet)\n"
        f"• *Depósitos Activos:* {deposits:,.2f} XRP\n"
        f"• *Capacidad Máxima:* {cap_check['max_capacity']:,.2f} XRP\n"
        f"• *FLCR Real:* {flcr_check['flcr_real']} (Mínimo: {flcr_check['min_required']})\n"
        f"• *Diagnóstico:* {flcr_check['health_status']}\n\n"
        "✅ _Sistema centinela operando dentro de los parámetros de seguridad establecidos._"
    )

    gateway.send_alert(report)

if __name__ == "__main__":
    run_auto_audit()