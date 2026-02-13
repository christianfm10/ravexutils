"""Excepciones personalizadas para el cliente RPC de Solana."""


class RPCException(Exception):
    """Excepción base para errores relacionados con llamadas RPC.

    Esta excepción se lanza cuando ocurre un error durante la comunicación
    con el RPC de Solana o cuando el RPC retorna un error.

    Attributes:
        message: Descripción del error ocurrido

    Example:
        >>> try:
        ...     result = await client.get_transaction("invalid_signature")
        ... except RPCException as e:
        ...     print(f"Error RPC: {e}")
    """

    def __init__(self, message: str) -> None:
        """Inicializa la excepción con un mensaje de error.

        Args:
            message: Descripción del error que se debe reportar
        """
        self.message = message
        super().__init__(self.message)


class InvalidAddressException(RPCException):
    """Excepción lanzada cuando se proporciona una dirección inválida.

    Se usa para errores de validación de direcciones de Solana (base58).

    Example:
        >>> if not is_valid_address(owner):
        ...     raise InvalidAddressException("Dirección de owner inválida")
    """

    pass


class TransactionNotFoundException(RPCException):
    """Excepción lanzada cuando una transacción no se encuentra.

    Se usa cuando se intenta obtener una transacción que no existe
    o que aún no ha sido confirmada por la red.

    Example:
        >>> try:
        ...     tx = await client.get_transaction(signature)
        ... except TransactionNotFoundException:
        ...     print("Transacción no encontrada o no confirmada aún")
    """

    pass


class RPCTimeoutException(RPCException):
    """Excepción lanzada cuando una petición RPC excede el tiempo de espera.

    Se usa cuando el servidor RPC no responde dentro del tiempo límite
    configurado en el cliente.

    Example:
        >>> try:
        ...     result = await client.get_token_accounts(owner)
        ... except RPCTimeoutException:
        ...     print("El servidor RPC no respondió a tiempo")
    """

    pass


class RPCConnectionException(RPCException):
    """Excepción lanzada cuando no se puede conectar al servidor RPC.

    Se usa cuando hay problemas de red o el servidor RPC no está disponible.

    Example:
        >>> try:
        ...     client = RPC_Client(base_url="https://invalid-rpc.com")
        ...     result = await client.get_token_accounts(owner)
        ... except RPCConnectionException:
        ...     print("No se pudo conectar al servidor RPC")
    """

    pass
