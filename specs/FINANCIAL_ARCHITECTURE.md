# 🛡️ ESPECIFICACIÓN TÉCNICA DE ARQUITECTURA FINANCIERA Y GESTIÓN DE RIESGOS
## Proyecto Hermes v1.2.0 — Infraestructura de Seguridad y Centinela Off-Chain para Bóvedas XLS-65 / XLS-66 en el XRP Ledger

---

## 1. INTRODUCCIÓN Y MARCO TEÓRICO

El **Proyecto Hermes v1.2.0** es una capa de seguridad y auditoría en tiempo real diseñada para el ecosistema de finanzas descentralizadas (DeFi) sobre el XRP Ledger. Se integra directamente con los estándares **XLS-65 (Single Asset Vaults)** y **XLS-66 (Native Lending Protocol)**.

Mientras que la capa base del XRP Ledger ejecuta transacciones de forma determinista y reactiva, Hermes actúa como un **Centinela Off-Chain de Cero Confianza (*Zero-Trust Sentinel*)**. Su objetivo es mitigar el riesgo sistémico de insolvencia, la concentración crediticia no diversificada y el contagio de pérdidas en las bóvedas de liquidez mediante la evaluación continua bloque a bloque y la ejecución preventiva de medidas de contención.

---

## 2. MODELADO MATEMÁTICO DE RIESGO CREDITICIO Y CONCENTRACIÓN

El motor de reglas en `evaluators/rules.py` traduce datos crudos del libro de contabilidad (obtenidos vía RPC asíncrono en `core/ledger_client.py`) en métricas cuantitativas financieras.

### 2.1. Índice de Cobertura de Primera Pérdida (FLCR)
El *First-Loss Capital Ratio* ($\text{FLCR}$) mide el margen de solvencia aportado por el gestor o los inversores de riesgo respecto al total de la liquidez expuesta:

$$\text{FLCR} = \frac{C_{\text{Junior}}}{L_{\text{Total Exposición}}} \times 100$$

Donde:
- $C_{\text{Junior}}$ es el capital aportado en la capa de primera pérdida.
- $L_{\text{Total Exposición}}$ es la suma del crédito emitido más los compromisos pendientes en XLS-66.

### 2.2. Penalización por Concentración (Herfindahl-Hirschman Index - HHI)
Para evitar que un solo prestatario acumule un porcentaje peligroso de la liquidez de la Bóveda XLS-65, Hermes calcula el índice HHI modificado ($\theta_i$):

$$HHI = \sum_{i=1}^{N} \left( \frac{s_i}{S} \right)^2$$

Donde $s_i$ representa la exposición al prestatario $i$ y $S$ es el total de la cartera de crédito. Si $HHI > 0.18$, la cartera se clasifica como *altamente concentrada*, lo que activa un factor de penalización dinámico que ajusta a la baja el límite de endeudamiento permitido ($L_{i,k}^{\max}$).

### 2.3. Valor en Riesgo ($\text{VaR}_{99\%}$)
El motor evalúa el riesgo de cola aplicando una estimación de Valor en Riesgo no paramétrica basada en la volatilidad histórica del activo subyacente y la tasa de morosidad esperada:

$$\text{VaR}_{99\%} = \mu_{\text{pérdida}} + z_{0.99} \cdot \sigma_{\text{pérdida}}$$

---

## 3. CASCADA DE TRAMOS Y JERARQUÍA DE ABSORCIÓN DE PÉRDIDAS

Las Bóvedas XLS-65 y los protocolos XLS-66 estructuran el capital en una jerarquía estricta de tramos (*Tranche Waterfall*) para delimitar la responsabilidad financiera y proteger a los depositantes ordinarios:

### 3.1. Tramo Senior (Inversores Institucionales y Minoristas Pasivos)
- **Prioridad de Reclamación:** Primera posición en flujo de retornos y devoluciones.
- **Exposición a Pérdidas:** Protegido contra impagos ordinarios por el colchón junior.
- **Rendimiento:** Tasa fija o referenciada preferente con menor volatilidad.

