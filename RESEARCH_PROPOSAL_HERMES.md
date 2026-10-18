# RESEARCH PROPOSAL: PROJECT HERMES
## Institutional Off-Chain Risk Sentinel & Multi-Layer Audit Architecture for XLS-65 and XLS-66 Protocols on the XRP Ledger

---

### 1. Title & Abstract (Resumen Ejecutivo)

* **Project Title:** Project Hermes: Off-Chain Risk Monitoring & Deterministic Audit Architecture for XLS-65/66 Lending Protocols.
* **Target Standards:** XLS-65 (Single Asset Vaults - SAV) and XLS-66 (Uncollateralized Lending / Savings Vaults).
* **Keywords:** XRPL, XLS-65, XLS-66, First-Loss Capital Ratio (FLCR), Off-Chain Sentinel, Automated UI Auditing, Deterministic Risk Evaluation.

#### Executive Abstract
The integration of decentralized credit mechanisms via the XLS-65 (Single Asset Vaults) and XLS-66 (Uncollateralized Lending) standards marks a structural evolution for institutional DeFi on the XRP Ledger (XRPL). However, while on-chain smart contracts enforce transaction execution and state changes deterministically, they cannot natively monitor off-chain operational risks, Loan Broker solvency margins, borrower concentration limits, or visual presentation mismatches across user interfaces (dApps).

Project Hermes addresses this structural risk gap by introducing an open-source, hybrid off-chain audit sentinel designed to protect liquidity providers and institutional depositors. Hermes operates via a two-layer verification architecture:
1. **On-Chain State Auditing (Passive Sentinel):** A high-throughput WebSocket/RPC listener that continuously calculates the First-Loss Capital Ratio (FLCR) and credit concentration metrics against predefined risk evaluators (`evaluators/rules.py`).
2. **Visual & Operational Consistency Verification (Active Sentinel):** An automated browser instance powered by Playwright and lightweight AI classification (`gemini-3.8-flash`) that verifies whether front-end dApp interfaces accurately reflect real-time on-chain parameters.

By combining deterministic RPC state extraction with automated UI audits and instant webhook alerts, Hermes establishes a standardized, auditable risk management framework for XRPL lending protocols, fostering institutional trust, capital safety, and systemic stability across the ecosystem.

---

### 2. Problem Statement (Laguna de Riesgo en XLS-65/66)

The XLS-65 and XLS-66 standards introduce native mechanisms for single-asset yield generation and uncollateralized lending pools on the XRP Ledger. While these protocols enforce strict state transitions on-chain, they inherently rely on off-chain actors (Loan Brokers, Vault Managers, and Liquidity Aggregators) for risk assessment, parameter updates, and user interaction.

This architecture introduces three critical systemic risks that cannot be mitigated solely through on-chain code:

1. **First-Loss Capital Buffer Depletion (FLCR Risk):**
   In XLS-66 lending markets, the Loan Broker provides a First-Loss Capital tranche to absorb initial defaults. If market volatility or default cascades cause the First-Loss Capital Ratio (FLCR) to drop below safety thresholds without immediate protocol pauses or alerts, depositors bear unmitigated downside risk.
2. **Unmonitored Credit Concentration:**
   On-chain specifications do not inherently restrict a Loan Broker from over-exposing vault capital to a small cluster of borrowers. Without continuous off-chain aggregation of active loans across multiple ledger sequences, hidden concentration risk remains undetected.
3. **Front-End / On-Chain State Desynchronization:**
   DeFi users interact with protocols via web dApps. Malicious, misconfigured, or cached front-end interfaces can display outdated yield rates, inaccurate FLCR metrics, or misrepresent liquidity depth. On-chain validation cannot prevent a dApp interface from misleading users if the UI fails to reflect actual ledger state.

---

### 3. Research Objectives & Methodology (Arquitectura Híbrida)

Project Hermes resolves these vulnerabilities through a Hybrid Off-Chain Audit Model combining low-latency state extraction, rule-based risk evaluation, and automated visual verification.

