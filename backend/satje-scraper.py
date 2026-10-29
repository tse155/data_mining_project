"""
Minimal probe for one court-system endpoint, replicating a request seen in the
browser's Network tab. Goal: learn the response shape for ONE case, politely.

Usage:
    pip install requests
    python probe_satje.py

Edit PAYLOAD below using the Network tab -> request -> "Payload" -> "view source".
Do not paste cookies, tokens or headers into public places.
"""

import json
import time
from pathlib import Path

import requests

URL = (
    "https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-SERVICE"
    "/api/consulta-causas/informacion/actuacionesJudiciales"
)
ORIGIN = "https://procesosjudiciales.funcionjudicial.gob.ec"

# Confirmed with curl: the body is a single JSON OBJECT (an array gets HTTP 400).
# If the server answers 400/422, compare with the Payload tab: a missing or
# misspelled field is the usual cause. Change one thing at a time.
PAYLOAD = {
    "idMovimientoJuicioIncidente": 21187831,
    "idJuicio": "17510201900371",
    "idJudicatura": "17510",
    "idIncidenteJudicatura": 22040693,
    "incidente": 1,
    "aplicativo": "web",
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": ORIGIN,
    "Referer": ORIGIN + "/",
    # Be honest about who you are; also fine to copy your browser's UA while testing.
    "User-Agent": "Mozilla/5.0 (research script; academic use)",
}

OUT_DIR = Path("/Users/cesartse/desktop/satje")
OUT_DIR.mkdir(exist_ok=True)


def describe(obj, depth=0, max_depth=3):
    """Print the structure (keys and types) without dumping huge text fields."""
    pad = "  " * depth
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and depth < max_depth:
                print(f"{pad}{k}: {type(v).__name__}")
                describe(v, depth + 1, max_depth)
            else:
                size = len(v) if isinstance(v, str) else ""
                print(f"{pad}{k}: {type(v).__name__} {size}")
    elif isinstance(obj, list):
        print(f"{pad}[list of {len(obj)}]")
        if obj and depth < max_depth:
            describe(obj[0], depth + 1, max_depth)


def main():
    resp = requests.post(URL, headers=HEADERS, json=PAYLOAD, timeout=30)
    print("Status:", resp.status_code)
    print("Content-Type:", resp.headers.get("Content-Type"))

    raw_path = OUT_DIR / "response_raw.txt"
    raw_path.write_text(resp.text, encoding="utf-8")
    print(f"Saved raw response to {raw_path} ({len(resp.text)} chars)")

    if resp.status_code == 429:
        print("Rate limited: stop, wait several minutes, then retry more slowly.")
        return
    if resp.status_code in (401, 403):
        print(
            "Access refused. Do not try to work around it; reassess "
            "(manual retrieval is the fallback)."
        )
        return
    if not resp.ok:
        print("Error body:", resp.text[:500])
        print("Hint: 400/422 usually means a missing or misnamed payload field.")
        return

    try:
        data = resp.json()
    except ValueError:
        print("Response is not JSON; inspect response_raw.txt")
        return

    print("\nStructure of the response:")
    describe(data)

    time.sleep(2)  # always pause between calls if you extend this into a loop


if __name__ == "__main__":
    main()
