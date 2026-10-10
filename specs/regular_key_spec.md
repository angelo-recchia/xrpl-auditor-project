# Especificación Técnica: Configuración de Regular Key Delegada (XLS-65 / Devnet)

## 1. Objetivo
Permitir la automatización de transacciones rutinarias en XRPL Devnet sin exponer la clave maestra de la cuenta principal (`rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj`), implementando el estándar nativo de Regular Key delegada.

## 2. Arquitectura de Seguridad
- **Clave Maestra (Cold):** Permanece en hardware wallet (Ledger / Tangem / Xaman). Solo se utiliza UNA VEZ para autorizar la Regular Key.
- **Regular Key (Bot / Automation):** Par de claves criptográfico secundario generado exclusivamente para operaciones automatizadas en Devnet.
- **Revocabilidad Inmediata:** Si la Regular Key se ve comprometida, la clave maestra puede deshabilitarla o rotarla con una transacción `SetRegularKey` en blanco.

## 3. Especificación de la Transacción SetRegularKey
- `TransactionType`: `SetRegularKey`
- `Account`: Cuenta principal (`rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj`).
- `RegularKey`: Dirección pública (`r...`) de la Regular Key delegada.
- `Fee`: Tarifa base en drops (1000 drops).
- `Sequence`: Secuencia actual de la cuenta principal.
- `NetworkID`: 2 (Devnet).

## 4. Salida
- Borrador `set_regular_key_<timestamp>_DRAFT_UNSIGNED.json` en `./progress/drafts/` para firma en frío por la cuenta principal.
- Archivo de configuración local para la Regular Key delegada (solo dirección pública y clave secundaria de prueba Devnet).
