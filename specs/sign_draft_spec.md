# Especificación Técnica: Gestor de Borradores y Firma en Frío (sign_draft)

## 1. Objetivo
Procesar borradores `_DRAFT_UNSIGNED.json`, validar los campos requeridos para la verificación física en hardware wallet (Ledger / Tangem / Xaman), calcular el hash canónico de firma binaria (`SigningHash`) y preparar la entrega aislada para firma offline.

## 2. Invariante de Seguridad
- El script no contiene ni solicita claves maestras.
- La bandera `--devnet-sign` o intentos de firma en caliente por software quedan expresamente bloqueados para la cuenta principal, derivando al flujo de firma en hardware o enlace Xaman.

## 3. Salida y Verificación
- Presentar en pantalla los valores exactos a cotejar en la pantalla del dispositivo físico:
  - Tipo de transacción (`TransactionType`)
  - Cuenta origen (`Account`)
  - Parámetros clave (`RegularKey`, `Amount`, `VaultID`, etc.)
  - `Fee`, `Sequence`, `NetworkID` (Devnet = 2)
  - `SigningHash` (Hash SHA-512Half del prefijo de firma binario).
- Generación opcional de payload JSON puro para importación en herramientas offline.
