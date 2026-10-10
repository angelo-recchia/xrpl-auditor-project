#!/usr/bin/env python3
"""
Simulación Avanzada de Inteligencia de Mercado: XLS-65 (Single Asset Vaults) + XLS-66 (Uncollateralized Lending)
Evalúa liquidez, modela riesgos matemáticos (Impermanent Yield Loss, Tasa Flotante, Falta de Colateral)
y genera el borrador DRAFT_UNSIGNED para firma en frío.
"""

import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

# Rutas canónicas
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DRAFTS_DIR = BASE_DIR / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Parámetros de Simulación de Mercado y Bóveda ─────────────────────
VAULT_ID = "24CCC67D1C8A53F9A0C8C7819811E6634BB6227468E6FD5A730C701D8099B403"
VAULT_OPERATOR = "rpz64En6Qa82H3Jp6UrhjPwAjFXzCphWyj"
BORROWER_ACCOUNT = "rBqxhg2jX8Bh8BjKjHvkXp9oLpP3kL5nWqN"

# Estado de la Bóveda XLS-65 (en XRP)
VAULT_TOTAL_ASSETS_XRP = 100.325925
VAULT_LOANS_OUTSTANDING_XRP = 0.0
VAULT_MAX_LTV_BPS = 8000           # 80.00% máx LTV
BASE_INTEREST_RATE_BPS = 650       # 6.50% tasa anual base
DURATION_HOURS = 720               # 30 días

# Propuesta de Préstamo no colateralizado XLS-66
LOAN_REQUEST_XRP = 25.0            # Monto solicitado
BORROWER_MONTHLY_CASHFLOW_XRP = 30.0 # Flujo de caja libre mensual estimado del borrower

def calculate_risks(principal_xrp: float, rate_bps: int, hours: int, vault_total: float, borrower_cf: float):
    """
    Modelado matemático de riesgos de ejecución:
    1. Impermanent Yield Loss (IYL): Coste de oportunidad de los LPs frente a tasa de staking/mercado externa.
    2. Riesgo de Tasa Flotante: Sensibilidad del DSCR (Debt Service Coverage Ratio) ante estrés de tasas (+200, +500 bps).
    3. Falta de Colateral: Pérdida Esperada (Expected Loss = PD * LGD * EAD) con LGD = 100%.
    """
    # 1. Coste de oportunidad / Impermanent Yield Loss vs benchmark de liquidez (ej. 9.0% en DEX/AMM)
    benchmark_rate_bps = 900
    spread_bps = benchmark_rate_bps - rate_bps
    time_factor = hours / (365 * 24)
    iyl_xrp = principal_xrp * (spread_bps / 10000.0) * time_factor

    # 2. Servicio de la deuda e impacto de tasa flotante
    base_interest_xrp = principal_xrp * (rate_bps / 10000.0) * time_factor
    total_due_base = principal_xrp + base_interest_xrp
    dscr_base = borrower_cf / total_due_base

    # Escenarios de estrés de tasa flotante (+200 bps y +500 bps)
    stress_rates = [rate_bps + 200, rate_bps + 500]
    stress_results = []
    for s_rate in stress_rates:
        s_interest = principal_xrp * (s_rate / 10000.0) * time_factor
        s_due = principal_xrp + s_interest
        s_dscr = borrower_cf / s_due
        stress_results.append({
            "rate_bps": s_rate,
            "rate_pct": s_rate / 100.0,
            "total_due_xrp": round(s_due, 4),
            "dscr": round(s_dscr, 2),
            "status": "VULNERABLE" if s_dscr < 1.15 else "RESILIENTE"
        })

    # 3. Falta de Colateral (LGD = 100%) y Dilución del NAV de los LPs
    # En un préstamo sin colateral, Default => Quita del 100% sobre principal
    lgd = 1.00 # 100%
    pd = 0.045 # 4.5% probabilidad histórica estimada para crédito no garantizado
    expected_loss_xrp = principal_xrp * lgd * pd
    nav_dilution_pct = (principal_xrp / vault_total) * 100.0

    return {
        "iyl_xrp": round(iyl_xrp, 6),
        "spread_bps": spread_bps,
        "base_interest_xrp": round(base_interest_xrp, 6),
        "total_due_base_xrp": round(total_due_base, 6),
        "dscr_base": round(dscr_base, 2),
        "stress_scenarios": stress_results,
        "lgd_pct": 100.0,
        "pd_pct": pd * 100.0,
        "expected_loss_xrp": round(expected_loss_xrp, 6),
        "nav_dilution_on_default_pct": round(nav_dilution_pct, 2)
    }

