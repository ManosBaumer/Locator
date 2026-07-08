from pathlib import Path

from app.ingestion.adapters.mcdonalds import RESULTS_PER_QUERY
from app.ingestion.adapters.mcdonalds_deliveryinfo import (
    CITY_INITIAL_STEP_DEGREES,
    DisclosureStore,
    McDonaldsDeliveryinfoAdapter,
    bbox_radius_for_store_count,
    city_disclosure_complete,
    city_should_subdivide,
    unmatched_disclosure_rows,
    disclosure_keys_by_city,
    match_disclosure_to_api,
    parse_deliveryinfo_page,
    parse_max_deliveryinfo_page,
)
from app.ingestion.adapters.mcdonalds_deliveryinfo_checkpoint import (
    McDonaldsDeliveryinfoCheckpoint,
)


SAMPLE_HTML = """
<table>
<tr><th>城市</th><th>门店名称</th></tr>
<tr>
  <td>城市 广州市</td>
  <td>门店名称 麦当劳广州天河领展广场餐厅</td>
  <td>信息公示</td>
</tr>
<tr>
  <td>城市 深圳市</td>
  <td>门店名称 麦当劳深圳万象城餐厅</td>
  <td>信息公示</td>
</tr>
</table>
<a href="?page=812">812</a>
"""


def test_parse_deliveryinfo_page() -> None:
    stores = parse_deliveryinfo_page(SAMPLE_HTML)
    assert stores == [
        DisclosureStore(city="广州市", name="麦当劳广州天河领展广场餐厅"),
        DisclosureStore(city="深圳市", name="麦当劳深圳万象城餐厅"),
    ]


def test_parse_max_deliveryinfo_page() -> None:
    assert parse_max_deliveryinfo_page(SAMPLE_HTML) == 812


def test_match_disclosure_to_api() -> None:
    disclosure = [
        DisclosureStore(city="广州市", name="麦当劳广州天河领展广场餐厅"),
        DisclosureStore(city="广州市", name="麦当劳广州不存在的餐厅"),
    ]
    api_stores = {
        "mcd-1": {
            "city": "广州市",
            "name": "麦当劳广州天河领展广场餐厅",
        }
    }
    matched, unmatched = match_disclosure_to_api(disclosure, api_stores)
    assert matched == 1
    assert unmatched == 1


def test_disclosure_keys_by_city() -> None:
    disclosure = [
        DisclosureStore(city="广州市", name="麦当劳广州天河领展广场餐厅"),
        DisclosureStore(city="广州市", name="麦当劳广州体育东餐厅"),
        DisclosureStore(city="深圳市", name="麦当劳深圳万象城餐厅"),
    ]
    grouped = disclosure_keys_by_city(disclosure)
    assert len(grouped["广州市"]) == 2
    assert len(grouped["深圳市"]) == 1


def test_city_disclosure_complete() -> None:
    disclosure = [
        DisclosureStore(city="广州市", name="麦当劳广州天河领展广场餐厅"),
        DisclosureStore(city="广州市", name="麦当劳广州体育东餐厅"),
    ]
    pending = disclosure_keys_by_city(disclosure)["广州市"]
    partial = {
        "mcd-1": {"city": "广州市", "name": "麦当劳广州天河领展广场餐厅"},
    }
    assert city_disclosure_complete(partial, "广州市", pending) is False
    complete = {
        "mcd-1": {"city": "广州市", "name": "麦当劳广州天河领展广场餐厅"},
        "mcd-2": {"city": "广州市", "name": "麦当劳广州体育东餐厅"},
    }
    assert city_disclosure_complete(complete, "广州市", pending) is True


def test_bbox_radius_for_store_count() -> None:
    assert bbox_radius_for_store_count(2) < bbox_radius_for_store_count(15)
    assert bbox_radius_for_store_count(50) >= bbox_radius_for_store_count(15)


def test_deliveryinfo_checkpoint_manifest_and_city_files(tmp_path: Path) -> None:
    checkpoint = McDonaldsDeliveryinfoCheckpoint(tmp_path, adapter_version="1.2.0")
    checkpoint.save_manifest(
        [
            {"city": "广州市", "name": "麦当劳广州天河领展广场餐厅"},
        ]
    )
    checkpoint.save_city(
        "广州市",
        {
            "mcd-1": {
                "external_id": "mcd-1",
                "city": "广州市",
                "name": "麦当劳广州天河领展广场餐厅",
            }
        },
        search_requests=12,
        stopped_early=True,
    )
    checkpoint.save_state(completed_cities=["广州市"], request_count=12)

    assert checkpoint.load_manifest() == [
        {"city": "广州市", "name": "麦当劳广州天河领展广场餐厅"},
    ]
    assert checkpoint.load_state() == {
        "completed_cities": ["广州市"],
        "request_count": 12,
    }
    stores = checkpoint.load_all_stores()
    assert stores["mcd-1"]["name"] == "麦当劳广州天河领展广场餐厅"
    checkpoint.save_geocode("广州市", 23.1, 113.2)
    assert checkpoint.load_geocode("广州市") == (23.1, 113.2)


def test_city_should_subdivide() -> None:
    saturated = [{"id": i} for i in range(RESULTS_PER_QUERY)]
    partial = [{"id": 1}]

    assert city_should_subdivide(saturated, 0.04) is True
    assert city_should_subdivide(saturated, 0.02) is True
    assert city_should_subdivide(saturated, 0.01) is False

    assert city_should_subdivide(partial, 0.04) is False
    assert city_should_subdivide(partial, 0.04, allow_partial_one_level=True) is True
    assert city_should_subdivide(partial, 0.02, allow_partial_one_level=True) is False

    assert city_should_subdivide([], CITY_INITIAL_STEP_DEGREES) is False


def test_unmatched_disclosure_rows() -> None:
    disclosure = [
        DisclosureStore(city="广州市", name="麦当劳广州天河领展广场餐厅"),
        DisclosureStore(city="广州市", name="麦当劳广州不存在的餐厅"),
    ]
    stores = {
        "mcd-1": {"city": "广州市", "name": "麦当劳广州天河领展广场餐厅"},
    }
    unmatched = unmatched_disclosure_rows(disclosure, stores)
    assert len(unmatched) == 1
    assert unmatched[0].name == "麦当劳广州不存在的餐厅"


def test_adapter_version() -> None:
    assert McDonaldsDeliveryinfoAdapter.adapter_version == "1.4.0"
    assert McDonaldsDeliveryinfoAdapter.chain_slug == "mcdonalds"
