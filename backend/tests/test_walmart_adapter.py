from app.ingestion.adapters.walmart import (
    is_sams_club_store,
    is_walmart_hypermarket,
    parse_amap_poi,
)


def test_is_walmart_hypermarket_accepts_parenthesis_name() -> None:
    assert is_walmart_hypermarket("沃尔玛(香蜜湖店)", "购物服务;超级市场;沃尔玛")


def test_is_walmart_hypermarket_rejects_company() -> None:
    assert not is_walmart_hypermarket("沃尔玛(中国)投资有限公司", "公司企业;公司")


def test_is_walmart_hypermarket_rejects_sams_name() -> None:
    assert not is_walmart_hypermarket("沃尔玛(山姆会员商店)", "购物服务;超级市场;沃尔玛")


def test_is_sams_club_store_accepts_parenthesis_name() -> None:
    assert is_sams_club_store("山姆会员商店(深圳龙华店)")


def test_is_sams_club_store_rejects_logistics() -> None:
    assert not is_sams_club_store("山姆会员店")


def test_parse_amap_poi_excludes_hong_kong() -> None:
    poi = {
        "id": "B0HK",
        "name": "山姆会员商店(香港店)",
        "address": "香港某地址",
        "location": "114.1,22.3",
        "pname": "香港特别行政区",
        "cityname": "香港特别行政区",
        "adname": "中西区",
        "type": "购物服务;超级市场;超市",
    }
    assert parse_amap_poi(poi, store_format="sams_club") is None


def test_parse_amap_poi_walmart() -> None:
    poi = {
        "id": "B0TEST",
        "name": "沃尔玛(香蜜湖店)",
        "address": "香梅北路2001号",
        "location": "114.03,22.55",
        "pname": "广东省",
        "cityname": "深圳市",
        "adname": "福田区",
        "type": "购物服务;超级市场;沃尔玛",
    }
    store = parse_amap_poi(poi, store_format="hypermarket")
    assert store is not None
    assert store["external_id"] == "amap-B0TEST"
    assert store["store_format"] == "hypermarket"
