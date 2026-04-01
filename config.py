import os

# config.py

# Development-only default for Flask session signing.
# Override with environment variable FLASK_SECRET_KEY in real environments.
FLASK_SECRET_KEY = "dev-only-change-me"

# Email / app URL settings
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "").strip()
REPLY_TO_EMAIL = os.getenv("REPLY_TO_EMAIL", FROM_EMAIL).strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5001").strip().rstrip("/")

# Your search preferences. You can have multiple sets.
PREFERENCES = [
    #{
    #    "from": ["SFO", "SJC"],         # Departure airports
    #    "to": ["SAN", "LAX"],           # Destination airports
    #    "max_price_per_traveler": 70,   # Max price per traveler in USD
    #    "days_of_week": [5, 6],      # Monday=0 ... Sunday=6
    #    "trip_name": "Bay Area to SoCal"
    #},
    {
        "from": ["SFO"],
        "to": ["CDG"],                  # Paris
        "max_price_per_traveler": 1200,
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],  # Any day
        "trip_name": "SFO to Paris"
    },
    {
    "from": ["SFO"],
    "to": ["BKK"],
    "max_price_per_traveler": 1500,
    "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    "trip_name": "SFO to Bangkok"
    }

]

# Range of dates to search (today → X days ahead)
SEARCH_DAYS_AHEAD = 60

# Retention/trust MVP tuning
BASE_DESTINATION_LIMIT = 3
BASELINE_LOOKBACK_DAYS = 30
BASELINE_MIN_OBSERVATIONS = 5
SIGNIFICANT_DROP_PCT = 20
DEAL_DEDUPE_HOURS = 24
NO_DEAL_CHECKIN_DAYS = 7
