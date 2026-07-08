import json
import uuid
from pathlib import Path

import httpx

BASE = "https://order.kfc.com.cn/store-portal"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def wrap(params: dict) -> dict:
    return {**params, "encodeList": [], "isFromCustomerClient": True, "secretKey": "kfc"}


def common() -> dict:
    return {
        "portalType": "WAP",
        "portalSource": "",
        "channelName": "Mobile Web",
        "channelId": "13",
        "brand": "KFC_PRE",
        "business": "preorder",
        "sessionId": str(uuid.uuid4()),
        "deviceId": str(uuid.uuid4()),
        "clientVersion": "v6.626(86ae5fef)",
        "env": "prod",
    }


def main() -> None:
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Referer": "https://order.kfc.com.cn/preorder-taro/store",
        "Origin": "https://order.kfc.com.cn",
    }
    with httpx.Client(timeout=30, headers=headers) as client:
        cities = json.loads(OUT.joinpath("cities_correct.json").read_text(encoding="utf-8"))
        print("cities top keys", cities.keys())
        data = cities.get("data")
        print("data type", type(data).__name__)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    print(k, "list len", len(v))

        for kw in ("\u80af\u5fb7\u57fa", "KFC", "a"):
            body = wrap(
                {
                    **common(),
                    "gbCityCode": "110100",
                    "keyword": kw,
                    "pageIndex": 1,
                    "pageSize": 20,
                    "mylatPhone": "",
                    "mylngPhone": "",
                }
            )
            r = client.post(
                BASE + "/api/v2/store/searchByCityCodeAndKeyword",
                content=json.dumps(body, separators=(",", ":")).encode(),
            )
            OUT.joinpath(f"stores_kw_{kw}.json").write_text(r.text, encoding="utf-8")
            print("keyword", kw, r.status_code, len(r.content))

        body = wrap(
            {
                **common(),
                "mylat": "39.9042",
                "mylng": "116.4074",
                "gbCityCode": "110100",
                "pageIndex": 1,
                "pageSize": 50,
            }
        )
        r = client.post(
            BASE + "/api/v2/store/searchByLbs",
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        OUT.joinpath("stores_lbs.json").write_text(r.text, encoding="utf-8")
        print("lbs", r.status_code, len(r.content))


if __name__ == "__main__":
    main()
