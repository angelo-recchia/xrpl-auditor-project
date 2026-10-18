import json
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def create_unsigned_draft():
    # Estructura de la transacción XRPL bajo arquitectura Zero-Trust
    draft_tx = {
        "TransactionType": "Payment",
        "Account": "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
        "Destination": "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
        "Amount": "1000000",  # 1 XRP en drops
        "Fee": "12",
        "Flags": 0,
        "Sequence": 1,
        "NetworkID": 2,
        "Memos": [
            {
                "Memo": {
                    "MemoData": "4865726d657332205a65726f2d5472757374"  # "Hermes2 Zero-Trust" en Hex
                }
            }
        ]
    }
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    drafts_dir = PROJECT_ROOT / "progress" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    filename = drafts_dir / f"payment_x10_{timestamp}_DRAFT_UNSIGNED.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft_tx, f, indent=2)
        
    print(f"[+] Borrador no firmado generado correctamente en: {filename}")
    return str(filename)

if __name__ == "__main__":
    create_unsigned_draft()
