"""
Suite QA de integración para core/ledger_client.py y main.py.
Valida correlación JSON-RPC (101/102), descubrimiento de pseudo-cuentas,
re-sondeo 64-hex (201/202), parseo de meta.AffectedNodes y filtro de fallos tec.
"""

import json
import pytest

from config import load_settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dispatchers.alert_queue import AlertQueueDispatcher
from evaluators.rules import LSF_LOW_DEEP_FREEZE
from main import LSF_LOAN_DEFAULT, HermesSentinel, extract_affected_nodes


class TestLedgerRehydrationCorrelation:
    @pytest.mark.asyncio
    async def test_rehydrate_state_handles_out_of_order_and_discovers_pseudo_account(self):
        client = XRPLedgerClient()
        frames = [
            json.dumps({"type": "ledgerClosed", "ledger_index": 1001}),
            json.dumps(
                {
                    "id": 102,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "LoanBroker",
                            "Account": "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
                        }
                    },
                }
            ),
            json.dumps({"type": "ledgerClosed", "ledger_index": 1002}),
            json.dumps({"id": 101, "status": "success", "result": {"node": {"LedgerEntryType": "Vault"}}}),
        ]
        sent = []

        class MockWS:
            async def send(self, msg):
                sent.append(json.loads(msg))

            async def recv(self):
                return frames.pop(0)

        state = await client.rehydrate_state(MockWS(), "A" * 64, "B" * 64)

        assert [m["id"] for m in sent] == [101, 102]
        assert state["vault"]["node"]["LedgerEntryType"] == "Vault"
        assert state["loan_broker"]["node"]["LedgerEntryType"] == "LoanBroker"
        assert "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh" in state["discovered_accounts"]
        assert [e["ledger_index"] for e in state["buffered_events"]] == [1001, 1002]

    @pytest.mark.asyncio
    async def test_request_ledger_refresh_sends_201_and_202_for_64hex_ids(self, monkeypatch):
        monkeypatch.setenv("HERMES_VAULT_ID", "A" * 64)
        monkeypatch.setenv("HERMES_LOAN_BROKER_ID", "B" * 64)
        cfg = load_settings()
        client = XRPLedgerClient(app_settings=cfg)

        sent = []
        pending = {}

        class MockWS:
            async def send(self, msg):
                sent.append(json.loads(msg))

        await client.request_ledger_refresh(MockWS(), pending)

        assert pending == {201: "vault", 202: "loan_broker"}
        assert [m["id"] for m in sent] == [201, 202]
        assert all(m["command"] == "ledger_entry" for m in sent)


class TestMainAffectedNodesAndSentinel:
    @pytest.mark.asyncio
    async def test_handle_ledger_event_parses_affected_nodes_and_tenth_bps(self, tmp_path):
        dispatcher = AlertQueueDispatcher(
            max_size=10,
            emergency_log_path=tmp_path / "emergency_halt.log",
        )
        sentinel = HermesSentinel(
            dispatcher=dispatcher,
            llm_client=HermesLLMClient(api_key=""),
        )

        event = {
            "validated": True,
            "ledger_index": 22325000,
            "meta": {
                "TransactionResult": "tesSUCCESS",
                "AffectedNodes": [
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "LoanBroker",
                            "LedgerIndex": "B" * 64,
                            "FinalFields": {
                                "LedgerEntryType": "LoanBroker",
                                "CoverAvailable": "9",
                                "DebtTotal": "100",
                                "CoverRateMinimum": 10000,  # 10% en 1/10th bps
                            },
                        }
                    },
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "RippleState",
                            "LedgerIndex": "C" * 64,
                            "FinalFields": {
                                "LedgerEntryType": "RippleState",
                                "Flags": LSF_LOW_DEEP_FREEZE,
                            },
                        }
                    },
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "Loan",
                            "LedgerIndex": "D" * 64,
                            "FinalFields": {
                                "LedgerEntryType": "Loan",
                                "Flags": LSF_LOAN_DEFAULT,
                            },
                        }
                    },
                ],
            },
        }

        await sentinel.handle_ledger_event(event)

        levels = []
        sources = []
        while not dispatcher.queue.empty():
            item = dispatcher.queue.get_nowait()
            levels.append(item["level"])
            sources.append(item["source"])

        assert "CRITICAL_DEEP_FREEZE" in levels
        assert "XRPL_TRUSTLINE_DEEP_FREEZE" in sources
        assert "XLS66_LOAN_DEFAULT" in sources

    def test_extract_affected_nodes_ignores_failed_tec_transactions(self):
        failed_event = {
            "validated": True,
            "meta": {
                "TransactionResult": "tecNO_PERMISSION",
                "AffectedNodes": [
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "LoanBroker",
                            "FinalFields": {"CoverAvailable": "1", "DebtTotal": "100"},
                        }
                    }
                ],
            },
        }
        extracted = extract_affected_nodes(failed_event)
        assert extracted["loan_broker"] is None