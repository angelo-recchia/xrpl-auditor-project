import json
import os
from glob import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def sign_draft():
    draft_pattern = str(PROJECT_ROOT / "progress" / "drafts" / "*_DRAFT_UNSIGNED.json")
    draft_files = glob(draft_pattern)
    if not draft_files:
        draft_files = glob("progress/drafts/*_DRAFT_UNSIGNED.json")
    if not draft_files:
        print("[-] No se encontraron borradores no firmados.")
        return
    
    latest_draft = max(draft_files, key=os.path.getmtime)
    print(f"[*] Leyendo borrador: {latest_draft}")
    
    with open(latest_draft, "r", encoding="utf-8") as f:
        draft_content = json.load(f)
        
    # Soporta tanto transacciones planas como plantillas con clave 'transaction'
    if "transaction" in draft_content and isinstance(draft_content["transaction"], dict):
        tx = draft_content["transaction"]
    else:
        tx = draft_content

    # Simulación de firma en frío bajo modelo Zero-Trust
    # En un entorno real, este bloque se procesa de forma aislada mediante Ledger o Xaman
    tx["SigningPubKey"] = "ED0000000000000000000000000000000000000000000000000000000000000000"
    tx["TxnSignature"] = "SIMULATED_COLD_STORAGE_SIGNATURE_OK"
    
    signed_filename = latest_draft.replace("_DRAFT_UNSIGNED.json", "_SIGNED.json")
    with open(signed_filename, "w", encoding="utf-8") as f:
        json.dump(draft_content, f, indent=2)
        
    print(f"[+] Transacción firmada generada correctamente en: {signed_filename}")
    return signed_filename

if __name__ == "__main__":
    sign_draft()

