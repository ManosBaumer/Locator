const crypto = require("crypto");

const APP_ID = "d82be6bbc1da11eb9dd000163e122ecb";
const SALT = "0d787c102fe2f7b4279af8925819d5fd";
const VERSION = "2.8.37";
const BASE_URL = "https://mxsa.mxbc.net/api";

function createStrBeforeSign(params) {
  const copy = { ...params };
  let str = "";
  const keys = Object.keys(copy).sort();
  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const val = copy[key];
    if (val || val === 0) {
      const serialized =
        val !== null && typeof val === "object" ? JSON.stringify(val) : val;
      str += `${i ? "&" : ""}${key}=${serialized}`;
    } else if (val !== "") {
      delete copy[key];
    }
  }
  return str;
}

function md5Hex(input) {
  return crypto.createHash("md5").update(input).digest("hex");
}

function md5Suffix(hex) {
  const bytes = Buffer.from(hex, "hex");
  const parts = [];
  for (let i = 0; i < 4; i++) {
    const offset = i * 4;
    let n =
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3];
    n = n | 0;
    parts.push(n === -2147483648 ? 2147483647 : Math.abs(n));
  }
  return parts.join("");
}

function signPayload(body, timeOffset = 0) {
  const params = { ...body };
  delete params.sign;
  params.appId = APP_ID;
  params.t = params.t ?? Date.now() - timeOffset;
  params.s = 3;
  const md5 = md5Hex(createStrBeforeSign(params) + SALT);
  params.sign = md5 + md5Suffix(md5);
  return params;
}

async function findNearStores({
  longitude,
  latitude,
  page = 1,
  limit = 20,
  distance = 10,
  cid = "",
}) {
  const body = signPayload({ longitude, latitude, page, limit, distance });
  const res = await fetch(`${BASE_URL}/v2/shopinfo/findNear`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      version: VERSION,
      "x-ssos-cid": cid,
      "access-token": "",
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

module.exports = { signPayload, findNearStores, APP_ID, SALT, VERSION, BASE_URL };
