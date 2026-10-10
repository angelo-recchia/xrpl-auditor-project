# Especificación Técnica: Monitor de Vencimiento de Préstamos XLS-66 sobre Bóveda X10

## 1. Objetivo
Monitorear de forma automatizada y periódica el vencimiento y estado de amortización de todos los préstamos activos (`Loan` ledger entries) vinculados al `LoanBroker` de la Bóveda X10 (`24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403`) en XRPL Devnet.

## 2. Parámetros de Ledger y Entorno
- **Red:** XRPL Devnet (`https://s.devnet.rippletest.net:51234`).
- **VaultID Canónico:** `24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403`.
- **Cuenta Owner:** `rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj`.
- **Cuenta LoanBroker:** `rhrdyFBNHY4U6ZdoPKfeSFJqcyAsdhHnRV`.
- **Ripple Epoch Offset:** 946684800 segundos (conversión a UTC Unix epoch).

## 3. Lógica de Monitoreo y Fechas
1. Localizar los objetos `Loan` vinculados al `LoanBrokerID` de la Bóveda X10.
2. Extraer campos clave:
   - `LoanSequence`: Índice correlativo del préstamo.
   - `Borrower`: Prestatario asociado.
   - `PrincipalOutstanding`: Principal pendiente en drops.
   - `TotalValueOutstanding`: Deuda total pendiente en drops.
   - `PaymentRemaining`: Cuotas pendientes de abono.
   - `PaymentInterval`: Intervalo de pago en segundos.
   - `NextPaymentDueDate`: Marca temporal de próximo vencimiento en Ripple epoch.
   - `GracePeriod`: Periodo de gracia en segundos.
3. Clasificar estado del préstamo:
   - **AL DÍA:** Fecha actual < `NextPaymentDueDate`.
   - **EN GRACIA:** `NextPaymentDueDate` <= Fecha actual < `NextPaymentDueDate` + `GracePeriod`.
   - **MORA / DEFAULT:** Fecha actual >= `NextPaymentDueDate` + `GracePeriod`.

## 4. Automatización Diaria
- Programación diaria (cron `0 8 * * *` o cada 24h).
- Salida estructurada de alertas e informe de estado.
