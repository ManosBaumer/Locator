from app.ingestion.adapters.seven_eleven import (
    _parse_amap_result_count,
    is_store_name,
    parse_amap_poi,
    parse_chengdu_store,
    split_city_full_name,
)


def test_parse_chengdu_store() -> None:
    store = parse_chengdu_store(
        {
            "id": "143",
            "shopName": "鹭洲里店",
            "phone": "028-67649473",
            "address": "天府二街1033号",
            "bMap_lng": "104.048713",
            "bMap_lat": "30.556705",
            "cityFullName": "四川省成都市高新区",
            "openDate": "2017-11-20",
        }
    )
    assert store["external_id"] == "cd-143"
    assert store["coordinate_system"] == "BD09"


def test_parse_amap_poi_excludes_taiwan() -> None:
    poi = {
        "id": "B0TW123",
        "name": "7-ELEVEn(幸运门市)",
        "address": "台北市中正区",
        "location": "121.470540,25.007599",
        "pname": "台湾省",
        "cityname": "台湾省",
        "adname": "中正区",
    }
    assert parse_amap_poi(poi) is None


def test_parse_amap_poi_filters_brand() -> None:
    poi = {
        "id": "B0TEST123",
        "name": "7-ELEVEn(建国门店)",
        "address": "建国门外大街",
        "location": "116.434,39.908",
        "pname": "北京市",
        "cityname": "北京市",
        "adname": "朝阳区",
    }
    store = parse_amap_poi(poi)
    assert store is not None
    assert store["external_id"] == "amap-B0TEST123"

    assert parse_amap_poi({**poi, "name": "柒一拾壹(北京)有限公司"}) is None
    assert parse_amap_poi({**poi, "name": "乐满地主题乐园(公交站)"}) is None


def test_is_store_name() -> None:
    assert is_store_name("7-ELEVEn(西花市大街店)")
    assert not is_store_name("柒一拾壹(北京)有限公司")
    assert not is_store_name("乐满地主题乐园(公交站)")


def test_parse_amap_result_count() -> None:
    assert _parse_amap_result_count("313") == 313
    assert _parse_amap_result_count("1000+") == 1000
    assert _parse_amap_result_count(None) == 0


def test_split_city_full_name() -> None:
    assert split_city_full_name("四川省成都市高新区") == ("四川省", "成都市", "高新区")
    assert split_city_full_name("北京市朝阳区") == ("北京市", "北京市", "朝阳区")
