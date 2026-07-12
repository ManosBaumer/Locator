/**
 * HeyTea GO Android app API (mainland China) — go.heytea.com
 * Not the WeChat mini program.
 */

const GO_BASE = "https://go.heytea.com";
const GO_VERSION = "3.7.6";
const CHINA_COUNTRY_CODE = "156";

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

async function parseEnvelope(res) {
  const status = res.status;
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`Invalid JSON (${status}): ${text.slice(0, 200)}`);
  }
  if (json.code !== 0) {
    throw new Error(`API code ${json.code}: ${json.message || "unknown"}`);
  }
  return json;
}

async function fetchMainlandCities() {
  const res = await fetch(
    `${GO_BASE}/api/service-sale/vip/openapi/area/include-country?include_country=1`,
    { headers: goHeaders() }
  );
  const envelope = await parseEnvelope(res);
  const china = (envelope.data || []).find((c) => c.code === CHINA_COUNTRY_CODE);
  return china?.city || [];
}

async function fetchShopsForCity(cityCode) {
  const res = await fetch(`${GO_BASE}/api/service-smc/grayapi/shop-list`, {
    method: "POST",
    headers: goHeaders(),
    body: JSON.stringify({
      country_code: CHINA_COUNTRY_CODE,
      city_code: cityCode,
      district_code: "",
      user_location: "",
    }),
  });
  const envelope = await parseEnvelope(res);
  return envelope.data || [];
}

module.exports = {
  GO_BASE,
  GO_VERSION,
  CHINA_COUNTRY_CODE,
  goHeaders,
  fetchMainlandCities,
  fetchShopsForCity,
};
