#!/usr/bin/env python3
"""
Generate complete city names mapping with Hebrew names.
This will create a comprehensive mapping for all 277 Israeli cities.
"""

import json
from pathlib import Path

# Major cities mapping (known translations)
KNOWN_CITIES = {
    "tel_aviv": {"hebrew": "תל אביב", "english": ["Tel Aviv", "Tel Aviv-Yafo", "Tel Aviv-Jaffa"]},
    "haifa": {"hebrew": "חיפה", "english": ["Haifa"]},
    "jerusalem": {"hebrew": "ירושלים", "english": ["Jerusalem", "Yerushalayim"]},
    "beer_sheva": {"hebrew": "באר שבע", "english": ["Beer Sheva", "Be'er Sheva", "Beersheba"]},
    "netanya": {"hebrew": "נתניה", "english": ["Netanya"]},
    "ashdod": {"hebrew": "אשדוד", "english": ["Ashdod"]},
    "rishon_lezion": {"hebrew": "ראשון לציון", "english": ["Rishon LeZion", "Rishon Lezion"]},
    "petah_tikva": {"hebrew": "פתח תקווה", "english": ["Petah Tikva", "Petach Tikva"]},
    "holon": {"hebrew": "חולון", "english": ["Holon"]},
    "bnei_brak": {"hebrew": "בני ברק", "english": ["Bnei Brak", "Bene Beraq"]},
    "ramat_gan": {"hebrew": "רמת גן", "english": ["Ramat Gan"]},
    "ashkelon": {"hebrew": "אשקלון", "english": ["Ashkelon"]},
    "rehovot": {"hebrew": "רחובות", "english": ["Rehovot"]},
    "bat_yam": {"hebrew": "בת ים", "english": ["Bat Yam"]},
    "kfar_saba": {"hebrew": "כפר סבא", "english": ["Kfar Saba"]},
    "herzliya": {"hebrew": "הרצליה", "english": ["Herzliya"]},
    "hadera": {"hebrew": "חדרה", "english": ["Hadera"]},
    "modiin": {"hebrew": "מודיעין", "english": ["Modiin", "Modi'in"]},
    "nazareth": {"hebrew": "נצרת", "english": ["Nazareth"]},
    "lod": {"hebrew": "לוד", "english": ["Lod"]},
    "ramla": {"hebrew": "רמלה", "english": ["Ramla", "Ramle"]},
    "raanana": {"hebrew": "רעננה", "english": ["Ra'anana", "Raanana"]},
    "rahat": {"hebrew": "רהט", "english": ["Rahat"]},
    "givatayim": {"hebrew": "גבעתיים", "english": ["Givatayim"]},
    "nahariya": {"hebrew": "נהריה", "english": ["Nahariya"]},
    "beitar_illit": {"hebrew": "ביתר עילית", "english": ["Beitar Illit"]},
    "acre": {"hebrew": "עכו", "english": ["Acre", "Akko"]},
    "umm_al_fahm": {"hebrew": "אום אל-פחם", "english": ["Umm al-Fahm"]},
    "eilat": {"hebrew": "אילת", "english": ["Eilat"]},
    "rosh_haayin": {"hebrew": "ראש העין", "english": ["Rosh HaAyin"]},
    "afula": {"hebrew": "עפולה", "english": ["Afula"]},
    "nes_ziona": {"hebrew": "נס ציונה", "english": ["Nes Ziona"]},
    "yavne": {"hebrew": "יבנה", "english": ["Yavne"]},
    "kiryat_ata": {"hebrew": "קריית אתא", "english": ["Kiryat Ata"]},
    "kiryat_gat": {"hebrew": "קריית גת", "english": ["Kiryat Gat"]},
    "kiryat_motzkin": {"hebrew": "קריית מוצקין", "english": ["Kiryat Motzkin"]},
    "kiryat_yam": {"hebrew": "קריית ים", "english": ["Kiryat Yam"]},
    "kiryat_bialik": {"hebrew": "קריית ביאליק", "english": ["Kiryat Bialik"]},
    "kiryat_ono": {"hebrew": "קריית אונו", "english": ["Kiryat Ono"]},
    "kiryat_shmona": {"hebrew": "קריית שמונה", "english": ["Kiryat Shmona"]},
    "or_yehuda": {"hebrew": "אור יהודה", "english": ["Or Yehuda"]},
    "ramat_hasharon": {"hebrew": "רמת השרון", "english": ["Ramat Hasharon"]},
    "hod_hasharon": {"hebrew": "הוד השרון", "english": ["Hod Hasharon"]},
    "beit_shemesh": {"hebrew": "בית שמש", "english": ["Beit Shemesh"]},
    "carmiel": {"hebrew": "כרמיאל", "english": ["Carmiel", "Karmiel"]},
    "yehud": {"hebrew": "יהוד", "english": ["Yehud"]},
    "tiberias": {"hebrew": "טבריה", "english": ["Tiberias"]},
    "tayibe": {"hebrew": "טייבה", "english": ["Tayibe"]},
    "dimona": {"hebrew": "דימונה", "english": ["Dimona"]},
    "tamra": {"hebrew": "טמרה", "english": ["Tamra"]},
    "sakhnin": {"hebrew": "סכנין", "english": ["Sakhnin"]},
    "yokneam": {"hebrew": "יקנעם", "english": ["Yokneam"]},
    "givat_shmuel": {"hebrew": "גבעת שמואל", "english": ["Givat Shmuel"]},
    "qalansawe": {"hebrew": "קלנסווה", "english": ["Qalansawe"]},
    "nesher": {"hebrew": "נשר", "english": ["Nesher"]},
    "beit_shean": {"hebrew": "בית שאן", "english": ["Beit She'an"]},
    "ofakim": {"hebrew": "אופקים", "english": ["Ofakim"]},
    "netivot": {"hebrew": "נתיבות", "english": ["Netivot"]},
    "tirat_carmel": {"hebrew": "טירת כרמל", "english": ["Tirat Carmel"]},
    "azor": {"hebrew": "אזור", "english": ["Azor"]},
    "ariel": {"hebrew": "אריאל", "english": ["Ariel"]},
    "arad": {"hebrew": "ערד", "english": ["Arad"]},
    "migdal_haemek": {"hebrew": "מגדל העמק", "english": ["Migdal HaEmek"]},
    "sderot": {"hebrew": "שדרות", "english": ["Sderot"]},
    "maalot_tarshiha": {"hebrew": "מעלות-תרשיחא", "english": ["Maalot-Tarshiha"]},
    "safed": {"hebrew": "צפת", "english": ["Safed", "Tzfat"]},
    "tel_mond": {"hebrew": "תל מונד", "english": ["Tel Mond"]},
    "shoham": {"hebrew": "שוהם", "english": ["Shoham"]},
}


