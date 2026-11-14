"""Fictional name generators. Nothing here is a real customer or person."""
PRE = ["Lumi", "Quor", "Hexa", "Vanta", "Orin", "Zeph", "Kali", "Brin", "Tavo", "Nexa", "Pelu", "Savi", "Dorn", "Ember", "Fyra",
       "Glim", "Halo", "Ivor", "Jenta", "Korva", "Lyra", "Mondo", "Nuvi", "Opal", "Praxi", "Rivo", "Solva", "Trell", "Ulma", "Veda",
       "Wren", "Xylo", "Yara", "Zonta", "Amber", "Cobalt", "Dusk", "Elan", "Fenn", "Garo"]
MID = ["var", "bell", "tek", "ly", "ora", "dyn", "ton", "mark", "sphere", "grid", "path", "wise", "forge", "loop", "scape", "ware"]
SUF = {"healthcare": ["Health", "Care", "Clinics"], "fintech": ["Pay", "Financial", "Capital"], "retail": ["Retail", "Goods", "Market"],
       "logistics": ["Logistics", "Freight", "Fleet"], "insurance": ["Insurance", "Assurance"], "travel": ["Travel", "Journeys"],
       "software": ["Labs", "Systems", "Software"], "telecom": ["Networks", "Telecom"], "education": ["Learning", "Academy"],
       "real_estate": ["Realty", "Homes"], "media": ["Media", "Studios"], "utilities": ["Energy", "Utilities"]}
INDUSTRIES = list(SUF)
FIRST = ["Maya", "Daniel", "Priya", "Tomas", "Elena", "Marcus", "Aiko", "Samir", "Nora", "Jonas", "Leila", "Ravi", "Cleo", "Owen",
         "Ines", "Felix", "Tara", "Hugo", "Zoe", "Anders", "Mina", "Caleb", "Rosa", "Kofi", "Yuki", "Dara", "Lena", "Mateo"]
LAST = ["Alder", "Brandt", "Chaudhry", "Dvorak", "Eriksen", "Fontaine", "Gallo", "Hartmann", "Ibarra", "Jansen", "Kowalski",
        "Lindqvist", "Morales", "Nakamura", "Okafor", "Petrov", "Quill", "Rahman", "Sorensen", "Takeda", "Umar", "Varga", "Whitlock", "Yilmaz"]
REP_TITLES = ["Account Executive", "Senior Account Executive", "Solutions Engineer"]
BUYER_ROLES = {"software": ["VP Engineering", "Head of Platform", "CTO", "ML Lead"], "default": ["Director of Operations", "Head of Customer Experience", "VP Engineering", "IT Director", "Product Lead"]}

def company(rng, industry, used):
    for _ in range(50):
        n = rng.choice(PRE) + (rng.choice(MID) if rng.random() < 0.6 else "")
        n = f"{n} {rng.choice(SUF[industry])}"
        if n not in used:
            used.add(n); return n
    raise RuntimeError("name space exhausted")

def person(rng, used=None):
    for _ in range(50):
        n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if used is None or n not in used:
            if used is not None: used.add(n)
            return n
    return n
