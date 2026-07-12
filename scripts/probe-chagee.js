/**
 * Probe Chagee store catalog APIs (mainland China vs international).
 *
 * Findings (2026-07):
 * - International (SG/MY/TH/…): POST api-sea.chagee.com/api/navigation/store/list
 *   Public, no auth. ~471 stores. Does NOT include mainland China (0 stores @ Shanghai).
 * - Mainland China: Qmai consumer stack on webapi.qmai.cn (store-id 49006).
 *   Endpoints like /web/catering2-apiserver/shop/list exist but return code 10008 without
 *   Qm-User-Token (WeChat mini-program / app session). No HeyTea-style public catalog found.
 * - api.chagee.com proxies to sea-gf-api.bwcj.biz and 404s for mainland store list.
 * - New CN app (com.chagee.application.cn) API host not reachable from this network; needs
 *   DevTools/APK capture (likely separate from api-sea until confirmed).
 *
 * Usage:
 *   node scripts/probe-chagee.js
 *   node scripts/probe-chagee.js --lat 31.2304 --lng 121.4737
 */

const lat = Number(process.argv.includes("--lat") ? process.argv[process.argv.indexOf("--lat") + 1] : 31.2304);
const lng = Number(process.argv.includes("--lng") ? process.argv[process.argv.indexOf("--lng") + 1] : 121.4737);

function seaHeaders(region = "SG") {
  return {
    ua: "Dart/2.12 (dart:io)",
    debug: "1",
    os: "web",
    language: region === "CN" ? "zh-cn" : "en-us",
    "accept-language": region === "CN" ? "zh-CN" : "en-US",
    region,
    channel: "H5",
    apv: "3.22.0",
    aid: "100001",
    timezoneoffset: "480",
    devicetimezoneregion: "Asia/Shanghai",
    authorization: "null",
    "content-type": "application/json",
  };
}

function qmaiHeaders() {
  return {
    "Content-Type": "application/json",
    Accept: "v=1.0",
    "Qm-From": "wechat",
    "Qm-From-Type": "catering",
    "store-id": "49006",
    "User-Agent": "Mozilla/5.0",
    Referer: "https://servicewechat.com/wxafec6f8422cb357b/140/page-frame.html",
  };
}

async function postJson(url, headers, body) {
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return { status: res.status, json, text: text.slice(0, 400) };
}

async function probeSea() {
  console.log("\n=== International: api-sea.chagee.com ===");
  const body = {
    latitude: lat,
    longitude: lng,
    pageNum: 1,
    pageSize: 5,
    channelCode: "H5",
    userId: "",
    isTakeaway: false,
  };
  const res = await postJson(
    "https://api-sea.chagee.com/api/navigation/store/list",
    seaHeaders("SG"),
    body
  );
  const total = res.json?.data?.total;
  const sample = res.json?.data?.pageList?.[0];
  console.log("HTTP", res.status, "errcode", res.json?.errcode, "total", total);
  if (sample) {
    console.log("Sample:", sample.storeNo, sample.storeName, sample.cityName, sample.latitude, sample.longitude);
  }

  const cnRes = await postJson(
    "https://api-sea.chagee.com/api/navigation/store/list",
    seaHeaders("CN"),
    body
  );
  console.log(
    "CN region @ Shanghai:",
    "total",
    cnRes.json?.data?.total,
    "stores",
    cnRes.json?.data?.pageList?.length ?? 0
  );

  const cityRes = await postJson(
    "https://api-sea.chagee.com/api/navigation/store/cityList",
    seaHeaders("SG"),
    {}
  );
  const cities = (cityRes.json?.data || []).flatMap((g) => g.cityList || []);
  const cnNamed = cities.filter((c) => /[\u4e00-\u9fff]/.test(c.cityName || ""));
  console.log("cityList:", cities.length, "cities with Chinese names:", cnNamed.length);
}

async function probeQmai() {
  console.log("\n=== Mainland (Qmai): webapi.qmai.cn ===");
  const body = {
    latitude: lat,
    longitude: lng,
    lng,
    lat,
    page: 1,
    pageSize: 20,
    appid: "wxafec6f8422cb357b",
  };
  const paths = [
    "/web/catering2-apiserver/shop/list",
    "/web/catering2-apiserver/shop/nearby",
    "/web/catering2-apiserver/store/list",
    "/web/catering/shop/list",
    "/web/catering/shop/nearby",
  ];
  for (const path of paths) {
    const res = await postJson(`https://webapi.qmai.cn${path}`, qmaiHeaders(), body);
    console.log(path, "->", res.status, res.json?.code ?? res.text.slice(0, 80));
  }
}

async function probeChinaGateway() {
  console.log("\n=== China gateway: api.chagee.com ===");
  const body = {
    latitude: lat,
    longitude: lng,
    pageNum: 1,
    pageSize: 5,
    channelCode: "H5",
    userId: "",
    isTakeaway: false,
  };
  const res = await postJson(
    "https://api.chagee.com/api/navigation/store/list",
    seaHeaders("CN"),
    body
  );
  console.log("HTTP", res.status, res.text.replace(/\s+/g, " ").slice(0, 200));
}

async function scrapeH5() {
  console.log("\n=== h5.bwcj.com asset scan ===");
  try {
    const res = await fetch("https://h5.bwcj.com", {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(15000),
    });
    const html = await res.text();
    const hits = [...html.matchAll(/https?:\/\/[^\s"'<>]+/g)]
      .map((m) => m[0])
      .filter((u) => /api|qmai|chagee|bwcj|store|shop/i.test(u));
    console.log("HTTP", res.status, "unique api-like URLs:", [...new Set(hits)].slice(0, 15));
  } catch (err) {
    console.log("fetch failed:", err.message);
  }
}

async function main() {
  console.log("Chagee probe @", lat, lng);
  await probeSea();
  await probeQmai();
  await probeChinaGateway();
  await scrapeH5();
  console.log("\n=== Verdict ===");
  console.log(
    "Mainland: no public unauthenticated store catalog found. Best lead is Qmai webapi.qmai.cn with Qm-User-Token, or capture the CN native app API."
  );
  console.log("International: api-sea.chagee.com/api/navigation/store/list (public, lat/lng pagination).");
  console.log("\nDone.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
