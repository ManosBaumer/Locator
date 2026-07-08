from app.ingestion.adapters.mcdonalds import (
    McDonaldsAdapter,
    McDonaldsDailyQuotaExceeded,
    McDonaldsTransientError,
    PlateauTracker,
    iter_initial_grid,
    parse_search_by_point_payload,
    parse_store_record,
    should_stop_on_plateau,
    should_subdivide,
    subdivide_cell,
)


def test_parse_store_record() -> None:
    record = {
        "id": "6a25d9d45675ea6c5775f3ad",
        "title": "麦当劳广州南站三楼A23检票口上方餐厅",
        "address": "石壁街南站南路133号332",
        "province": "广东省",
        "city": "广州市",
        "district": "番禺区",
        "tel": "020-22510993",
        "location": {"lat": 22.98847, "lng": 113.26986},
    }
    store = parse_store_record(record)
    assert store is not None
    assert store["external_id"] == "mcd-6a25d9d45675ea6c5775f3ad"
    assert store["latitude"] == 22.98847
    assert store["longitude"] == 113.26986


def test_parse_store_record_excludes_hong_kong() -> None:
    record = {
        "id": "hk-1",
        "title": "麦当劳香港店",
        "address": "香港某地址",
        "province": "香港特别行政区",
        "city": "香港特别行政区",
        "location": {"lat": 22.3, "lng": 114.1},
    }
    assert parse_store_record(record) is None


def test_should_subdivide_when_saturated() -> None:
    rows = [{"_distance": 2000} for _ in range(10)]
    assert should_subdivide(rows, 0.10) is True
    assert should_subdivide(rows, 0.004) is False


def test_should_subdivide_on_partial_hits() -> None:
    rows = [{"_distance": 2000} for _ in range(3)]
    assert should_subdivide(rows, 0.10) is True
    assert should_subdivide(rows, 0.004) is False


def test_should_subdivide_empty_large_cells() -> None:
    assert should_subdivide([], 0.10) is True
    assert should_subdivide([], 0.05) is False
    assert should_subdivide([], 0.025) is False


def test_subdivide_cell_returns_four_children() -> None:
    children = subdivide_cell(23.12, 113.35, 0.10)
    assert len(children) == 4
    steps = {step for _, _, step in children}
    assert steps == {0.05}


def test_initial_grid_skips_excluded_coordinates() -> None:
    cells = list(
        iter_initial_grid(
            min_lat=22.0,
            max_lat=22.2,
            min_lng=113.5,
            max_lng=113.7,
            step=0.10,
        )
    )
    for lat, lng, _ in cells:
        assert not (113.50 <= lng <= 113.60 and 22.08 <= lat <= 22.22)


def test_adapter_version() -> None:
    assert McDonaldsAdapter.adapter_version == "0.3.3"


def test_should_stop_on_plateau() -> None:
    assert should_stop_on_plateau(4999, 5000) is False
    assert should_stop_on_plateau(5000, 5000) is True
    assert should_stop_on_plateau(5000, 999) is False


def test_plateau_tracker_stops_on_sparse_window() -> None:
    tracker = PlateauTracker()
    for _ in range(4999):
        reached, _ = tracker.record_request(0, 5000, queue_size=0)
        assert reached is False
    reached, window_new = tracker.record_request(1, 5000, queue_size=0)
    assert reached is True
    assert window_new == 1


def test_plateau_tracker_waits_for_queue_to_drain() -> None:
    tracker = PlateauTracker()
    for _ in range(4999):
        tracker.record_request(0, 5000, queue_size=10_000)
    reached, _ = tracker.record_request(1, 5000, queue_size=10_000)
    assert reached is False


def test_plateau_tracker_continues_when_finding_stores() -> None:
    tracker = PlateauTracker()
    for _ in range(5000):
        reached, _ = tracker.record_request(1, 5000, queue_size=0)
        assert reached is False


def test_parse_search_by_point_payload_quota() -> None:
    payload = {
        "message": {
            "status": 121,
            "message": "此key每日调用量已达到上限",
        }
    }
    try:
        parse_search_by_point_payload(payload)
        raise AssertionError("expected McDonaldsDailyQuotaExceeded")
    except McDonaldsDailyQuotaExceeded as exc:
        assert "上限" in str(exc)


def test_parse_search_by_point_payload_success() -> None:
    payload = {
        "count": 1,
        "data": [{"id": "abc", "location": {"lat": 23.1, "lng": 113.2}}],
    }
    rows = parse_search_by_point_payload(payload)
    assert len(rows) == 1
    assert rows[0]["id"] == "abc"


def test_parse_search_by_point_payload_transient_error() -> None:
    payload = {
        "message": {
            "status": 539,
            "message": "内部错误，请稍后重试",
        }
    }
    try:
        parse_search_by_point_payload(payload)
        raise AssertionError("expected McDonaldsTransientError")
    except McDonaldsTransientError as exc:
        assert "539" in str(exc)