#### A. Layer 1: Passive On-Chain Monitoring Engine
* **Protocol Direct Connection:** Connects via WebSocket/RPC to XRPL nodes (Mainnet/Testnet/Devnet) listening to `ledger` streams and account state objects related to XLS-65 Vaults and XLS-66 Loan Brokers.
* **Mathematical Risk Evaluator (`evaluators/rules.py`):** Calculates critical risk metrics deterministically at every ledger close (e.g., First-Loss Capital Ratio). If FLCR falls below minimum safety thresholds, or single-borrower concentration exceeds maximum risk limits, the engine triggers an immediate alert.

#### B. Layer 2: Active Visual & UI Audit Engine
* **Automated Browser Instance (Playwright):** Launches headless browser sessions targeting active dApp front-ends hosting XLS-65/66 vaults.
* **Cross-Verification with Ledger Data:** Scrapes displayed UI values (e.g., APY, total deposited, FLCR percentage) and compares them against raw ledger data extracted in Layer 1.
* **Lightweight Multimodal Classification (`gemini-3.8-flash`):** Evaluates visual discrepancies, UI layout shifts, or hidden risk disclosures to detect front-end spoofing, outdated UI states, or misleading information.

---

### 4. Technical Design & Formal Specifications

#### System Module Structure
* `sentinel/listener.py`: Manages WebSocket connections to XRPL RPC nodes and processes incoming ledger transactions.
* `evaluators/rules.py`: Modular Python library housing mathematical evaluation logic (FLCR calculation, exposure ceilings, liquidity depth checks).
* `auditors/ui_inspector.py`: Playwright integration script executing headlessly to capture dApp DOM states and screenshots.
* `classifiers/ai_evaluator.py`: Interface with `gemini-3.8-flash` API for rapid anomaly classification and visual verification.
* `alerts/dispatcher.py`: Multi-channel notification pipeline (Webhooks, Discord, Telegram, Structured JSON logs).

---

### 5. Milestones & Budget Breakdown (Hitos de Desarrollo e Infraestructura)

The funding request is structured into three sequential, deliverable-based milestones ($15,000 USD each, Total: $45,000 USD):

| Milestone | Key Focus & Technical Scope | Target Deliverables (Auditable on GitHub) | Budget |
| :--- | :--- | :--- | :--- |
| **Milestone 1** | **Core Sentinel Engine & FLCR Evaluators (Testnet/Devnet)** | • Fully functional WebSocket/RPC listener.<br>• Deterministic risk rules library (`evaluators/rules.py`).<br>• Testnet execution scripts simulating FLCR depletion.<br>• Unit test coverage > 85%. | **$15,000 USD** |
| **Milestone 2** | **UI Audit Engine (Playwright) & AI Risk Classifier** | • Headless Playwright integration for dApp scraping.<br>• Discrepancy detection module with `gemini-3.8-flash`.<br>• Multi-channel alerting pipeline (Webhooks/Telegram). | **$15,000 USD** |
| **Milestone 3** | **Docker Packaging, SDK & Validator Documentation** | • Single-command Docker Compose deployment (`docker compose up`).<br>• Open-source Python/TypeScript SDK.<br>• Developer documentation & deployment guide for node operators. | **$15,000 USD** |

---

### 6. Expected Impact & Open-Source Delivery (Retorno al Ecosistema XRPL)

1. **Public Infrastructure Standard:** Project Hermes will be released under the MIT Open-Source License, allowing any developer, validator, or institutional fund manager to deploy their own monitoring sentinel.
2. **Institutional Confidence for XLS-65/66:** Provides capital allocators with transparent, verifiable risk metrics, lowering the barrier for institutional liquidity entry into XRPL yield vaults.
3. **Prevention of Systemic Failure:** Early warning signals for First-Loss Capital depletion allow Loan Brokers and depositors to act before liquidation cascades or pool insolvencies occur.
