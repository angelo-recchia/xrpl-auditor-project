import hashlib
import json
import hmac

def generate_telemetry_hash(audit_data):
    """
    Genera una huella digital SHA-256 inalterable a partir de las métricas de riesgo de la bóveda.
    """
    data_string = json.dumps(audit_data, sort_keys=True)
    return hashlib.sha256(data_string.encode('utf-8')).hexdigest()

def sign_telemetry_report(audit_data, secret_key="HERMES_AUDIT_KEY"):
    """
    Firma digitalmente el reporte de salud para certificar la autenticidad del motor Sentinel.
    """
    payload = json.dumps(audit_data, sort_keys=True).encode('utf-8')
    signature = hmac.new(secret_key.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    return {
        "telemetry_hash": generate_telemetry_hash(audit_data),
        "signature": signature,
        "status": "VERIFIED_BY_SENTINEL"
    }
