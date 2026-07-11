/** @deprecated Prefer require("./scripts/lib/mixue-api") — kept for quick local tests. */
module.exports = require("./scripts/lib/mixue-api");

if (require.main === module) {
  const { findNearStores } = module.exports;
  findNearStores({ longitude: 116.4074, latitude: 39.9042 })
    .then((data) => console.log(JSON.stringify(data, null, 2)))
    .catch(console.error);
}
