from pydantic import Field, BaseModel


class DevWalletFunding(BaseModel):
    wallet_address: str = Field(..., alias="walletAddress")
    funding_wallet_address: str = Field(..., alias="fundingWalletAddress")
    signature: str = Field(..., alias="signature")
    amount_sol: float = Field(..., alias="amountSol")
    funded_at: str = Field(..., alias="fundedAt")
    model_config = {"populate_by_name": True}


# class PulseItem(BaseModel):
#     pair_address: str
#     token_address: str | None = None
#     dev_address: str | None = None
#     token_name: str | None = None
#     token_ticker: str | None = None
#     token_decimals: int | None = None
#     protocol: str | None = None
#     market_cap_sol: float | None = None
#     liquidity_sol: float | None = None
#     liquidity_token: float | None = None
#     bonding_curve_percent: float | None = None
#     migrated_tokens: int | None = None
#     first_mint_date: str | None = None
#     dev_wallet_funding: DevWalletFunding | None = None
#     dev_tokens: int | None = None


class PairItem(BaseModel):
    pair_address: str
    signature: str | None = None
    token_address: str | None = None
    deployer_address: str | None = None
    token_name: str | None = None
    token_ticker: str | None = None
    token_uri: str | None = None
    token_decimals: int | None = None
    protocol: str | None = None
    first_market_cap_sol: float | None = None
    high_market_cap_sol: float | None = None
    market_cap_sol: float | None = None
    initial_liquidity_sol: float | None = None
    initial_liquidity_token: float | None = None
    supply: float | None = None
    bonding_curve_percent: float | None = None
    migrated_tokens: int | None = None
    created_at: str | None = None
    dev_wallet_funding: DevWalletFunding | None = None
    dev_tokens: int | None = None
    num_txn: int | None = None
    num_buys: int | None = None
    num_sells: int | None = None
    buy_amount: float | None = None

    # Networks
    website: str | None = None
    twitter: str | None = None


"""
PairInfo
{
    "tokenImage": "https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/4awjcfg9fgK547L4hLkAUGZVDPiryk8GB5VYDgpvpump.webp",
    "dexPaid": true,
    "protocol": "Pump AMM",
    "signature": "3uqwZTiPVzp68aDzEtHLGjwhMnFvoaBGt5nrwLzZathmfKxr5TfJKn5qUqqjg3FUThzTdJV1FuzDsF26GdcKGMiN",
    "tokenTicker": "GOLDIE",
    "updatedAt": "2026-05-18T04:50:14.502901+00:00",
    "createdAt": "2026-05-18T04:27:34.476778+00:00",
    "protocolDetails": {
        "creator": "34KTtfW1JuoHzMw5uf3xydMAmCR1v6HpPiexBUqoAytj",
        "cashback": false,
        "isMayhem": false,
        "pairSolAccount": "5whJcyokXqtWeVpP6bvLazgeTWUETggGeCjqg6Hyo8si",
        "isTokenSideX": true,
        "feeShare": true,
        "isOffchain": false,
        "pairTokenAccount": "A4uhbjT9idK2Tt789JNVqEyUSAeWWAH9Lj78p9tKktvG",
        "tokenProgram": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    },
    "deployerAddress": "8FiuwM6FmVKmBLCaJ6QcNScnVw4NuNs7Tt4Skf91saF8",
    "pairAddress": "7C3MJJhFd5RwvGG9ihx84ScA3wFxGmkwMaL56mB5dSph",
    "tokenAddress": "4awjcfg9fgK547L4hLkAUGZVDPiryk8GB5VYDgpvpump",
    "displayProtocol": "Pump AMM",
    "website": "https://thegoldie.fun/",
    "pairTokenAccount": "A4uhbjT9idK2Tt789JNVqEyUSAeWWAH9Lj78p9tKktvG",
    "discord": null,
    "telegram": null,
    "tokenUri": "https://ipfs.io/ipfs/bafkreihpthkh4a4ou3rqrkj2lezs6rhrauhla3u6escokwbxv3pw445vda",
    "lpBurned": 100,
    "slot": 420480915,
    "extra": {
        "migratedFrom": "Pump V1",
        "pumpDeployerAddress": "4PVd852TSm3DHX5xnHdNCs1JCwd11WgzRGQymQixA3az"
    },
    "initialLiquiditySol": 84.990359191,
    "initialLiquidityToken": 206900000,
    "tokenName": "GOLDIE",
    "freezeAuthority": null,
    "openTrading": "2026-05-18T04:25:41.112+00:00",
    "pairSolAccount": "5whJcyokXqtWeVpP6bvLazgeTWUETggGeCjqg6Hyo8si",
    "tokenDecimals": 6,
    "top10Holders": 7.6969121733863,
    "twitter": "https://x.com/thegoldiechamp",
    "mintAuthority": null,
    "supply": 999978329.16752,
    "isWatchlisted": false,
    "pumpLiveStreamData": null,
    "twitterHandleHistory": [],
    "devWalletFunding": {
        "walletAddress": "4PVd852TSm3DHX5xnHdNCs1JCwd11WgzRGQymQixA3az",
        "fundingWalletAddress": "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV",
        "signature": "xE9D6R5XzcdNW9sbcUygySaGB4PLMvJMsVnVyTjxmHwT5QQKg55eT3rZVwXWyF6eZZURveqcYJwt8fJDRMXYyzB",
        "amountSol": 40,
        "fundedAt": "2026-05-18T03:53:23.000Z"
    },
    "userCount": 2
}
"""


