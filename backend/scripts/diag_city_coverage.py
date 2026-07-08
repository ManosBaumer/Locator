import asyncio
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import async_session
from app.models.chain import Chain
from app.models.location import Location

manifest = json.loads(
    Path("/tmp/mcdonalds-checkpoint/deliveryinfo_manifest.json").read_text()
)["stores"]
disc = Counter(s["city"] for s in manifest)


async def main() -> None:
    async with async_session() as s:
        cid = (
            await s.execute(select(Chain.id).where(Chain.slug == "mcdonalds"))
        ).scalar_one()
        rows = (
            await s.execute(
                select(Location.city, func.count())
                .where(Location.chain_id == cid)
                .group_by(Location.city)
            )
        ).all()
        dbc = {c: n for c, n in rows}

    header = "city".ljust(12) + "disc".rjust(6) + "db".rjust(7) + "ratio".rjust(8)
    print(header)
    suspect = []
    for city, d in disc.most_common():
        if d < 40:
            continue
        n = dbc.get(city, 0)
        ratio = n / d if d else 0
        flag = "  <-- LOW" if ratio < 1.05 else ""
        if ratio < 1.05:
            suspect.append(city)
        print(city.ljust(12) + str(d).rjust(6) + str(n).rjust(7) + f"{ratio:>8.2f}" + flag)

    print()
    print("suspect (db <= 1.05x disclosure):", len(suspect))
    print(",".join(suspect))


asyncio.run(main())
