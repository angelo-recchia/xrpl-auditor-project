# Especificación Técnica: Emisión de Préstamos XLS-66 sobre Bóveda X10

## 1. Objetivo
Definir los parámetros de cálculo financiero, validación de liquidez y generación de transacciones `LoanCreate` (XLS-66) sin firmar (`DRAFT_UNSIGNED`) contra la Bóveda XLS-65 "Cold storage X10" en XRPL Devnet.

## 2. Parámetros de Entrada CLI
- `--amount`: Monto del préstamo en XRP (requerido, flotante > 0).
- `--payments`: Número de cuotas/pagos programados (requerido, entero >= 1).
- `--interest`: Tasa de interés nominal anual en porcentaje (requerido, flotante >= 0, p. ej. 5.0 para 5.0% anual = 500 bps).
- `--borrower`: Dirección XRPL del prestatario (opcional, predeterminado: `rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN` o variable de entorno `BORROWER_ADDRESS`).
- `--vault-id`: Identificador de la bóveda (opcional, predeterminado: `24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403`).
- `--duration-days`: Duración total en días (opcional, predeterminado: 30 días por cuota o 90 días para 3 cuotas).

## 3. Modelo Financiero y Amortización Lineal
- **Principal:** `P_drops = amount * 1,000,000` drops.
- **Tasa en bps:** `rate_bps = int(interest * 100)`.
- **Amortización:** Lineal en $N$ períodos iguales.
- **Interés Total:** Cálculo en gotas (drops):
  $$I_{drops} = \frac{P_{drops} \times rate\_bps \times duration\_hours}{10000 \times 365 \times 24}$$
- **Cuota periódica:** Desglose de amortización de principal constante ($P / N$) más intereses devengados por período.

## 4. Validación de Liquidez (XLS-65)
Antes de generar el borrador:
1. Consultar estado en tiempo real de la Bóveda X10 en Devnet.
2. Comprobar que `AssetsAvailable >= P_drops`.
3. Evaluar LTV resultante:
   $$LTV_{bps} = \frac{DebtTotal + P_{drops}}{AssetsTotal} \times 10000$$
4. Estado de liquidez:
   - SALUDABLE: LTV <= 8000 bps (80%) y capacidad disponible restante > 0.
   - ESTRÉS: 8000 bps < LTV <= 9000 bps.
   - CRÍTICO: LTV > 9000 bps o disponible insuficiente.

## 5. Salida de Seguridad (Cold Signing)
- El script no realiza firmas ni solicita claves privadas / semillas bajo ninguna circunstancia.
- Genera un archivo con formato estandarizado `DRAFT_UNSIGNED`:
  `./progress/drafts/loan_create_x10_<timestamp>_DRAFT_UNSIGNED.json`
- Debe incluir contexto del ledger, desglose de pagos, campos de verificación previa a firma externa en hardware (Ledger / Tangem / Xaman) y objeto de transacción `LoanCreate`.
