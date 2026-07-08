"""Helpers to collapse duplicate store records that differ only by address wording."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_CHAIN_PREFIXES = (
    "全家便利店",
    "全家FamilyMart",
    "FamilyMart",
    "全家",
    "7-ELEVEn",
    "7-ELEVEN",
    "7-11",
    "永辉超市",
    "永辉",
    "盒马",
    "麦当劳",
    "肯德基",
    "KFC",
    "七鲜超市",
    "七鲜生活",
)

_REGION_SUFFIXES = (
    "特别行政区",
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "自治区",
    "省",
    "市",
)

_STREET_NUMBER = re.compile(
    r"([\u4e00-\u9fff]{2,30}(?:路|街|道|巷|里|大道|大街|公路|快速|环线))"
    r"(\d+(?:-\d+)?)",
)


def normalize_store_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"\s+", "", name.strip())
    for prefix in _CHAIN_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    cleaned = cleaned.strip("()（）·-— ")
    return cleaned.casefold()


def normalize_region(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"\s+", "", value.strip())
    for suffix in _REGION_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.casefold()


def normalize_city(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"\s+", "", value.strip())
    if "省" in cleaned:
        _, after_province = cleaned.split("省", 1)
        if after_province:
            cleaned = after_province
    return normalize_region(cleaned)


def normalize_address_core(
    address: str | None,
    *,
    province: str | None = None,
    city: str | None = None,
    district: str | None = None,
) -> str:
    if not address:
        return ""

    cleaned = re.sub(r"\s+", "", address.strip())
    for prefix in (
        province or "",
        city or "",
        district or "",
        f"{normalize_region(province)}{normalize_region(city)}",
        f"{normalize_region(province)}省{normalize_region(city)}市",
        f"{normalize_region(city)}市",
    ):
        prefix = re.sub(r"\s+", "", prefix)
        if prefix and cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]

    cleaned = cleaned.lstrip("省市区县 ")
    cleaned = cleaned.replace("号", "")

    match = _STREET_NUMBER.search(cleaned)
    if match:
        return f"{match.group(1).casefold()}{match.group(2)}"

    return cleaned.casefold()


def make_content_external_id(prefix: str, store: dict[str, Any]) -> str:
    """Stable ID from semantic store identity, not raw address text."""
    key = "|".join(
        [
            normalize_region(store.get("province")),
            normalize_city(store.get("city")),
            normalize_store_name(store.get("name")),
            normalize_address_core(
                store.get("address"),
                province=store.get("province"),
                city=store.get("city"),
                district=store.get("district"),
            ),
        ]
    )
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def dedup_key_for_store(store: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_region(store.get("province")),
        normalize_city(store.get("city")),
        normalize_store_name(store.get("name")),
        normalize_address_core(
            store.get("address"),
            province=store.get("province"),
            city=store.get("city"),
            district=store.get("district"),
        ),
    )


def pick_richer_store(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Prefer the record with more complete location fields and longer address."""
    existing_score = (
        len(existing.get("address") or ""),
        len(existing.get("district") or ""),
        len(existing.get("city") or ""),
    )
    candidate_score = (
        len(candidate.get("address") or ""),
        len(candidate.get("district") or ""),
        len(candidate.get("city") or ""),
    )
    return candidate if candidate_score > existing_score else existing
