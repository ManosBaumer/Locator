from app.ingestion.adapters.costco import COSTCO_STORES, CostcoAdapter


def test_costco_store_count() -> None:
    assert len(COSTCO_STORES) == 7


def test_costco_store_ids_unique() -> None:
    ids = [store["external_id"] for store in COSTCO_STORES]
    assert len(ids) == len(set(ids))


async def test_costco_shenzhen_has_verified_coordinates() -> None:
    adapter = CostcoAdapter()
    raw = await adapter.fetch_raw_data()
    shenzhen = next(store for store in raw if store["external_id"] == "costco-shenzhen")
    assert shenzhen["address"].endswith("民达路68号")
    assert shenzhen["latitude"] == 22.626941
    assert shenzhen["longitude"] == 114.013758


async def test_costco_fetch_and_parse() -> None:
    adapter = CostcoAdapter()
    raw = await adapter.fetch_raw_data()
    locations = await adapter.parse_locations(raw)

    assert len(locations) == 7
    normalized = await adapter.normalize(locations[0])
    assert normalized.external_id == "costco-shanghai-minhang"
    assert normalized.address == "上海市闵行区朱建路235号"
    assert normalized.city == "上海市"