def validate_vault_liquidity(vault_total: float, outstanding: float, requested: float, max_ltv_bps: int):
    """Valida solvencia y umbrales de liquidez XLS-65."""
    available_before = vault_total - outstanding
    new_outstanding = outstanding + requested
    ltv_after_bps = int(round((new_outstanding / vault_total) * 10000))
    available_after = vault_total - new_outstanding

    is_capacity_ok = available_before >= requested
    is_ltv_ok = ltv_after_bps <= max_ltv_bps

    status = "SALUDABLE"
    if not is_ltv_ok or not is_capacity_ok:
        status = "CRÍTICO"
    elif ltv_after_bps > (max_ltv_bps * 0.8):
        status = "ESTRÉS"

    return {
        "available_before_xrp": round(available_before, 6),
        "available_after_xrp": round(available_after, 6),
        "ltv_after_bps": ltv_after_bps,
        "ltv_after_pct": ltv_after_bps / 100.0,
        "is_capacity_ok": is_capacity_ok,
        "is_ltv_ok": is_ltv_ok,
        "within_limits": is_capacity_ok and is_ltv_ok,
        "liquidity_status": status
    }

def generate_unsigned_loan_draft(validation: dict, risks: dict):
    """Construye y exporta la estructura canónica DRAFT_UNSIGNED."""
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    iso_now = datetime.now(timezone.utc).isoformat()
    principal_drops = int(LOAN_REQUEST_XRP * 1_000_000)
    interest_drops = int(risks["base_interest_xrp"] * 1_000_000)
    total_repay_drops = principal_drops + interest_drops

    draft = {
        "template_meta": {
            "template_id": f"xls66_uncollateralized_loan_{timestamp_str}",
            "version": "1.0.0",
            "generated_at": iso_now,
            "network": "XRPL Devnet (NetworkID: 2)",
            "status": "DRAFT_UNSIGNED",
            "purpose": f"LoanCreate XLS-66 — Préstamo no colateralizado de {LOAN_REQUEST_XRP} XRP sobre Bóveda X10"
        },
        "vault_context": {
            "VaultID": VAULT_ID,
            "VaultOperator": VAULT_OPERATOR,
            "TotalAssets_XRP": VAULT_TOTAL_ASSETS_XRP,
            "LTV_after_loan_bps": validation["ltv_after_bps"],
            "MaxLoanToValueBps": VAULT_MAX_LTV_BPS,
            "liquidity_status": validation["liquidity_status"]
        },
        "loan_terms": {
            "borrower": BORROWER_ACCOUNT,
            "principal_xrp": LOAN_REQUEST_XRP,
            "principal_drops": str(principal_drops),
            "annual_rate_bps": BASE_INTEREST_RATE_BPS,
            "duration_hours": DURATION_HOURS,
            "amortization": "bullet",
            "day_count": "actual/365",
            "collateral_required": False,
            "interest_drops": str(interest_drops),
            "total_repay_drops": str(total_repay_drops)
        },
        "risk_modeling": {
            "dscr_base": risks["dscr_base"],
            "expected_loss_xrp": risks["expected_loss_xrp"],
            "max_nav_dilution_pct": risks["nav_dilution_on_default_pct"],
            "floating_rate_stress_tested": True
        },
        "transaction": {
            "TransactionType": "LoanCreate",
            "Account": VAULT_OPERATOR,
            "Borrower": BORROWER_ACCOUNT,
            "VaultID": VAULT_ID,
            "Principal": str(principal_drops),
            "InterestRateBps": BASE_INTEREST_RATE_BPS,
            "LoanDurationHours": DURATION_HOURS,
            "Amortization": "bullet",
            "Fee": "1000",
            "Sequence": 3,
            "NetworkID": 2
        },
        "fields_to_verify_before_cold_signing": [
            f"TransactionType: LoanCreate",
            f"Account (Operator): {VAULT_OPERATOR}",
            f"Borrower: {BORROWER_ACCOUNT}",
            f"VaultID: {VAULT_ID}",
            f"Principal: {principal_drops} drops ({LOAN_REQUEST_XRP} XRP)",
            f"InterestRateBps: {BASE_INTEREST_RATE_BPS} (6.50% anual)",
            f"Duration: {DURATION_HOURS} horas (30 días)",
            f"Amortization: bullet (interés y principal al vencimiento)",
            "Fee: 1000 drops",
            "NetworkID: 2"
        ],
        "cold_signing": {
            "status": "PENDING",
            "device": "Ledger Nano S Plus / Tangem / Xaman",
            "security_rule": "Firma offline obligatoria. Prohibida la firma en caliente."
        }
    }

    filename = DRAFTS_DIR / f"loan_create_x10_{timestamp_str}_DRAFT_UNSIGNED.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    return filename, draft

