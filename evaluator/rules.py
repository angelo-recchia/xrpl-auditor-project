"""
Módulo: evaluator/rules.py
Proyecto: Hermes (XRPL XLS-65/66)
Descripción: Motor analítico off-chain optimizado con alta precisión numérica (Decimal),
             validación de invariantes, control de concentración agregada por prestatario
             y evaluación de salud de bóvedas XLS-65 y préstamos XLS-66.
"""

from decimal import Decimal, InvalidOperation


class HermesRiskEngine:
    def __init__(self, min_coverage_ratio: float | str, max_concentration_ratio: float | str):
        """
        Inicializa el motor con umbrales estrictos en formato Decimal para evitar errores de punto flotante.
        Rango permitido: (0.0, 1.0]
        """
        try:
            self.min_coverage_ratio = Decimal(str(min_coverage_ratio))
            self.max_concentration_ratio = Decimal(str(max_concentration_ratio))
        except (InvalidOperation, ValueError):
            raise ValueError("Los ratios deben ser valores numéricos válidos.")

        if not (Decimal('0.0') < self.min_coverage_ratio <= Decimal('1.0')):
            raise ValueError("El ratio de cobertura mínimo debe estar estrictamente entre 0.0 y 1.0.")
        if not (Decimal('0.0') < self.max_concentration_ratio <= Decimal('1.0')):
            raise ValueError("El ratio de concentración máximo debe estar estrictamente entre 0.0 y 1.0.")

    def calculate_max_vault_capacity(self, flc: float | str) -> Decimal:
        """
        Fórmula 1: Capacidad Máxima de la Bóveda basada en el First-Loss Capital (FLC).
        """
        flc_dec = Decimal(str(flc))
        return flc_dec / self.min_coverage_ratio

    def check_vault_capacity_limit(self, flc: float | str, total_deposits: float | str) -> dict:
        """
        Verifica si los depósitos actuales respetan el límite seguro de capital.
        """
        flc_dec = Decimal(str(flc))
        deposits_dec = Decimal(str(total_deposits))
        max_capacity = self.calculate_max_vault_capacity(flc_dec)
        is_safe = deposits_dec <= max_capacity
        
        return {
            "max_capacity": float(max_capacity),
            "current_deposits": float(deposits_dec),
            "is_safe": is_safe,
            "status": "OK" if is_safe else "ALERTA: Exceso de depósitos sin respaldo FLC suficiente"
        }

    def check_borrower_concentration_aggregated(self, max_capacity: float | str, existing_borrower_debt: float | str, new_loan_request: float | str) -> dict:
        """
        Fórmula 2 (Modificada): Límite de Exposición Agregada por Prestatario.
        Suma la deuda acumulada de la cuenta prestataria en múltiples Loan LedgerObjects más el nuevo tramo.
        """
        capacity_dec = Decimal(str(max_capacity))
        existing_debt_dec = Decimal(str(existing_borrower_debt))
        new_loan_dec = Decimal(str(new_loan_request))
        
        total_aggregated_debt = existing_debt_dec + new_loan_dec
        max_loan_allowed = capacity_dec * self.max_concentration_ratio
        
        is_compliant = total_aggregated_debt <= max_loan_allowed
        
        return {
            "max_loan_allowed": float(max_loan_allowed),
            "existing_debt": float(existing_debt_dec),
            "requested_loan": float(new_loan_dec),
            "total_aggregated_debt": float(total_aggregated_debt),
            "is_compliant": is_compliant,
            "status": "OK" if is_compliant else "ALERTA CRÍTICA: Sobreexposición agregada de prestatario detectada"
        }

    def evaluate_real_flcr(self, flc_actual: float | str, total_depositors_active: float | str) -> dict:
        """
        Fórmula 3: Ratio de Cobertura de Primera Pérdida Real (FLCR Real) con control de activos cero.
        """
        flc_dec = Decimal(str(flc_actual))
        depositors_dec = Decimal(str(total_depositors_active))

        if depositors_dec == Decimal('0'):
            return {
                "flcr_real": 1.0,
                "min_required": float(self.min_coverage_ratio),
                "health_status": "Sin pasivo activo (Cobertura óptima / Cero riesgo)"
            }

        flcr_real = flc_dec / depositors_dec
        is_healthy = flcr_real >= self.min_coverage_ratio
        
        return {
            "flcr_real": float(flcr_real.quantize(Decimal('0.0001'))),
            "min_required": float(self.min_coverage_ratio),
            "health_status": "Bóveda de Riesgo Controlado" if is_healthy else "Alerta Roja de Insolvencia"
        }


class XLS65VaultEvaluator:
    @staticmethod
    def evaluate_vault(total_assets: float, total_shares: float, available_liquidity: float) -> dict:
        """Evalúa los parámetros de salud de una bóveda XLS-65."""
        ratio = total_assets / total_shares if total_shares > 0 else 0.0
        liquidity_ratio = available_liquidity / total_assets if total_assets > 0 else 0.0
        
        health = "SALUDABLE"
        if liquidity_ratio < 0.05:
            health = "CRÍTICO"
        elif liquidity_ratio < 0.15:
            health = "ESTRÉS"
            
        return {
            "asset_to_share_ratio": round(ratio, 4),
            "liquidity_ratio": round(liquidity_ratio, 4),
            "vault_health": health
        }

class XLS66LendingEvaluator:
    @staticmethod
    def evaluate_position(borrowed_amount: float, collateral_value: float, debt_service: float, cash_flow: float) -> dict:
        """Evalúa el LTV, DSCR y clasifica el estado de salud de un préstamo XLS-66."""
        ltv = (borrowed_amount / collateral_value) if collateral_value > 0 else 1.0
        dscr = (cash_flow / debt_service) if debt_service > 0 else 0.0
        
        # Clasificación de estado de salud bajo criterios de riesgo
        if ltv >= 0.85 or (debt_service > 0 and dscr < 1.0):
            health = "CRÍTICO"
        elif ltv >= 0.75 or (debt_service > 0 and dscr < 1.25):
            health = "ESTRÉS"
        else:
            health = "SALUDABLE"
            
        return {
            "ltv": round(ltv, 4),
            "dscr": round(dscr, 4),
            "health_status": health
        }

if __name__ == "__main__":
    # Prueba unitaria rápida del módulo de reglas
    vault_test = XLS65VaultEvaluator.evaluate_vault(10000.0, 9500.0, 2000.0)
    lending_test = XLS66LendingEvaluator.evaluate_position(7000.0, 10000.0, 1000.0, 1500.0)
    
    print("[*] Test XLS-65 Vault:", vault_test)
    print("[*] Test XLS-66 Lending:", lending_test)
    
    risk_engine = HermesRiskEngine(min_coverage_ratio=0.20, max_concentration_ratio=0.10)
    capacity_test = risk_engine.check_vault_capacity_limit(flc=20000, total_deposits=95000)
    concentration_test = risk_engine.check_borrower_concentration_aggregated(
        max_capacity=100000, existing_borrower_debt=5000, new_loan_request=4000
    )
    flcr_test = risk_engine.evaluate_real_flcr(flc_actual=20000, total_depositors_active=95000)

    print("[*] Test Risk Engine Capacity:", capacity_test)
    print("[*] Test Risk Engine Concentration:", concentration_test)
    print("[*] Test Risk Engine FLCR:", flcr_test)
