from app.ingestion.adapters.yonghui import make_store_external_id, parse_store_table


def test_parse_store_table_four_columns() -> None:
    html = """
    <table>
      <tr><th>省份</th><th>城市</th><th>门店名称</th><th>门店地址</th></tr>
      <tr>
        <td>福建省</td><td>福州市</td><td>金祥店</td>
        <td>福州市仓山区金祥路530号</td>
      </tr>
    </table>
    """
    stores = parse_store_table(html)
    assert len(stores) == 1
    assert stores[0]["province"] == "福建"
    assert stores[0]["city"] == "福州"
    assert stores[0]["external_id"].startswith("yh-")


def test_parse_store_table_excludes_taiwan() -> None:
    html = """
    <table>
      <tr><th>省份</th><th>城市</th><th>门店名称</th><th>门店地址</th></tr>
      <tr>
        <td>台湾省</td><td>台北市</td><td>台北店</td>
        <td>台北市中正区重庆南路一段</td>
      </tr>
    </table>
    """
    assert parse_store_table(html) == []


def test_make_store_external_id_stable() -> None:
    store = {
        "province": "福建",
        "city": "福州",
        "name": "金祥店",
        "address": "福州市仓山区金祥路530号",
    }
    assert make_store_external_id(store) == make_store_external_id(store)
