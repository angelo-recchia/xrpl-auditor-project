# Especificación Técnica: Consulta de Estado de Bóveda X10 (XLS-65 / XLS-66)

## 1. Objetivo
Definir la arquitectura, parámetros de entrada, flujo de consulta y validación técnica para inspeccionar el estado en vivo de la Bóveda "Cold storage X10" (XLS-65 Single Asset Vault y LoanBroker XLS-66 asociado) desplegada en la red XRPL Devnet.

## 2. Entorno y Parámetros de Red
- **Red:** XRPL Devnet.
- **Endpoint RPC predeterminado:** `https://s.devnet.rippletest.net:51234` (configurable vía variable de entorno `XRPL_DEVNET_RPC_URL`).
- **Endpoint WebSocket alternativo:** `wss://s.devnet.rippletest.net:51233` (configurable vía `XRPL_DEVNET_WS_URL`).
- **Seguridad en Credenciales:** El script es estrictamente de solo lectura (read-only); no maneja, solicita ni almacena claves privadas ni frases semilla.

## 3. Identificadores de la Bóveda X10
- **Nombre de la Bóveda:** "Cold storage X10"
- **VaultID (Índice de Ledger):** `24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403` (configurable vía variable de entorno `XRPL_VAULT_ID`).
- **Cuenta Propietaria / Operador:** `rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj` (configurable vía variable de entorno `XRPL_VAULT_OWNER`).

## 4. Estructura de Datos en el Ledger

### 4.1. Entrada de Bóveda (`Vault`)
- `LedgerEntryType`: `Vault`
- `index`: VaultID (`24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403`)
- `Owner`: Dirección del propietario de la bóveda
- `Account`: Cuenta técnica de la bóveda
- `Asset`: Objeto de activo (p. ej. `{"currency": "XRP"}`)
- `AssetsTotal`: Total de activos custodiados en la bóveda (en drops si es XRP)
- `AssetsAvailable`: Activos disponibles para retiro o emisión de préstamos
- `Data`: Metadatos codificados en formato hexadecimal (contiene JSON con nombre y atributos descriptivos)
- `ShareMPTID`: Identificador de emisión de MPToken asociado a los shares
- `WithdrawalPolicy`: Política de retiro (1 = FCFS / First-come, first-served)

### 4.2. Broker de Préstamos Asociado (`LoanBroker` - XLS-66)
- `LedgerEntryType`: `LoanBroker`
- `VaultID`: Vinculado al VaultID de la bóveda
- `DebtTotal`: Deuda total emitida/activa
- `DebtMaximum`: Límite máximo de deuda permitida
- `CoverAvailable`: Cobertura/garantía disponible
- `LoanSequence`: Secuencia de préstamos emitidos

## 5. Lógica de Consulta y Verificación
1. **Conexión:** Inicializar cliente RPC hacia Devnet.
2. **Consulta Primaria (Ledger Entry):** Consultar el objeto ledger mediante el método `ledger_entry` con el `index` de la bóveda.
3. **Consulta Secundaria (Account Objects):** Consultar los objetos de cuenta asociados al propietario (`account_objects`) para identificar brokers de préstamo (`LoanBroker`) o tokens (`MPToken`).
4. **Decodificación de Metadatos:** Si el campo `Data` contiene un valor en hexadecimal, convertirlo a texto legible UTF-8 / JSON.
5. **Cálculo de Métricas:**
   - Balance total y disponible en XRP (drops / 1,000,000).
   - Deuda activa en préstamos (DebtTotal).
   - Ratio de Utilización: `(AssetsTotal - AssetsAvailable) / AssetsTotal * 100` o `(DebtTotal / AssetsTotal) * 100`.
   - Estado de Liquidez: SALUDABLE, ESTRÉS o CRÍTICO según límites de LTV y capacidad disponible.
6. **Formato de Salida:** Salida concisa en consola y exportación opcional de resumen en JSON.
