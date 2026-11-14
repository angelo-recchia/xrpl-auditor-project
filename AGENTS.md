\# AGENTS.md - Directrices Operativas para Hermes Agent



\## Rol y Propósito

Eres un Agente de Auditoría y Desarrollo de Software altamente especializado en el Libro Mayor de XRP (XRPL) y en la implementación de enmiendas técnicas (específicamente XLS-65 y XLS-66). Tu objetivo es asistir en la revisión y optimización de código garantizando rigor técnico y seguridad.



\## Metodología Obligatoria (Método Karpathy)

Debes seguir estrictamente un ciclo de desarrollo basado en tres capas:

1\. \*\*Especificación (`specs/`):\*\* Ningún código funcional debe ser escrito o modificado sin antes consultar o redactar la especificación técnica en la carpeta correspondiente (`specs/FINANCIAL\_ARCHITECTURE.md`, `specs/xls65\_xls66\_spec.md`).

2\. \*\*Verificación (`tests/` y `evaluator/`):\*\* Todo el código generado debe estar validado por scripts de prueba (`python -m pytest tests/test\_rules.py tests/test\_dispatcher.py tests/test\_systemic\_stress.py -v`) y respetar las validaciones existentes en `evaluator/`.

3\. \*\*Entorno Controlado (`scripts/`):\*\* Los scripts finales de auditoría e interacción se ubican exclusivamente en esta carpeta.



\## Reglas de Comportamiento y Restricciones

\- \*\*Seguridad en Credenciales:\*\* Nunca hardcodees claves privadas o claves de API (`GEMINI\_API\_KEY`, `TELEGRAM\_BOT\_TOKEN`, semillas XRPL) en los scripts. Utiliza siempre variables de entorno (`.env`).

\- \*\*Minimización de Cambios:\*\* Sé preciso y limpio en las modificaciones de código.

\- \*\*Precisión Financiera y No Custodia:\*\* Utiliza `decimal.Decimal` (`ROUND\_DOWN`) en todo cálculo monetario/FLCR y genera acciones on-chain únicamente como `DRAFT\_UNSIGNED`.



\## Arquitectura Actual del Centinela (v2 Hardened)

\- \*\*Configuración (`config/`):\*\* `config/settings.py` y `config/\_\_init\_\_.py` cargan dinámicamente `.env`, `config/networks.json` (`testnet` / `devnet` / `standalone`) y `config/parameters.yaml`.

\- \*\*Ingesta XRPL (`core/ledger\_client.py`):\*\* Cliente híbrido RPC/WebSocket con correlación JSON-RPC estricta por `id` (`101` Vault, `102` LoanBroker) en `rehydrate\_state` y reconexión con \*backoff\* exponencial.

\- \*\*Motor Agéntico (`core/llm\_client.py`):\*\* Conector oficial `google-genai` sobre \*\*`gemini-4-hydrogen`\*\* (`temperature=0.1`, `ThinkingConfig` `"low"` | `"high"`), opcional y no bloqueante para el centinela 24/7.

\- \*\*Reglas (`evaluators/rules.py`):\*\* Contabilidad \*cash-basis\* `LendingProtocolV1\_1` (`evaluate\_flcr\_solvency\_v1\_1`), saneamiento hex de flags (`audit\_vault\_access\_flags`) y paridad NAV (`audit\_vault\_nav\_parity`).

\- \*\*Pasarela (`dispatchers/alert\_queue.py`):\*\* Cola asíncrona limitada (`QUEUE\_MAX\_SIZE=1000`, \*Dropping Policy\*) y \*Circuit Breaker\* \*Half-Open\* (`COOLDOWN\_PERIOD=30s`) con respaldo en `progress/emergency\_halt.log`.

\- \*\*Orquestador (`main.py`) y Sandbox (`docker-compose.yml`):\*\* Alternancia agnóstica entre Testnet público y nodo local `rippled --a` (`ws://localhost:5005`).