### 3.2. Tramo Mezzanine (Colchón de Estabilización Opcional)
- **Prioridad de Reclamación:** Subordinada al tramo Senior, preferente al Junior.
- **Función:** Amortiguador dinámico activable ante estrés moderado en el mercado.

### 3.3. Tramo Junior / First-Loss Capital (Loan Broker y Operador de Bóveda)
- **Prioridad de Reclamación:** Última posición en orden de cobro.
- **Exposición a Pérdidas:** Absorbe el 100% de los impagos de los préstamos XLS-66 hasta agotar su capital.
- **Compromiso Mínimo:** Obligación de mantener un $\text{FLCR} \ge 10\%$ respecto al total prestado.

---

## 4. MATRIZ DE RIESGO Y UMBRALES ESCALONADOS (SEMÁFORO SENTINEL)

De acuerdo con `config/parameters.yaml`, Hermes clasifica el estado de la bóveda en cuatro niveles operativos:

| Nivel | Rango FLCR | Acción Operativa Recomendada | Mecanismo de Alerta |
| :--- | :--- | :--- | :--- |
| **VERDE** | $\text{FLCR} \ge 12\%$ | Monitoreo estándar cada bloque (3-5s). Sin riesgo aparente. | Registro de telemetría pasivo. |
| **AMARILLO** | $10\% \le \text{FLCR} < 12\%$ | Desviación leve. Reducción de latencia de sondeo RPC. | Notificación informativa a la consola. |
| **NARANJA** | $8\% \le \text{FLCR} < 10\%$ | Estrés moderado. Requerimiento de inyección de capital junior o pausa voluntaria. | Alerta preventiva push a Telegram. |
| **ROJO** | $\text{FLCR} < 8\%$ | **CRÍTICO:** Perforación del límite de seguridad. Disparo de protocolo de emergencia. | Alerta Telegram + Borrador Multi-sig `FREEZE_CREDIT`. |

### Regla Adicional de Concentración Individual
- **Cuota Máxima por Prestatario:** Ningún prestatario puede exceder el $20\%$ (`max_borrower_share = 0.20`) del total de la cartera activa.
- **Acción ante Infracción:** Emisión inmediata de alerta de sobreconcentración independientemente del nivel global de FLCR.

---

## 5. PROTOCOLO DE CONTENCIÓN Y MITIGACIÓN (ACCIONES MULTI-SIG)

Cuando se detecta una condición **ROJA**, el módulo `actions/multisig_builder.py` genera un borrador de transacción de emergencia sin firmar (`DRAFT_UNSIGNED`):

1. **Tipo de Transacción:** `AccountSet` con memo institucional estructurado (`4865726d6573456d657267656e6379`).
2. **Acción de Emergencia:** `FREEZE_CREDIT` (bloqueo cautelar de emisión de nuevos préstamos).
3. **Seguridad y Cero Confianza:** El centinela jamás almacena ni manipula claves privadas. El payload se genera con `SigningPubKey: ""` para que el quórum multi-sig del Loan Broker lo apruebe y firme en frío mediante dispositivos aislados (Ledger Nano S Plus / Xaman).

---

## 6. TELEMETRÍA Y ANCLAJE CRIPTOGRÁFICO DE AUDITORÍA

Para garantizar la transparencia ante depositantes Senior y supervisores:

1. **Hash de Telemetría SHA-256 (`crypto_anchor.py`):** Cada estado de auditoría genera una huella digital determinista e inmutable.
2. **Sello Criptográfico HMAC-SHA256:** Certifica que el análisis fue emitido por el Centinela Hermes autorizado (`VERIFIED_BY_SENTINEL`).
3. **Verificación de Integridad de Frontend (`ui_verifier.py`):** Previene ataques Man-in-the-Middle (MiTM) comparando los valores renderizados en la dApp web con los datos On-Chain reales consultados vía RPC.
4. **Anclaje On-Chain:** La huella maestra consolidada (`MANIFEST.sha256`) puede sellarse en el Ledger mediante un campo `MemoData` en una transacción estándar, garantizando procedencia y autoría temporal inmutable.
