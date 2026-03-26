from nats.aio.client import Client as NATS

WS_CLUSTER_URL = "wss://prod-v2.nats.realtime.pump.fun/"


async def disconnected_cb():
    print("Desconectado del servidor")


async def error_cb(e):
    print(f"Error: {e}")


async def closed_cb():
    print("Conexión cerrada definitivamente")


async def connect_to_nats() -> NATS:
    nc = NATS()

    async def reconnected_cb():
        if not nc.connected_url:
            return
        print(f"Reconectado a {nc.connected_url.netloc}")

    await nc.connect(
        servers=[WS_CLUSTER_URL],
        user="subscriber",
        password="lW5a9y20NceF6AE9",
        connect_timeout=1,
        max_reconnect_attempts=5,
        reconnect_time_wait=2,
        disconnected_cb=disconnected_cb,
        reconnected_cb=reconnected_cb,
        error_cb=error_cb,
        closed_cb=closed_cb,
    )
    print("Connected to NATS at", WS_CLUSTER_URL)
    return nc
