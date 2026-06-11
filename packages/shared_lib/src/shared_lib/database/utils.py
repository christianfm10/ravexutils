from typing import TYPE_CHECKING

from sqlalchemy import select, MetaData, Table

if TYPE_CHECKING:
    from .db_manager import AsyncDatabaseManager


# General migration script to move data from old table to new table, the fields should be similar but we can add transformations if needed
# Example INSER INTO new_table (field1, field2) SELECT field1, field2 FROM old_table
async def migrate_old_table_to_new_table(
    db_manager: "AsyncDatabaseManager", old_table_name: str, new_table: "Table"
):
    async with db_manager.get_session() as session:
        metadata = MetaData()
        async with db_manager.engine.begin() as conn:
            old_table = await conn.run_sync(
                lambda sync_conn: Table(
                    old_table_name,
                    metadata,
                    autoload_with=sync_conn,
                )
            )
        # result = await session.execute(select(old_table_name))
        # old_data = result.fetchall()

        async with db_manager.get_session() as session:
            result = await session.execute(select(old_table))

            for row in result.fetchall():
                data = dict(row._mapping)

                data["base_amount"] = int(data["base_amount"])

                await session.execute(new_table.insert().values(**data))

            await session.commit()
        # for row in old_data:
        #     # Transform the data if needed, for example if the new table has different field names or types
        #     new_row = {
        #         "base_amount": int(row.base_amount),
        #         # "field1": row.field1,
        #         # Add more fields as needed
        #     }
        #     # Insert the new row into the new table
        #     await session.execute(new_table_name.insert().values(**new_row))

        # await session.commit()
