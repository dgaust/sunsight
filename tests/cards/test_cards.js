/*
 * Tests for the Ecowitt cards. No Home Assistant, no browser, no deps —
 * the card file is evaluated in a vm context with the handful of globals
 * it touches stubbed out, then exercised against a fixture captured from
 * a real HA instance (tests/fixtures/devices.json).
 *
 *   node tests/cards/test_cards.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const CARD = path.join(ROOT, "custom_components", "sunsight", "www", "ecowitt-cards.js");
const FIXTURE = path.join(__dirname, "fixtures", "devices.json");

class FakeHTMLElement {
  attachShadow() { return {}; }
  appendChild() {}
  addEventListener() {}
  dispatchEvent() {}
}

const ctx = vm.createContext({
  console: { info() {} },
  HTMLElement: FakeHTMLElement,
  customElements: {
    _m: new Map(),
    get(t) { return this._m.get(t); },
    define(t, c) { this._m.set(t, c); },
  },
  document: { createElement: () => new FakeHTMLElement() },
  window: {},
  Event: class {},
  CustomEvent: class {},
});

vm.runInContext(
  fs.readFileSync(CARD, "utf8") +
    "\nglobalThis.__api = { discover, cardinal, windLabel," +
    " compassSvg, fmt, num, metricEntries, metricEntryFor, METRIC_CATALOGUE," +
    " DEFAULT_METRICS, withHubMetrics, parseScale, bandFor, scaleColor," +
    " numberLocale," +
    " scaleGradient, scaleTicks, DEFAULT_SOIL_SCALE, DEFAULT_UV_SCALE," +
    " NEEDLE_STYLES, DEFAULT_NEEDLE, customEntryFor, CLASS_ICONS };",
  ctx
);
const api = ctx.__api;

/* ---- fixture -> hass-shaped object ---- */
const dump = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
const hass = { states: {}, entities: {}, devices: {} };
const deviceIds = {};
let n = 0;
for (const [devName, info] of Object.entries(dump)) {
  const devId = "dev" + ++n;
  deviceIds[devName] = devId;
  hass.devices[devId] = { id: devId, name: devName, _via: info.via_device };
  for (const e of info.entities) {
    hass.entities[e.entity_id] = { device_id: devId };
    hass.states[e.entity_id] = {
      state: e.state,
      attributes: {
        friendly_name: e.name,
        unit_of_measurement: e.unit,
        device_class: e.device_class,
      },
    };
  }
}

/* Resolve via_device names to ids, the shape hass.devices actually has. */
for (const dev of Object.values(hass.devices)) {
  dev.via_device_id = dev._via ? deviceIds[dev._via] : null;
  delete dev._via;
}

