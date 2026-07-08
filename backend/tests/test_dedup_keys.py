from app.ingestion.dedup_keys import (
    make_content_external_id,
    normalize_address_core,
    normalize_store_name,
)


def test_normalize_store_name_strips_familymart_prefix() -> None:
    assert normalize_store_name("全家保利国际店") == "保利国际店"


def test_normalize_address_core_extracts_street_number() -> None:
    long_form = normalize_address_core(
        "广东省广州市海珠区阅江中路686保利国际广场西馆展览中心首层C105",
        province="广东",
        city="广州",
        district="海珠区",
    )
    short_form = normalize_address_core(
        "广州市海珠区阅江中路686号105房",
        province="广东",
        city="广州",
        district="海珠区",
    )
    assert long_form == short_form == "阅江中路686"


def test_make_content_external_id_collapses_address_variants() -> None:
    store_a = {
        "province": "广东",
        "city": "广州",
        "district": "海珠区",
        "name": "全家保利国际店",
        "address": "广东省广州市海珠区阅江中路686保利国际广场西馆展览中心首层C105",
    }
    store_b = {
        "province": "广东",
        "city": "广东省广州",
        "district": None,
        "name": "保利国际店",
        "address": "广州市海珠区阅江中路686号105房",
    }
    assert make_content_external_id("fm", store_a) == make_content_external_id("fm", store_b)
