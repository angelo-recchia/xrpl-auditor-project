"""
Puente de compatibilidad legado (evaluator/rules.py).

La única fuente canónica oficial del motor financiero de Project Hermes
reside ahora en `evaluators/rules.py`. Este archivo se conserva únicamente
para mantener retrocompatibilidad con pruebas históricas en `evaluator/`.
"""

from evaluators.rules import (
    HermesRiskEngine,
    XLS65VaultEvaluator,
    XLS66LendingEvaluator,
)

__all__ = [
    "HermesRiskEngine",
    "XLS65VaultEvaluator",
    "XLS66LendingEvaluator",
]