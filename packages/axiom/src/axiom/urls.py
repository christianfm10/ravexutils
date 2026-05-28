from yarl import URL

from shared_lib.baseclient.endpoint import Endpoint


class AxiomBaseUrls:
    BASE_URL = URL("https://axiom.trade")


class AxiomEndpoint:
    base_url = URL("https://axiom.trade")
    subdomains = [
        "api",
        "api2",
        "api3",
        "api4",
        "api5",
        "api6",
        "api7",
        "api8",
        "api9",
        "api10",
    ]
    endpoint = Endpoint.generate_random_base_and_subdomain(
        base=base_url, subdomains=subdomains, subdomain_id=8
    )


class GMGNEndpoint:
    base_url = URL("https://gmgn.ai")
    endpoint = Endpoint.from_url(url=base_url)
    pf_path = "/pf/api/v1"
    vas_path = "/vas/api/v1"
    td_path = "/td/api/v1"


class ClusterEndpoint:
    base_url = URL("wss://axiom.trade")
    subdomains = [
        "cluster2",
        "cluster3",
    ]
    endpoint = Endpoint.generate_random_base_and_subdomain(
        base=base_url, subdomains=subdomains, subdomain_id=1
    )


class PulseEndpoint:
    subdomains = [
        "pulse",
        "pulse2",
    ]
    base_url = URL("wss://axiom.trade/ws")
    endpoint = Endpoint.generate_random_base_and_subdomain(
        base=base_url, subdomains=subdomains, subdomain_id=2
    )


class EucalyptusEndpoint:
    subdomains = [
        "eucalyptus",
    ]
    base_url = URL("wss://axiom.trade/ws")
    endpoint = Endpoint.generate_random_base_and_subdomain(
        base=base_url, subdomains=subdomains, subdomain_id=1
    )


class WSBaseUrls:
    WS_CLUSTER_URL = URL("wss://cluster3.axiom.trade/")
    WS_EUCALYPTUS_URL = URL("wss://eucalyptus.axiom.trade/ws")
    WS_PULSE_URL = URL("wss://pulse2.axiom.trade/ws")


class AxiomTradeApiUrls:
    LOGIN_STEP1 = "/login-password-v2"
    LOGIN_STEP2 = "/login-otp"
    LOGOUT = "/auth/logout"
    REFRESH_TOKEN = "/refresh-access-token"
    USER_INFO = "/user/info"
    SUBSCRIBE_NEW_TOKENS = "/ws/subscribe/new-tokens"
    SUBSCRIBE_ORDERS = "/ws/subscribe/orders"
    SUBSCRIBE_POSITIONS = "/ws/subscribe/positions"