class PairInfo(BaseModel):
    token_image: str | None = Field(None, alias="tokenImage")
    dex_paid: bool | None = Field(None, alias="dexPaid")
    protocol: str | None = None
    signature: str | None = None
    token_ticker: str | None = Field(None, alias="tokenTicker")
    updated_at: str | None = Field(None, alias="updatedAt")
    created_at: str | None = Field(None, alias="createdAt")
    protocol_details: dict | None = Field(None, alias="protocolDetails")
    deployer_address: str | None = Field(None, alias="deployerAddress")
    pair_address: str | None = Field(None, alias="pairAddress")
    token_address: str | None = Field(None, alias="tokenAddress")
    display_protocol: str | None = Field(None, alias="displayProtocol")
    website: str | None = None
    pair_token_account: str | None = Field(None, alias="pairTokenAccount")
    discord: str | None = None
    telegram: str | None = None
    token_uri: str | None = Field(None, alias="tokenUri")
    lp_burned: float | None = Field(None, alias="lpBurned")
    slot: int | None = None
    extra: dict | None = None
    initial_liquidity_sol: float | None = Field(None, alias="initialLiquiditySol")
    initial_liquidity_token: float | None = Field(None, alias="initialLiquidityToken")
    token_name: str | None = Field(None, alias="tokenName")
    freeze_authority: str | None = Field(None, alias="freezeAuthority")
    open_trading: str | None = Field(None, alias="openTrading")
    pair_sol_account: str | None = Field(None, alias="pairSolAccount")
    token_decimals: int | None = Field(None, alias="tokenDecimals")
    top10_holders: float | None = Field(None, alias="top10Holders")
    twitter: str | None = Field(None, alias="twitter")
    mint_authority: str | None = Field(None, alias="mintAuthority")
    supply: float | None = None
    is_watchlisted: bool | None = Field(None, alias="isWatchlisted")
    pump_live_stream_data: dict | None = Field(None, alias="pumpLiveStreamData")
    twitter_handle_history: list | None = Field(None, alias="twitterHandleHistory")
    dev_wallet_funding: DevWalletFunding | None = Field(None, alias="devWalletFunding")


class Token(BaseModel):
    token_address: str
    creation_timestamp: int
    launchpad: str | None = None
    name: str
    open_timestamp: int
    price: str
    symbol: str


class HoldingList(BaseModel):
    token: Token
    start_holding_at: int
    end_holding_at: int


class HoldingData(BaseModel):
    list: list[HoldingList]
    next: str | None = None


class HoldingResponse(BaseModel):
    code: int
    message: str
    reason: str
    data: HoldingData
