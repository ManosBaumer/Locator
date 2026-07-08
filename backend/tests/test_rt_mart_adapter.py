from app.ingestion.adapters.rt_mart import parse_store_cards, split_city_and_name

SAMPLE_HTML = """
<div class="store-item">
  <a href="/stores/store-info?storeId=1001">了解门店</a>
  <div>上海市-闸北店</div>
  <div>营业时间：07:30 - 22:00</div>
  <div>门店地址：上海市闸北区共和新路3318号</div>
  <div>服务电话：021-56032077</div>
</div>
"""


def test_parse_store_cards_extracts_fields() -> None:
    stores = parse_store_cards(SAMPLE_HTML)
    assert len(stores) == 1
    assert stores[0]["store_id"] == "1001"
    assert stores[0]["display_name"] == "上海市-闸北店"
    assert stores[0]["address"] == "上海市闸北区共和新路3318号"
    assert stores[0]["hours"] == "07:30 - 22:00"
    assert stores[0]["phone"] == "021-56032077"


def test_split_city_and_name() -> None:
    assert split_city_and_name("上海市-闸北店") == ("上海市", "闸北店")
    assert split_city_and_name("闸北店") == (None, "闸北店")