def main():
    print("======================================================================")
    print(" INTELIGENCIA DE MERCADO XRPL: XLS-65 (VAULTS) + XLS-66 (LENDING)")
    print("======================================================================")
    print(f"Timestamp:       {datetime.now(timezone.utc).isoformat()}")
    print(f"Bóveda Analizada:{VAULT_ID[:16]}... (Cold storage X10)")
    print(f"Activo Custodia: XRP | Total: {VAULT_TOTAL_ASSETS_XRP:.6f} XRP")
    print(f"Solicitud:       {LOAN_REQUEST_XRP:.2f} XRP no colateralizado a {BASE_INTEREST_RATE_BPS/100:.2f}% (30d)")
    print("----------------------------------------------------------------------")

    # 1. Validación de Liquidez
    val = validate_vault_liquidity(
        VAULT_TOTAL_ASSETS_XRP,
        VAULT_LOANS_OUTSTANDING_XRP,
        LOAN_REQUEST_XRP,
        VAULT_MAX_LTV_BPS
    )

    print("1. EVALUACIÓN DE LIQUIDEZ Y LTV (XLS-65):")
    print(f"  - Disponible previo:  {val['available_before_xrp']:.6f} XRP")
    print(f"  - Disponible tras op: {val['available_after_xrp']:.6f} XRP")
    print(f"  - LTV Resultante:     {val['ltv_after_pct']:.2f}% (Máx permitido: {VAULT_MAX_LTV_BPS/100:.2f}%)")
    print(f"  - Estado de Bóveda:   [{val['liquidity_status']}]")

    if not val["within_limits"]:
        print("\n[RECHAZADO] La solicitud excede los límites de solvencia de la bóveda.")
        sys.exit(1)
    print("  ✓ Verificación de capacidad y solvencia: APROBADA")
    print("----------------------------------------------------------------------")

    # 2. Análisis Matemático de Riesgos
    risks = calculate_risks(
        LOAN_REQUEST_XRP,
        BASE_INTEREST_RATE_BPS,
        DURATION_HOURS,
        VAULT_TOTAL_ASSETS_XRP,
        BORROWER_MONTHLY_CASHFLOW_XRP
    )

    print("2. ANÁLISIS CUANTITATIVO DE RIESGOS DE EJECUCIÓN:")
    print("  A. Impermanent Yield Loss (IYL):")
    print(f"     * Coste de Oportunidad LP: {risks['iyl_xrp']:.6f} XRP (vs benchmark 9.00% DEX/AMM)")
    print(f"     * Spread de rendimiento:   {risks['spread_bps']} bps")
    print("  B. Riesgo de Tasa Flotante y Cobertura (DSCR):")
    print(f"     * DSCR Caso Base (6.50%):  {risks['dscr_base']}x (Cobertura solvente > 1.20x)")
    for s in risks["stress_scenarios"]:
        print(f"     * Estrés +{s['rate_bps']-BASE_INTEREST_RATE_BPS} bps ({s['rate_pct']:.2f}%): DSCR = {s['dscr']}x [{s['status']}]")
    print("  C. Falta de Colateral (Uncollateralized Credit Risk):")
    print(f"     * Loss Given Default (LGD): {risks['lgd_pct']:.1f}% (Pérdida total de principal)")
    print(f"     * Probabilidad Default (PD):{risks['pd_pct']:.2f}%")
    print(f"     * Pérdida Esperada E(L):    {risks['expected_loss_xrp']:.6f} XRP")
    print(f"     * Dilución Máx NAV Bóveda:  {risks['nav_dilution_on_default_pct']:.2f}% sobre el equity LP")
    print("----------------------------------------------------------------------")

    # 3. Generación del Borrador DRAFT_UNSIGNED
    draft_file, draft_json = generate_unsigned_loan_draft(val, risks)
    print("3. GENERACIÓN DE BORRADOR DE TRANSACCIÓN (DRAFT_UNSIGNED):")
    print(f"  ✓ Archivo: {draft_file.resolve()}")
    print(f"  ✓ Estado:  {draft_json['template_meta']['status']}")
    print(f"  ✓ Hash ID: {draft_json['template_meta']['template_id']}")
    print("======================================================================")
    print("BORRADOR LISTO PARA TRANSFERENCIA Y FIRMA EN HARDWARE WALLET (ZERO-TRUST).")

if __name__ == "__main__":
    main()
