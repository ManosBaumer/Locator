from app.ingestion.adapters.kfc import (
    parse_kfc_store_list_payload,
    parse_kfc_store_portal_row,
    parse_kfc_store_row,
)


def test_parse_kfc_store_portal_row() -> None:
    store = parse_kfc_store_portal_row(
        {
            "storecode": "BJN034",
            "storename": "王府井建华餐厅",
            "address": "王府井大街192号",
            "cityName": "北京",
            "districtName": "东城区",
            "phone": "18010166615",
            "lat": "39.91126",
            "lng": "116.411453",
            "typeCode": "H",
            "gbCityCode": "110100",
        }
    )
    assert store is not None
    assert store["external_id"] == "kfc-BJN034"
    assert store["coordinate_system"] == "GCJ02"
    assert store["name"].startswith("肯德基")


def test_parse_kfc_store_portal_row_skips_non_mainland() -> None:
    assert parse_kfc_store_portal_row(
        {
            "storecode": "HK001",
            "storename": "测试餐厅",
            "address": "测试地址",
            "lat": "22.3",
            "lng": "114.1",
            "gbCityCode": "810000",
            "typeCode": "H",
        }
    ) is None


def test_parse_kfc_store_row() -> None:
    store = parse_kfc_store_row(
        {
            "storeName": "肯德基(建国门店)",
            "addressDetail": "建国门外大街1号",
            "cityName": "北京市",
            "provinceName": "北京市",
            "pro": "010-12345678",
            "storeCode": "BJ001",
            "lng": "116.434",
            "lat": "39.908",
        }
    )
    assert store is not None
    assert store["external_id"] == "kfc-BJ001"
    assert store["coordinate_system"] == "GCJ02"
    assert store["phone"] == "010-12345678"


def test_parse_kfc_store_list_payload() -> None:
    payload = {
        "Table": [{"rowcount": 2}],
        "Table1": [
            {
                "storeName": "肯德基(人民广场店)",
                "addressDetail": "南京东路100号",
                "cityName": "上海市",
                "provinceName": "上海市",
                "storeCode": "SH001",
            },
            {
                "storeName": "肯德基(天河店)",
                "addressDetail": "天河路1号",
                "cityName": "广州市",
                "provinceName": "广东省",
                "storeCode": "GZ001",
            },
        ],
    }
    rowcount, stores = parse_kfc_store_list_payload(payload)
    assert rowcount == 2
    assert len(stores) == 2
    assert stores[0]["external_id"] == "kfc-SH001"
