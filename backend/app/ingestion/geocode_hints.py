import re

from app.schemas.poi import NormalizedLocation

_CITY_IN_ADDRESS = re.compile(r"([\u4e00-\u9fff]{2,10}?(?:市|地区|盟|州))")


def normalize_city_hint(city: str | None) -> str | None:
    if not city:
        return None
    cleaned = city.strip().removesuffix("市")
    return cleaned or None


def infer_city_from_address(address: str | None) -> str | None:
    if not address:
        return None
    match = _CITY_IN_ADDRESS.search(address)
    if not match:
        return None
    return normalize_city_hint(match.group(1))


def geocode_city_candidates(location: NormalizedLocation) -> list[str | None]:
    candidates: list[str | None] = []
    seen: set[str | None] = set()
    for city in (infer_city_from_address(location.address), location.city):
        normalized = normalize_city_hint(city)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    if None not in seen:
        candidates.append(None)
    return candidates


def join_region(province: str | None, city: str | None, district: str | None) -> str | None:
    parts = [part for part in (province, city, district) if part]
    if not parts:
        return None
    return "".join(parts)
