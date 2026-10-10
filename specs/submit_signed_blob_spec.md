# Especificación Técnica: Envío de Blobs Firmados a XRPL Devnet (submit_signed_blob)

## 1. Objetivo
Tomar un `tx_blob` en formato hexadecimal resultante de la firma aislada en hardware (Ledger / Tangem / Xaman) y enviarlo al nodo JSON-RPC de XRPL Devnet mediante el comando nativo `submit`.

## 2. Invariante de Seguridad
- El script únicamente transmite un blob ya firmado criptográficamente. No interactúa con claves privadas.

## 3. Salida
- Confirmación del `engine_result` (p. ej. `tesSUCCESS`).
- Hash de la transacción confirmada en el ledger.
