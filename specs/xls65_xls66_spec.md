# Especificación Técnica: Enmiendas XLS-65 y XLS-66

## 1. Objetivo de la Auditoría
Validar la lógica de funcionamiento, el manejo de estados y la seguridad de las transacciones asociadas a las enmiendas XLS-65 (Protocolo de Préstamos / Lending) y XLS-66 (Single Asset Vaults - SAV) en entornos de prueba del XRPL.

## 2. Alcance XLS-65 (Lending Protocol)
- **Acuerdos de Crédito:** Verificación de la creación, modificación y cancelación de términos de préstamo nativos.
- **Gestión de Liquidez:** Auditoría de la aportación de capital por parte de los prestamistas y la retirada de fondos con intereses acumulados.
- **Control de Riesgos:** Comprobación de las condiciones de liquidación y garantías asociadas.

## 3. Alcance XLS-66 (Single Asset Vaults - SAV)
- **Depósitos y Reembolsos:** Validación de la operativa de depósito de un único activo digital y emisión de tokens de participación en la bóveda.
- **Estrategias Automatizadas:** Análisis de la ejecución de rendimientos y comisiones configuradas en la bóveda de activo único.
- **Manejo de Errores:** Comprobación del comportamiento del contrato/ledger ante fondos insuficientes o estados de bloqueo.

## 4. Criterios de Éxito (Verificación)
- Ninguna transacción de prueba debe superar los límites de gas/comisión estándar sin una razón justificada.
- Todos los scripts de la carpeta `evaluator/` deben arrojar un resultado exitoso (`PASS`) antes de considerar cualquier lógica apta para su despliegue en Testnet.