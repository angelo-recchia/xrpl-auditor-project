# Especificación Técnica: Automatización de Pagos XLS-66 (LoanPayment) sobre Bóveda X10

## 1. Objetivo
Definir la arquitectura, parámetros de transacción y flujo de generación de borradores `DRAFT_UNSIGNED` para operaciones de amortización y pago de cuotas (`LoanPayment`) sobre la Bóveda X10 y su LoanBroker XLS-66 en XRPL Devnet.

## 2. Parámetros de Entorno y Red
- **Red:** XRPL Devnet (`https://s.devnet.rippletest.net:51234`).
- **VaultID Canónico:** `24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403` (64 caracteres hex, configurable vía `VAULT_ID`).
- **Prestatario (Borrower/Payer):** Configurable vía `BORROWER_ADDRESS`, predeterminado `rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN`.
- **Operador/Owner de Bóveda:** `rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj`.
- **Seguridad:** Generación estricta de borradores JSON sin firmar (`DRAFT_UNSIGNED`) en `./progress/drafts/`. Cero manejo de claves privadas.

## 3. Estructura de la Transacción LoanPayment (XLS-66)
- `TransactionType`: `LoanPayment`
- `Account`: Cuenta del prestatario que efectúa el pago.
- `VaultID`: Identificador canónico de la bóveda XLS-65 asociada.
- `Amount`: Monto a amortizar (en drops si es XRP).
- `PaymentType`: Pago ordinario de cuota / amortización anticipada.
- `Fee`: Tarifa de red estimada en drops.
- `Sequence`: Secuencia de la cuenta pagadora.
- `NetworkID`: Identificador de red (Devnet = 2).

## 4. Salida
- Archivo JSON en `./progress/drafts/auto_payment_x10_<timestamp>_DRAFT_UNSIGNED.json`.
- Estado de firma: `PENDING` (firma obligatoria en frío en Ledger/Tangem/Xaman).
