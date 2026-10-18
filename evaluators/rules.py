import os
import yaml
from evaluator.rules import HermesRiskEngine, XLS65VaultEvaluator

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'parameters.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def evaluate_vault_risk(flcr_actual, borrower_shares):
    config = load_config()
    thresholds = config['thresholds']
    max_share = config['max_borrower_share']
    
    # 1. Evaluación de Alertas Escalonadas por FLCR
    if flcr_actual >= thresholds['green']:
        level = "VERDE"
        action = "Monitoreo estándar. Sin riesgo aparente."
    elif flcr_actual >= thresholds['yellow']:
        level = "AMARILLO"
        action = "Desviación leve. Incrementar frecuencia de sondeo."
    elif flcr_actual >= thresholds['orange']:
        level = "NARANJA"
        action = "Estrés moderado. Alerta preventiva al Loan Broker para inyección de capital junior o freno voluntario."
    else:
        level = "ROJO"
        action = "CRÍTICO: Perforación del límite de seguridad. Disparar generación de transacción multi-sig de emergencia."

    # 2. Control de Concentración por Prestatario
    concentration_alerts = []
    for borrower, share in borrower_shares.items():
        if share > max_share:
            concentration_alerts.append(f"Prestatario {borrower} excede la cuota permitida ({share*100:.1f}% > {max_share*100:.1f}%)")

    return {
        "flcr_actual": flcr_actual,
        "risk_level": level,
        "recommended_action": action,
        "concentration_violations": concentration_alerts
    }
