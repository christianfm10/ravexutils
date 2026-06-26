"""
Rich split-screen display for monitoring tools.

State
-----
- ``log_buffer``  : rotating deque of formatted log lines
- ``balances``    : wallet → mint → token amount
- ``prices``      : mint  → latest USDT price

Public API
----------
- ``BufferLogHandler``       – attach to root logger; feeds log_buffer
- ``redirect_logs_to_buffer`` – convenience: swap stream handlers for BufferLogHandler
- ``build_balance_table``    – renders the wallet balance Rich Table
- ``build_log_text``         – renders the log panel Rich Text
- ``make_layout``            – creates the two-panel Layout
- ``run_display``            – async task; refreshes the layout indefinitely
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime

from rich.layout import Layout
from rich.markup import escape as markup_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from shared_lib.utils.numbers import human_readable_number

# ── Module-level state ────────────────────────────────────────────────────────

LOG_BUFFER_SIZE = 200
log_buffer: deque[str] = deque(maxlen=LOG_BUFFER_SIZE)

balances: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
prices: dict[str, float] = {}

_LEVEL_STYLE: dict[str, str] = {
    "DEBUG": "dim cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}

# ── Logging handler ───────────────────────────────────────────────────────────


class BufferLogHandler(logging.Handler):
    """Captures formatted log records into ``log_buffer`` for the UI panel."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level = record.levelname
            style = _LEVEL_STYLE.get(level, "white")
            log_buffer.append(
                f"[dim]{ts}[/dim] [{style}]{level:<8}[/{style}] "
                f"[dim]{markup_escape(record.name)}[/dim]  "
                f"{markup_escape(record.getMessage())}"
            )
        except Exception:
            self.handleError(record)


def redirect_logs_to_buffer() -> None:
    """Remove existing stream handlers from the root logger and install BufferLogHandler."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if isinstance(handler, logging.StreamHandler):
            root.removeHandler(handler)
    root.addHandler(BufferLogHandler())


# ── Renderers ─────────────────────────────────────────────────────────────────


def build_balance_table(
    balances_data: dict[str, dict[str, float]] | None = None,
    prices_data: dict[str, float] | None = None,
    low_threshold: float = 20_000,
    max_rows: int = 40,
) -> Table:
    """Build a Rich Table with columns: Wallet | Mint | Balance | Price.

    If *balances_data* / *prices_data* are omitted the module-level
    ``balances`` / ``prices`` dicts are used (backward-compatible).
    """
    _balances = balances_data if balances_data is not None else balances
    _prices = prices_data if prices_data is not None else prices

    table = Table(expand=True, show_header=True, header_style="bold magenta")
    table.add_column("Wallet", style="cyan", no_wrap=True)
    table.add_column("Mint", style="magenta", no_wrap=True)
    table.add_column("Balance", justify="right")
    table.add_column("Price", justify="right", style="yellow")

    count = 0
    for wallet, mints in list(_balances.items()):
        for mint, balance in list(mints.items()):
            if balance <= 0:
                continue
            bal_style = "bold red" if balance < low_threshold else "green"
            table.add_row(
                wallet[:4] + "…",
                mint[:4] + "…",
                f"[{bal_style}]{human_readable_number(round(balance, 4))}[/{bal_style}]",
                f"${human_readable_number(round(_prices.get(mint, 0), 4))}",
            )
            count += 1
            if count >= max_rows:
                return table
    return table


def build_log_text() -> Text:
    """Build a Rich Text of recent log lines, newest first."""
    text = Text(overflow="ellipsis", no_wrap=False)
    for line in reversed(list(log_buffer)):
        text.append_text(Text.from_markup(line))
        text.append("\n")
    return text


# ── Layout ────────────────────────────────────────────────────────────────────


def make_layout(balances_width: int = 65) -> Layout:
    """
    Create a two-panel side-by-side layout.

    Parameters
    ----------
    balances_width:
        Fixed character width for the right (balances) panel.
        The left (logs) panel takes all remaining space.
    """
    layout = Layout()
    layout.split_row(
        Layout(name="logs"),
        Layout(name="balances", size=balances_width),
    )
    layout["logs"].update(
        Panel("Starting…", title="[bold cyan]Logs[/bold cyan]", border_style="cyan")
    )
    layout["balances"].update(
        Panel(
            "", title="[bold green]Wallet Balances[/bold green]", border_style="green"
        )
    )
    return layout


# ── Display task ──────────────────────────────────────────────────────────────


async def run_display(
    layout: Layout,
    balances_data: dict[str, dict[str, float]] | None = None,
    prices_data: dict[str, float] | None = None,
    low_threshold: float = 20_000,
    interval: float = 0.1,
) -> None:
    """
    Async task: refresh both layout panels every *interval* seconds.

    Pass *balances_data* / *prices_data* to display an external state dict
    instead of the module-level defaults (useful when using the Monitor class).
    """
    while True:
        try:
            layout["logs"].update(
                Panel(
                    build_log_text(),
                    title="[bold cyan]Logs[/bold cyan]",
                    border_style="cyan",
                )
            )
            layout["balances"].update(
                Panel(
                    build_balance_table(balances_data, prices_data, low_threshold),
                    title="[bold green]Wallet Balances[/bold green]",
                    border_style="green",
                )
            )
        except Exception:
            pass
        await asyncio.sleep(interval)
