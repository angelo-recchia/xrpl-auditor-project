"""
Suite QA de integración para core/ledger_client.py y main.py.
Valida correlación JSON-RPC (101/102), descubrimiento de pseudo-cuentas,
re-sondeo 64-hex (201/202), parseo de meta.AffectedNodes y filtro de fallos tec.
"""

from decimal import Decimal
import asyncio
import copy
import json
import pytest

from config import load_settings
from core.ledger_client import XRPLedgerClient
from core.llm_client import HermesLLMClient
from dispatchers.alert_queue import AlertQueueDispatcher
from evaluators.rules import LSF_LOW_DEEP_FREEZE
from main import LSF_LOAN_DEFAULT, HermesSentinel, evaluate_snapshot_risk, extract_affected_nodes


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

    @pytest.mark.asyncio
    async def test_rehydrate_state_resolves_share_mpt_id_and_injects_outstanding_amount(self):
        client = XRPLedgerClient()
        share_mpt_id = "00000001" + "A" * 40
        sent = []
        frames = [
            json.dumps(
                {
                    "id": 101,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "Vault",
                            "AssetsTotal": "1000",
                            "Scale": 6,
                            "ShareMPTID": share_mpt_id,
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "id": 102,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "LoanBroker",
                            "CoverAvailable": "15",
                            "DebtTotal": "100",
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "id": 151,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "MPTokenIssuance",
                            "OutstandingAmount": "1000000000",
                        }
                    },
                }
            ),
        ]

        class MockWS:
            async def send(self, msg):
                sent.append(json.loads(msg))

            async def recv(self):
                return frames.pop(0)

        state = await client.rehydrate_state(MockWS(), "V" * 64, "B" * 64)

        assert [m["id"] for m in sent] == [101, 102, 151]
        assert sent[2] == {
            "id": 151,
            "command": "ledger_entry",
            "mpt_issuance": share_mpt_id,
            "ledger_index": "validated",
        }
        assert state["mpt_issuance"]["node"]["OutstandingAmount"] == "1000000000"
        assert state["vault"]["node"]["OutstandingAmount"] == "1000000000"

    @pytest.mark.asyncio
    async def test_stream_validated_ledgers_refresh_injects_mpt_even_when_251_arrives_before_201(self, monkeypatch):
        vault_id = "V" * 64
        share_mpt_id = "00000001" + "C" * 40
        monkeypatch.setenv("HERMES_VAULT_ID", vault_id)
        monkeypatch.setenv("HERMES_LOAN_BROKER_ID", "")
        cfg = load_settings()
        client = XRPLedgerClient(app_settings=cfg)

        sent = []
        frames = [
            json.dumps(
                {
                    "id": 101,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "Vault",
                            "AssetsTotal": "1000",
                            "Scale": 6,
                            "ShareMPTID": share_mpt_id,
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "id": 151,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "MPTokenIssuance",
                            "OutstandingAmount": "1000000000",
                        }
                    },
                }
            ),
            json.dumps({"id": 103, "status": "success", "result": {}}),
            json.dumps({"type": "ledgerClosed", "ledger_index": 22370000}),
            # En el refresco tras ledgerClosed, 251 (MPTokenIssuance) llega ANTES que 201 (Vault)
            json.dumps(
                {
                    "id": 251,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "MPTokenIssuance",
                            "OutstandingAmount": "2500000000",
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "id": 201,
                    "status": "success",
                    "result": {
                        "node": {
                            "LedgerEntryType": "Vault",
                            "AssetsTotal": "2500",
                            "Scale": 6,
                            "ShareMPTID": share_mpt_id,
                        }
                    },
                }
            ),
        ]

        class MockWS:
            async def send(self, msg):
                sent.append(json.loads(msg))

            async def recv(self):
                if not frames:
                    raise AssertionError("No se esperaban más tramas recv()")
                return frames.pop(0)

        class MockConnectCtx:
            async def __aenter__(self):
                return MockWS()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr("core.ledger_client.websockets.connect", lambda *args, **kwargs: MockConnectCtx())

        stop_event = asyncio.Event()
        rehydrated_snapshots = []
        seen_events = []

        async def on_rehydrated(snap):
            rehydrated_snapshots.append(copy.deepcopy(snap))
            if len(rehydrated_snapshots) >= 2:
                stop_event.set()

        async def on_event(ev):
            seen_events.append(ev)

        await asyncio.wait_for(
            client.stream_validated_ledgers(
                on_event=on_event,
                on_rehydrated=on_rehydrated,
                stop_event=stop_event,
                max_reconnects=0,
            ),
            timeout=5.0,
        )

        assert [m["id"] for m in sent] == [101, 151, 103, 201, 251]
        assert len(seen_events) == 1
        assert len(rehydrated_snapshots) == 2
        assert rehydrated_snapshots[0]["vault"]["node"]["OutstandingAmount"] == "1000000000"
        assert rehydrated_snapshots[1]["vault"]["node"]["AssetsTotal"] == "2500"
        assert rehydrated_snapshots[1]["vault"]["node"]["OutstandingAmount"] == "2500000000"


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
        assert extracted["vaults"] == []
        assert extracted["loan_brokers"] == []

    def test_extract_affected_nodes_collects_lists_and_filters_by_configured_ids(self, monkeypatch):
        vault_1 = "A" * 64
        vault_2 = "B" * 64
        broker_1 = "C" * 64
        broker_2 = "D" * 64

        event = {
            "validated": True,
            "meta": {
                "TransactionResult": "tesSUCCESS",
                "AffectedNodes": [
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "Vault",
                            "LedgerIndex": vault_1,
                            "FinalFields": {"AssetsTotal": "95", "SharesTotal": "100"},
                        }
                    },
                    {
                        "CreatedNode": {
                            "LedgerEntryType": "Vault",
                            "LedgerIndex": vault_2,
                            "NewFields": {"AssetsTotal": "100", "SharesTotal": "100"},
                        }
                    },
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "LoanBroker",
                            "LedgerIndex": broker_1,
                            "FinalFields": {"CoverAvailable": "8", "DebtTotal": "100", "CoverRateMinimum": 10000},
                        }
                    },
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "LoanBroker",
                            "LedgerIndex": broker_2,
                            "FinalFields": {"CoverAvailable": "15", "DebtTotal": "100", "CoverRateMinimum": 10000},
                        }
                    },
                ],
            },
        }

        monkeypatch.setenv("HERMES_VAULT_ID", "")
        monkeypatch.setenv("HERMES_LOAN_BROKER_ID", "")
        unfiltered = extract_affected_nodes(event, app_settings=load_settings())
        assert [v["ledger_index"] for v in unfiltered["vaults"]] == [vault_1, vault_2]
        assert [b["ledger_index"] for b in unfiltered["loan_brokers"]] == [broker_1, broker_2]

        monkeypatch.setenv("HERMES_VAULT_ID", vault_1.lower())
        monkeypatch.setenv("HERMES_LOAN_BROKER_ID", broker_2.lower())
        filtered_cfg = load_settings()
        filtered = extract_affected_nodes(event, app_settings=filtered_cfg)
        assert [v["ledger_index"] for v in filtered["vaults"]] == [vault_1]
        assert [b["ledger_index"] for b in filtered["loan_brokers"]] == [broker_2]

    @pytest.mark.asyncio
    async def test_sentinel_deduplication_cooldown_level_change_and_healthy_reset(self, tmp_path):
        now = [100.0]
        dispatcher = AlertQueueDispatcher(
            max_size=20,
            emergency_log_path=tmp_path / "emergency_halt.log",
        )
        sentinel = HermesSentinel(
            dispatcher=dispatcher,
            llm_client=HermesLLMClient(api_key=""),
            alert_cooldown_seconds=300.0,
            clock=lambda: now[0],
        )

        broker_id = "E" * 64

        def make_broker_state(cover: str, debt: str = "100"):
            return {
                "index": broker_id,
                "node": {
                    "LedgerEntryType": "LoanBroker",
                    "CoverAvailable": cover,
                    "DebtTotal": debt,
                    "CoverRateMinimum": 10000,  # 10%, warning_buffer = 12%
                },
            }

        # 1. Primera alerta WARNING -> se emite
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("11")})
        assert dispatcher.queue.qsize() == 1
        assert dispatcher.queue.get_nowait()["level"] == "WARNING"

        # 2. Mismo nivel dentro del cooldown -> suprimida
        now[0] = 150.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("11")})
        assert dispatcher.queue.empty()

        # 3. Cambio de nivel WARNING -> CRITICAL_DEEP_FREEZE -> se emite inmediatamente
        now[0] = 160.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("9")})
        assert dispatcher.queue.qsize() == 1
        assert dispatcher.queue.get_nowait()["level"] == "CRITICAL_DEEP_FREEZE"

        # 4. Mismo nivel CRITICAL_DEEP_FREEZE dentro del cooldown -> suprimida
        now[0] = 400.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("9")})
        assert dispatcher.queue.empty()

        # 5. Expirado el cooldown (>= 300s desde t=160) -> vuelve a emitir
        now[0] = 460.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("9")})
        assert dispatcher.queue.qsize() == 1
        assert dispatcher.queue.get_nowait()["level"] == "CRITICAL_DEEP_FREEZE"

        # 6. Recuperación a HEALTHY limpia el estado; nueva degradación inmediata vuelve a emitir
        now[0] = 470.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("20")})
        assert dispatcher.queue.empty()

        now[0] = 475.0
        await sentinel.handle_rehydrated_state({"loan_broker": make_broker_state("9")})
        assert dispatcher.queue.qsize() == 1
        assert dispatcher.queue.get_nowait()["level"] == "CRITICAL_DEEP_FREEZE"

    @pytest.mark.asyncio
    async def test_sentinel_evaluates_multiple_affected_nodes_and_filters_target_ids(self, monkeypatch, tmp_path):
        target_vault = "1" * 64
        other_vault = "2" * 64
        monkeypatch.setenv("HERMES_VAULT_ID", target_vault)
        cfg = load_settings()

        dispatcher = AlertQueueDispatcher(
            max_size=20,
            emergency_log_path=tmp_path / "emergency_halt.log",
        )
        sentinel = HermesSentinel(
            app_settings=cfg,
            dispatcher=dispatcher,
            llm_client=HermesLLMClient(api_key=""),
        )

        event = {
            "validated": True,
            "ledger_index": 22350010,
            "meta": {
                "TransactionResult": "tesSUCCESS",
                "AffectedNodes": [
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "Vault",
                            "LedgerIndex": other_vault,
                            "FinalFields": {"AssetsTotal": "50", "SharesTotal": "100"},
                        }
                    },
                    {
                        "ModifiedNode": {
                            "LedgerEntryType": "Vault",
                            "LedgerIndex": target_vault,
                            "FinalFields": {"AssetsTotal": "90", "SharesTotal": "100"},
                        }
                    },
                ],
            },
        }

        await sentinel.handle_ledger_event(event)
        assert dispatcher.queue.qsize() == 1
        alert = dispatcher.queue.get_nowait()
        assert alert["source"] == "XLS65_NAV_PARITY"
        assert alert["object_id"] == target_vault

    def test_evaluate_snapshot_risk_with_scale_outstanding_amount_and_unrealized_loss(self):
        vault_id = "F" * 64
        healthy_warn: list[tuple[str, str]] = []
        alerts_warn = evaluate_snapshot_risk(
            {
                "index": vault_id,
                "node": {
                    "LedgerEntryType": "Vault",
                    "AssetsTotal": "1000",
                    "OutstandingAmount": "1000000000",
                    "Scale": 6,
                    "LossUnrealized": "50",
                },
            },
            None,
            ledger_index=22360001,
            healthy_keys_out=healthy_warn,
        )

        assert ("XLS65_NAV_PARITY", vault_id) in healthy_warn
        assert len(alerts_warn) == 1
        assert alerts_warn[0]["source"] == "XLS65_UNREALIZED_LOSS"
        assert alerts_warn[0]["level"] == "WARNING"
        assert alerts_warn[0]["object_id"] == vault_id
        assert alerts_warn[0]["metrics"]["loss_ratio"] == Decimal("0.050000")

        healthy_recovered: list[tuple[str, str]] = []
        alerts_recovered = evaluate_snapshot_risk(
            {
                "index": vault_id,
                "node": {
                    "LedgerEntryType": "Vault",
                    "AssetsTotal": "1000",
                    "OutstandingAmount": "1000000000",
                    "Scale": 6,
                    "LossUnrealized": "0",
                },
            },
            None,
            ledger_index=22360002,
            healthy_keys_out=healthy_recovered,
        )

        assert alerts_recovered == []
        assert ("XLS65_NAV_PARITY", vault_id) in healthy_recovered
        assert ("XLS65_UNREALIZED_LOSS", vault_id) in healthy_recovered