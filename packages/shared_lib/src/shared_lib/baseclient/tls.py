import ssl
import typing
from functools import lru_cache

from httpcore import AsyncConnectionPool, AsyncHTTPProxy, AsyncSOCKSProxy
from httpcore import ConnectionPool, HTTPProxy, SOCKSProxy


def mimic_tls_fingerprint_from_browser(
    pool: typing.Union[
        AsyncConnectionPool,
        AsyncHTTPProxy,
        AsyncSOCKSProxy,
        ConnectionPool,
        HTTPProxy,
        SOCKSProxy,
    ],
    ecdh_curve: typing.Optional[str] = None,
    cipher_suite: typing.Optional[str] = None,
):
    if pool._ssl_context is None:
        pool._ssl_context = ssl.create_default_context()

    ecdh_curve = ecdh_curve or "secp384r1"
    cipher_suite = cipher_suite or get_cipher_suite()
    pool._ssl_context.set_ecdh_curve(ecdh_curve)
    pool._ssl_context.set_ciphers(cipher_suite)
    pool._ssl_context.check_hostname = False

    pool._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    pool._ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
    pool._ssl_context = pool._ssl_context


@lru_cache
def get_cipher_suite() -> str:
    cipher_suites = [
        "TLS_AES_128_GCM_SHA256",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-AES256-SHA",
        "ECDHE-ECDSA-AES128-SHA",
        "ECDHE-RSA-AES128-SHA",
        "ECDHE-RSA-AES256-SHA",
        "AES128-GCM-SHA256",
        "AES256-GCM-SHA384",
        "AES128-SHA",
        "AES256-SHA",
    ]

    return ":".join(cipher_suites)


def create_tls_context(
    ecdh_curve: typing.Optional[str] = None,
    cipher_suite: typing.Optional[str] = None,
) -> ssl.SSLContext:
    """
    Create a configured SSL context that mimics browser TLS fingerprint.

    Args:
        ecdh_curve: ECDH curve to use. Defaults to "secp384r1".
        cipher_suite: Cipher suite string. Defaults to browser-like suite.

    Returns:
        Configured ssl.SSLContext ready to use with HTTP clients.
    """
    ssl_context = ssl.create_default_context()

    ecdh_curve = ecdh_curve or "secp384r1"
    cipher_suite = cipher_suite or get_cipher_suite()

    ssl_context.set_ecdh_curve(ecdh_curve)
    ssl_context.set_ciphers(cipher_suite)
    ssl_context.check_hostname = False
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

    return ssl_context
