from app.ingestion.adapters.seven_fresh import (
    SevenFreshAdapter,
    parse_store_record,
)


def test_parse_store_record_supermarket_swaps_coordinates() -> None:
    record = {
        "id": "0c73da96f4f24b05b9847d00417db220",
        "name": "顺义锦荟港店",
        "address": "北京顺义区站前街3号院1号楼锦荟港B1层七鲜超市",
        "longitude": "40.126245",
        "latitude": "116.647047",
    }
    store = parse_store_record(record, store_format="supermarket", format_label="七鲜超市")
    assert store is not None
    assert store["external_id"] == "7fresh-sm-0c73da96f4f24b05b9847d00417db220"
    assert store["store_format"] == "supermarket"
    assert store["latitude"] == 40.126245
    assert store["longitude"] == 116.647047
    assert store["name"] == "七鲜超市 顺义锦荟港店"


def test_parse_store_record_life() -> None:
    record = {
        "id": "31df06134faf483c81514bbfac5076e8",
        "name": "九龙山家园店",
        "address": "北京市朝阳区广渠路九龙山家园1号楼1层4门1-D2",
        "longitude": "39.893689",
        "latitude": "116.468202",
    }
    store = parse_store_record(record, store_format="life", format_label="七鲜生活")
    assert store is not None
    assert store["external_id"] == "7fresh-life-31df06134faf483c81514bbfac5076e8"
    assert store["store_format"] == "life"
    assert "七鲜生活" in store["name"]


def test_adapter_version() -> None:
    assert SevenFreshAdapter.adapter_version == "0.1.0"
