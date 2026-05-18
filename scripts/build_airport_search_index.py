import csv
import json
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV = BASE_DIR / "airports.csv"
OUTPUT_JSON = BASE_DIR / "static" / "airport_search_index.json"

COUNTRY_NAMES = {
    "US": "United States",
    "FR": "France",
    "ES": "Spain",
    "IT": "Italy",
    "JP": "Japan",
    "TH": "Thailand",
    "MX": "Mexico",
    "CA": "Canada",
    "GB": "United Kingdom",
    "PT": "Portugal",
    "GR": "Greece",
    "DE": "Germany",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "IE": "Ireland",
    "AU": "Australia",
    "NZ": "New Zealand",
    "KR": "South Korea",
    "CN": "China",
    "TW": "Taiwan",
    "VN": "Vietnam",
    "SG": "Singapore",
    "ID": "Indonesia",
    "PH": "Philippines",
    "MY": "Malaysia",
    "BR": "Brazil",
    "AR": "Argentina",
    "CO": "Colombia",
    "PE": "Peru",
}

COUNTRY_FLAGS = {
    "US": "🇺🇸",
    "FR": "🇫🇷",
    "ES": "🇪🇸",
    "IT": "🇮🇹",
    "JP": "🇯🇵",
    "TH": "🇹🇭",
    "MX": "🇲🇽",
    "CA": "🇨🇦",
    "GB": "🇬🇧",
    "PT": "🇵🇹",
    "GR": "🇬🇷",
    "DE": "🇩🇪",
    "NL": "🇳🇱",
    "CH": "🇨🇭",
    "IE": "🇮🇪",
    "AU": "🇦🇺",
    "NZ": "🇳🇿",
    "KR": "🇰🇷",
    "CN": "🇨🇳",
    "TW": "🇹🇼",
    "VN": "🇻🇳",
    "SG": "🇸🇬",
    "ID": "🇮🇩",
    "PH": "🇵🇭",
    "MY": "🇲🇾",
    "BR": "🇧🇷",
    "AR": "🇦🇷",
    "CO": "🇨🇴",
    "PE": "🇵🇪",
}

MAJOR_CITY_OVERRIDES = {
    "Paris": "PAR",
    "New York": "NYC",
    "London": "LON",
    "Tokyo": "TYO",
    "Los Angeles": "LAX",
    "San Francisco": "SFO",
    "Chicago": "CHI",
    "Washington": "WAS",
    "Milan": "MIL",
    "Rome": "ROM",
    "Bangkok": "BKK",
    "Osaka": "OSA",
}


def clean_text(value):
    return (value or "").strip()


def country_name(code):
    return COUNTRY_NAMES.get(code, code)


def country_flag(code):
    return COUNTRY_FLAGS.get(code, "🌍")


def normalize_city_name(city):
    city = clean_text(city)

    # Clean messy municipality values from the CSV.
    # Example:
    # "Paris (Roissy-en-France, Val-d'Oise)" -> "Paris"
    if " (" in city:
        city = city.split(" (", 1)[0].strip()

    return city


def build_index():
    airports = []
    city_groups = defaultdict(list)
    countries = {}

    with INPUT_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            airport_type = clean_text(row.get("type"))
            scheduled_service = clean_text(row.get("scheduled_service"))
            iata = clean_text(row.get("iata_code"))
            airport_name = clean_text(row.get("name"))
            municipality = normalize_city_name(row.get("municipality"))
            iso_country = clean_text(row.get("iso_country"))

            # MVP filter:
            # Keep only real commercial airports with IATA codes.
            if airport_type not in {"large_airport", "medium_airport"}:
                continue

            if scheduled_service != "yes":
                continue

            if not iata:
                continue

            if not municipality:
                continue

            display_country = country_name(iso_country)
            flag = country_flag(iso_country)

            airport_item = {
                "type": "airport",
                "label": f"✈️ {airport_name} ({iata})",
                "subtitle": f"{municipality}, {display_country}",
                "value": iata,
                "iata": iata,
                "city": municipality,
                "country": display_country,
                "country_code": iso_country,
                "search_text": f"{airport_name} {iata} {municipality} {display_country}".lower(),
                "rank_boost": 60 if airport_type == "large_airport" else 35,
            }

            airports.append(airport_item)

            city_key = f"{municipality}|{display_country}"
            city_groups[city_key].append(airport_item)

            countries[iso_country] = {
                "type": "country",
                "label": f"{flag} {display_country}",
                "subtitle": "Country",
                "value": f"country:{iso_country}",
                "country": display_country,
                "country_code": iso_country,
                "search_text": f"{display_country} {iso_country}".lower(),
                "rank_boost": 80,
            }

    city_items = []

    for city_key, city_airports in city_groups.items():
        city, display_country = city_key.split("|", 1)
        iso_country = city_airports[0]["country_code"]
        flag = country_flag(iso_country)

        airport_codes = [airport["iata"] for airport in city_airports]
        preferred_code = MAJOR_CITY_OVERRIDES.get(city)

        if not preferred_code:
            preferred_code = airport_codes[0]

        city_items.append({
            "type": "city",
            "label": f"{flag} {city}, {display_country}",
            "subtitle": "All airports",
            "value": f"city:{city}:{iso_country}",
            "city": city,
            "country": display_country,
            "country_code": iso_country,
            "iata_codes": airport_codes,
            "search_text": f"{city} {display_country} {' '.join(airport_codes)}".lower(),
            "rank_boost": 100 if len(city_airports) > 1 else 70,
        })

    search_index = list(countries.values()) + city_items + airports

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False, indent=2)

    print(f"Created {OUTPUT_JSON}")
    print(f"Countries: {len(countries)}")
    print(f"Cities: {len(city_items)}")
    print(f"Airports: {len(airports)}")
    print(f"Total search items: {len(search_index)}")


if __name__ == "__main__":
    build_index()