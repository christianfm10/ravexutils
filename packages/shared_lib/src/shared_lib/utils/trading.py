"""
Shared state management for PumpAxiom trading bot.

This module provides a centralized state management system for tracking
trading positions, wallet information, and performance metrics across
both Axiom and PumpPortal WebSocket handlers.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from datetime import datetime
import logging

if TYPE_CHECKING:
    from pumpportal.ws_client import PumpPortalWSClient

logger = logging.getLogger(__name__)


@dataclass
class TokenPosition:
    """Represents a trading position for a specific token."""

    mint: str
    entry_market_cap: float
    entry_time: datetime
    sol_invested: float
    status: str = "active"  # active, sold, expired

    def get_profit_loss_percent(self, current_market_cap: float) -> float:
        """Calculate profit/loss percentage based on current market cap."""
        if self.entry_market_cap == 0:
            return 0.0
        return (
            (current_market_cap - self.entry_market_cap) / self.entry_market_cap
        ) * 100


@dataclass
class TradingState:
    """
    Centralized state management for the trading bot.

    This class tracks:
    - Active token positions
    - Trading parameters (SOL amounts, targets)
    - Performance metrics (wins, losses, accumulated P/L)
    - Last valid deployer addresses for optimization
    """

    # Trading parameters
    sol_amount: float = 0.001
    profit_target_percent: float = 50.0
    stop_loss_percent: float = -1000.0

    # Performance tracking
    lost_accumulated: float = 0.0
    total_wins: int = 0
    total_losses: int = 0
    total_trades: int = 0

    # Active positions
    positions: dict[str, TokenPosition] = field(default_factory=dict)

    # Optimization cache
    last_valid_dev_address: str = ""

    # Configuration
    my_public_key: str = ""

    # WebSocket client for subscriptions
    ws_client: "PumpPortalWSClient | None" = None

    # Buy amount multiplier (number of doublings, resets on profitable sell, max 6)
    buy_multiplier: int = 0
    sol_amount: float = 0.04

    def create_position(
        self,
        mint: str,
        entry_market_cap: float,
        sol_invested: float,
        status: str = "active",
    ) -> TokenPosition:
        """
        Create a new trading position.

        ## Parameters
        - `mint`: Token mint address
        - `entry_market_cap`: Market cap at entry point (SOL)
        - `sol_invested`: Amount of SOL invested

        ## Returns
        TokenPosition object that's also stored in positions dict
        """
        position = TokenPosition(
            mint=mint,
            entry_market_cap=entry_market_cap,
            entry_time=datetime.now(),
            sol_invested=sol_invested,
            status=status,
        )
        self.positions[mint] = position
        logger.info(
            f"Position created for {mint} at {entry_market_cap} SOL "
            f"with {sol_invested} SOL invested"
        )
        return position

    def close_position(
        self, mint: str, exit_market_cap: float, profit_loss_percent: float
    ) -> None:
        """
        Close a trading position and update performance metrics.

        ## Parameters
        - `mint`: Token mint address
        - `exit_market_cap`: Market cap at exit point (SOL)
        - `profit_loss_percent`: P/L percentage
        """
        position = self.positions.get(mint)
        if position is None:
            logger.warning(f"Attempted to close non-existent position: {mint}")
            return

        position.status = "sold"
        self.total_trades += 1

        if profit_loss_percent > 0:
            self.total_wins += 1
            self.lost_accumulated = 0.0  # Reset accumulated losses on win
            self.buy_multiplier = 0
            self.sol_amount = 0.02
            logger.info(
                f"✅ Position closed with PROFIT: {mint} | "
                f"P/L: {profit_loss_percent:.2f}% | "
                f"Entry: {position.entry_market_cap} SOL | "
                f"Exit: {exit_market_cap} SOL"
            )
        else:
            self.total_losses += 1
            self.lost_accumulated += abs(profit_loss_percent)
            logger.info(
                f"❌ Position closed with LOSS: {mint} | "
                f"P/L: {profit_loss_percent:.2f}% | "
                f"Accumulated losses: {self.lost_accumulated:.2f}%"
            )

        # Remove from active positions
        # del self.positions[mint]

    def get_position(self, mint: str) -> "TokenPosition | None":
        """Get active position for a token, or None if not found."""
        return self.positions.get(mint)

    def has_position(self, mint: str) -> bool:
        """Check if there's an active position for a token."""
        return mint in self.positions

    def get_win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.total_wins / self.total_trades) * 100

    def get_performance_summary(self) -> str:
        """Get a formatted string with performance metrics."""
        return (
            f"📊 Trading Performance:\n"
            f"Total Trades: {self.total_trades}\n"
            f"Wins: {self.total_wins} | Losses: {self.total_losses}\n"
            f"Win Rate: {self.get_win_rate():.1f}%\n"
            f"Active Positions: {len(self.positions)}\n"
            f"Accumulated Losses: {self.lost_accumulated:.2f}%"
        )

    def reset_metrics(self) -> None:
        """Reset all performance metrics (useful for testing or new sessions)."""
        self.lost_accumulated = 0.0
        self.total_wins = 0
        self.total_losses = 0
        self.total_trades = 0
        logger.info("Performance metrics reset")


# Global shared state instance

trading_state = TradingState()