let failures = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label} => ${got}${ok ? "" : `  (want ${want})`}`);
}
function assert(label, cond) {
  if (!cond) failures++;
  console.log(`  ${cond ? "ok  " : "FAIL"} ${label}`);
}

/* ---- every entity on every device must be classified ---- */
console.log("discovery");
for (const [devName, devId] of Object.entries(deviceIds)) {
  const ids = api.discover(hass, devId);
  const owned = Object.keys(hass.entities).filter(
    (e) => hass.entities[e].device_id === devId
  );
  const unclassified = owned.filter((e) => !Object.values(ids).includes(e));
  assert(
    `${devName}: ${owned.length - unclassified.length}/${owned.length} classified` +
      (unclassified.length ? ` — left over: ${unclassified.join(", ")}` : ""),
    unclassified.length === 0
  );
}

/* ---- ids that contain one another must not collide ---- */
console.log("ambiguous ids");
const ws = api.discover(hass, deviceIds["Ecowitt Weather Station"]);
const soil = api.discover(hass, deviceIds["Ecowitt Soil Moisture Sensor D431A"]);
const gw = api.discover(hass, deviceIds["Ecowitt Gateway"]);
check("wind_dir not the avg sensor", ws.wind_dir, "sensor.ecowitt_wind_direction_13360");
check("wind_dir_avg distinct", ws.wind_dir_avg, "sensor.ecowitt_wind_direction_avg_13360");
check("voltage not capacitor", ws.voltage, "sensor.ecowitt_voltage_13360");
check("cap_voltage distinct", ws.cap_voltage, "sensor.ecowitt_capacitor_voltage_13360");
check("daily rain not max gust", ws.rain_daily, "sensor.ecowitt_daily_rain_13360");
check("max gust distinct", ws.max_gust, "sensor.ecowitt_max_daily_gust_13360");
check("soil moisture not battery", soil.soil_moisture, "sensor.ecowitt_soil_moisture_d431a");
check("soil battery distinct", soil.soil_battery, "sensor.ecowitt_soil_moisture_battery_d431a");
check("soil online is binary", soil.online, "binary_sensor.ecowitt_soil_moisture_d431a_online");
check("gateway indoor temp", gw.temp_in, "sensor.ecowitt_temperature_indoor");
check("gateway indoor humidity", gw.hum_in, "sensor.ecowitt_humidity_humidityin");
assert("gateway has no outdoor temp", gw.temp_out === undefined);

/* The WH40 tipping bucket is a second, independent rain source alongside
 * the WS90's piezo. Its battery entity ("rain_battery") sits in the middle
 * of the rain_* accumulation names, which is exactly the kind of overlap
 * the ordered rules exist to resolve. */
const wh40 = api.discover(hass, deviceIds["Ecowitt Rain Sensor"]);
check("wh40 rate", wh40.rain_rate, "sensor.ecowitt_rain_rate_11c87");
check("wh40 daily", wh40.rain_daily, "sensor.ecowitt_daily_rain_11c87");
check("wh40 event", wh40.rain_event, "sensor.ecowitt_rain_event_11c87");
check("wh40 battery not a rain total", wh40.battery, "sensor.ecowitt_rain_battery_11c87");
assert("wh40 battery did not claim a rain_* slot",
  ![wh40.rain_rate, wh40.rain_daily, wh40.rain_event, wh40.rain_hourly,
    wh40.rain_weekly, wh40.rain_monthly, wh40.rain_yearly, wh40.rain_24h]
    .includes("sensor.ecowitt_rain_battery_11c87"));
assert("wh40 has no piezo binary (tipping bucket)", wh40.rain_piezo === undefined);
check("wh40 online", wh40.online, "binary_sensor.ecowitt_sensor_11c87_online");

/* Two soil probes must resolve to different entities on different devices. */
const soil1 = api.discover(hass, deviceIds["Ecowitt Soil Moisture Sensor D42E2"]);
check("soil CH1 moisture", soil1.soil_moisture, "sensor.ecowitt_soil_moisture_d42e2");
assert("soil CH1 and CH2 are distinct", soil1.soil_moisture !== soil.soil_moisture);

/* ---- an unknown device yields nothing rather than throwing ---- */
console.log("edge cases");
assert("unknown device => {}", Object.keys(api.discover(hass, "nope")).length === 0);
assert("missing hass => {}", Object.keys(api.discover(null, "dev1")).length === 0);
check(
  "unavailable state formats as dash",
  api.fmt({ states: { "sensor.x": { state: "unavailable", attributes: {} } } }, "sensor.x"),
  "—"
);
check(
  "non-numeric state passes through",
  api.fmt({ states: { "sensor.x": { state: "D431A", attributes: {} } } }, "sensor.x"),
  "D431A"
);
const stateOf = (value, attrs, locale) => ({
  states: { "sensor.x": { state: String(value), attributes: attrs || {} } },
  ...(locale ? { locale } : {}),
});
check(
  "display precision honoured",
  api.fmt(stateOf("1029.23", { suggested_display_precision: 0 }), "sensor.x"),
  "1,029"
);

/* ---- number formatting ---- */
console.log("number format");
/* Grouping follows the user's Home Assistant setting, which is not always
 * implied by the language: an English UI may still want 1.234,5. */
check("grouped by default", api.fmt(stateOf("74300", { suggested_display_precision: 0 }), "sensor.x"), "74,300");
check("comma_decimal",
  api.fmt(stateOf("74300", { suggested_display_precision: 1 }, { number_format: "comma_decimal" }), "sensor.x"),
  "74,300.0");
check("decimal_comma",
  api.fmt(stateOf("74300", { suggested_display_precision: 1 }, { number_format: "decimal_comma" }), "sensor.x"),
  "74.300,0");
/* "none" is a deliberate choice meaning no separators at all, so it must
 * not be treated the same as "unset". */
check("none groups nothing",
  api.fmt(stateOf("74300", { suggested_display_precision: 1 }, { number_format: "none" }), "sensor.x"),
  "74300.0");
check("language follows the profile language",
  api.fmt(stateOf("74300", { suggested_display_precision: 0 }, { number_format: "language", language: "de" }), "sensor.x"),
  "74.300");
check("small numbers are untouched",
  api.fmt(stateOf("18.4", { suggested_display_precision: 1 }), "sensor.x"), "18.4");
check("precision still applies", api.fmt(stateOf("0.4372", {}), "sensor.x", 2), "0.44");
/* A malformed language tag from the profile must not blank a reading. */
check("bad locale falls back rather than throwing",
  api.fmt(stateOf("1234.5", { suggested_display_precision: 1 }, { number_format: "language", language: "not a locale" }), "sensor.x"),
  "1234.5");
check("unavailable is still a dash",
  api.fmt(stateOf("unavailable", {}), "sensor.x"), "—");
check("non-numeric still passes through",
  api.fmt(stateOf("D431A", {}), "sensor.x"), "D431A");

check("locale resolution: none", api.numberLocale({ locale: { number_format: "none" } }), null);
check("locale resolution: unset uses language",
  api.numberLocale({ locale: { language: "en-GB" } }), "en-GB");
check("locale resolution: no locale object at all",
  api.numberLocale({}), undefined);

/* ---- third-party soil probes ---- */
console.log("third-party soil");
const tp = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "third-party.json"), "utf8"));
const tpEntities = Object.values(tp)[0].entities;

/* HA gives no ordering guarantee for hass.entities, so build the probe in
 * both the natural order and the awkward one where the metadata entities
 * come first. Discovery must agree either way. */
const probeHass = (order) => {
  const h = { states: {}, entities: {}, devices: { probe: { id: "probe", name: "Sunflower" } } };
  for (const e of order) {
    h.entities[e.entity_id] = { device_id: "probe" };
    h.states[e.entity_id] = {
      state: e.state,
      attributes: { unit_of_measurement: e.unit, device_class: e.device_class },
    };
  }
  return h;
};
const natural = probeHass(tpEntities);
const awkward = probeHass([...tpEntities].sort(
  (a, b) => (/battery_type|last_replaced/.test(a.entity_id) ? -1 : 1)));

const idsNatural = api.discover(natural, "probe");
const idsAwkward = api.discover(awkward, "probe");

check("moisture found on a Tuya probe",
  idsNatural.soil_moisture, "sensor.outdoors_sunflower_moisture_soil_moisture");
check("battery found", idsNatural.battery, "sensor.outdoors_sunflower_moisture_battery");
/* The bug this guards: "battery_type" holds "2x AAA", which parses to 2 and
 * would render as a critical 2% battery. */
check("battery is order-independent", idsAwkward.battery, idsNatural.battery);
assert("battery_type never claims the battery slot",
  idsAwkward.battery !== "sensor.outdoors_sunflower_moisture_battery_type" &&
  idsNatural.battery !== "sensor.outdoors_sunflower_moisture_battery_type");
assert("a date entity never claims it either",
  ![idsNatural.battery, idsAwkward.battery]
    .includes("sensor.outdoors_sunflower_moisture_battery_last_replaced"));
check("its soil temperature is picked up too",
  idsNatural.temp_out, "sensor.outdoors_sunflower_moisture_temperature");

/* Naming entities directly must work with no device at all. */
const SoilCard = ctx.customElements.get("ecowitt-soil-card");
const loose = Object.create(SoilCard.prototype);
loose._config = { moisture: "sensor.my_probe", battery: "sensor.my_probe_batt" };
loose._ids = {};
loose._applyEntityOverrides();
check("moisture override applies", loose._ids.soil_moisture, "sensor.my_probe");
check("battery override applies", loose._ids.soil_battery, "sensor.my_probe_batt");
assert("a moisture entity alone is a valid config",
  SoilCard.prototype._isConfigured.call(loose, { moisture: "sensor.my_probe" }));
assert("a device alone is still valid",
  SoilCard.prototype._isConfigured.call(loose, { device: "abc" }));
assert("neither is not",
  !SoilCard.prototype._isConfigured.call(loose, { name: "x" }));
/* Other cards still insist on a device. */
const WindCard = ctx.customElements.get("ecowitt-wind-card");
assert("the wind card still requires a device",
  !WindCard.prototype._isConfigured.call({}, { moisture: "sensor.x" }));

/* ---- configurable metric tiles ---- */
console.log("metrics");
const { metricEntries, metricEntryFor, METRIC_CATALOGUE, DEFAULT_METRICS } = api;
const keysOf = (cfg) => metricEntries(cfg).map((e) => e.key).join(",");
const labelsOf = (cfg) => metricEntries(cfg).map((e) => e.label).join(",");

check("absent config falls back to defaults", keysOf({}), DEFAULT_METRICS.join(","));
check("non-array metrics falls back", keysOf({ metrics: "nope" }), DEFAULT_METRICS.join(","));
check("order is preserved exactly",
  keysOf({ metrics: ["vpd", "uv", "hum_out"] }), "vpd,uv,hum_out");
check("unknown keys are dropped",
  keysOf({ metrics: ["uv", "not_a_metric", "vpd"] }), "uv,vpd");
/* An empty list must mean "no tiles", not "give me the defaults" — the
 * difference between honouring a choice and overriding it. */
check("empty list yields no tiles", metricEntries({ metrics: [] }).length, 0);
check("duplicates are left alone", keysOf({ metrics: ["uv", "uv"] }), "uv,uv");

assert("every default metric is in the catalogue",
  DEFAULT_METRICS.every((k) => METRIC_CATALOGUE[k]));

/* ---- custom entity tiles ---- */
console.log("custom tiles");
const { customEntryFor } = api;
const customCfg = { metrics: ["uv", { entity: "sensor.anything", name: "My thing" }] };
const customEntries = metricEntries(customCfg);
check("a custom entry survives parsing", customEntries.length, 2);
assert("it is flagged custom", customEntries[1].custom === true);
check("it keeps its entity", customEntries[1].entity, "sensor.anything");
check("and its name", customEntries[1].label, "My thing");
assert("a custom entry has no catalogue key", customEntries[1].key === undefined);
/* No name means "ask the entity", which can only happen at render time. */
check("a nameless custom entry defers its label",
  metricEntries({ metrics: [{ entity: "sensor.x" }] })[0].label, null);
assert("an object with neither entity nor metric is dropped",
  metricEntries({ metrics: [{ name: "orphan" }] }).length === 0);
/* A freshly added custom tile has no entity yet. The row must survive so
 * the editor has somewhere to put the picker; the card just renders no
 * tile for it. */
const placeholder = metricEntries({ metrics: [{ entity: "" }] });
check("an empty custom entry is kept as a placeholder", placeholder.length, 1);
assert("and is still flagged custom", placeholder[0].custom === true);

check("stored without a name stays bare",
  JSON.stringify(customEntryFor("sensor.x", "")), '{"entity":"sensor.x"}');
check("stored with a name keeps it",
  JSON.stringify(customEntryFor("sensor.x", " Label ")),
  '{"entity":"sensor.x","name":"Label"}');
/* Catalogue and custom tiles must mix in one list, in order. */
check("mixed list keeps order",
  metricEntries({ metrics: ["uv", { entity: "sensor.a" }, "vpd"] })
    .map((e) => e.key || e.entity).join(","),
  "uv,sensor.a,vpd");

/* Rendering resolves a custom tile from the entity itself. */
const WeatherCard = ctx.customElements.get("ecowitt-weather-card");
const fake = Object.create(WeatherCard.prototype);
fake._ids = { uv: "sensor.ecowitt_uv_index_13360" };
fake._hass = { states: {
  "sensor.custom_thing": {
    state: "12.5",
    attributes: { friendly_name: "Pool temperature", device_class: "temperature", unit_of_measurement: "°C" },
  },
  "sensor.iconless": { state: "3", attributes: {} },
  "sensor.ecowitt_uv_index_13360": { state: "7", attributes: {} },
} };
const resolved = fake._resolveSpec({ custom: true, entity: "sensor.custom_thing", label: null, icon: null, digits: null });
check("label falls back to the friendly name", resolved.label, "Pool temperature");
check("icon comes from the device class", resolved.icon, "mdi:thermometer");
check("an explicit name wins",
  fake._resolveSpec({ custom: true, entity: "sensor.custom_thing", label: "Pool", icon: null, digits: null }).label, "Pool");
check("an entity with nothing to go on still gets an icon",
  fake._resolveSpec({ custom: true, entity: "sensor.iconless", label: null, icon: null, digits: null }).icon, "mdi:gauge");
check("and falls back to its id for a label",
  fake._resolveSpec({ custom: true, entity: "sensor.iconless", label: null, icon: null, digits: null }).label, "sensor.iconless");
assert("an entity that does not exist is skipped",
  fake._resolveSpec({ custom: true, entity: "sensor.missing", label: null }) === null);
/* digits: 0 is falsy, so the fallback must test for an integer. */
check("zero precision is respected",
  fake._resolveSpec({ key: "uv", label: "UV", icon: "x", digits: 0 }).digits, 0);
check("absent precision defaults to one",
  fake._resolveSpec({ custom: true, entity: "sensor.custom_thing", label: null, digits: null }).digits, 1);

/* ---- per-tile name overrides ---- */
console.log("tile names");
check("bare keys use the catalogue label",
  labelsOf({ metrics: ["cap_voltage"] }), "Capacitor voltage");
check("an override replaces it",
  labelsOf({ metrics: [{ metric: "cap_voltage", name: "Capacitor" }] }), "Capacitor");
check("override does not change the key",
  keysOf({ metrics: [{ metric: "cap_voltage", name: "Capacitor" }] }), "cap_voltage");
/* Old configs are plain strings and must keep working unchanged. */
check("string and object entries mix",
  labelsOf({ metrics: ["uv", { metric: "vpd", name: "Deficit" }] }), "UV index,Deficit");
check("blank name falls back to the default",
  labelsOf({ metrics: [{ metric: "uv", name: "   " }] }), "UV index");
check("non-string name falls back",
  labelsOf({ metrics: [{ metric: "uv", name: 42 }] }), "UV index");
check("names are trimmed",
  labelsOf({ metrics: [{ metric: "uv", name: "  Sun  " }] }), "Sun");
assert("an object entry with an unknown metric is dropped",
  metricEntries({ metrics: [{ metric: "nope", name: "x" }] }).length === 0);
assert("a malformed entry is dropped",
  metricEntries({ metrics: [null, undefined, 7, {}] }).length === 0);

/* Storing: only pin a name when it actually differs from the default, so
 * YAML stays terse and defaults are free to change later. */
check("default name stores as a bare key",
  JSON.stringify(metricEntryFor("uv", "UV index")), '"uv"');
check("blank stores as a bare key", JSON.stringify(metricEntryFor("uv", "")), '"uv"');
check("a real override is stored",
  JSON.stringify(metricEntryFor("cap_voltage", "Capacitor")),
  '{"metric":"cap_voltage","name":"Capacitor"}');
check("round trip survives",
  labelsOf({ metrics: [metricEntryFor("cap_voltage", "Capacitor")] }), "Capacitor");

/* ---- hub fallback ---- */
console.log("hub metrics");
const { withHubMetrics } = api;
const wsDev = deviceIds["Ecowitt Weather Station"];
const gwDev = deviceIds["Ecowitt Gateway"];
const wsHub = withHubMetrics(hass, wsDev, api.discover(hass, wsDev));

/* A WS90 has no barometer; the pressure sensors live on the gateway it
 * reports through. Following via_device_id is what makes the tile usable. */
assert("WS90 has no pressure of its own", ws.press_rel === undefined);
check("pressure borrowed from the gateway",
  wsHub.press_rel, "sensor.ecowitt_pressure_relative");
check("absolute pressure too",
  wsHub.press_abs, "sensor.ecowitt_pressure_absolute");
check("indoor climate too", wsHub.temp_in, "sensor.ecowitt_temperature_indoor");
check("indoor humidity too", wsHub.hum_in, "sensor.ecowitt_humidity_humidityin");

/* Only flagged keys travel. Borrowing anything else would attach another
 * device's reading to this card — a sibling's battery, say. */
check("own outdoor temperature is untouched",
  wsHub.temp_out, "sensor.ecowitt_outdoor_temp_13360");
check("own battery is not replaced",
  wsHub.battery, "sensor.ecowitt_battery_13360");
assert("no soil moisture leaks in from a sibling",
  wsHub.soil_moisture === undefined);
assert("no rain sensor battery leaks in",
  wsHub.battery !== "sensor.ecowitt_rain_battery_11c87");

/* The soil probes share the same gateway, so they inherit the same hub
 * metrics without ever picking up each other's readings. */
const soilHub = withHubMetrics(hass, deviceIds["Ecowitt Soil Moisture Sensor D431A"], soil);
check("a soil probe sees gateway pressure",
  soilHub.press_rel, "sensor.ecowitt_pressure_relative");
check("its own moisture is unchanged",
  soilHub.soil_moisture, "sensor.ecowitt_soil_moisture_d431a");

/* The gateway is the root: no parent, nothing to borrow, no crash. */
const gwHub = withHubMetrics(hass, gwDev, gw);
check("gateway keeps its own pressure",
  gwHub.press_rel, "sensor.ecowitt_pressure_relative");
check("gateway gains nothing", Object.keys(gwHub).length, Object.keys(gw).length);
assert("unknown device is handled",
  Object.keys(withHubMetrics(hass, "nope", {})).length === 0);

/* ---- configurable scales ---- */
console.log("scales");
const { parseScale, bandFor, scaleColor, scaleGradient, scaleTicks,
        DEFAULT_SOIL_SCALE, DEFAULT_UV_SCALE } = api;

const labelAt = (v, scale) => bandFor(v, scale).label;

/* Defaults still behave as before. */
const soilDef = parseScale({}, DEFAULT_SOIL_SCALE);
check("default soil 10", labelAt(10, soilDef), "Very dry");
check("default soil 51", labelAt(51, soilDef), "Ideal");
check("default soil 95", labelAt(95, soilDef), "Saturated");
check("null reads as a dash", labelAt(null, soilDef), "—");
const uvDef = parseScale({}, DEFAULT_UV_SCALE);
check("default uv 0", labelAt(0, uvDef), "Low");
check("default uv 7", labelAt(7, uvDef), "High");
check("default uv 12", labelAt(12, uvDef), "Extreme");

/* A bare array replaces the bands and keeps the default max. */
const custom = parseScale({ scale: [
  { to: 40, label: "Too dry", color: "error" },
  { label: "Wet enough", color: "info" },
] }, DEFAULT_SOIL_SCALE);
check("custom band low", labelAt(10, custom), "Too dry");
check("custom band high", labelAt(90, custom), "Wet enough");
check("custom keeps default max", custom.max, 100);
check("boundary is exclusive at the top", labelAt(40, custom), "Wet enough");
check("just below the boundary", labelAt(39.9, custom), "Too dry");

/* The object form can move the axis maximum too. */
const scaled = parseScale({ scale: { max: 60, bands: [
  { to: 30, label: "Low", color: "warning" },
  { label: "High", color: "success" },
] } }, DEFAULT_SOIL_SCALE);
check("explicit max is honoured", scaled.max, 60);
check("band within new axis", labelAt(45, scaled), "High");

/* Order shouldn't matter; the open-ended band always sorts last. */
const unordered = parseScale({ scale: [
  { label: "Top", color: "info" },
  { to: 50, label: "Bottom", color: "error" },
] }, DEFAULT_SOIL_SCALE);
check("unordered bands sort", unordered.bands.map((b) => b.label).join(","), "Bottom,Top");
check("unordered resolves low", labelAt(10, unordered), "Bottom");
check("unordered resolves high", labelAt(80, unordered), "Top");

/* Malformed config must fall back rather than render a broken axis. */
check("empty array falls back", parseScale({ scale: [] }, DEFAULT_SOIL_SCALE), DEFAULT_SOIL_SCALE);
check("garbage falls back", parseScale({ scale: "nope" }, DEFAULT_SOIL_SCALE), DEFAULT_SOIL_SCALE);
check("bands of junk fall back",
  parseScale({ scale: [null, 5, {}] }, DEFAULT_SOIL_SCALE), DEFAULT_SOIL_SCALE);
check("absent scale falls back", parseScale({}, DEFAULT_SOIL_SCALE), DEFAULT_SOIL_SCALE);
check("zero max is rejected",
  parseScale({ scale: { max: 0, bands: [{ label: "x" }] } }, DEFAULT_SOIL_SCALE).max, 100);

/* Colours resolve to theme tokens, with pass-through for anything else. */
check("token maps to a theme var", scaleColor("error"), "var(--error-color)");
check("alias maps too", scaleColor("danger"), "var(--error-color)");
check("missing colour is neutral", scaleColor(undefined), "var(--disabled-color)");
check("unknown value passes through", scaleColor("var(--my-color)"), "var(--my-color)");

/* The axis is generated, so it must cover the full width and stop there. */
const grad = scaleGradient(soilDef);
assert("gradient starts at 0%", grad.includes("0%"));
assert("gradient ends at 100%", grad.includes("100%)"));
assert("gradient has no NaN", !grad.includes("NaN"));
const ticks = scaleTicks(soilDef);
assert("ticks include the boundaries",
  ["0", "20", "35", "65", "80"].every((v) => ticks.includes(`>${v}<`)));
assert("ticks have no NaN", !ticks.includes("NaN"));
assert("a single open band still renders",
  !scaleGradient(parseScale({ scale: [{ label: "All", color: "info" }] },
    DEFAULT_SOIL_SCALE)).includes("NaN"));

/* ---- UV defaults against the Bureau of Meteorology ---- */
console.log("uv categories");
const uvScale = parseScale({}, DEFAULT_UV_SCALE);
const uvLabel = (v) => bandFor(v, uvScale).label;

/* BoM: Low 0-2, Moderate 3-5, High 6-7, Very high 8-10, Extreme 11+. Check
 * every boundary from both sides, since an off-by-one here would misreport
 * whether sun protection is advised. */
[[0, "Low"], [1, "Low"], [2, "Low"],
 [3, "Moderate"], [4, "Moderate"], [5, "Moderate"],
 [6, "High"], [7, "High"],
 [8, "Very high"], [9, "Very high"], [10, "Very high"],
 [11, "Extreme"], [12, "Extreme"], [15, "Extreme"]]
  .forEach(([v, want]) => check(`uv ${v}`, uvLabel(v), want));

/* The 3 boundary is the one that carries public-health meaning. */
check("2.9 is still Low", uvLabel(2.9), "Low");
check("3.0 is Moderate", uvLabel(3), "Moderate");
assert("protection is not advised below 3",
  !/protection required/i.test(bandFor(2, uvScale).description));
assert("protection is advised from 3 up",
  [3, 6, 8, 11].every((v) => /protection required/i.test(bandFor(v, uvScale).description)));
assert("every UV band has advice",
  uvScale.bands.every((b) => b.description && b.description.length > 10));

/* Descriptions survive parsing, are optional, and are overridable. */
check("description is carried through",
  bandFor(7, uvScale).description.startsWith("Sun protection required"), true);
check("soil defaults carry none",
  bandFor(50, parseScale({}, DEFAULT_SOIL_SCALE)).description, "");
check("a custom description is honoured",
  bandFor(50, parseScale({ scale: [{ label: "Fine", color: "info", description: "All good" }] },
    DEFAULT_SOIL_SCALE)).description, "All good");
check("a non-string description is dropped",
  bandFor(50, parseScale({ scale: [{ label: "X", color: "info", description: 7 }] },
    DEFAULT_SOIL_SCALE)).description, "");
check("null value has no description", bandFor(null, uvScale).description, "");

/* ---- helpers ---- */
console.log("helpers");
check("cardinal(0)", api.cardinal(0), "N");
check("cardinal(78)", api.cardinal(78), "ENE");
check("cardinal(180)", api.cardinal(180), "S");
check("cardinal(359) wraps to N", api.cardinal(359), "N");
check("cardinal(-90) normalises", api.cardinal(-90), "W");
check("cardinal(null)", api.cardinal(null), "—");
check("windLabel(0)", api.windLabel(0), "Calm");
check("windLabel(3.96)", api.windLabel(3.96), "Light air");

/* ---- compass markers explain themselves ---- */
console.log("compass titles");
/* The dashed marker prompted a "what is that line?" question, so both
 * markers carry a title. The average is over the last 10 minutes. */
const withBoth = api.compassSvg(132, 89, 44, "arrow");
assert("the dashed marker names the 10-minute window",
  /<title>Average wind direction over the last 10 minutes<\/title>/.test(withBoth));
assert("the solid needle says it is the current direction",
  /<title>Current wind direction<\/title>/.test(withBoth));
assert("no dangling title when there is no average",
  !api.compassSvg(132, 89, null, "arrow").includes("Average wind direction"));
assert("the current-direction title still appears without an average",
  api.compassSvg(132, 89, null, "arrow").includes("Current wind direction"));
assert("no titles at all when direction is unknown",
  !api.compassSvg(132, null, null, "arrow").includes("<title>"));

/* The average marker is dropped on the weather card's inline compass: a few
 * faint pixels with no row beside it to explain them. Same 90px threshold
 * the cardinal letters use. */
assert("132px draws the average marker",
  api.compassSvg(132, 89, 44, "arrow").includes("stroke-dasharray"));
assert("72px does not",
  !api.compassSvg(72, 89, 44, "arrow").includes("stroke-dasharray"));
assert("72px carries no orphaned average tooltip",
  !api.compassSvg(72, 89, 44, "arrow").includes("Average wind direction"));
assert("72px still draws the needle",
  api.compassSvg(72, 89, 44, "arrow").includes("polygon"));
assert("the threshold matches the cardinal letters",
  api.compassSvg(90, 89, 44, "arrow").includes("stroke-dasharray") &&
  api.compassSvg(89, 89, 44, "arrow").includes("stroke-dasharray") === false);

/* ---- needle styles ---- */
console.log("needle styles");
const svgFor = (style, size) => api.compassSvg(size || 132, 89, null, style);

assert("both styles are offered",
  Object.keys(api.NEEDLE_STYLES).sort().join(",") === "arrow,classic");
check("the clearer one is the default", api.DEFAULT_NEEDLE, "arrow");

/* The arrow style is only unambiguous if its two ends differ: a hollow
 * ring at the source and a solid head downwind. */
assert("arrow has a hollow tail ring",
  /<circle[^>]*fill="none"[^>]*stroke="var\(--primary-color\)"/.test(svgFor("arrow")));
assert("arrow has a solid head", /<polygon[^>]*fill="var\(--primary-color\)"/.test(svgFor("arrow")));
assert("classic is a single solid pointer",
  svgFor("classic").match(/<polygon/g).length === 1 &&
  !/<circle[^>]*fill="none"[^>]*stroke="var\(--primary-color\)"/.test(svgFor("classic")));

/* Whatever the style, the rotation and the geometry must hold. */
["arrow", "classic"].forEach((style) => {
  [72, 132].forEach((size) => {
    const svg = svgFor(style, size);
    assert(`${style} at ${size}px is well formed`,
      svg.includes("<svg") && svg.trim().endsWith("</svg>") && !svg.includes("NaN"));
  });
  const m = svgFor(style).match(/rotate\((\d+(?:\.\d+)?) /);
  check(`${style} still points downwind`, m && Number(m[1]), 269);
});

/* An unset or misspelled style must not blank the needle. */
assert("unset style falls back", svgFor(undefined).includes("polygon"));
assert("unknown style falls back", svgFor("banana").includes("polygon"));
assert("unset matches the default exactly",
  svgFor(undefined) === svgFor(api.DEFAULT_NEEDLE));

/* ---- wind arrow direction ---- */
console.log("wind arrow");
/* The bearing is where the wind comes FROM; the arrow is drawn pointing
 * downwind, 180 degrees opposite, matching the Ecowitt console. Pull the
 * needle's own rotation out of the SVG rather than trusting the maths. */
const needleRotation = (deg) => {
  const svg = api.compassSvg(120, deg, null);
  const m = svg.match(/rotate\((\d+(?:\.\d+)?) /);
  return m ? Number(m[1]) : null;
};
check("wind from N draws south", needleRotation(0), 180);
check("wind from E draws west", needleRotation(90), 270);
check("wind from S draws north", needleRotation(180), 0);
check("wind from W draws east", needleRotation(270), 90);
check("89 draws 269", needleRotation(89), 269);
check("wraps past 360", needleRotation(300), 120);
/* The cardinal text still names the source, not the drawn direction. */
check("cardinal still reports the source", api.cardinal(90), "E");
assert("arrow and cardinal deliberately disagree by 180",
  needleRotation(90) === 270 && api.cardinal(90) === "E");

for (const d of [0, 78, 359, null]) {
  const svg = api.compassSvg(120, d, 38);
  assert(
    `compassSvg(dir=${d}) well formed`,
    svg.includes("<svg") && svg.trim().endsWith("</svg>") && !svg.includes("NaN")
  );
}

console.log(failures ? `\n${failures} FAILURE(S)` : "\nall tests passed");
process.exit(failures ? 1 : 0);
