"""Regenerate tests/fixtures/devices.json from a live Home Assistant instance.

Run this after pairing new Ecowitt hardware (and reloading the integration),
so the test suite exercises discovery against what you actually own:

    cp .env.example .env      # fill in HA_URL and HA_TOKEN
    python tests/capture_fixture.py

The token is read from .env, which is gitignored, and is never printed. IP
addresses are stripped from device and entity names, since the fixture is
committed to a public repository. Still worth skimming the diff for anything
else you would rather not publish.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Device names often embed the gateway's IP ("Ecowitt Gateway 192.0.2.10").
# The fixture is committed to a public repository, so strip them rather than
# relying on remembering to do it by hand after every capture.
IPV4 = re.compile(r"\s*\b\d{1,3}(?:\.\d{1,3}){3}\b")


def scrub(value):
    return IPV4.sub("", value).strip() if isinstance(value, str) else value

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENV = os.path.join(ROOT, ".env")
DEST = os.path.join(HERE, "fixtures", "devices.json")
DOMAIN = sys.argv[1] if len(sys.argv) > 1 else "ecowitt_local"

# Ask HA to resolve each of the integration's entities to its device, which
# is the only reliable way to group them — entity ids alone don't say which
# physical sensor they came from.
# via_device_id matters: hub-level readings (pressure, indoor climate) live
# on the gateway, and the cards follow that link to offer them on a sensor
# device's card. The fixture has to carry it or the tests can't see it.
TEMPLATE = """
{%%- set ns = namespace(rows=[]) -%%}
{%%- for e in integration_entities('%s') -%%}
  {%%- set d = device_id(e) -%%}
  {%%- set v = device_attr(d, 'via_device_id') -%%}
  {%%- set ns.rows = ns.rows + [{
      'entity_id': e,
      'device': device_attr(d, 'name_by_user') or device_attr(d, 'name'),
      'model': device_attr(d, 'model'),
      'via_device': (device_attr(v, 'name_by_user') or device_attr(v, 'name'))
                    if v else None
  }] -%%}
{%%- endfor -%%}
{{ ns.rows | tojson }}
""" % DOMAIN


def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"No .env at {path}. Copy .env.example and fill it in.")
    vals = {}
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def call(url, token, path, payload=None):
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=json.dumps(payload).encode() if payload else None,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method="POST" if payload else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def main():
    env = load_env(ENV)
    url, token = env.get("HA_URL", ""), env.get("HA_TOKEN", "")
    if not url or not token:
        sys.exit("HA_URL and HA_TOKEN must both be set in .env")

    try:
        rows = json.loads(call(url, token, "/api/template", {"template": TEMPLATE}))
        states = {s["entity_id"]: s for s in json.loads(call(url, token, "/api/states"))}
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code} {exc.reason}")

    if not rows:
        sys.exit(f"No entities found for integration '{DOMAIN}'.")

    devices = {}
    for r in rows:
        st = states.get(r["entity_id"], {})
        attrs = st.get("attributes", {}) or {}
        dev = devices.setdefault(
            scrub(r["device"]) or "(no device)",
            {
                "model": r.get("model"),
                "via_device": scrub(r.get("via_device")),
                "entities": [],
            },
        )
        dev["entities"].append({
            "entity_id": r["entity_id"],
            "name": scrub(attrs.get("friendly_name")),
            "state": st.get("state"),
            "unit": attrs.get("unit_of_measurement"),
            "device_class": attrs.get("device_class"),
            "state_class": attrs.get("state_class"),
        })

    for dev in devices.values():
        dev["entities"].sort(key=lambda e: e["entity_id"])

    with open(DEST, "w", encoding="utf-8") as fh:
        json.dump(devices, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"Wrote {DEST}")
    for name, info in sorted(devices.items()):
        print(f"  {name} [{info.get('model') or '?'}] — {len(info['entities'])} entities")


if __name__ == "__main__":
    main()
