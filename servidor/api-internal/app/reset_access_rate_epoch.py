"""Explicit privileged recovery after loss of the dedicated traffic Redis volume."""

import argparse
import asyncio
import os
import uuid

import asyncpg


async def reset(expected: uuid.UUID):
    conn = await asyncpg.connect(os.environ["DB_DSN"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(739115992)")
            row = await conn.fetchrow(
                "SELECT epoch,initialized FROM access_rate_epoch WHERE singleton FOR UPDATE"
            )
            if row is None or row["epoch"] != expected or not row["initialized"]:
                raise RuntimeError("Expected initialized traffic epoch does not match")
            epoch = await conn.fetchval(
                "UPDATE access_rate_epoch SET epoch=gen_random_uuid(),initialized=false WHERE singleton RETURNING epoch"
            )
            print(
                f"Traffic epoch replaced: {epoch}. Durable quotas are unchanged. Start the authorizer with an empty traffic Redis volume."
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-epoch", type=uuid.UUID, required=True)
    parser.add_argument("--confirm-rate-counter-loss", action="store_true", required=True)
    args = parser.parse_args()
    asyncio.run(reset(args.expected_epoch))
