from app.ingestion.adapters.aldi import (
    extract_region_from_area,
    parse_address_region,
    parse_store_record,
    parse_stores_from_html,
)


def test_parse_store_record() -> None:
    store = parse_store_record(
        {
            "id": 1746783648744,
            "fields": {
                "storesName": "静安体育中心店",
                "storesAddress": "上海市静安区江宁路428号1楼",
                "startTime": "07:00:00",
                "endTime": "22:00:00",
                "area": {
                    "name": "静安区",
                    "fields": {
                        "parent": {
                            "name": "上海",
                            "fields": {"parent": {"name": "上海"}},
                        }
                    },
                },
            },
        }
    )
    assert store is not None
    assert store["store_id"] == "1746783648744"
    assert store["province"] == "上海市"
    assert store["city"] == "上海市"
    assert store["district"] == "静安区"
    assert store["hours"] == "07:00-22:00"


def test_parse_address_region_jiangsu() -> None:
    province, city, district = parse_address_region("江苏省无锡市梁溪区人民中路139号")
    assert province == "江苏省"
    assert city == "无锡市"
    assert district == "梁溪区"


def test_extract_region_from_area() -> None:
    province, city, district = extract_region_from_area(
        {
            "name": "姑苏区",
            "fields": {
                "parent": {
                    "name": "苏州",
                    "fields": {"parent": {"name": "江苏省"}},
                }
            },
        }
    )
    assert province == "江苏省"
    assert city == "苏州"
    assert district == "姑苏区"


def test_parse_stores_from_html_embedded_blob() -> None:
    html = (
        "data_json:'{\"id\":123,\"fields\":{\"storesName\":\"测试店\","
        "\"storesAddress\":\"江苏省苏州市工业园区星港街199号\","
        "\"startTime\":\"08:00:00\",\"endTime\":\"22:00:00\"}}',other"
    )
    stores = parse_stores_from_html(html)
    assert len(stores) == 1
    assert stores[0]["name"] == "测试店"
    assert stores[0]["province"] == "江苏省"
