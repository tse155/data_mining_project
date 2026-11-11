"""
Probe for the staje court system endpoints.
Functions to retrieve the ids of judicial process using the required payload
Functions to retrieve the judicial case in json format
Functions to filter the relevant "actividad" of the judicial process -> tax ruling
Functions to save the filtered json file with the ruling "actividad" for further processing

Usage:
-> state a year for which the judicial process may be retrieved.
-> state a range of judicial process to be retrieved

Notes:
-> Not all judicial processes may have a ruling. Therefore, some json files may be empty
-> We are using code 17510 which corresponds to the Tax Court sitting in Quito
-> We are retrieving first level rulings (instancia unica), not cassation appeal rulings

"""

import json
import time
import html
from pathlib import Path
from bs4 import BeautifulSoup  # type: ignore

# from rapidfuzz import fuzz, process  # type: ignore
import re
import unicodedata


import requests

# URL of the api endpoint that returns a json file with the judicial process information
URL_Actuaciones = (
    "https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-SERVICE"
    "/api/consulta-causas/informacion/actuacionesJudiciales"
)


ORIGIN = "https://procesosjudiciales.funcionjudicial.gob.ec"

# Confirmed with curl: the body is a single JSON OBJECT (an array gets HTTP 400).
# If the server answers 400/422, compare with the Payload tab: a missing or
# misspelled field is the usual cause. Change one thing at a time.


HEADERS_actuaciones = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": ORIGIN,
    "Referer": ORIGIN + "/",
    "User-Agent": "Mozilla/5.0 (research script; academic use)",
}

HEADERS_ids = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://procesosjudiciales.funcionjudicial.gob.ec",
    "Referer": "https://procesosjudiciales.funcionjudicial.gob.ec/",
}

OUT_DIR = Path("/Users/cesartse/desktop/satje/processed")
# RAW_DIR = Path("/Users/cesartse/desktop/satje/rawfiles")
OUT_DIR.mkdir(exist_ok=True)

# -----Regex type to select only the relevant part of judicial process------#

RULING_TIPO = re.compile(r"^SENTENCIA\b.*\(RESOLUCION\)$")

# -----Regex type to select only the case heard by the Quito tax court------#
INSTANCE_TYPE = re.compile(
    r"(?i)TRIBUNAL\s+DISTRITAL\s+DE\s+LO\s+CONTENCIOSO\s+TRIBUTARIO\s+CON\s+SEDE\s+EN\s+EL\s+DISTRITO\s+METROPOLITANO\s+DE\s+QUITO,\s+PROVINCIA\s+DE\s+PICHINCHA"
)


# -----Description functions or what is responded by the endpoint------#


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


# -----Auxiliary functions to clean and to format the json returned by the endpoint------#


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def norm_tipo(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(s or "")).strip().upper()


# -----Functions to clean the json returned by the endpoint and retrieve only the ruling activity------#
# Important: the ruling activity also includes the specific ruling, but also other information


def clean(field: str) -> str:
    """
    json files have special &amp and iacute chars for HTML.
    using beautiful soup those chars are modified to their intended spanish form
    """
    prev = None
    while prev != field:  # handles double-encoded text like &amp;iacute;
        prev, field = field, html.unescape(field)
    return BeautifulSoup(field, "html.parser").get_text(" ", strip=True)


