from pathlib import Path
import httpx, json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
url = "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname"
data = {"cname": "\u5317\u4eac", "pid": "", "pageIndex": "1", "pageSize": "5"}
headers = {"User-Agent": UA, "Referer": "http://www.kfc.com.cn/kfccda/storelist/index.aspx", "X-Requested-With": "XMLHttpRequest"}
r = httpx.post(url, data=data, headers=headers, timeout=30, follow_redirects=True)
out = Path("scripts/kfc_probe_out/legacy_test.json")
out.write_bytes(r.content)
print(r.status_code, len(r.content), r.text[:80])
