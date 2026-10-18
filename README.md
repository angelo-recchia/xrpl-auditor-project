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
* **Decoupled Client-Side Signing:** Any operational or administrative actions remain entirely on the client side using hardware-isolated or secure key environments (e.g., Xaman, Ledger, or Tangem).
* **Deterministic & Tamper-Proof Telemetry:** All calculated metrics (FLCR, HHI) are derived directly from verified on-chain ledger state data, eliminating off-chain data manipulation or spoofed health scores.

> **Core Guarantee:** Hermes protects depositor capital by maintaining absolute isolation from private key material and transaction authorization layers, ensuring full compliance with institutional self-custody standards.
