import os
import aiohttp
import asyncio

async def send_telegram_alert(message: str) -> bool:
    """
    Envía una alerta push en tiempo real a través de Telegram Bot API.
    Requiere las variables de entorno TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("[!] Aviso: Credenciales de Telegram no detectadas en el entorno (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🚨 [PROYECTO HERMES - SENTINEL ALERT]\n\n{message}",
        "parse_mode": "Markdown"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    print("[+] Alerta push enviada a Telegram con éxito.")
                    return True
                else:
                    error_text = await response.text()
                    print(f"[!] Error en la API de Telegram: {error_text}")
                    return False
    except Exception as e:
        print(f"[!] Excepción al conectar con Telegram: {e}")
        return False

if __name__ == "__main__":
    # Prueba rápida del notificador
    asyncio.run(send_telegram_alert("Prueba de conectividad del Sentinel Hermes v1.2.0."))
