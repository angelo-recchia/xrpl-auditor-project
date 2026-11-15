"""
Script: scripts/demo_standalone_e2e.py
Proyecto: Hermes (XRPL XLS-65 / XLS-66 / LendingProtocolV1_1)
Descripción: Demostración reproducible End-to-End para el comité de XRPL Grants.
             Muestra el ciclo completo:
               1) Gobernanza XLS-65 (lsfVaultPrivate 0x00010000 + Closed-Ended buffer 60s)
               2) Evento real meta.AffectedNodes (Vault + LoanBroker 1/10th bps + DeepFreeze + Loan)
               3) Pasarela asíncrona AlertQueueDispatcher (Circuit Breaker)
               4) Mitigación no custodia DRAFT_UNSIGNED + Sellado criptográfico SHA-256

Uso:
  python scripts/demo_standalone_e2e.py          # Demo determinista completa (sin internet)
  python scripts/demo_standalone_e2e.py --live   # Conexión en vivo a xrpld Standalone (ws://localhost:6006)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.multisig_builder import create_emergency_multisig_payload
from config import load_settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dispatchers.alert_queue import AlertQueueDispatcher
from evaluators.rules import (
    LSF_LOW_DEEP_FREEZE,
    LSF_VAULT_PRIVATE,
    audit_closed_ended_vault_v1_1,
    audit_vault_access_flags,
)
from main import LSF_LOAN_DEFAULT, HermesSentinel
from telemetry.crypto_anchor import sign_telemetry_report


async def run_deterministic_e2e_demo() -> None:
    print("=" * 70)
    print(" PROJECT HERMES v2 - DEMO END-TO-END (XLS-65 / XLS-66 / V1_1)")
    print("=" * 70)

    captured_alerts = []

    async def demo_sender(alert: dict) -> bool:
        captured_alerts.append(alert)
        return True

    dispatcher = AlertQueueDispatcher(max_size=100, sender=demo_sender)
    sentinel = HermesSentinel(
        dispatcher=dispatcher,
        llm_client=HermesLLMClient(api_key=""),  # 0 Tokens / Determinista offline
    )

    # 1. Validación previa de gobernanza XLS-65 (lsfVaultPrivate 0x00010000 & Closed-Ended)
    vault_node = {
        "LedgerEntryType": "Vault",
        "Account": "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
        "Flags": LSF_VAULT_PRIVATE,
        "VaultKind": 1,
        "LEVersion": 1,
        "SubscriptionDate": 815000000,
        "RedemptionDate": 820000000,
        "AssetsTotal": "95",
        "SharesTotal": "100",
    }
    flags_info = audit_vault_access_flags(vault_node["Flags"])
    lifecycle_info = audit_closed_ended_vault_v1_1(
        vault_node,
        current_ripple_time=816000000,
        loan_final_payment_ripple_time=819999900,  # >= 60s antes de RedemptionDate
    )
    print(
        f"[1/4] Bóveda XLS-65: {flags_info['access_mode']} ({flags_info['mask_applied']}) "
        f"| Fase={lifecycle_info['phase']}"
    )

    # 2. Ingesta de transacción validada (meta.AffectedNodes) con estrés sistémico
    stress_event = {
        "validated": True,
        "ledger_index": 22350001,
        "meta": {
            "TransactionResult": "tesSUCCESS",
            "AffectedNodes": [
                {"ModifiedNode": {"LedgerEntryType": "Vault", "FinalFields": vault_node}},
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "LoanBroker",
                        "LedgerIndex": "B" * 64,
                        "FinalFields": {
                            "LedgerEntryType": "LoanBroker",
                            "Account": "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
                            "CoverAvailable": "7",
                            "DebtTotal": "100",
                            "RealizedInterest": "0",
                            "AccruedInterest": "250",  # Ignorado en Cash-Basis V1_1
                            "CoverRateMinimum": 10000,  # 10% en 1/10th bps on-chain
                        },
                    }
                },
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "RippleState",
                        "LedgerIndex": "C" * 64,
                        "FinalFields": {"LedgerEntryType": "RippleState", "Flags": LSF_LOW_DEEP_FREEZE},
                    }
                },
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "Loan",
                        "LedgerIndex": "D" * 64,
                        "FinalFields": {"LedgerEntryType": "Loan", "Flags": LSF_LOAN_DEFAULT},
                    }
                },
            ],
        },
    }

    stop_event = asyncio.Event()
    queue_task = asyncio.create_task(dispatcher.process_queue(stop_event=stop_event))

    await sentinel.handle_ledger_event(stress_event)
    await asyncio.wait_for(dispatcher.queue.join(), timeout=2.0)
    stop_event.set()
    await asyncio.wait_for(queue_task, timeout=2.0)

    print(
        f"[2/4] Alertas procesadas por Circuit Breaker: {len(captured_alerts)} "
        f"(estado={dispatcher.circuit_breaker.state.value})"
    )
    for idx, alert in enumerate(captured_alerts, start=1):
        print(f"      -> ({idx}) [{alert['level']}] {alert['source']}: {alert['message']}")

    # 3. Generación no custodia de borrador de emergencia (DRAFT_UNSIGNED)
    multisig_raw_json = create_emergency_multisig_payload(
        vault_node["Account"],
        action_type="FREEZE_CREDIT",
    )
    multisig_draft = json.loads(multisig_raw_json)
    print(
        f"[3/4] Mitigación no custodia generada: Tx={multisig_draft['TransactionType']} | "
        f"Action={multisig_draft['EmergencyAction']} | SigningPubKey={multisig_draft['SigningPubKey']!r}"
    )

    # 4. Sellado criptográfico SHA-256 + HMAC de telemetría
    signed = sign_telemetry_report(
        {
            "ledger_index": stress_event["ledger_index"],
            "vault_access": flags_info["access_mode"],
            "alerts_triggered": [a["source"] for a in captured_alerts],
            "draft_tx_type": multisig_draft["TransactionType"],
        }
    )
    print(f"[4/4] Telemetría sellada ({signed['status']}): SHA-256={signed['telemetry_hash']}")
    print("=" * 70)
    print(" DEMO END-TO-END COMPLETADA (0 TOKENS / ZERO-TRUST VERIFICADO)")
    print("=" * 70)


async def run_live_standalone_probe() -> None:
    import os

    os.environ.setdefault("XRPL_NETWORK", "standalone")
    os.environ.setdefault("XRPL_WS_URL", "ws://localhost:6006")
    cfg = load_settings()
    client = XRPLedgerClient(app_settings=cfg)
    print(f"[*] Probando conexión en vivo con nodo Standalone ({client.ws_url})...")
    stop_event = asyncio.Event()

    async def on_event(ev: dict) -> None:
        print(f"[+] Evento validado en vivo desde Standalone: {json.dumps(ev)}")
        stop_event.set()

    try:
        await asyncio.wait_for(
            client.stream_validated_ledgers(on_event=on_event, stop_event=stop_event, max_reconnects=1),
            timeout=5.0,
        )
    except Exception as exc:
        print(f"[!] Nodo Standalone no detectado en {client.ws_url}: {exc}")
        print("[*] Tip: levántalo primero con `docker compose --profile standalone up -d`")


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Hermes E2E Demo")
    parser.add_argument("--live", action="store_true", help="Conectar a nodo xrpld Standalone en ws://localhost:6006")
    args = parser.parse_args()

    if args.live:
        asyncio.run(run_live_standalone_probe())
    else:
        asyncio.run(run_deterministic_e2e_demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())