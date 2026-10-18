"""
Módulo: scripts/rpc_connector.py
Proyecto: Hermes (XRPL XLS-65/66)
Descripción: Conector off-chain de lectura pasiva vía RPC para XRPL Devnet/Testnet.
             Soporta sesión persistente con reintentos, detección de errores rippled
             y extracción de estado de Bóvedas XLS-65 y Préstamos XLS-66.
"""

import json
from typing import Any, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class XRPLRPCConnector:
    # Por defecto XRPL Devnet según directivas del proyecto (SOUL.md)
    DEFAULT_DEVNET_RPC = "https://s.devnet.rippletest.net:51234"

    def __init__(self, rpc_url: Optional[str] = None, timeout: int = 8):
        """
        Inicializa el conector RPC con sesión persistente y reintentos automáticos.
        """
        self.rpc_url = rpc_url or self.DEFAULT_DEVNET_RPC
        self.timeout = timeout
        
        # Sesión HTTP persistente con reintentos en errores 5xx
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.4, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def query_ledger_entry(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envía una petición POST JSON-RPC y valida tanto el transporte HTTP como la respuesta de rippled.
        """
        try:
            response = self.session.post(
                self.rpc_url,
                json=request_body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": True,
                "error_type": "TRANSPORT_ERROR",
                "message": f"Fallo de conexión HTTP con el nodo RPC: {str(e)}"
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": True,
                "error_type": "JSON_DECODE_ERROR",
                "message": f"Respuesta no válida del nodo RPC: {str(e)}"
            }

        # Validación a nivel de protocolo rippled (HTTP 200 pero error en ledger)
        res_payload = data.get("result", {})
        if res_payload.get("status") == "error" or "error" in res_payload:
            return {
                "success": False,
                "error": True,
                "error_type": "RIPPLED_ERROR",
                "rippled_error": res_payload.get("error"),
                "message": res_payload.get("error_message", "Error reportado por el nodo rippled"),
                "raw_result": res_payload
            }

        return {
            "success": True,
            "error": False,
            "result": res_payload
        }

    def fetch_ledger_entry_by_index(self, index_hash: str) -> Dict[str, Any]:
        """
        Consulta pasiva de cualquier objeto de ledger (Vault XLS-65 o Loan XLS-66) por su hash de 256 bits.
        """
        payload = {
            "method": "ledger_entry",
            "params": [
                {
                    "index": index_hash,
                    "ledger_index": "validated"
                }
            ]
        }
        res = self.query_ledger_entry(payload)
        if not res.get("success"):
            return res

        node_data = res.get("result", {}).get("node", {})
        return {
            "success": True,
            "error": False,
            "index": index_hash,
            "ledger_entry_type": node_data.get("LedgerEntryType"),
            "node": node_data,
            "status": "Lectura RPC Exitosa"
        }

    def fetch_vault_state(self, vault_id: str) -> Dict[str, Any]:
        """
        Consulta específica de un objeto Vault (XLS-65).
        """
        res = self.fetch_ledger_entry_by_index(vault_id)
        if not res.get("success"):
            return res
        
        node = res.get("node", {})
        res["vault_summary"] = {
            "account": node.get("Account"),
            "assets_total": node.get("AssetsTotal"),
            "assets_available": node.get("AssetsAvailable"),
            "share_mpt_id": node.get("ShareMPTID"),
            "sequence": node.get("Sequence")
        }
        return res

    def fetch_loan_state(self, loan_id: str) -> Dict[str, Any]:
        """
        Consulta específica de un objeto Loan (XLS-66).
        """
        res = self.fetch_ledger_entry_by_index(loan_id)
        if not res.get("success"):
            return res
        
        node = res.get("node", {})
        res["loan_summary"] = {
            "borrower": node.get("Borrower") or node.get("Account"),
            "principal_outstanding": node.get("PrincipalOutstanding") or node.get("Amount"),
            "interest_rate": node.get("InterestRate"),
            "maturity_date": node.get("MaturityDate")
        }
        return res
