# Project Hermes: Institutional Off-Chain Risk Sentinel
**Hybrid Audit Architecture for XLS-65 (Single Asset Vaults) & XLS-66 (Native Lending) on the XRP Ledger**

* **Status:** Active Research & Development / Grant Proposal Stage
* **Target Standards:** XLS-65, XLS-66 (`LendingProtocolV1_1`)
* **Funding Request:** $45,000 USD (3 Milestones of $15,000 USD)
* **License:** MIT License

---

## 🛡️ Executive Summary

Project Hermes is an open-source, hybrid off-chain risk sentinel designed to protect institutional liquidity providers and depositors interacting with lending markets on the XRP Ledger (XRPL). While ledger state changes execute deterministically on-chain, off-chain operational risks—such as First-Loss Capital Ratio (FLCR) depletion, credit concentration, and dApp front-end desynchronization—require dedicated monitoring architecture.

Hermes bridges this gap via a two-layer verification model:

1. **Passive On-Chain Sentinel (24/7 Zero-LLM Core):** High-throughput WebSocket/RPC listener (`core/ledger_client.py`) with strict JSON-RPC ID correlation (`rehydrate_state`), evaluating ledger state deterministically via `decimal.Decimal` (`ROUND_DOWN`) rules (`evaluators/rules.py`) and non-blocking Circuit Breaker alerting (`dispatchers/alert_queue.py`).
2. **Active UI & AI Verification Layer (Optional / On-Demand):** Headless browser automation (`browser/engine.py`, Playwright) paired with optional AI risk synthesis (`core/llm_client.py` powered by **`gemini-4-hydrogen`**, migrated from `gemini-3.8-flash` and configurable via `GEMINI_MODEL`) to detect front-end discrepancies and summarize critical incidents without ever acting as a single point of failure.

---

## ⚖️ Architectural Scope & Actor Delimitation

Project Hermes operates strictly as an off-chain audit and risk governance layer, maintaining zero execution or custody risk over protocol liquidity:

* **Loan Broker:** Hermes does not manage credit facilities or handle pool funds. It passively audits the Loan Broker by continuously evaluating First-Loss Capital Ratio (`FLCR >= 10%` under `LendingProtocolV1_1` cash-basis accounting) to ensure primary loss absorption capacity.
* **Borrower:** Hermes does not issue loans or conduct off-chain credit scoring. It deterministically enforces single-borrower exposure caps (`max_borrower_share <= 20%`) alongside portfolio-wide Herfindahl-Hirschman Index limits (`HHI <= 0.25`) to prevent single-entity systemic exposure.
* **Depositor:** Depositors do not interact directly with Hermes; they are the primary protected institutional entity. Hermes runs real-time telemetry to classify vault health across deterministic risk tiers, triggering non-custodial risk mitigation signals (`DRAFT_UNSIGNED`).

**Summary:** Hermes does not implement core lending entities; it implements the objective risk governance framework that audits the interactions between Brokers, Borrowers, and Depositors on XLS-65 and XLS-66 standards.

---

## 📂 Project Repository Structure

```text
xrpl-auditor-project/
├── main.py                         # Async 24/7 sentinel orchestrator (rehydrate + stream + queue)
├── run_sentinel.py                 # Single-shot live audit entrypoint
├── config/
│   ├── __init__.py                 # Unified settings package export
│   ├── settings.py                 # Dynamic .env, networks.json & parameters.yaml loader
│   ├── networks.json               # Agnostic network endpoints (testnet, devnet, standalone)
│   └── parameters.yaml             # Institutional thresholds (FLCR, HHI, max_borrower_share)
├── core/
│   ├── ledger_client.py            # Correlated JSON-RPC (101/102) & WebSocket stream with backoff
│   ├── llm_client.py               # Optional Gemini 4 Hydrogen connector (Zero-LLM fallback)
│   ├── auditor.py                  # LTV / DSCR credit position auditor
│   └── notifier.py                 # Async Telegram alert transport
├── evaluators/
│   ├── rules.py                    # Deterministic Decimal rules (V1_1 cash-basis, flags, NAV)
│   └── ui_verifier.py              # Front-end vs. ledger consistency verifier
├── dispatchers/
│   └── alert_queue.py              # Bounded queue (Dropping Policy) & Circuit Breaker (Half-Open)
├── browser/
│   └── engine.py                   # Headless Playwright engine for dApp UI inspection
├── actions/
│   └── multisig_builder.py         # Non-custodial DRAFT_UNSIGNED emergency payload builder
├── telemetry/
│   └── crypto_anchor.py            # SHA-256 / HMAC-SHA256 audit proof anchoring
├── specs/
│   ├── FINANCIAL_ARCHITECTURE.md   # Quantitative model, tranche waterfall & standalone sandbox
│   └── xls65_xls66_spec.md         # Protocol specifications for XLS-65 / XLS-66
├── tests/                          # Deterministic pytest suite & systemic stress scenarios
├── Dockerfile                      # Containerized 24/7 sentinel runtime
├── docker-compose.yml              # Agnostic deployment + rippled --a standalone sandbox
├── .env.example                    # Public environment template (no secrets)
├── requirements.txt                # Reproducible Python dependencies
├── RESEARCH_PROPOSAL_HERMES.md     # Full XRPL Grants proposal
├── AGENTS.md                       # Operational guidelines for autonomous coding agents
└── README.md                       # Repository root documentation
```

---

## 📊 Key Mathematical Risk Evaluators