def clean_json_data(data):
    """Recursively traverses JSON structures to clean string values.
    For efficiency purposes this function filters the ruling "activity" in the json
    Guarantees that only the ruling is actually cleaned.
    Thus, this avoids cleaning the whole json response that can be extense
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "tipo":
                formated_value = norm_tipo(value)
                # print(value)
                # print(formated_value)
                if RULING_TIPO.match(formated_value):
                    return {key: clean_json_data(value) for key, value in data.items()}
                else:
                    return None
    elif isinstance(data, list):
        return [clean_json_data(item) for item in data]
    elif isinstance(data, str):
        return clean(data)
    else:
        return data  # Returns numbers, booleans, or None as-is


def process_json_file(input_filename: str, output_filename: str):
    """Loads a JSON file, calls the cleaning function, and saves the output."""
    # 1. Read the JSON file
    with open(input_filename, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # 2. Clean the entire dataset
    cleaned_data = clean_json_data(json_data)

    # 3. Save the cleaned JSON back to a file
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=4, ensure_ascii=False)


def remove_nulls(data):
    if isinstance(data, dict):
        return {
            k: remove_nulls(v)
            for k, v in data.items()
            if v is not None and remove_nulls(v) is not None
        }
    elif isinstance(data, list):
        return [remove_nulls(v) for v in data if v is not None]
    return data


def get_judicatura_ids(header, id_juicio):
    """ "
    To retrieve all the activity of a judicial process we need specific ids
    Using the judicial process number and not specifying a expected response format,
    it is possible to retrieve those ids and use them in the payload
    to retrieve the judicial process activity in json format

    Returns: the actual payload to be used in the endpoint that returns
    the json of a judicial process
    """

    URL_id = f"https://api.funcionjudicial.gob.ec/EXPEL-CONSULTA-CAUSAS-CLEX-SERVICE/api/consulta-causas-clex/informacion/getIncidenteJudicatura/{id_juicio}"
    try:
        # Perform the GET request
        response_id = requests.get(URL_id, headers=header)

        if response_id.status_code == 200:
            data = response_id.json()

            # Replicating  jq logic: '.[].lstIncidenteJudicatura[]'
            # jq logic was identified using curl and specific request bodies
            for item in data:
                # Safely get the list, defaulting to an empty list if not found
                judictura_name = item.get("nombreJudicatura")

                formated_value = norm_tipo(judictura_name)
                # print(value)
                # print(formated_value)
                if INSTANCE_TYPE.match(formated_value):
                    lst_incidente = item.get("lstIncidenteJudicatura", [])

                    for inc in lst_incidente:
                        return {
                            "idMovimientoJuicioIncidente": inc[
                                "idMovimientoJuicioIncidente"
                            ],
                            "idJuicio": id_juicio,
                            "idJudicatura": item.get("idJudicatura", "17510"),
                            "idIncidenteJudicatura": inc["idIncidenteJudicatura"],
                            "incidente": inc["incidente"],
                            "aplicativo": "web",
                        }

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


def main():
    log = {}
    # define the desired year
    ejercicio = 2021
    # define the desired range
    for i in range(1, 400):
        # i = f"0{i}"

        id_juicio = f"17510{ejercicio}{i:05d}"

        PAYLOAD = get_judicatura_ids(HEADERS_ids, id_juicio)

        resp = requests.post(
            URL_Actuaciones, headers=HEADERS_actuaciones, json=PAYLOAD, timeout=30
        )
        if resp.status_code == 429:
            print("rate limited, stopping")
            break
        if not resp.ok:
            log[id_juicio] = f"failed {resp.status_code}"
            continue  # nothing is written
        # (OUT_DIR / f"{id_juicio}.json").write_text(resp.text, encoding="utf-8")

        cleaned_json = clean_json_data(resp.json())

        not_null_json = remove_nulls(cleaned_json)

        # 3. Convert the cleaned Python object back into a formatted JSON string
        json_string = json.dumps(not_null_json, indent=4, ensure_ascii=False)

        # 4. Save the string using your Path object
        raw_path = OUT_DIR / f"{id_juicio}.json"
        raw_path.write_text(json_string, encoding="utf-8")

        # if resp.status_code == 429:
        #     print("Rate limited: stop, wait several minutes, then retry more slowly.")
        #     return
        # if resp.status_code in (401, 403):
        #     print(
        #         "Access refused. Do not try to work around it; reassess "
        #         "(manual retrieval is the fallback)."
        #     )
        #     return
        # if not resp.ok:
        #     print("Error body:", resp.text[:500])
        #     print("Hint: 400/422 usually means a missing or misnamed payload field.")
        #     return

        # try:
        #     data = resp.json()
        # except ValueError:
        #     print("Response is not JSON; inspect response_raw.txt")
        #     return

        print("\nStructure of the response:")
        describe(resp.json())

        time.sleep(4)  # pausing between calls is advisable


if __name__ == "__main__":
    main()
