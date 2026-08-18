"""Pakistan geography reference data used by the normalization engine.

Kept as data (not code branches) so new cities/regions are a one-line change.
"""

from __future__ import annotations

from dataclasses import dataclass


class Province:
    PUNJAB = "Punjab"
    SINDH = "Sindh"
    KHYBER_PAKHTUNKHWA = "Khyber Pakhtunkhwa"
    BALOCHISTAN = "Balochistan"
    ISLAMABAD = "Islamabad Capital Territory"
    GILGIT_BALTISTAN = "Gilgit-Baltistan"
    AJK = "Azad Jammu and Kashmir"


PROVINCES: list[str] = [
    Province.PUNJAB,
    Province.SINDH,
    Province.KHYBER_PAKHTUNKHWA,
    Province.BALOCHISTAN,
    Province.ISLAMABAD,
    Province.GILGIT_BALTISTAN,
    Province.AJK,
]

PROVINCE_ALIASES: dict[str, str] = {
    "punjab": Province.PUNJAB,
    "pb": Province.PUNJAB,
    "sindh": Province.SINDH,
    "sind": Province.SINDH,
    "sd": Province.SINDH,
    "kpk": Province.KHYBER_PAKHTUNKHWA,
    "kp": Province.KHYBER_PAKHTUNKHWA,
    "khyber pakhtunkhwa": Province.KHYBER_PAKHTUNKHWA,
    "khyber pakhtoonkhwa": Province.KHYBER_PAKHTUNKHWA,
    "nwfp": Province.KHYBER_PAKHTUNKHWA,
    "balochistan": Province.BALOCHISTAN,
    "baluchistan": Province.BALOCHISTAN,
    "islamabad": Province.ISLAMABAD,
    "islamabad capital territory": Province.ISLAMABAD,
    "ict": Province.ISLAMABAD,
    "federal capital": Province.ISLAMABAD,
    "gilgit baltistan": Province.GILGIT_BALTISTAN,
    "gilgit-baltistan": Province.GILGIT_BALTISTAN,
    "gb": Province.GILGIT_BALTISTAN,
    "azad jammu and kashmir": Province.AJK,
    "azad kashmir": Province.AJK,
    "ajk": Province.AJK,
    "aj&k": Province.AJK,
}


@dataclass(frozen=True)
class City:
    name: str
    slug: str
    province: str
    aliases: tuple[str, ...] = ()
    is_major: bool = False


CITIES: tuple[City, ...] = (
    City("Karachi", "karachi", Province.SINDH, ("khi", "karachi city"), True),
    City("Lahore", "lahore", Province.PUNJAB, ("lhr", "lahore city"), True),
    City("Islamabad", "islamabad", Province.ISLAMABAD, ("isb", "islamabad city"), True),
    City("Rawalpindi", "rawalpindi", Province.PUNJAB, ("rwp", "pindi"), True),
    City("Faisalabad", "faisalabad", Province.PUNJAB, ("lyallpur",), True),
    City("Multan", "multan", Province.PUNJAB, (), True),
    City("Peshawar", "peshawar", Province.KHYBER_PAKHTUNKHWA, (), True),
    City("Quetta", "quetta", Province.BALOCHISTAN, (), True),
    City("Gujranwala", "gujranwala", Province.PUNJAB, (), True),
    City("Sialkot", "sialkot", Province.PUNJAB, (), True),
    City("Hyderabad", "hyderabad", Province.SINDH, ("hyderabad sindh",), True),
    City("Sukkur", "sukkur", Province.SINDH, (), False),
    City("Bahawalpur", "bahawalpur", Province.PUNJAB, (), False),
    City("Sargodha", "sargodha", Province.PUNJAB, (), False),
    City("Abbottabad", "abbottabad", Province.KHYBER_PAKHTUNKHWA, (), False),
    City("Mardan", "mardan", Province.KHYBER_PAKHTUNKHWA, (), False),
    City("Gujrat", "gujrat", Province.PUNJAB, (), False),
    City("Sahiwal", "sahiwal", Province.PUNJAB, (), False),
    City("Rahim Yar Khan", "rahim-yar-khan", Province.PUNJAB, ("rym khan", "ryk"), False),
    City("Larkana", "larkana", Province.SINDH, (), False),
    City("Nawabshah", "nawabshah", Province.SINDH, ("shaheed benazirabad",), False),
    City("Mirpur Khas", "mirpur-khas", Province.SINDH, (), False),
    City("Gwadar", "gwadar", Province.BALOCHISTAN, (), False),
    City("Turbat", "turbat", Province.BALOCHISTAN, (), False),
    City("Gilgit", "gilgit", Province.GILGIT_BALTISTAN, (), False),
    City("Skardu", "skardu", Province.GILGIT_BALTISTAN, (), False),
    City("Muzaffarabad", "muzaffarabad", Province.AJK, (), False),
    City("Mirpur", "mirpur-ajk", Province.AJK, ("mirpur azad kashmir",), False),
    City("Jhelum", "jhelum", Province.PUNJAB, (), False),
    City("Okara", "okara", Province.PUNJAB, (), False),
    City("Kasur", "kasur", Province.PUNJAB, (), False),
    City("Dera Ghazi Khan", "dera-ghazi-khan", Province.PUNJAB, ("dg khan",), False),
    City("Sheikhupura", "sheikhupura", Province.PUNJAB, (), False),
    City("Wah Cantt", "wah-cantt", Province.PUNJAB, ("wah cantonment", "wah"), False),
    City("Chiniot", "chiniot", Province.PUNJAB, (), False),
    City("Kohat", "kohat", Province.KHYBER_PAKHTUNKHWA, (), False),
    City("Swat", "swat", Province.KHYBER_PAKHTUNKHWA, ("mingora", "saidu sharif"), False),
    City("Attock", "attock", Province.PUNJAB, (), False),
    City("Jacobabad", "jacobabad", Province.SINDH, (), False),
    City("Khuzdar", "khuzdar", Province.BALOCHISTAN, (), False),
)

CITY_BY_SLUG: dict[str, City] = {c.slug: c for c in CITIES}

# Lookup table: every alias + name -> City
CITY_LOOKUP: dict[str, City] = {}
for _c in CITIES:
    CITY_LOOKUP[_c.name.lower()] = _c
    CITY_LOOKUP[_c.slug] = _c
    for _a in _c.aliases:
        CITY_LOOKUP[_a.lower()] = _c

MAJOR_CITIES: list[City] = [c for c in CITIES if c.is_major]

COUNTRY_ALIASES: dict[str, str] = {
    "pakistan": "PK",
    "pk": "PK",
    "islamic republic of pakistan": "PK",
    "pak": "PK",
}
