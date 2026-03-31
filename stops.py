# stops.py
# Przystanki komunikacji miejskiej w pobliżu ul. Kameralnej 3, Warszawa (Praga Północ)
# Kameralna 3 współrzędne: 52.2601, 21.0456
#
# Jak znaleźć busstopId dla nowego przystanku:
# https://api.um.warszawa.pl/api/action/dbtimetable_get?
#   id=b27f4c17-5c50-4a5b-89dd-236b282bc499&name=NAZWA_PRZYSTANKU&apikey=TWOJ_KLUCZ
#
# Jak sprawdzić słupki i linie na przystanku:
# https://api.um.warszawa.pl/api/action/dbtimetable_get?
#   id=88cd555f-6f31-43ca-9de4-66c479ad5942&busstopId=ID&busstopNr=01&apikey=TWOJ_KLUCZ

# Każdy wpis to jeden słupek (fizyczny znak na przystanku).
# busstopId  = ID przystanku (wspólny dla wszystkich słupków w tym miejscu)
# busstopNr  = numer słupka (01, 02...) - kierunek jazdy
# lines      = linie zatrzymujące się na tym słupku
# distance_m = przybliżona odległość od Kameralnej 3 (metry)
#
# UWAGA: te dane wymagają weryfikacji po uzyskaniu klucza API.
# Nazwy i ID przystanków są orientacyjne - zweryfikuj przez API przed uruchomieniem.

STOPS = [
    # --- ZĄBKOWSKA (tramwaje + autobusy, ~300m) ---
    {
        "name": "Ząbkowska",
        "busstopId": "4022",
        "busstopNr": "01",
        "lines": ["4", "13", "25", "26"],
        "type": "tram",
        "distance_m": 300,
        "direction": "centrum",
    },
    {
        "name": "Ząbkowska",
        "busstopId": "4022",
        "busstopNr": "02",
        "lines": ["4", "13", "25", "26"],
        "type": "tram",
        "distance_m": 300,
        "direction": "praga",
    },

    # --- WILEŃSKA (węzeł tramwajowo-autobusowy, ~500m) ---
    {
        "name": "Dworzec Wileński",
        "busstopId": "4025",
        "busstopNr": "01",
        "lines": ["4", "9", "13", "25", "26"],
        "type": "tram",
        "distance_m": 500,
        "direction": "centrum",
    },
    {
        "name": "Dworzec Wileński",
        "busstopId": "4025",
        "busstopNr": "02",
        "lines": ["4", "9", "13", "25", "26"],
        "type": "tram",
        "distance_m": 500,
        "direction": "praga_polnoc",
    },

    # --- STALOWA / ŚRODKOWA (autobusy, ~250m) ---
    {
        "name": "Środkowa",
        "busstopId": "4031",
        "busstopNr": "01",
        "lines": ["102", "125", "135", "146", "N44"],
        "type": "bus",
        "distance_m": 250,
        "direction": "centrum",
    },
    {
        "name": "Środkowa",
        "busstopId": "4031",
        "busstopNr": "02",
        "lines": ["102", "125", "135", "146", "N44"],
        "type": "bus",
        "distance_m": 250,
        "direction": "praga",
    },
]

# Wszystkie unikalne linie obsługujące okolice Kameralnej
ALL_LINES = sorted(set(
    line for stop in STOPS for line in stop["lines"]
))

# Resource IDs dla endpointów API UM Warszawa (zweryfikowane, stabilne)
RESOURCE_IDS = {
    # Lista przystanków wg nazwy → zwraca busstopId i busstopNr
    "stops_by_name":  "b27f4c17-5c50-4a5b-89dd-236b282bc499",
    # Rozkład jazdy dla przystanku (zwraca godziny odjazdów)
    "timetable":      "88cd555f-6f31-43ca-9de4-66c479ad5942",
    # Lokalizacja GPS autobusów (real-time, odświeżane co ~10-20s)
    "buses_gps":      "f2e5503e-927d-4ad3-9500-4ab9e55deb59",
    # Lokalizacja GPS tramwajów (real-time, odświeżane co ~30s)
    "trams_gps":      "c7238cfe-8b1f-4c38-bb4a-de386db7e776",
}

if __name__ == "__main__":
    print(f"Zdefiniowane przystanki: {len(STOPS)} słupków")
    print(f"Monitorowane linie: {', '.join(ALL_LINES)}")
    for s in STOPS:
        print(f"  {s['name']} [{s['busstopId']}/{s['busstopNr']}] "
              f"— {s['type']} — {', '.join(s['lines'])} "
              f"— {s['distance_m']}m — kier. {s['direction']}")
