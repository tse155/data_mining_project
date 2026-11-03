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
import html
from pathlib import Path
from bs4 import BeautifulSoup  # type: ignore
from rapidfuzz import fuzz, process  # type: ignore

import requests

# from test_scraper_json import strip_accents

URL = (
    "https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-SERVICE"
    "/api/consulta-causas/informacion/actuacionesJudiciales"
)
ORIGIN = "https://procesosjudiciales.funcionjudicial.gob.ec"

# Confirmed with curl: the body is a single JSON OBJECT (an array gets HTTP 400).
# If the server answers 400/422, compare with the Payload tab: a missing or
# misspelled field is the usual cause. Change one thing at a time.
ejercicio = 2023
secuencial = 476

PAYLOAD = {
    "idMovimientoJuicioIncidente": 21187831,
    "idJuicio": f"17510{ejercicio}00{secuencial}",
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


def clean(field: str) -> str:
    prev = None
    while prev != field:  # handles double-encoded text like &amp;iacute;
        prev, field = field, html.unescape(field)
    return BeautifulSoup(field, "html.parser").get_text(" ", strip=True)


def clean_json_data(data):
    """Recursively traverses JSON structures to clean all string values."""
    if isinstance(data, dict):
        # print("new block")
        # for key, value in data.items():
        # print(key)
        # print(value)
        return {key: clean_json_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_json_data(item) for item in data]
    elif isinstance(data, str):
        return clean(data)
    else:
        return data  # Returns numbers, booleans, or None as-is


def process_json_file(input_filename: str, output_filename: str):
    """Loads a JSON file, cleans it, and saves the output."""
    # 1. Read the JSON file
    with open(input_filename, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # 2. Clean the entire dataset
    cleaned_data = clean_json_data(json_data)

    # 3. Save the cleaned JSON back to a file
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=4, ensure_ascii=False)


def main():
    resp = requests.post(URL, headers=HEADERS, json=PAYLOAD, timeout=30)
    print("Status:", resp.status_code)
    print("Content-Type:", resp.headers.get("Content-Type"))

    cleaned_json = clean_json_data(resp.json())

    # 3. Convert the cleaned Python object back into a formatted JSON string
    json_string = json.dumps(cleaned_json, indent=4, ensure_ascii=False)

    # 4. Save the string using your Path object
    raw_path = OUT_DIR / f"17510{ejercicio}00{secuencial}.json"
    raw_path.write_text(json_string, encoding="utf-8")

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
