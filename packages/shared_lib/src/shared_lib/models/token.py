from pydantic import Field, BaseModel, AliasChoices, ConfigDict, field_validator
from shared_lib.utils.date import datetime_to_unix_timestamp, string_to_datetime


class DevWalletFunding(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)
    wallet_address: str = Field(..., alias="walletAddress")
    funding_wallet_address: str = Field(..., alias="fundingWalletAddress")
    signature: str = Field(..., alias="signature")
    amount_sol: float = Field(..., alias="amountSol")
    funded_at: str = Field(..., alias="fundedAt")


class TokenItem(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    pair_address: str = Field(
        validation_alias=AliasChoices(
            "pairAddress", "pair_address", "bonding_curve", "bondingCurveKey"
        )
    )
    signature: str | None = None
    token_address: str | None = Field(
        validation_alias=AliasChoices(
            "mint",
            "tokenAddress",
        )
    )
    deployer_address: str | None = Field(
        validation_alias=AliasChoices(
            "creator",
            "traderPublicKey",
        )
    )
    token_name: str | None = Field(
        validation_alias=AliasChoices(
            "name",
            "tokenName",
        )
    )
    token_ticker: str | None = Field(
        validation_alias=AliasChoices(
            "symbol",
        )
    )
    token_uri: str | None = Field(validation_alias=AliasChoices("metadata_uri", "uri"))
    token_decimals: int | None = None
    protocol: str | None = None
    is_cashback_enabled: bool | None = None
    is_offchain_enabled: bool | None = None
    is_usdc: bool | None = None
    sol_amount: float | None = Field(default=None, alias="solAmount")
    initial_buy: float | None = Field(default=None, alias="initialBuy")
    is_mayhem_mode: bool | None = False
    # mayhem_state: str | None = None

    # first_market_cap_sol: float | None = None
    # high_market_cap_sol: float | None = None
    market_cap_sol: float | None = None
    migration_ts: int | None = None
    migrated: bool = False
    # initial_liquidity_sol: float | None = None
    # initial_liquidity_token: float | None = None
    supply: float | None = None
    bonding_curve_percent: float | None = None
    migrated_tokens: int | None = 0
    created_at: int | None = Field(
        default=None, validation_alias=AliasChoices("created_timestamp")
    )
    # created_timestamp: int | None = None

    # Dev Wallet Funding
    dev_wallet_funding: DevWalletFunding | None = None

    dev_tokens: int | None = 1
    # num_txn: int | None = None
    # num_buys: int | None = None
    # num_sells: int | None = None
    buy_amount: float | None = None

    # Networks
    website: str | None = None
    has_website: bool = False
    twitter: str | None = None
    has_twitter: bool = False
    telegram: str | None = None
    has_telegram: bool = False
    # discord: str | None = None
    description: str | None = None
    desc_size: int | None = None
    uri_size: int | None = None
    has_description: bool = False
    # video: str | None = None
    # twitter_type: str | None = None
    # twitter_data: dict | None = None

    # Live
    is_currently_live: bool | None = None
    live: bool | None = None

    # Complete
    complete: bool = False

    # has_arrived
    has_pumpportal_arrived: bool = False
    has_axiom_arrived: bool = False
    has_nats_arrived: bool = False
    has_pulse_arrived: bool = False
    has_twitter_arrived: bool = False

    # Hold
    dev_holds_percent: float | None = None

    @field_validator("created_at", mode="before")
    def normalize_created_at(cls, v):
        if v is None:
            return None
        if isinstance(v, int):
            if v > 1e12:
                return v // 1000
            return v
        if isinstance(v, str):
            try:
                datetime = string_to_datetime(v)
                if datetime is None:
                    raise ValueError("Invalid datetime string format")
                dt = datetime_to_unix_timestamp(datetime, milliseconds=False)
                return dt
            except ValueError:
                return v  # Assume it's already a properly formatted string
        raise ValueError(
            "created_timestamp must be an integer or a string date ISO 8601 format"
        )

    @field_validator("token_decimals", mode="before")
    def round_mcap(cls, v):
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return round(v, 3)
        raise ValueError("token_decimals must be an integer or a float")
