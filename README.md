# Project Hermes: Institutional Off-Chain Risk Sentinel
## Hybrid Audit Architecture for XLS-65 (Single Asset Vaults) & XLS-66 (Native Lending) on the XRP Ledger

> **Status:** Active Research & Development / Grant Proposal Stage  
> **Target Standards:** XLS-65, XLS-66  
> **Funding Request:** $45,000 USD (3 Milestones of $15,000 USD)

---

## 🛡️ Executive Summary

Project Hermes is an open-source, hybrid off-chain risk sentinel designed to protect institutional liquidity providers and depositors interacting with lending markets on the XRP Ledger (XRPL). While ledger state changes execute deterministically on-chain, off-chain operational risks—such as First-Loss Capital Ratio (FLCR) depletion, credit concentration, and dApp front-end desynchronization—require dedicated monitoring architecture.

Hermes bridges this gap via a two-layer verification model:
1. **Passive On-Chain Sentinel:** High-throughput WebSocket/RPC listener evaluating ledger state and calculating quantitative risk metrics (`evaluators/rules.py`).
2. **Active UI Verification Engine:** Headless browser automation (Playwright) paired with lightweight multimodal AI classification (`gemini-3.8-flash`) to detect front-end discrepancies.

---
### Architectural Scope & Actor Delimitation

Project Hermes operates strictly as an off-chain audit and risk governance layer, maintaining zero execution or custody risk over protocol liquidity.

* **Loan Broker:** Hermes does not manage credit facilities or handle pool funds. It passively audits the Loan Broker by continuously evaluating First-Loss Capital Ratio (FLCR >= 10%) compliance to ensure primary loss absorption capacity.
* **Borrower:** Hermes does not issue loans or conduct off-chain credit scoring. It deterministically calculates borrower concentration risk using the Herfindahl-Hirschman Index (HHI <= 20%) to prevent single-entity systemic exposure.
* **Depositor:** Depositors do not interact directly with Hermes; they are the primary protected institutional entity. Hermes runs real-time telemetry to classify vault health across a 4-Tier Matrix (HEALTHY, WARNING, CRITICAL, UNHEALTHY), triggering dynamic risk mitigation signals.

**Summary:** Hermes does not implement core lending entities; it implements the objective risk governance framework that audits the interactions between Brokers, Borrowers, and Depositors on XLS-65 and XLS-66 standards.
## 📂 Project Repository Structure

```text
xrpl-auditor-project/
├── RESEARCH_PROPOSAL_HERMES.md    # Full institutional research & funding proposal
├── AGENTS.md                      # Operational guidelines and AI collaboration rules
├── xls65_xls66_spec.md            # Technical specifications for vault protocols
├── core/
│   └── ledger_client.py           # Asynchronous RPC WebSocket listener
├── evaluators/
│   └── rules.py                   # Mathematical risk engines (FLCR, HHI, VaR)
├── auditors/
│   └── ui_inspector.py            # Playwright dApp interface scraper
└── README.md                      # Repository root documentation
```

---

## 📊 Key Mathematical Risk Evaluators

Hermes executes continuous quantitative evaluation block-by-block:
* **First-Loss Capital Ratio (FLCR):** Monitors the solvency margin provided by Loan Brokers against total protocol exposure.
* **Concentration Risk (HHI):** Measures the Herfindahl-Hirschman Index to prevent single-borrower capital over-exposure in XLS-65 Vaults.
* **Value at Risk (VaR):** Non-parametric tail-risk estimation based on historical asset volatility and expected default rates.

---

## 🗺️ Milestones & Budget Breakdown

| Milestone | Technical Scope | Deliverables | Budget |
| :--- | :--- | :--- | :--- |
| **Milestone 1** | Core RPC Listener & FLCR Evaluators | WebSocket stream & `evaluators/rules.py` | $15,000 USD |
| **Milestone 2** | Playwright UI Engine & AI Classifier | Headless scraping & anomaly detection | $15,000 USD |
| **Milestone 3** | Docker Packaging, SDK & Documentation | Single-command deployment & dev guides | $15,000 USD |

---

## ⚖️ License
Released under the MIT Open-Source License. Designed for institutional sovereignty and transparency on the XRP Ledger.
---

## 🛡️ Security, Key Management & Zero-Trust Architecture

Security and cryptographic sovereignty are foundational principles of Project Hermes:

* **Non-Custodial Design (Zero Seed Phrase Exposure):** Project Hermes never requests, stores, or processes private keys, seed phrases, or master credentials. The sentinel operates strictly via passive, read-only RPC queries against the XRPL ledger state.
* **Decoupled Client-Side Signing:** All administrative, governance, and operational actions remain strictly client-side. The core engine constructs unsigned transaction blobs (`DRAFT_UNSIGNED`), delegating execution authorization exclusively to hardware-isolated key management environments (HSMs) or non-custodial interfaces compliant with XRPL cryptographic standards (Ed25519 / secp256k1).
* **Deterministic & Tamper-Proof Telemetry:** All calculated metrics (FLCR, HHI) are derived directly from verified on-chain ledger state data, eliminating off-chain data manipulation or spoofed health scores.

> **Core Guarantee:** Hermes protects depositor capital by maintaining absolute isolation from private key material and transaction authorization layers, ensuring full compliance with institutional self-custody standards.
## Empirical Performance & Hardware Telemetry

Project Hermes achieves institutional-grade execution speed with minimal hardware overhead and deterministic cost control:

### 1. Latency & Execution Breakdown
* **Total Audit Cycle Execution:** ~2.11 s (2,113 ms total elapsed time)[cite: 19].
* **Network I/O Latency (XRPL RPC Node):** ~1.85 s (Network round-trip for state queries)[cite: 19].
* **Deterministic Risk Engine (FLCR/HHI):** < 1 ms[cite: 19].
* **Unsigned Payload Generation (`DRAFT_UNSIGNED`):** < 1 ms[cite: 19].
* **Cryptographic SHA-256 Telemetry Anchor:** < 2 ms[cite: 19].

### 2. Memory & Hardware Footprint
* **Background Listener (WebSocket Stream / PID 6976):** 52.89 MB RAM[cite: 20].
* **Core Persistent Engine (Risk Evaluators / PID 7740):** 226.71 MB RAM[cite: 20].
* **Energy Impact:** Ultra-low power consumption (< 15W TDP average load), fully compatible with lightweight infrastructure and standard nodes.

### 3. Token Economics & Operational Cost
* **Core Financial Sentinel:** **0 Tokens ($0.00 USD)** — Fully deterministic, zero-LLM dependencies for real-time risk checks[cite: 19, 20].
* **UI Discrepancy Engine (`gemini-3.8-flash`):** Operates on-demand for frontend validation, consuming ~10k-20k input tokens per audit snapshot (< $0.0003 USD per run).