def get_all_city_names():
    """Get all city names from landuse directory."""
    landuse_dir = Path("data/processed/israel/cities_landuse")
    if not landuse_dir.exists():
        print(f"Error: {landuse_dir} not found")
        return []

    cities = []
    for file in sorted(landuse_dir.glob("*_landuse.gpkg")):
        city_name = file.stem.replace("_landuse", "")
        cities.append(city_name)

    return cities


def generate_english_name(city_name):
    """Generate English display name from file name."""
    # Replace underscores with spaces and title case
    parts = city_name.split("_")
    return " ".join(word.capitalize() for word in parts)


def main():
    print("Generating city names mapping...")

    # Get all cities
    all_cities = get_all_city_names()
    print(f"Found {len(all_cities)} cities")

    # Build mapping
    mapping = {}
    known_count = 0
    generated_count = 0

    for city in all_cities:
        if city in KNOWN_CITIES:
            mapping[city] = KNOWN_CITIES[city]
            known_count += 1
        else:
            # Generate entry with placeholder Hebrew
            english_name = generate_english_name(city)
            mapping[city] = {
                "hebrew": f"[TO_FILL: {english_name}]",  # Placeholder for manual filling
                "english": [english_name],
            }
            generated_count += 1

    # Save mapping
    output_file = Path("data/processed/israel/city_names_mapping_full.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"\nMapping generated:")
    print(f"  - {known_count} cities with Hebrew names")
    print(f"  - {generated_count} cities need Hebrew names (marked with [TO_FILL:])")
    print(f"  - Total: {len(mapping)} cities")
    print(f"\nSaved to: {output_file}")
    print(f"\nNext steps:")
    print(f"1. Fill in missing Hebrew names in {output_file}")
    print(f"2. Or use Google Translate API to auto-translate")
    print(f"3. Then rename to city_names_mapping.json")


if __name__ == "__main__":
    main()
