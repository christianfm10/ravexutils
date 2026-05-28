from dataclasses import dataclass
from collections import Counter
from collections.abc import Iterable
from typing import Any, Callable, Sequence, Type, TYPE_CHECKING, TypeVar

from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

if TYPE_CHECKING:
    from shared_lib.database.db_manager import AsyncDatabaseManager
    from sqlalchemy.orm.attributes import InstrumentedAttribute


# async def analyze_symbol_abstracted(db_manager):
#     """Abstracted variant of analyze_symbol using reusable query/count helpers."""
#     symbols = await fetch_distinct_values(db_manager, UserCreatedCoinDB.symbol)
#     dict_counter: dict[int, int] = {}

#     for symbol in symbols:
#         coins = await fetch_coins_filtered(
#             db_manager,
#             UserCreatedCoinDB.symbol == symbol,
#             UserCreatedCoinDB.is_active.is_not(False),
#             UserCreatedCoinDB.created_timestamp > 1778228986000,
#             UserCreatedCoinDB.ath_market_cap > 7_000,
#         )
#         if not coins:
#             continue

#         counts, local_counter, _ = count_attempts_until_threshold(
#             coins,
#             threshold=10_000,
#             include_complete_marker=True,
#             append_last_if_counter_gt=1,
#         )
#         for key, value in local_counter.items():
#             dict_counter[key] = dict_counter.get(key, 0) + value

#         if not counts:
#             continue
#         print(f"\nSymbol: {symbol}")
#         print(counts)

#     print(dict(sorted(dict_counter.items())))


async def fetch_filtered[T](
    db_manager: AsyncDatabaseManager,
    model: Type[T],
    *conditions: ColumnElement[bool],
    order_by: Any | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Sequence[T]:
    async with db_manager.get_session() as session:
        query: Select[tuple[T]] = select(model)

        if conditions:
            query = query.where(*conditions)

        if order_by is not None:
            query = query.order_by(order_by)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        result = await session.execute(query)

        return result.scalars().all()


T = TypeVar("T")


@dataclass(slots=True)
class AttemptAnalysisResult:
    total_rows: int
    successful_hits: int
    trailing_unsuccessful: int
    counts: list[int]
    attempts_distribution: dict[int, int]

    @property
    def coins_consumed_in_hits(self) -> int:
        return sum(self.counts)

    @property
    def hit_ratio(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return self.successful_hits / self.total_rows


def format_attempt_analysis_report(result: AttemptAnalysisResult) -> str:
    """Build a readable report instead of raw lists for easier interpretation."""
    lines = [
        "Attempt Analysis",
        f"- Total rows analyzed: {result.total_rows}",
        f"- Successful hits: {result.successful_hits}",
        f"- Trailing unsuccessful rows: {result.trailing_unsuccessful}",
        f"- Coins consumed in hits: {result.coins_consumed_in_hits}",
        f"- Hit ratio over total rows: {result.hit_ratio:.2%}",
        "- Distribution by attempts needed:",
    ]

    if not result.attempts_distribution:
        lines.append("  (no successful hits)")
        return "\n".join(lines)

    for attempts, frequency in sorted(result.attempts_distribution.items()):
        pct = (frequency / result.successful_hits) if result.successful_hits else 0.0
        lines.append(f"  {attempts} attempt(s): {frequency} hit(s) ({pct:.2%} of hits)")
    return "\n".join(lines)


def threshold_func_default(row: object) -> bool:
    return True


def count_attempts_global(
    rows: Iterable[T],
    threshold_func: Callable[[T], bool] = threshold_func_default,
) -> tuple[list[int], dict[int, int], int]:
    """
    Count attempts until a condition is met.


    Returns:
        counts: sequence lengths before success
        hit_counter: frequency of each sequence length
        trailing_unsuccessful: unfinished streak at the end
    """

    counts: list[int] = []
    trailing_unsuccessful = 0

    for row in rows:
        if threshold_func(row):
            counts.append(trailing_unsuccessful + 1)
            trailing_unsuccessful = 0
        else:
            trailing_unsuccessful += 1

    hit_counter = dict(Counter(counts))

    return counts, hit_counter, trailing_unsuccessful


async def analyze_creators_abstracted(
    db_manager,
    model: Type[Any],
    *conditions: ColumnElement[bool],
    order_by: Any | None = None,
    limit: int | None = None,
    offset: int | None = None,
    threshold_func: Callable[[T], bool] = threshold_func_default,
    theshold_func: Callable[[T], bool] | None = None,
    include_raw_counts: bool = False,
    # value_getter: Callable[[Any], Any] = lambda x: getattr(x, "ath_market_cap", None),
) -> AttemptAnalysisResult | None:
    """Abstracted variant of analyze_creators using reusable query/count helpers."""
    rows = await fetch_filtered(
        db_manager,
        model,
        *conditions,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )
    if not rows:
        return

    active_threshold_func = theshold_func or threshold_func

    counts, dict_counter, trailing_unsuccessful = count_attempts_global(
        rows,
        threshold_func=active_threshold_func,
    )
    if not counts:
        result = AttemptAnalysisResult(
            total_rows=len(rows),
            successful_hits=0,
            trailing_unsuccessful=trailing_unsuccessful,
            counts=[],
            attempts_distribution={},
        )
        print(format_attempt_analysis_report(result))
        return result

    result = AttemptAnalysisResult(
        total_rows=len(rows),
        successful_hits=len(counts),
        trailing_unsuccessful=trailing_unsuccessful,
        counts=counts,
        attempts_distribution=dict(sorted(dict_counter.items(), key=lambda x: x[0])),
    )

    if include_raw_counts:
        print(f"Raw counts: {result.counts}")
    print(format_attempt_analysis_report(result))
    return result


async def analyze_tries_by_field(
    db_manager,
    model: Type[Any],
    *conditions: ColumnElement[bool],
    field: InstrumentedAttribute | None = None,
    order_by: Any | None = None,
    limit: int | None = None,
    offset: int | None = None,
    threshold_func: Callable[[T], bool] = threshold_func_default,
) -> dict[Any, AttemptAnalysisResult]:
    """Analyze attempts distribution grouped by distinct values of a specified field."""
    rows = await fetch_filtered(
        db_manager,
        model,
        *conditions,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )
    if not rows:
        return {}

    # Group rows by distinct values of the specified field
    if field is None:
        raise ValueError("Field must be specified for grouping")
    groups: dict[Any, list[Any]] = {}
    for row in rows:
        key = getattr(row, field.key or "unknown")
        groups.setdefault(key, []).append(row)

    # Analyze each group separately
    results: dict[Any, AttemptAnalysisResult] = {}
    for key, group_rows in groups.items():
        counts, dict_counter, trailing_unsuccessful = count_attempts_global(
            group_rows,
            threshold_func=threshold_func,
        )
        result = AttemptAnalysisResult(
            total_rows=len(group_rows),
            successful_hits=len(counts),
            trailing_unsuccessful=trailing_unsuccessful,
            counts=counts,
            attempts_distribution=dict(
                sorted(dict_counter.items(), key=lambda x: x[0])
            ),
        )
        results[key] = result
        print(
            f"\nAnalysis for {field.key}={key}:\n{format_attempt_analysis_report(result)}"
        )

    return results
