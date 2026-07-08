from app.ingestion.amap_regions import (
    is_excluded_mainland_coordinates,
    is_excluded_mainland_region,
    is_excluded_mainland_text,
    is_mainland_scope_location,
)


def test_is_excluded_mainland_region_taiwan_province() -> None:
    assert is_excluded_mainland_region("台湾省")
    assert is_excluded_mainland_region("台灣")


def test_is_excluded_mainland_text_taiwan_address() -> None:
    assert is_excluded_mainland_text("台中市西区台湾大道二段")


def test_is_excluded_mainland_text_mainland_ok() -> None:
    assert not is_excluded_mainland_text("浙江省杭州市")
    assert not is_excluded_mainland_text("福建省平潭县")


def test_is_excluded_mainland_coordinates_taiwan() -> None:
    assert is_excluded_mainland_coordinates(120.545, 24.098)
    assert is_excluded_mainland_coordinates(121.47, 25.01)


def test_is_excluded_mainland_coordinates_mainland_fujian() -> None:
    assert not is_excluded_mainland_coordinates(119.79, 25.50)
    assert not is_excluded_mainland_coordinates(118.09, 24.48)


def test_is_excluded_mainland_region_hong_kong_and_macau() -> None:
    assert is_excluded_mainland_region("香港特别行政区")
    assert is_excluded_mainland_region("澳门特别行政区")
    assert is_excluded_mainland_region("澳門")


def test_is_excluded_mainland_text_keeps_mainland_hong_kong_road() -> None:
    assert not is_excluded_mainland_text("青岛市市南区香港中路31号银座商城")
    assert not is_excluded_mainland_text("北京市东城区王府井东街8号澳门中心1层")


def test_is_excluded_mainland_coordinates_macau() -> None:
    assert is_excluded_mainland_coordinates(113.55, 22.19)


def test_is_excluded_mainland_coordinates_shenzhen_not_excluded() -> None:
    assert not is_excluded_mainland_coordinates(114.009, 22.630)


def test_is_mainland_scope_location() -> None:
    assert not is_mainland_scope_location(province="香港特别行政区", city="香港特别行政区")
    assert is_mainland_scope_location(province="广东省", city="深圳市", address="深圳市龙华区民达路68号")
    assert is_mainland_scope_location(
        province="山东省",
        city="青岛市",
        address="青岛市市南区香港中路31号",
    )
