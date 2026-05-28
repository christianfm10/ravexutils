"""API endpoint descriptor.

A single :class:`Endpoint` instance is the *one source of truth* for a
client's URL, replacing the ``BASE_URL / _ORIGIN / host`` attributes that
would otherwise be duplicated in every client class.

Typical usage::

    # Simple API (no subdomain split)
    class PumpFunClient(BaseAioHttpClient):
        ENDPOINT = Endpoint.from_url("https://frontend-api.pump.fun")

    # Subdomain API where cookies/CORS use the root domain
    class AxiomClient(AuthAioHttpClient):
        ENDPOINT = Endpoint.from_base_and_subdomain("https://axiom.trade", "api8")

Setting ``ENDPOINT`` on a subclass of :class:`BaseAioHttpClient` automatically
fills in ``BASE_URL`` and ``_ORIGIN`` via ``__init_subclass__``, so no further
boilerplate is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from yarl import URL


@dataclass(frozen=True)
class Endpoint:
    """Immutable API endpoint descriptor.

    Attributes
    ----------
    url:
        Full API URL used as the base for all HTTP requests.
        e.g. ``URL("https://api8.axiom.trade")``
    root_origin:
        Optional root-domain override for the cookie/CORS origin.
        Use when the API lives on a subdomain but authentication cookies
        and the ``Origin`` header reference the parent domain.
        e.g. ``URL("https://axiom.trade")``
    """

    url: URL
    root_origin: URL
    scheme: str = "https"

    def __post_init__(self) -> None:
        if not self.url.host:
            raise ValueError(
                f"Endpoint URL must include a host component: {self.url!r}"
            )

    # ── constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_url(cls, url: str | URL) -> Endpoint:
        """Create an endpoint from a full URL string or :class:`~yarl.URL`.

        >>> Endpoint.from_url("https://frontend-api.pump.fun").host
        'frontend-api.pump.fun'
        """
        root_origin = URL(url).origin() if isinstance(url, str) else url.origin()
        return cls(
            url=URL(url) if isinstance(url, str) else url, root_origin=root_origin
        )

    @classmethod
    def generate_random_base_and_subdomain(
        cls, base: str | URL, subdomains: list[str], subdomain_id: int
    ) -> Endpoint:
        """Generate a random endpoint from a base URL and a list of subdomains.

        >>> Endpoint.generate_random_base_and_subdomain("https://axiom.trade", ["api2", "api3", "api4"], 2).host
        'api3.axiom.trade'
        """
        root = URL(base) if isinstance(base, str) else base
        subdomain = subdomains[subdomain_id - 1]
        return cls(url=root.with_host(f"{subdomain}.{root.host}"), root_origin=root)

    @classmethod
    def from_base_and_subdomain(cls, base: str | URL, subdomain: str) -> Endpoint:
        """Create an endpoint targeting *subdomain* of *base*.

        The root *base* URL is automatically stored as the cookie/CORS origin,
        so cookies scoped to ``.axiom.trade`` are correctly shared across
        all API subdomains.

        >>> ep = Endpoint.from_base_and_subdomain("https://axiom.trade", "api8")
        >>> ep.str_url   # 'https://api8.axiom.trade'
        >>> ep.host       # 'api8.axiom.trade'
        >>> ep.origin     # 'https://axiom.trade'
        """
        root = URL(base) if isinstance(base, str) else base
        return cls(url=root.with_host(f"{subdomain}.{root.host}"), root_origin=root)

    # ── derived properties ────────────────────────────────────────────────────

    @property
    def str_url(self) -> str:
        """Full URL string for HTTP requests: ``'https://api8.axiom.trade'``."""
        return str(self.url)

    @property
    def host(self) -> str:
        """Hostname for the ``Host`` header: ``'api8.axiom.trade'``."""
        return cast(str, self.url.host)

    @property
    def origin(self) -> str:
        """CORS / cookie origin.

        Returns the ``root_origin`` if set, otherwise the full URL origin.

        * Subdomain API  → ``'https://axiom.trade'``
        * Plain API      → ``'https://frontend-api.pump.fun'``
        """
        return str((self.root_origin or self.url).origin())

    @property
    def domain(self) -> str:
        """Domain for cookie scoping: ``'axiom.trade'``."""
        domain = (
            self.root_origin.host if self.root_origin.host else str(self.root_origin)
        )

        return domain

    @property
    def subdomain(self) -> str | None:
        """First host label when the host has more than two parts, else *None*.

        >>> Endpoint.from_url("https://api8.axiom.trade").subdomain
        'api8'
        >>> Endpoint.from_url("https://pump.fun").subdomain
        None
        """
        parts = cast(str, self.url.host).split(".")
        return parts[0] if len(parts) > 2 else None

    # ── mutation (returns new instance — dataclass is frozen) ─────────────────

    def with_subdomain(self, subdomain: str) -> Endpoint:
        """Return a new :class:`Endpoint` targeting a different *subdomain*.

        The ``root_origin`` is preserved so cookie scoping stays correct.

        >>> ep = Endpoint.from_base_and_subdomain("https://axiom.trade", "api8")
        >>> ep.with_subdomain("api7").host
        'api7.axiom.trade'
        """
        parts = cast(str, self.url.host).split(".")
        base_parts = parts[1:] if len(parts) > 2 else parts
        return Endpoint(
            url=self.url.with_host(f"{subdomain}.{'.'.join(base_parts)}"),
            root_origin=self.root_origin,
        )
