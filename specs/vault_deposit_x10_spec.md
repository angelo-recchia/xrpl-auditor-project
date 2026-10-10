# Especificación Técnica: Depósito en Bóveda XLS-65 (VaultDeposit) sobre Bóveda X10

## 1. Objetivo
Generar borradores seguros sin firmar (`DRAFT_UNSIGNED`) para la operación `VaultDeposit` de la enmienda XLS-65 sobre la Bóveda X10 en XRPL Devnet, e inspeccionar el estado contable y de saldos de las carteras depositantes mediante la bandera `--wallet-info`.

## 2. Reglas Estrictas de Seguridad y Política Anti-Bypass
- NUNCA manejar, cargar ni solicitar semillas (`seed`), claves privadas o frases de recuperación en código caliente (`Wallet.from_seed`).
- No existen mecanismos de bypass (`--devnet-bypass`, `--force-sign`, etc.): toda bandera o intento de evadir la firma en frío es interceptada y rechazada inmediatamente.
- Toda operación de firma se realiza exclusivamente en frío mediante hardware externo (Ledger Nano S Plus / Tangem / Xaman).
- Salida obligatoria: archivo JSON en `./progress/drafts/<descriptor>_DRAFT_UNSIGNED.json`.

## 3. Especificación de la Transacción XLS-65 (VaultDeposit)
- `TransactionType`: `VaultDeposit`
- `Account`: Cuenta pública del depositante (r...).
- `VaultID`: `24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403`.
- `Amount`: Monto en drops (1 XRP = 1,000,000 drops).
- `Fee`: Tarifa de red estimada en drops.
- `Sequence`: Secuencia de la cuenta depositante.
- `NetworkID`: 2 (Devnet).

## 4. Inspección de Cartera (`--wallet-info`)
- Consultar `account_info` y `account_objects` en el endpoint RPC activo.
- Presentar:
  - Dirección pública evaluada.
  - Saldo total y saldo disponible en XRP (restando reserva base de 10 XRP + reservas por objetos).
  - Secuencia actual de la cuenta.
  - Tenencia de tokens MPT/Shares de la Bóveda X10 (`0000000150A0473ED67EC32DF4A1F42BA35CC9882344EF38`).
  - Estado de activación en el Ledger.
