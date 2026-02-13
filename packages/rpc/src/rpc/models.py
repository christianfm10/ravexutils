"""Modelos de datos para las respuestas del RPC de Solana.

Este módulo contiene los modelos Pydantic que representan las estructuras
de datos retornadas por el RPC de Solana.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class APIBaseModel(BaseModel):
    """Clase base para todos los modelos de API.

    Proporciona serialización JSON mejorada con formato legible.
    """

    def __str__(self) -> str:
        """Retorna una representación JSON formateada del modelo."""
        return self.model_dump_json(indent=2, ensure_ascii=False)


class RPCResponse(APIBaseModel):
    """Respuesta genérica del RPC de Solana.

    Attributes:
        jsonrpc: Versión del protocolo JSON-RPC (siempre "2.0")
        result: Resultado de la llamada RPC
        id: Identificador de la petición
        error: Error si la llamada falló, None en caso contrario
    """

    jsonrpc: str
    result: dict[str, Any]
    id: int
    error: dict[str, Any] | None = None


# -----------------------------------GetTokenAccounts Models-----------------------------------#


class RPCTokenAccounts(APIBaseModel):
    """Representa una cuenta de token individual en Solana.

    Attributes:
        address: Dirección pública de la cuenta de token (formato base58)
        mint: Dirección del mint del token (formato base58)
        owner: Dirección del propietario de la cuenta (formato base58)
        amount: Balance en unidades mínimas del token (sin decimales)
        delegated_amount: Cantidad delegada a otra cuenta
        frozen: Indica si la cuenta está congelada
    """

    address: str
    mint: str
    owner: str
    amount: int
    delegated_amount: int
    frozen: bool

    @field_validator("amount", "delegated_amount")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Valida que los montos sean no negativos."""
        if v < 0:
            raise ValueError("Los montos deben ser no negativos")
        return v


