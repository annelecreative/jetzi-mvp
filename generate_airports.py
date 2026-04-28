import csv
import json

INPUT_FILE = "airports.csv"
OUTPUT_FILE = "data/airports_min.json"

airports = []

with open(INPUT_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        code = row.get("iata_code", "").strip()
        name = row.get("name", "").strip()
        city = row.get("municipality", "").strip()
        country = row.get("iso_country", "").strip()

        # Only keep airports with IATA codes (what users search)
        if not code:
            continue

        airports.append({
            "code": code.upper(),
            "name": name,
            "city": city,
            "country": country,
        })

# Optional: sort for nicer UX
airports.sort(key=lambda x: (x["city"], x["code"]))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(airports, f, indent=2)

print(f"✅ Generated {len(airports)} airports → {OUTPUT_FILE}")