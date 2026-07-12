/**
 * Probe PetroChina 95504 station search endpoint.
 * Run from a China IP / browser session if Aliyun WAF blocks overseas requests.
 *
 *   node scripts/probe-petrochina.js
 *   node scripts/probe-petrochina.js --lat 39.9042 --lng 116.4074
 */
const BASE = "https://www.95504.net/NewServiceWithSupport/StationSearch.aspx";

function parseArgs(argv) {
  const args = { lat: 39.9042, lng: 116.4074, distance: 5000 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--lat") args.lat = Number(argv[++i]);
    else if (a === "--lng") args.lng = Number(argv[++i]);
    else if (a === "--distance") args.distance = Number(argv[++i]);
  }
  return args;
}

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  Accept: "application/json, text/javascript, */*; q=0.01",
  "Accept-Language": "zh-CN,zh;q=0.9",
  Referer: BASE,
  Origin: "https://www.95504.net",
  "X-Requested-With": "XMLHttpRequest",
};

async function tryRequest(label, url, init) {
  try {
    const res = await fetch(url, init);
    const text = await res.text();
    const preview = text.slice(0, 500).replace(/\s+/g, " ");
    console.log(`\n=== ${label} ===`);
    console.log(`HTTP ${res.status} ${res.statusText} (${text.length} bytes)`);
    console.log(preview);
    if (text.startsWith("{") || text.startsWith("[")) {
      try {
        console.log("JSON:", JSON.stringify(JSON.parse(text), null, 2).slice(0, 2000));
      } catch {
        /* ignore */
      }
    }
    return { ok: res.ok, status: res.status, text };
  } catch (err) {
    console.log(`\n=== ${label} ===`);
    console.log("ERROR:", err.message);
    return { ok: false, error: err.message };
  }
}

async function main() {
  const { lat, lng, distance } = parseArgs(process.argv);
  console.log(`Probing ${BASE} near ${lat}, ${lng} (distance=${distance}m)`);

  await tryRequest("GET page", BASE, { headers: HEADERS });

  const formBodies = [
    `longitude=${lng}&latitude=${lat}&distance=${distance}`,
    `lng=${lng}&lat=${lat}&distance=${distance}`,
    `Lon=${lng}&Lat=${lat}&Radius=${distance}`,
    `x=${lng}&y=${lat}&r=${distance}`,
  ];
  for (const body of formBodies) {
    await tryRequest(`POST form ${body.split("&")[0]}…`, BASE, {
      method: "POST",
      headers: { ...HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      body,
    });
  }

  const jsonBody = JSON.stringify({ longitude: lng, latitude: lat, distance });
  await tryRequest("POST JSON", BASE, {
    method: "POST",
    headers: { ...HEADERS, "Content-Type": "application/json; charset=UTF-8" },
    body: jsonBody,
  });

  // Common ASP.NET WebMethod suffixes
  for (const method of ["GetStationList", "SearchStation", "GetNearStation", "QueryStation"]) {
    await tryRequest(`POST /${method}`, `${BASE}/${method}`, {
      method: "POST",
      headers: { ...HEADERS, "Content-Type": "application/json; charset=UTF-8" },
      body: jsonBody,
    });
  }
}

main();
