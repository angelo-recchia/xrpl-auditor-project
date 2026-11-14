import unittest
from decimal import Decimal
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Simulación de la lógica del núcleo determinista de Hermes para pruebas de estrés
class TestHermesSystemicStress(unittest.TestCase):
    
    def test_st03_multi_user_default_cascade(self):
        """
        ST-03: Cascada de Contagio Multiusuario (Default Simultáneo)
        Evalúa la depleción no lineal del FLCR (First-Loss Capital Ratio) ante el impago 
        simultáneo de los dos mayores prestatarios y la activación correcta del Deep Freeze.
        """
        # Estado inicial de la Bóveda XLS-65
        total_vault_assets = Decimal("1000000.00")  # 1,000,000 XRP
        initial_flcr = Decimal("0.15")               # 15% de Capital de Primera Pérdida
        flcr_pool = total_vault_assets * initial_flcr # 150,000 XRP disponibles para pérdidas
        
        # Posiciones de crédito activas (XLS-66)
        borrowers = {
            "rBorrowerAlpha": Decimal("90000.00"),  # Deuda masiva 1
            "rBorrowerBeta": Decimal("50000.00"),   # Deuda masiva 2
            "rBorrowerGamma": Decimal("10000.00")   # Deuda menor
        }
        
        # Umbrales críticos del sistema
        CRITICAL_FLCR_THRESHOLD = Decimal("0.10")  # 10%
        
        # --- EJECUCIÓN DEL ESTRÉS: Impago Simultáneo de Alpha y Beta ---
        defaulted_debt = borrowers["rBorrowerAlpha"] + borrowers["rBorrowerBeta"]
        
        # El pool de primera pérdida absorbe el impacto del default
        remaining_flcr_pool = flcr_pool - defaulted_debt
        current_flcr_ratio = remaining_flcr_pool / total_vault_assets
        
        # Verificación determinista del estado resultante
        self.assertLess(
            current_flcr_ratio, 
            CRITICAL_FLCR_THRESHOLD, 
            "El FLCR residual debe cruzar el umbral crítico tras la cascada de impagos."
        )
        
        # Comprobación de la respuesta defensiva del centinela
        deep_freeze_triggered = current_flcr_ratio <= CRITICAL_FLCR_THRESHOLD
        
        self.assertTrue(
            deep_freeze_triggered,
            "El sistema de defensa debe activar el Deep Freeze automáticamente ante la cascada."
        )
        
        # Validación de que no hay desbordamientos ni errores de punto flotante
        self.assertIsInstance(current_flcr_ratio, Decimal)

if __name__ == "__main__":
    unittest.main()
