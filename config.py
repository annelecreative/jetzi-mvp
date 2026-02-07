# config.py

# Your search preferences. You can have multiple sets.
PREFERENCES = [
    #{
    #    "from": ["SFO", "SJC"],         # Departure airports
    #    "to": ["SAN", "LAX"],           # Destination airports
    #    "max_price": 70,                # Max price in USD
    #    "days_of_week": [5, 6],      # Monday=0 ... Sunday=6
    #    "trip_name": "Bay Area to SoCal"
    #},
    {
        "from": ["SFO"],
        "to": ["CDG"],                  # Paris
        "max_price": 1200,
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],  # Any day
        "trip_name": "SFO to Paris"
    },
    {
    "from": ["SFO"],
    "to": ["BKK"],
    "max_price": 1500,
    "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    "trip_name": "SFO to Bangkok"
    }

]

# Range of dates to search (today → X days ahead)
SEARCH_DAYS_AHEAD = 60