Hermes executes continuous quantitative evaluation block-by-block using deterministic `decimal.Decimal` (`ROUND_DOWN`) arithmetic:

* **First-Loss Capital Ratio (FLCR — Cash-Basis V1_1):** Audits Loan Broker solvency (`EffectiveDebt = PrincipalDebt + RealizedInterest`, ignoring unpaid accrued interest) with division-by-zero guards and progressive thresholds (`HEALTHY`, `WARNING`, `CRITICAL_DEEP_FREEZE`).
* **Concentration Risk (Borrower Cap & HHI):** Enforces single-borrower exposure caps (`max_borrower_share <= 20%`) and portfolio-wide Herfindahl-Hirschman Index limits (`HHI <= 0.25`) across XLS-65 Vaults.
* **Vault Access & NAV Parity (XLS-65):** Sanitizes heterogeneous `Flags` (`int(flags, 0) & 0x0001`) to classify `PERMISSIONED` vs. `OPEN` vaults and verifies 6-decimal truncated `NAV per Share` parity (`0.000001`).
* **Value at Risk (VaR 99%):** Non-parametric tail-risk estimation based on historical asset volatility and expected default rates.

---

## 🗺️ Milestones & Budget Breakdown

| Milestone | Technical Scope | Deliverables | Budget |
| :--- | :--- | :--- | :--- |
| **Milestone 1** | **Core RPC Listener & FLCR Evaluators** | Correlated WebSocket stream (`101`/`102`), `evaluators/rules.py` & `pytest` suite | **$15,000 USD** |
| **Milestone 2** | **Playwright UI Engine & AI Risk Layer** | Headless scraping (`browser/engine.py`), `core/llm_client.py` (`gemini-4-hydrogen`) & Circuit Breaker alerts | **$15,000 USD** |
| **Milestone 3** | **Docker Packaging, Standalone Sandbox & Docs** | Agnostic `docker-compose.yml` (`rippled --a`), architecture specs & operator guides | **$15,000 USD** |

---

## 🛡️ Security, Key Management & Zero-Trust Architecture

Security and cryptographic sovereignty are foundational principles of Project Hermes:

* **Non-Custodial Design (Zero Seed Phrase Exposure):** Project Hermes never requests, stores, or processes private keys, seed phrases, or master credentials. The sentinel operates strictly via passive, read-only RPC/WebSocket queries against XRPL ledger state.
* **Decoupled Client-Side Signing:** All administrative, governance, and emergency mitigation actions remain strictly client-side. `actions/multisig_builder.py` constructs unsigned transaction blobs (`DRAFT_UNSIGNED`), delegating signing exclusively to hardware-isolated environments (HSMs / Ledger / Xaman) compliant with Ed25519 / secp256k1.
* **Deterministic & Tamper-Proof Telemetry:** All calculated metrics (FLCR, HHI, NAV) derive directly from validated ledger state and can be anchored via SHA-256 / HMAC-SHA256 (`telemetry/crypto_anchor.py`).

---

## ⚡ Empirical Performance & Hardware Telemetry

Measured in local Windows/Devnet execution benchmarks:

### 1. Latency & Execution Breakdown
* **Total Audit Cycle Execution:** ~2.11 s (2,113 ms total elapsed time).
* **Network I/O Latency (XRPL RPC Node):** ~1.85 s (network round-trip for state queries).
* **Deterministic Risk Engine (FLCR / HHI / NAV):** < 1 ms.
* **Unsigned Payload Generation (`DRAFT_UNSIGNED`):** < 1 ms.
* **Cryptographic SHA-256 Telemetry Anchor:** < 2 ms.

### 2. Memory & Hardware Footprint
* **Background Listener (WebSocket Stream):** ~52.89 MB RAM.
* **Core Persistent Engine (Risk Evaluators):** ~226.71 MB RAM.
* **Energy Impact:** Ultra-low power consumption (< 15W TDP average load), compatible with lightweight nodes and containers.

### 3. Token Economics & 24/7 Offline/Online Resilience
* **Core Financial Sentinel (24/7 Online & Offline):** **0 Tokens ($0.00 USD)** — Fully deterministic, zero-LLM dependencies for real-time ledger monitoring (`Testnet`, `Devnet`, or offline `rippled --a` Standalone mode).
* **Optional AI Layer (`gemini-4-hydrogen`):** Invoked strictly on-demand for UI discrepancy audits or critical incident summaries (`$0.00 USD` within Google AI Studio Free Tier limits; ~$0.015–$0.03 USD per ~10k–20k input-token Paid Tier UI snapshot). If no `GEMINI_API_KEY` is present or the node is offline, the sentinel automatically falls back cleanly with zero interruption.

---

## 🚀 Quickstart (Local, Standalone Sandbox & QA Tests)

```bash
# 1. Install dependencies & configure environment
pip install -r requirements.txt
cp .env.example .env

# 2. Run the 24/7 asynchronous sentinel (Testnet by default via XRPL_WS_URL)
python main.py

# 3. Run offline/sovereign Docker Standalone sandbox (rippled --a on ws://localhost:5005)
docker compose --profile standalone up -d

# 4. Run deterministic QA test suite
python -m pytest tests/test_rules.py tests/test_dispatcher.py tests/test_systemic_stress.py -v
```

---

## ⚖️ License

Released under the **MIT Open-Source License**. Designed for institutional sovereignty, auditability, and systemic resilience on the XRP Ledger.