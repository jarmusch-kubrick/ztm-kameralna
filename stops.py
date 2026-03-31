# stops.py
# Przystanki przy ul. Kameralnej 3, Warszawa
#
# Dane linii zweryfikowane ze zdjęć aplikacji (31.03.2026)
# busstopId — DO WERYFIKACJI przez API po uzyskaniu klucza
#
# Jak zweryfikować busstopId:
# Wejdź na wtp.waw.pl, kliknij przystanek, sprawdź parametr wtp_st w URL

STOPS = [

    # ── RATUSZOWA-ZOO ────────────────────────────────────────────────────────
    # busstopId=1004 zweryfikowane przez targeo.pl (id 100401, 100402)
    # Słupek 01 → kierunek Ratuszowa (centrum)
    {
        "name": "Ratuszowa-Zoo",
        "busstopId": "1004",
        "busstopNr": "01",
        "lines": ["6", "18", "20", "23", "28", "W"],
        "type": "tram",
        "direction": "Ratuszowa",
        "distance_m": 400,
    },
    # Słupek 02 → kierunek Pl. Hallera (praga)
    {
        "name": "Ratuszowa-Zoo",
        "busstopId": "1004",
        "busstopNr": "02",
        "lines": ["6", "18", "20", "23", "28"],
        "type": "tram",
        "direction": "Pl. Hallera",
        "distance_m": 400,
    },

    # ── DWORZEC WILEŃSKI ─────────────────────────────────────────────────────
    # busstopId=1003 zweryfikowane przez Warszawikia i targeo.pl (id 100305 itd.)
    # Słupek 01 → autobusy kierunek Ząbkowska
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "01",
        "lines": ["120", "135", "162", "166", "169", "170", "338",
                  "509", "512", "N02", "N03", "N14", "N16", "N21", "N64", "N71"],
        "type": "bus",
        "direction": "Ząbkowska",
        "distance_m": 600,
    },
    # Słupek 02 → autobusy kierunek Inżynierska
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "02",
        "lines": ["162", "166", "169", "170", "190", "338",
                  "509", "512", "N03", "N14", "N64"],
        "type": "bus",
        "direction": "Inżynierska",
        "distance_m": 600,
    },
    # Słupek 03 → tramwaje + autobusy kierunek Park Praski
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "03",
        "lines": ["4", "13", "20", "23", "26", "76", "W", "160", "190"],
        "type": "tram",
        "direction": "Park Praski",
        "distance_m": 600,
    },
    # Słupek 04 → autobusy kierunek Rzeszotarskiej
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "04",
        "lines": ["120", "135", "160", "162", "170", "190",
                  "338", "512", "N02", "N11", "N61"],
        "type": "bus",
        "direction": "Rzeszotarskiej",
        "distance_m": 600,
    },
    # Słupek 05 → autobusy kierunek Rondo Starzyńskiego
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "05",
        "lines": ["135", "509", "N11", "N16", "N21", "N61", "N71"],
        "type": "bus",
        "direction": "Rondo Starzyńskiego",
        "distance_m": 600,
    },
    # Słupek 07 → tramwaje kierunek Ząbkowska
    {
        "name": "Dw. Wileński",
        "busstopId": "1003",
        "busstopNr": "07",
        "lines": ["3", "6", "13", "25", "26", "28", "W"],
        "type": "tram",
        "direction": "Ząbkowska",
        "distance_m": 600,
    },
]

# Wszystkie unikalne linie
ALL_LINES = sorted(set(
    line for stop in STOPS for line in stop["lines"]
))

# Resource IDs dla API UM Warszawa (zweryfikowane)
RESOURCE_IDS = {
    "stops_by_name": "b27f4c17-5c50-4a5b-89dd-236b282bc499",
    "timetable":     "88cd555f-6f31-43ca-9de4-66c479ad5942",
    "buses_gps":     "f2e5503e927d-4ad3-9500-4ab9e55deb59",
    "trams_gps":     "c7238cfe-8b1f-4c38-bb4a-de386db7e776",
}

if __name__ == "__main__":
    print(f"Przystanki: {len(STOPS)} słupków")
    print(f"Linie ({len(ALL_LINES)}): {', '.join(ALL_LINES)}")
    for s in STOPS:
        print(f"  {s['name']} [{s['busstopNr']}] → {s['direction']}"
              f" | {s['type']} | {', '.join(s['lines'][:5])}{'...' if len(s['lines']) > 5 else ''}")
