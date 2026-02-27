"""Cliente RPC para interactuar con la blockchain de Solana."""

from typing import Any, Awaitable, Callable, Literal

from shared_lib.baseclient import Client

from rpc.exceptions import RPCException
from rpc.models import (
    RPCGetBalanceResult,
    RPCGetSignaturesForAddressResult,
    RPCGetTokenAccountsByOwnerResult,
    RPCGetTokenAccountsResult,
    RPCGetTransactionResult,
    RPCSignatureInfo,
)
from shared_lib.utils.cex import CEXs


# Tipos de encoding soportados por Solana RPC
EncodingType = Literal["json", "jsonParsed", "base58", "base64"]
# Niveles de commitment soportados
CommitmentLevel = Literal["processed", "confirmed", "finalized"]


class RPC_Client(Client):
    """Cliente para interactuar con el RPC de Solana.

    Este cliente proporciona métodos para consultar información de la blockchain
    de Solana, incluyendo cuentas de tokens y transacciones.

    Attributes:
        BASE_URL: URL por defecto del RPC de Solana mainnet-beta

    Example:
        >>> async with RPC_Client() as client:
        ...     result = await client.get_token_accounts(owner="...")
        ...     print(f"Total cuentas: {result.total}")
    """

    BASE_URL = "https://api.mainnet-beta.solana.com"

    def __init__(
        self,
        base_url: str = "https://api.mainnet-beta.solana.com",
        timeout: float = 5.0,
    ):
        """Inicializa el cliente RPC de Solana.

        Args:
            base_url: URL del endpoint RPC de Solana. Por defecto usa mainnet-beta.
            timeout: Tiempo máximo de espera para las peticiones en segundos.
                Por defecto 30 segundos.

        Example:
            >>> # Usar mainnet (por defecto)
            >>> client = RPC_Client()
            >>>
            >>> # Usar devnet
            >>> client = RPC_Client(base_url="https://api.devnet.solana.com")
            >>>
            >>> # Con timeout personalizado
            >>> client = RPC_Client(timeout=60.0)
        """
        super().__init__(base_url=base_url, timeout=timeout)

    async def get_token_accounts(
        self,
        owner: str,
        mint: str | None = None,
        show_zero_balance: bool = False,
        limit: int = 10,
    ) -> RPCGetTokenAccountsResult:
        """Obtiene las cuentas de tokens asociadas a una wallet.

        Args:
            owner: Dirección de la wallet propietaria (formato base58).
            mint: Dirección del mint del token para filtrar resultados.
                Si es None, retorna todas las cuentas de tokens. Por defecto None.
            show_zero_balance: Si True, incluye cuentas con balance cero.
                Por defecto False.
            limit: Número máximo de cuentas a retornar. Por defecto 10.

        Returns:
            Objeto RPCGetTokenAccountsResult conteniendo:
                - total: Número total de cuentas encontradas
                - limit: Límite aplicado
                - cursor: Cursor para paginación (si existe)
                - token_accounts: Lista de cuentas de tokens

        Raises:
            ValueError: Si la dirección del owner es inválida.
            RPCException: Si ocurre un error en la llamada RPC.

        Example:
            >>> # Obtener todas las cuentas
            >>> result = await client.get_token_accounts(
            ...     owner="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
            ... )
            >>>
            >>> # Filtrar por un token específico
            >>> result = await client.get_token_accounts(
            ...     owner="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            ...     mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            ... )
        """
        if not owner or not isinstance(owner, str):
            raise ValueError("La dirección del owner debe ser una cadena válida")

        method = "getTokenAccounts"
        params = {
            "limit": limit,
            "owner": owner,
            "options": {
                "showZeroBalance": show_zero_balance,
            },
        }

        # Solo añadir mint si se proporciona
        if mint is not None:
            params["mint"] = mint

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        result = await self._post(payload=payload)

        if "error" in result:
            error_msg = result["error"].get("message", "Error desconocido")
            raise RPCException(f"Error RPC: {error_msg}")

        return RPCGetTokenAccountsResult(**result["result"])

    async def get_transaction(
        self,
        signature: str,
        encoding: EncodingType = "json",
        commitment: CommitmentLevel = "finalized",
        from_pk: str | None = None,
        to_pk: str | None = None,
    ) -> RPCGetTransactionResult:
        """Obtiene los detalles de una transacción por su firma.

        Args:
            signature: Firma de la transacción (formato base58).
            encoding: Formato de codificación de la respuesta. Por defecto "json".
                Opciones: "json", "jsonParsed", "base58", "base64".
            commitment: Nivel de confirmación de la transacción.
                Por defecto "finalized". Opciones: "processed", "confirmed", "finalized".
            from_pk: Dirección del remitente para calcular SOL enviado. Opcional.
            to_pk: Dirección del destinatario para calcular SOL recibido. Opcional.

        Returns:
            Objeto RPCGetTransactionResult conteniendo:
                - meta: Metadatos de la transacción (balances, fees, etc.)
                - transaction: Datos de la transacción (mensaje, firmas, etc.)
                - sol_amount: SOL recibido en to_pk (si se proporciona)
                - send_sol_amount: SOL enviado desde from_pk (si se proporciona)

        Raises:
            ValueError: Si la firma es inválida (demasiado corta o no es string).
            RPCException: Si ocurre un error en la llamada RPC o la transacción
                no se encuentra.

        Example:
            >>> # Obtener transacción básica
            >>> tx = await client.get_transaction(
            ...     signature="5wJG7K9qY1V6P9Z3Y8X9..."
            ... )
            >>>
            >>> # Calcular SOL transferido
            >>> tx = await client.get_transaction(
            ...     signature="5wJG7K9qY1V6P9Z3Y8X9...",
            ...     from_pk="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            ...     to_pk="8qbHbw2BbbTHBW1sbeqakYXVKRQM8Ne7pLK7m6CVfeR"
            ... )
            >>> print(f"SOL enviado: {tx.send_sol_amount / 1e9} SOL")
        """
        if not isinstance(signature, str) or len(signature) < 20:
            raise ValueError(
                "La firma debe ser una cadena válida de al menos 20 caracteres"
            )

        method = "getTransaction"
        params = [
            signature,
            {
                "commitment": commitment,
                "encoding": encoding,
                "maxSupportedTransactionVersion": 0,
            },
        ]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        result = await self._post(payload=payload)

        if "error" in result:
            error_msg = result["error"].get("message", "Error desconocido")
            raise RPCException(f"Error RPC: {error_msg}")

        if result.get("result") is None:
            raise RPCException(f"Transacción no encontrada: {signature}")

        return RPCGetTransactionResult(
            **result["result"],
            from_pk=from_pk,
            to_pk=to_pk,
        )

    async def get_token_accounts_by_owner(
        self,
        owner: str,
        mint: str | None = None,
        commitment: CommitmentLevel = "finalized",
        encoding: EncodingType = "jsonParsed",
    ) -> RPCGetTokenAccountsByOwnerResult:
        """Consulta `getTokenAccountsByOwner` del RPC de Solana.

        Construye el payload en formato de lista de parámetros que acepta
        el endpoint y retorna un modelo tipado con la respuesta.

        Args:
            owner: Dirección del owner (base58).
            mint: Mint del token para filtrar (opcional).
            commitment: Nivel de confirmación (processed|confirmed|finalized).
            encoding: Encoding de la respuesta (jsonParsed|json|base58|base64).

        Returns:
            RPCGetTokenAccountsByOwnerResult con `context` y `value` (lista de cuentas).

        Raises:
            ValueError: Si `owner` no es válido.
            RPCException: Si el RPC responde con error.
        """
        if not owner or not isinstance(owner, str):
            raise ValueError("La dirección del owner debe ser una cadena válida")

        method = "getTokenAccountsByOwner"

        # Parametros: [owner, filterObject, options]
        filter_obj = {"mint": mint} if mint is not None else {}
        options = {"commitment": commitment, "encoding": encoding}
        params = [owner, filter_obj or {}, options]

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        result = await self._post(payload=payload)

        if "error" in result:
            error_msg = result["error"].get("message", "Error desconocido")
            raise RPCException(f"Error RPC: {error_msg}")

        return RPCGetTokenAccountsByOwnerResult(**result["result"])

    async def get_balance(
        self,
        pubkey: str,
        commitment: CommitmentLevel = "finalized",
    ) -> RPCGetBalanceResult:
        """Obtiene el balance de una cuenta en lamports.

        Args:
            pubkey: Dirección de la cuenta (formato base58).
            commitment: Nivel de confirmación para consultar el balance.
                Por defecto "finalized". Opciones: "processed", "confirmed", "finalized".

        Returns:
            Balance de la cuenta en lamports (RPCGetBalanceResult).

        Raises:
            ValueError: Si la dirección es inválida.
            RPCException: Si ocurre un error en la llamada RPC.

        Example:
            >>> balance = await client.get_balance(
            ...     pubkey="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
            ... )
            >>> print(f"Balance: {balance / 1e9} SOL")
        """
        if not pubkey or not isinstance(pubkey, str):
            raise ValueError("La dirección de la cuenta debe ser una cadena válida")

        method = "getBalance"
        params = [pubkey, {"commitment": commitment}]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        result = await self._post(payload=payload)

        if "error" in result:
            error_msg = result["error"].get("message", "Error desconocido")
            raise RPCException(f"Error RPC: {error_msg}")

        return RPCGetBalanceResult(**result["result"])

    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 1000,
        before: str | None = None,
        until: str | None = None,
        min_context_slot: int | None = None,
        commitment: CommitmentLevel = "finalized",
    ) -> RPCGetSignaturesForAddressResult:
        """Obtiene las firmas de transacciones para una dirección.

        Args:
            address: Dirección de la cuenta (formato base58).
            limit: Número máximo de firmas a retornar (1-1000). Por defecto 1000.
            before: Empezar búsqueda antes de esta firma. Opcional.
            until: Buscar hasta esta firma. Opcional.
            commitment: Nivel de confirmación. Por defecto "finalized".

        Returns:
            RPCGetSignaturesForAddressResult con lista de firmas encontradas.

        Raises:
            ValueError: Si la dirección es inválida o limit está fuera de rango.
            RPCException: Si ocurre un error en la llamada RPC.

        Example:
            >>> # Obtener últimas 10 firmas
            >>> result = await client.get_signatures_for_address(
            ...     address="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            ...     limit=10
            ... )
            >>> for sig_info in result.signatures:
            ...     print(f"Signature: {sig_info.signature}")
            ...     print(f"  Slot: {sig_info.slot}")
            ...     print(f"  Status: {sig_info.confirmationStatus}")
        """
        if not address or not isinstance(address, str):
            raise ValueError("La dirección debe ser una cadena válida")

        if not 1 <= limit <= 1000:
            raise ValueError("El límite debe estar entre 1 y 1000")

        method = "getSignaturesForAddress"
        options: dict[str, Any] = {
            "limit": limit,
            "commitment": commitment,
        }

        if before is not None:
            options["before"] = before
        if until is not None:
            options["until"] = until
        if min_context_slot is not None:
            options["minContextSlot"] = min_context_slot

        params = [address, options]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        result = await self._post(payload=payload)

        if "error" in result:
            error_msg = result["error"].get("message", "Error desconocido")
            raise RPCException(f"Error RPC: {error_msg}")

        # El resultado es directamente una lista de objetos de firma
        signatures_data = result.get("result", [])
        return RPCGetSignaturesForAddressResult(signatures=signatures_data)

    async def trace_wallet_origin(
        self,
        address: str,
        goal_address: str | None = None,
        size_limit: int = 10,
        max_depth: int = 5,
        pages: int = 1,
        handle_address_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Traza el origen de los fondos de una wallet siguiendo transacciones.

        Args:
            starting_address: Dirección inicial para comenzar el rastreo.
            goal_address: Dirección objetivo para detener el rastreo. Opcional.
            max_depth: Número máximo de saltos (transacciones) a seguir.
            size_limit: Número de transacciones a revisar por cada dirección. Por defecto 10.

        Returns:
            None. Imprime en consola el rastro de transacciones.

        Raises:
            ValueError: Si la dirección es inválida.
            RPCException: Si ocurre un error en la llamada RPC.
        """

        for hop in range(max_depth):
            print(f"Hop {hop + 1}: Address {address}")
            if goal_address and address == goal_address:
                print(f"Reached goal address: {goal_address}")
                break
            if address in CEXs:
                print(f"Reached known CEX address: {address}")
                break

            if handle_address_callback:
                await handle_address_callback(address)

            before = None  # Puedes implementar paginación usando el último signature de la página anterior
            for page in range(pages):
                print(
                    f"  Page {page + 1}: Fetching signatures for address {address}..."
                )
                result = await self.get_signatures_for_address(
                    address=address,
                    limit=size_limit,
                    before=before,
                )
                if result.signatures:
                    before = result.signatures[-1].signature
                    if len(result.signatures) < size_limit:
                        funding_signature = result.signatures[-1].signature
                        result = await self.get_transaction(signature=funding_signature)
                        address = result.transaction.message.account_keys[0]
                        print(f"  Found funding txn: {funding_signature}")
                        print(f"  New address: {address}")
                        print(
                            f"  SOL funding: {result.meta.delta_balances[0] / 1e9} SOL"
                        )
                        break  # No hay más transacciones para esta dirección
                    else:
                        continue
                else:
                    funding_signature = before
                    if funding_signature is None:
                        print(
                            f"No signatures found for address {address} on page {page + 1}."
                        )
                        break
                    result = await self.get_transaction(signature=funding_signature)
                    address = result.transaction.message.account_keys[0]
                    print(f"  Found funding txn: {funding_signature}")
                    print(f"  New address: {address}")
                    print(f"  SOL funding: {result.meta.delta_balances[0] / 1e9} SOL")
                    break
            else:
                print(
                    f"The pages limit of {pages} was reached for address {address} without finding more signatures."
                )
                break

    async def fetch_and_process_wallet_signatures(
        self,
        address: str,
        page_size: int = 10,
        max_pages: int = 5,
        handle_signature_callback: Callable[[RPCSignatureInfo], Awaitable[None]]
        | None = None,
    ):
        before = None
        for page in range(max_pages):
            print(f"Fetching page {page + 1} of signatures for address {address}...")
            result = await self.get_signatures_for_address(
                address=address,
                limit=page_size,
                before=before,
            )
            before = result.signatures[-1].signature if result.signatures else None

            for signature in result.signatures:
                await handle_signature_callback(
                    signature
                ) if handle_signature_callback else None

            if len(result.signatures) < page_size:
                print("No more signatures to fetch.")
                break

            # result = await self.get_signatures_for_address(
            #     address=address,
            #     limit=size_limit,
            # )

            # if len(result.signatures) < size_limit:
            #     funding_signature = result.signatures[-1].signature
            #     result = await self.get_transaction(signature=funding_signature)
            #     address = result.transaction.message.account_keys[0]
            #     print(f"  Found funding txn: {funding_signature}")
            #     print(f"  New address: {address}")
            #     print(f"  SOL change: {result.meta.delta_balances[0] / 1e9} SOL")

    #         if len(result.signatures) == 0:
    #             print("  No se encontraron más transacciones.")
    #             break

    #         txn = result.signatures[-1]
    #         result = await self.get_transaction(signature=txn.signature)

    #         if result.meta.delta_balances[0] > 0:
    #             print("  🚀 ¡Instrucción de recepción detectada!")
    #             break
    #         elif result.meta.delta_balances[0] < 0:
    #             address = result.transaction.message.account_keys[0]
    #             print(f"Found send txn from address: {address}")

    #         return
    #         result = await rpc_client.get_signatures_for_address(
    #         # address="FzzetY6rk2VgPAsqThqDbL8X1RB1u3TP4xLJKoG7MVHY",
    #         address="28QrY82PD7Ba7owMcQAiBVDrovYgKP8HZFFY6gN48DLB",
    #         # before="4TjEdy1pANtr5oL7ToAcPWMiEA5EAcZK1UH5vib78wrPeMGsUYqfB2RJnsTHBWYrABwARso5fLjp85AjTGdcU9UW",
    #         before="5JHDEhkoP5k2Y4KJRX3Vb5LgPi2W2QPjTc9zHT1BMbDsPLb9wcakg7g71RimBHxSwCB3NZDwkt2nwHJurynwRXmW",
    #         commitment="finalized",
    #         limit=10,
    #     )
    #     for i in range(4):
    #         if 0 < len(result.signatures):
    #             txn = result.signatures[-1]
    #             result = await rpc_client.get_transaction(signature=txn.signature)
    #             if DEBRIDGE in result.transaction.message.account_keys:
    #                 print(
    #                     f"Found debridge txn:{result.meta.delta_balances[0] / 1e9} SOL"
    #                 )
    #                 break
    #             elif result.meta.delta_balances[0] < 0:
    #                 address = result.transaction.message.account_keys[0]
    #                 print(f"Found send txn from address: {address}")
    #                 print(f"Amount: {result.meta.delta_balances[0] / 1e9} SOL")
    #                 result = await rpc_client.get_signatures_for_address(
    #                     address=address, limit=100
    #                 )
    #                 # print(f"Last signature: {result.signatures[-1]}")
    #             else:
    #                 break
    #         else:
    #             print("No more signatures to process.")
