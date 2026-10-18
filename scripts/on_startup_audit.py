import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")

def main():
    print("Iniciando auditoria de arranque...")
    if TELEGRAM_BOT_TOKEN == "TU_TOKEN_AQUI":
        print("Aviso: TELEGRAM_BOT_TOKEN no configurado en entorno local.")
    else:
        print("Token de Telegram detectado correctamente.")

if __name__ == "__main__":
    main()

