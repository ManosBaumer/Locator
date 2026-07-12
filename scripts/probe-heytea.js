/**
 * Probe HeyTea GO (mainland) store catalog API — not WeChat mini program.
 * Based on reverse-engineered HeyTea GO Android app headers (go.heytea.com).
 */
const GO_BASE = "https://go.heytea.com";
const GO_VERSION = "3.7.6";

function goHeaders() {
  return {
    Accept: "application/prs.heytea.v1+json",
    "Content-Type": "application/json",
    "User-Agent": "okhttp/4.12.0",
    Client: "2",
    "X-client": "app",
    "X-version": GO_VERSION,
    version: GO_VERSION,
    "GTM-Zone": "Asia/Shanghai",
    "Accept-Language": "zh-CN",
  };
}

async function getJson(url, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: { ...goHeaders(), ...(init.headers || {}) },
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return { status: res.status, json, text: text.slice(0, 500) };
}

async function main() {
  console.log("=== 1. Area / city list ===");
  const area = await getJson(
    `${GO_BASE}/api/service-sale/vip/openapi/area/include-country?include_country=1`
  );
  console.log("HTTP", area.status, "code", area.json?.code, area.json?.message);
  const china = (area.json?.data || []).find((c) => c.code === "156");
  const cities = china?.city || [];
  console.log("China cities:", cities.length);
  if (cities[0]) console.log("Sample city:", cities[0]);

  const testCity = cities.find((c) => /北京|110/.test(JSON.stringify(c))) || cities[0];
  if (!testCity) {
    console.log("No cities returned");
    return;
  }

  console.log("\n=== 2. Shop list for one city ===", testCity.city_code, testCity.name || "");
  const shops = await getJson(`${GO_BASE}/api/service-smc/grayapi/shop-list`, {
    method: "POST",
    body: JSON.stringify({
      country_code: "156",
      city_code: testCity.city_code,
      district_code: "",
      user_location: "",
    }),
  });
  console.log("HTTP", shops.status, "code", shops.json?.code, shops.json?.message);
  const list = shops.json?.data || [];
  console.log("Shops in city:", list.length);
  if (list[0]) {
    console.log("Sample shop:", {
      id: list[0].id,
      name: list[0].name,
      address: list[0].address,
      latitude: list[0].latitude,
      longitude: list[0].longitude,
      is_open: list[0].is_open,
      is_enable: list[0].is_enable,
    });
  }

  console.log("\n=== 3. Point search (international-style, CN app domain) ===");
  const near = await getJson(
    "https://app-cn.heytea-co.com/api/service-smc/openapi/app/user/closest/shop-list?country_code=156&user_location=116.4074,39.9042",
    {
      headers: {
        ...goHeaders(),
        "x-region-code": "CN",
        "x-region-id": "23",
        "client-system": "android",
        "Accept-Language": "en-US",
        "X-version": "2.3.1",
        version: "2.3.1",
      },
    }
  );
  console.log("HTTP", near.status, "code", near.json?.code, near.json?.message);
  console.log("Nearby count:", (near.json?.data || []).length);

  console.log("\n=== 4. Quick full-catalog estimate (first 5 cities) ===");
  let total = 0;
  for (const city of cities.slice(0, 5)) {
    const r = await getJson(`${GO_BASE}/api/service-smc/grayapi/shop-list`, {
      method: "POST",
      body: JSON.stringify({
        country_code: "156",
        city_code: city.city_code,
        district_code: "",
        user_location: "",
      }),
    });
    const n = (r.json?.data || []).length;
    total += n;
    console.log(`  ${city.city_code} ${city.name || ""}: ${n} shops`);
    await new Promise((r) => setTimeout(r, 100));
  }
  console.log("First 5 cities total:", total, "| extrapolated ~", Math.round((total / 5) * cities.length));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
