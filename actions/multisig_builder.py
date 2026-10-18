import json

def create_emergency_multisig_payload(vault_account, action_type="FREEZE_CREDIT"):
    """
    Genera una carga útil de transacción XRPL no firmada (Multi-sig draft) 
    para que el Loan Broker la apruebe y firme con su esquema de llaves múltiples.
    """
    tx = {
        "TransactionType": "AccountSet",
        "Account": vault_account,
        "Fee": "15",
        "Memos": [
            {
                "Memo": {
                    "MemoData": "4865726d6573456d657267656e6379",
                    "MemoFormat": "746578742f706c61696e"
                }
            }
        ],
        "EmergencyAction": action_type,
        "SigningPubKey": ""
    }
    return json.dumps(tx, indent=4)
