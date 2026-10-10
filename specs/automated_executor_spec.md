# Especificación Técnica: Ejecutor Automatizado con Regular Key Delegada

## 1. Objetivo
Permitir la ejecución autónoma y desatendida de transacciones rutinarias (`VaultDeposit`, `LoanPayment`) en XRPL Devnet empleando la Regular Key delegada, preservando la clave maestra en frío.

## 2. Flujo Operativo
1. Cargar las credenciales de la Regular Key desde `./progress/bot_keys/regular_key_bot.json`.
2. Verificar en el ledger si la cuenta principal (`Account`) tiene activada la `RegularKey` correspondiente (mediante `account_info`).
   - Si no está activada: Detener ejecución y notificar que se requiere la firma única del borrador `SetRegularKey`.
   - Si está activada: Proceder con la firma mediante la Regular Key delegada.
3. Construir la transacción con:
   - `Account`: Cuenta principal.
   - `SigningPubKey`: Clave pública de la Regular Key.
   - `TxnSignature`: Firma calculada con la clave privada de la Regular Key.
4. Serializar a `tx_blob` y enviar vía `submit`.
