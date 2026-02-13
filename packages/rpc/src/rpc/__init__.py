from rpc.client import RPC_Client
from rpc.exceptions import (
    InvalidAddressException,
    RPCConnectionException,
    RPCException,
    RPCTimeoutException,
    TransactionNotFoundException,
)
from rpc.models import (
    RPCGetBalanceResult,
    RPCGetSignaturesForAddressResult,
    RPCGetTokenAccountsByOwnerResult,
    RPCGetTokenAccountsResult,
    RPCGetTransactionResult,
    RPCMessageModel,
    RPCMetaTransaction,
    RPCResponse,
    RPCSignatureInfo,
    RPCTokenAccounts,
    RPCTransaction,
)

__version__ = "0.1.0"

__all__ = [
    # Cliente principal
    "RPC_Client",
    # Excepciones
    "RPCException",
    "InvalidAddressException",
    "TransactionNotFoundException",
    "RPCTimeoutException",
    "RPCConnectionException",
    # Modelos de respuesta
    "RPCGetTokenAccountsResult",
    "RPCGetTokenAccountsByOwnerResult",
    "RPCGetBalanceResult",
    "RPCGetSignaturesForAddressResult",
    "RPCGetTransactionResult",
    "RPCSignatureInfo",
    "RPCTokenAccounts",
    "RPCMetaTransaction",
    "RPCTransaction",
    "RPCMessageModel",
    "RPCResponse",
]


def main() -> None:
    print("Hello from rpc!")
