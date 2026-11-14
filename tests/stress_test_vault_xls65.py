import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluator.rules import XLS65VaultEvaluator, HermesRiskEngine
from core.notifier import send_telegram_alert

async def evaluate_and_dispatch_xls65(s: dict) -> dict:
    total_assets = s["total_assets"]
    total_shares = s["total_shares"]
    available_liquidity = s["available_liquidity"]
    
    result = XLS65VaultEvaluator.evaluate_vault(total_assets, total_shares, available_liquidity)
    print(f"[{s['name']}]")
    print(f"  -> Activos Totales: {total_assets:,.2f} XRP")
    print(f"  -> Participaciones (Shares): {total_shares:,.2f}")
    print(f"  -> Liquidez Disponible: {available_liquidity:,.2f} XRP ({result['liquidity_ratio']*100:.1f}%)")
    print(f"  -> Ratio Activo/Share: {result['asset_to_share_ratio']}")
    print(f"  -> Diagnóstico Bóveda XLS-65: {result['vault_health']}")

    if result['vault_health'] == "CRÍTICO":
        alert_msg = (
            f"*ALERTA CRÍTICA DE ILIQUIDEZ EN BÓVEDA XLS-65*\n"
            f"• Estado: *{result['vault_health']}*\n"
            f"• Liquidez Disponible: {result['liquidity_ratio']*100:.2f}%\n"
            f"• Ratio Activo/Share: {result['asset_to_share_ratio']}\n"
            f"• Acción: Bloqueo preventivo de redenciones masivas e inyección de liquidez requerida."
        )
        print(f"  -> [TELEGRAM] Disparando alerta de liquidez crítica al operador...")
        success = await send_telegram_alert(alert_msg, level="CRITICAL")
        if success:
            print(f"  -> [TELEGRAM] Alerta despachada con éxito.")
        else:
            print(f"  -> [TELEGRAM] Aviso: No se pudo enviar (verifique .env o tokens).")
    return result

def run_st65_01():
    """ST65-01: Bóveda XLS-65 en Salud Óptima (Liquidez 85%, Asset/Share 1.0)."""
    s = {
        "name": "Escenario XLS-65 01: Salud Óptima (ST65-01)",
        "total_assets": 1000000.0,
        "total_shares": 1000000.0,
        "available_liquidity": 850000.0
    }
    return asyncio.run(evaluate_and_dispatch_xls65(s))

def run_st65_02():
    """ST65-02: Estrés de Liquidez Moderado (Liquidez 10%, Estado ESTRÉS)."""
    s = {
        "name": "Escenario XLS-65 02: Estrés de Liquidez (ST65-02)",
        "total_assets": 1000000.0,
        "total_shares": 1000000.0,
        "available_liquidity": 100000.0
    }
    return asyncio.run(evaluate_and_dispatch_xls65(s))

def run_st65_03():
    """ST65-03: Corrida Bancaria / Iliquidez Crítica (Liquidez 2%, Estado CRÍTICO)."""
    s = {
        "name": "Escenario XLS-65 03: Corrida Bancaria / Iliquidez Crítica (ST65-03)",
        "total_assets": 1000000.0,
        "total_shares": 1000000.0,
        "available_liquidity": 20000.0
    }
    return asyncio.run(evaluate_and_dispatch_xls65(s))

def run_st65_04():
    """ST65-04: Dilución Severa del NAV / Quita por Impagos (Asset/Share 0.85)."""
    s = {
        "name": "Escenario XLS-65 04: Dilución Severa del NAV (ST65-04)",
        "total_assets": 850000.0,
        "total_shares": 1000000.0,
        "available_liquidity": 120000.0
    }
    return asyncio.run(evaluate_and_dispatch_xls65(s))

async def run_xls65_stress_matrix():
    scenarios = [
        {"name": "Escenario XLS-65 01: Salud Óptima (ST65-01)", "total_assets": 1000000.0, "total_shares": 1000000.0, "available_liquidity": 850000.0},
        {"name": "Escenario XLS-65 02: Estrés de Liquidez (ST65-02)", "total_assets": 1000000.0, "total_shares": 1000000.0, "available_liquidity": 100000.0},
        {"name": "Escenario XLS-65 03: Corrida Bancaria / Iliquidez Crítica (ST65-03)", "total_assets": 1000000.0, "total_shares": 1000000.0, "available_liquidity": 20000.0},
        {"name": "Escenario XLS-65 04: Dilución Severa del NAV (ST65-04)", "total_assets": 850000.0, "total_shares": 1000000.0, "available_liquidity": 120000.0}
    ]

    print('=== EJECUTANDO MATRIZ DE ESTRÉS XLS-65 (SINGLE ASSET VAULTS) ===\n')
    for s in scenarios:
        await evaluate_and_dispatch_xls65(s)
        print('-' * 60)

if __name__ == '__main__':
    asyncio.run(run_xls65_stress_matrix())
