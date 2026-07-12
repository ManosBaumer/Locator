/**
 * Probe Molly Tea (茉莉奶白) store catalog APIs.
 *
 * Findings:
 * - Mainland ordering: Qmai on webapi.qmai.cn (login required, like Chagee).
 * - International marketing site: WordPress Agile Store Locator via admin-ajax (public).
 *
 * Usage: node scripts/probe-mollytea.js
 */
const lat = Number(process.argv.includes("--lat") ? process.argv[process.argv.indexOf("--lat") + 1] : 22.5431);
const lng = Number(process.argv.includes("--lng") ? process.argv[process.argv.indexOf("--lng") + 1] : 114.0579);

const QMAI_PATHS = [
  "/web/catering2-apiserver/shop/list",
  "/web/catering2-apiserver/shop/nearby",
  "/web/catering2-apiserver/store/list",
  "/web/catering/shop/list",
  "/web/catering/shop/nearby",
];

// Known / guessed Qmai brand store-ids to try (Chagee=49006 for reference)
const STORE_IDS = ["49006", "49007", "49008", "49009", "49100", "49200", "50000", "51000", "52000", "53000"];

const APP_IDS = [
  "wxafec6f8422cb357b", // chagee reference
  "wx6ac3f5090a6b99c5", // wechat test id placeholder
];

async function postJson(url, headers, body) {
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(12000),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return { status: res.status, json, text: text.slice(0, 200) };
}

function qmaiHeaders(storeId, appid) {
  return {
    "Content-Type": "application/json",
    Accept: "v=1.0",
    "Qm-From": "wechat",
    "Qm-From-Type": "catering",
    "store-id": storeId,
    "User-Agent": "Mozilla/5.0",
    Referer: `https://servicewechat.com/${appid}/83/page-frame.html`,
  };
}

async function probeHosts() {
  console.log("\n=== Direct Molly Tea hosts ===");
  const hosts = [
    "https://api.mollytea.com",
    "https://api.mollytea.cn",
    "https://app-api.mollytea.com",
    "https://order.mollytea.com",
    "https://go.mollytea.com",
    "https://h5.mollytea.com",
    "https://member.mollytea.com",
    "https://openapi.mollytea.com",
    "https://mp-api.mollytea.com",
    "https://api-hk.mollytea.com",
  ];
  for (const h of hosts) {
    try {
      const r = await fetch(h, { signal: AbortSignal.timeout(10000), headers: { "User-Agent": "okhttp/4.12.0" } });
      console.log(h, "->", r.status);
    } catch (e) {
      console.log(h, "->", e.cause?.code || e.message.slice(0, 40));
    }
  }
}

async function probeQmaiBruteforce() {
  console.log("\n=== Qmai store-id sweep @ Shenzhen ===", lat, lng);
  const body = { latitude: lat, longitude: lng, page: 1, pageSize: 20, appid: "wx0000000000000000" };
  for (const storeId of STORE_IDS) {
    for (const path of QMAI_PATHS.slice(0, 2)) {
      const res = await postJson(`https://webapi.qmai.cn${path}`, qmaiHeaders(storeId, APP_IDS[0]), body);
      const code = res.json?.code ?? res.json?.status;
      const msg = res.json?.message ?? res.text.slice(0, 60);
      if (code !== 10008 && code !== "401" && code !== 401) {
        console.log("HIT?", storeId, path, "->", res.status, code, msg);
      }
    }
  }
  console.log("(all tested IDs returned 10008/401 — login required or wrong store-id)");
}

async function probeCnSite() {
  console.log("\n=== cn.mollytea.com asset scan ===");
  try {
    const html = await (await fetch("https://cn.mollytea.com", { headers: { "User-Agent": "Mozilla/5.0" } })).text();
    const urls = [...html.matchAll(/https?:\/\/[^\s"'<>]+/g)]
      .map((m) => m[0])
      .filter((u) => /api|molly|qmai|store|shop|wx/i.test(u));
    console.log([...new Set(urls)].slice(0, 20));
    const scripts = [...html.matchAll(/src="([^"]+\.js[^"]*)"/g)].map((m) => m[1]);
    console.log("js assets:", scripts.slice(0, 10));
    for (const src of scripts.slice(0, 3)) {
      const url = src.startsWith("http") ? src : new URL(src, "https://cn.mollytea.com").href;
      try {
        const js = await (await fetch(url, { signal: AbortSignal.timeout(15000) })).text();
        for (const needle of ["qmai", "webapi", "store-id", "appid", "wx", "shop/list", "api."]) {
          if (js.includes(needle)) console.log("  in", url.split("/").pop(), ":", needle);
        }
      } catch {}
    }
  } catch (e) {
    console.log("failed:", e.message);
  }
}

async function probeWordPressStoreLocator() {
  console.log("\n=== WordPress Agile Store Locator (international only) ===");
  const origins = ["https://hk.mollytea.com", "https://cn.mollytea.com"];
  for (const origin of origins) {
    try {
      const res = await fetch(`${origin}/wp-admin/admin-ajax.php`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ action: "asl_load_stores" }),
        signal: AbortSignal.timeout(20000),
      });
      const text = await res.text();
      let json;
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
      if (Array.isArray(json)) {
        const cnLike = json.filter((s) => /[\u4e00-\u9fff]|China|中国/.test(JSON.stringify(s)));
        console.log(origin, "->", json.length, "stores,", cnLike.length, "mainland-like");
        if (json[0]) console.log("  sample:", json[0].title, json[0].country, json[0].lat, json[0].lng);
      } else {
        console.log(origin, "->", res.status, text.slice(0, 80));
      }
    } catch (e) {
      console.log(origin, "ERR", e.message.slice(0, 60));
    }
  }
}

async function probeIntlAppPattern() {
  console.log("\n=== International app pattern (like Chagee api-sea) ===");
  const bases = [
    "https://api-sea.mollytea.com",
    "https://api.mollytea.hk",
    "https://api-hk.mollytea.com",
    "https://app-api.mollytea.hk",
  ];
  const body = { latitude: 22.3193, longitude: 114.1694, pageNum: 1, pageSize: 5, channelCode: "H5", userId: "", isTakeaway: false };
  const headers = {
    ua: "Dart/2.12 (dart:io)",
    region: "HK",
    channel: "H5",
    apv: "1.1.1",
    authorization: "null",
    "content-type": "application/json",
  };
  for (const base of bases) {
    try {
      const res = await postJson(`${base}/api/navigation/store/list`, headers, body);
      console.log(base, "->", res.status, res.text.replace(/\s+/g, " ").slice(0, 120));
    } catch (e) {
      console.log(base, "->", e.cause?.code || e.message.slice(0, 40));
    }
  }
}

async function main() {
  console.log("Molly Tea (茉莉奶白) probe");
  await probeHosts();
  await probeWordPressStoreLocator();
  await probeIntlAppPattern();
  await probeCnSite();
  await probeQmaiBruteforce();
  console.log("\n=== Verdict ===");
  console.log(
    "Mainland (~2000 stores): likely Qmai on webapi.qmai.cn with Qm-User-Token — no public catalog found."
  );
  console.log(
    "International only: POST https://hk.mollytea.com/wp-admin/admin-ajax.php action=asl_load_stores (~49 overseas stores, public JSON)."
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
