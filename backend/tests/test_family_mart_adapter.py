from app.ingestion.adapters.family_mart import (
    decode_page_text,
    make_store_external_id,
    parse_store_table,
    repair_corrupted_export_text,
)


def test_parse_store_table_five_columns() -> None:
    html = """
    <table>
      <tr><th>省</th><th>市</th><th>区</th><th>名</th><th>地址</th></tr>
      <tr>
        <td>北京</td><td>北京</td><td>朝阳区</td><td>常营一店</td>
        <td>北京市朝阳区常惠路6号楼1层101</td>
      </tr>
    </table>
    """
    stores = parse_store_table(html)
    assert len(stores) == 1
    assert stores[0]["province"] == "北京"
    assert stores[0]["district"] == "朝阳区"
    assert stores[0]["external_id"].startswith("fm-")


def test_parse_store_table_four_columns() -> None:
    html = """
    <table>
      <tr><th>省</th><th>市</th><th>名</th><th>地址</th></tr>
      <tr>
        <td>广东</td><td>深圳</td><td>全家便利店（红桂路店）</td>
        <td>深圳市罗湖区红桂路金众经典家园1B</td>
      </tr>
    </table>
    """
    stores = parse_store_table(html)
    assert len(stores) == 1
    assert stores[0]["district"] is None


def test_decode_page_text_gbk() -> None:
    html = "北京市朝阳区".encode("gbk")
    assert "北京市" in decode_page_text(html)


def test_repair_corrupted_export_text() -> None:
    assert repair_corrupted_export_text("金?M阁金茗阁裙楼1B") == "金茗阁裙楼1B"
    assert repair_corrupted_export_text("地铁?I岭站店") == "地铁下梅林站店"
    assert repair_corrupted_export_text("上海市宝山区?川路1588号") == "上海市宝山区蕰川路1588号"
    assert repair_corrupted_export_text("地铁沥滘镜?") == "地铁沥滘站"
    assert repair_corrupted_export_text("广州市海珠区广州地铁三号线沥滘?LJ-3-5S") == "广州市海珠区广州地铁三号线沥滘站LJ-3-5S"
    assert repair_corrupted_export_text("北京市朝阳区") == "北京市朝阳区"


def test_parse_store_table_repairs_corrupted_address() -> None:
    html = """
    <table>
      <tr><th>省</th><th>市</th><th>区</th><th>名</th><th>地址</th></tr>
      <tr>
        <td>广东</td><td>深圳</td><td>罗湖区</td><td>红桂路店</td>
        <td>深圳市罗湖区红桂路金众经典家园金?M阁金茗阁裙楼1B</td>
      </tr>
    </table>
    """
    stores = parse_store_table(html)
    assert len(stores) == 1
    assert "?" not in stores[0]["address"]
    assert "金茗阁" in stores[0]["address"]


def test_parse_store_table_excludes_taiwan_address() -> None:
    html = """
    <table>
      <tr><th>省</th><th>市</th><th>区</th><th>名</th><th>地址</th></tr>
      <tr>
        <td>浙江</td><td>杭州</td><td>西湖区</td><td>台湾大道店</td>
        <td>台中市西区台湾大道556-5号</td>
      </tr>
    </table>
    """
    assert parse_store_table(html) == []


def test_make_store_external_id_stable() -> None:
    store = {
        "province": "上海",
        "city": "上海",
        "district": "静安区",
        "name": "常德店",
        "address": "上海市静安区常德路333号",
    }
    assert make_store_external_id(store) == make_store_external_id(store)
