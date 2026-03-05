from shared_lib.pydantic import APIBaseModel
from pydantic import Field
from rich.text import Text


class PumpPortalBaseModel(APIBaseModel):
    sol_amount: float = Field(alias="solAmount")
    creator: str = Field(alias="traderPublicKey")
    mint: str
    name: str | None = None
    symbol: str | None = None
    tx_type: str = Field(alias="txType")
    uri: str | None = None
    signature: str
    is_scam: bool = False
    pool: str
    market_cap_sol: float = Field(default=0.0, alias="marketCapSol")

    # Serialization
    # Make a short string representation for logging using creator, mint, name/symbol, amount

    def short_str(self):
        markup_text = f"[b green]Dev:[/b green] [green]{self.creator}[/green]\n[b cyan]Mint:[/b cyan] [cyan]{self.mint}[/cyan]\n[b magenta]Name:[/b magenta] {self.name}\\{self.symbol} - [b yellow]Amount:[/b yellow] {self.sol_amount} SOL"
        return markup_text
