from app.utils.geocoding.amap import _confidence_from_level


def test_confidence_from_level_rejects_district_only() -> None:
    assert _confidence_from_level("区县") == 0.5


def test_confidence_from_level_accepts_doorplate() -> None:
    assert _confidence_from_level("门牌号") == 0.9