class RPCGetTokenAccountsResult(APIBaseModel):
    """Resultado de una consulta de cuentas de tokens.

    Attributes:
        total: Número total de cuentas encontradas
        limit: Límite aplicado en la consulta
        cursor: Cursor para paginación (None si no hay más resultados)
        token_accounts: Lista de cuentas de tokens encontradas
    """

    total: int
    limit: int
    cursor: str | None = None
    token_accounts: list[RPCTokenAccounts]

    @field_validator("total", "limit")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Valida que total y limit sean positivos."""
        if v < 0:
            raise ValueError("Total y limit deben ser no negativos")
        return v


# -----------------------------------GetTransaction Models-----------------------------------#


class RPCMetaTransaction(APIBaseModel):
    """Metadatos de una transacción de Solana.

    Contiene información sobre los cambios de estado causados por la transacción,
    incluyendo balances antes y después de la ejecución.

    Attributes:
        post_balances: Balances de las cuentas después de la transacción (lamports)
        pre_balances: Balances de las cuentas antes de la transacción (lamports)
        delta_balances: Cambios en los balances (post - pre) calculados automáticamente
    """

    post_balances: list[int] = Field(..., alias="postBalances")
    pre_balances: list[int] = Field(..., alias="preBalances")
    pre_token_balances: list[dict] = Field(..., alias="preTokenBalances")
    post_token_balances: list[dict] = Field(..., alias="postTokenBalances")
    delta_balances: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def calculate_delta_balance(self) -> "RPCMetaTransaction":
        """Calcula automáticamente los cambios de balance para cada cuenta.

        delta_balance[i] = post_balances[i] - pre_balances[i]

        Un valor positivo indica que la cuenta recibió lamports.
        Un valor negativo indica que la cuenta envió lamports.
        """
        if len(self.pre_balances) != len(self.post_balances):
            raise ValueError(
                "pre_balances y post_balances deben tener la misma longitud"
            )

        self.delta_balances = [
            post - pre
            for post, pre in zip(self.post_balances, self.pre_balances, strict=False)
        ]
        return self


class RPCMessageModel(APIBaseModel):
    """Mensaje de una transacción de Solana.

    Attributes:
        account_keys: Lista de direcciones de cuentas involucradas en la transacción
    """

    account_keys: list[str] = Field(..., alias="accountKeys")


class RPCTransaction(APIBaseModel):
    """Datos de una transacción de Solana.

    Attributes:
        message: Mensaje de la transacción conteniendo las cuentas y instrucciones
    """

    message: RPCMessageModel


class RPCGetTransactionResult(APIBaseModel):
    """Resultado completo de una consulta de transacción.

    Attributes:
        meta: Metadatos de la transacción (balances, fees, etc.)
        transaction: Datos de la transacción (mensaje, firmas, etc.)
        to_pk: Dirección del destinatario para cálculo de SOL recibido (opcional)
        from_pk: Dirección del remitente para cálculo de SOL enviado (opcional)
        sol_amount: SOL recibido en lamports (calculado si to_pk está presente)
        send_sol_amount: SOL enviado en lamports (calculado si from_pk está presente)

    Note:
        - 1 SOL = 1,000,000,000 lamports
        - Los montos se calculan automáticamente si se proporcionan to_pk o from_pk
    """

    meta: RPCMetaTransaction
    transaction: RPCTransaction
    to_pk: str | None = None
    from_pk: str | None = None
    sol_amount: float | None = None
    send_sol_amount: float | None = None
    buyed_tokens_amount: int | None = None

    @model_validator(mode="after")
    def set_buyed_tokens(self) -> "RPCGetTransactionResult":
        if self.meta.post_token_balances:
            for x in self.meta.post_token_balances:
                if x["owner"] == self.to_pk:
                    self.buyed_tokens_amount = x["uiTokenAmount"]["amount"]
        return self

    @model_validator(mode="after")
    def calculate_sol_amounts(self) -> "RPCGetTransactionResult":
        """Calcula los montos de SOL recibidos y enviados.

        Si to_pk está presente, calcula sol_amount como el cambio absoluto
        en el balance de esa cuenta.

        Si from_pk está presente, calcula send_sol_amount como el cambio absoluto
        en el balance de esa cuenta.

        Los montos se retornan en lamports (unidades mínimas).
        Para convertir a SOL: sol_amount / 1_000_000_000
        """
        account_keys = self.transaction.message.account_keys

        # Calcular SOL recibido en to_pk
        if self.to_pk is not None:
            try:
                index = account_keys.index(self.to_pk)
                if index < len(self.meta.pre_balances) and index < len(
                    self.meta.post_balances
                ):
                    self.sol_amount = abs(
                        self.meta.post_balances[index] - self.meta.pre_balances[index]
                    )
                else:
                    self.sol_amount = None
            except ValueError:
                # to_pk no está en account_keys
                self.sol_amount = None

        # Calcular SOL enviado desde from_pk
        if self.from_pk is not None:
            try:
                index = account_keys.index(self.from_pk)
                if index < len(self.meta.pre_balances) and index < len(
                    self.meta.post_balances
                ):
                    self.send_sol_amount = abs(
                        self.meta.post_balances[index] - self.meta.pre_balances[index]
                    )
                else:
                    self.send_sol_amount = None
            except ValueError:
                # from_pk no está en account_keys
                self.send_sol_amount = None

        return self


# -----------------------------------GetBalance Model-----------------------------------#
class RPCGetBalanceResult(APIBaseModel):
    """Resultado de una consulta de balance de cuenta.

    Attributes:
        value: Balance de la cuenta en lamports
    """

    value: int


# -----------------------------------GetTokenAccountsByOwner Models-----------------------------------#


class RPCContext(APIBaseModel):
    """Contexto devuelto por algunas respuestas RPC (slot, apiVersion)."""

    slot: int
    apiVersion: str | None = None


class RPCTokenAmount(APIBaseModel):
    """Modelo para tokenAmount dentro del parsed info."""

    amount: str
    decimals: int | None = None
    uiAmount: float | None = None
    uiAmountString: str | None = None


class RPCParsedInfo(APIBaseModel):
    """Información parseada del account.data.parsed."""

    isNative: bool | None = None
    mint: str | None = None
    owner: str | None = None
    state: str | None = None
    tokenAmount: RPCTokenAmount | None = None


class RPCDataParsed(APIBaseModel):
    """Estructura de account.data cuando el program es spl-token y está parsed."""

    program: str
    parsed: dict | None = None
    space: int | None = None


class RPCAccountInner(APIBaseModel):
    """Modelo para el campo `account` dentro del valor del response."""

    lamports: int
    data: dict
    owner: str
    executable: bool
    rentEpoch: int
    space: int | None = None


class RPCValueItem(APIBaseModel):
    """Item individual en la lista `value` de la respuesta getTokenAccountsByOwner."""

    pubkey: str
    account: RPCAccountInner


class RPCGetTokenAccountsByOwnerResult(APIBaseModel):
    """Resultado del método getTokenAccountsByOwner.

    Attributes:
        context: Información de contexto (slot, apiVersion)
        value: Lista de cuentas encontradas (pubkey + account)
    """

    context: RPCContext
    value: list[RPCValueItem]


# -----------------------------------GetSignaturesForAddress Models-----------------------------------#


class RPCSignatureInfo(APIBaseModel):
    """Información de una firma de transacción.

    Attributes:
        signature: Firma de la transacción (base58)
        slot: Slot en el que se confirmó la transacción
        err: Error si la transacción falló, None si fue exitosa
        memo: Memo asociado a la transacción (opcional)
        blockTime: Timestamp Unix de cuando se procesó la transacción (opcional)
        confirmationStatus: Estado de confirmación (finalized, confirmed, processed)
    """

    signature: str
    slot: int
    err: dict[str, Any] | None = None
    memo: str | None = None
    blockTime: int | None = None
    confirmationStatus: str | None = None


class RPCGetSignaturesForAddressResult(APIBaseModel):
    """Resultado del método getSignaturesForAddress.

    Retorna una lista de firmas de transacciones para una dirección dada.

    Attributes:
        signatures: Lista de información de firmas
    """

    signatures: list[RPCSignatureInfo] = Field(default_factory=list)
