"""
Technology Deep Dive — Shared Configuration
API settings, queries, company mappings, domain rules, relevance filters.
"""

# ── API Configuration ──────────────────────────────────────────────────────────

import os
SERP_API_KEY = os.environ.get("SERP_API_KEY", "YOUR_API_KEY_HERE")
SERP_BASE_URL = "https://serpapi.com/search"
SERP_RESULTS_PER_PAGE = 100
SERP_MAX_PAGES = 2
SERP_RATE_LIMIT_SECONDS = 2
SERP_MAX_RETRIES = 3
SERP_BACKOFF_BASE = 5  # seconds, doubles each retry

# ── Date Range ─────────────────────────────────────────────────────────────────

DATE_AFTER = "publication:20251001"
DATE_BEFORE = "publication:20260401"

# ── Company Mappings ───────────────────────────────────────────────────────────

PARENT_GROUPS = {
    "Apple": ["Apple", "Apple Health", "Apple Vision Products Group"],
    "Google / Alphabet": ["Google", "Alphabet", "Google for Health", "Verily", "DeepMind"],
    "Meta": ["Meta", "Facebook", "Reality Labs", "Ray-Ban Meta"],
    "Samsung": ["Samsung", "Samsung Health", "Samsung Galaxy"],
    "TCL": ["TCL", "TCL RayNeo"],
    "EssilorLuxottica": ["EssilorLuxottica", "Ray-Ban"],
}

# Reverse lookup: entity name → parent group
ENTITY_TO_PARENT = {}
for parent, entities in PARENT_GROUPS.items():
    for entity in entities:
        ENTITY_TO_PARENT[entity.lower()] = parent

# Extended assignee patterns for matching Google Patents legal names to our target list.
# Includes English, Chinese, Korean, and Japanese variants seen in patent filings.
ASSIGNEE_PATTERNS = {
    "Apple": [
        "apple inc", "apple", "苹果公司", "アップル", "애플",
    ],
    "Google / Alphabet": [
        "google", "alphabet", "verily life sciences", "verily",
        "deepmind", "谷歌",
    ],
    "Meta": [
        "meta platforms", "meta ", "facebook", "reality labs",
        "元平台技术", "脸书",
    ],
    "Samsung": [
        "samsung electronics", "samsung display", "samsung",
        "삼성전자", "삼성디스플레이", "三星电子", "三星显示",
    ],
    "TCL": [
        "tcl", "rayneo",
    ],
    "EssilorLuxottica": [
        "essilor", "luxottica", "依视路", "에씰로",
        "ray-ban", "rayban",
    ],
}

# ── Country-to-Region Mapping ──────────────────────────────────────────────────

COUNTRY_TO_REGION = {
    "US": "North America", "CA": "North America",
    "EP": "Europe", "DE": "Europe", "FR": "Europe", "GB": "Europe",
    "IT": "Europe", "ES": "Europe", "NL": "Europe", "CH": "Europe",
    "AT": "Europe", "BE": "Europe", "SE": "Europe", "DK": "Europe",
    "FI": "Europe", "NO": "Europe", "IE": "Europe", "PL": "Europe",
    "CZ": "Europe", "PT": "Europe", "HU": "Europe", "RO": "Europe",
    "CN": "China",
    "WO": "Global",
    "JP": "Asia", "KR": "Asia", "TW": "Asia", "IN": "Asia",
    "SG": "Asia", "AU": "Asia",
    "SA": "MENA", "AE": "MENA", "IL": "MENA",
}

# ── Domain Classification Rules ────────────────────────────────────────────────
# Ordered list of (keywords, domain_name). First match wins.

DOMAIN_RULES = [
    (["near-infrared", "nir", "photobiomodulation", "pbm", "red light",
      "rlrl", "light therapy", "retinal stimulation", "low-level light",
      "infrared led therapy"], "NIR/PBM"),
    (["myopia", "defocus", "axial elongation", "myopia control",
      "dims", "halt", "spectacle lens"], "Myopia Control"),
    (["waveguide", "holographic", "micro-led", "micro-oled",
      "augmented reality", "ar display", "birdbath", "electrochromic"],
     "Optics"),
    (["smart glasses", "wearable", "eyewear", "glasses"], "Wearable"),
    (["adaptive optics", "optical", "lens", "prescription"], "Optics"),
    (["sensor", "chipset", "npu", "camera module"], "Chipset/Sensor"),
    (["therapeutic", "medical", "ophthalmic", "retina", "eye health",
      "ocular"], "Therapeutic Device"),
]
DOMAIN_FALLBACK = "Patent Filing"

# ── Patent Queries (SERP API) ──────────────────────────────────────────────────

PATENT_QUERIES_CORE = [
    {
        "q": '"near-infrared" AND "myopia" AND "glasses"',
        "category": "core",
        "descriptor_hint": "near infrared stimulation, myopia progression treatment",
    },
    {
        "q": '"photobiomodulation" AND "retina"',
        "category": "core",
        "descriptor_hint": "photobiomodulation retina, retinal stimulation therapy",
    },
    {
        "q": '"smart glasses" AND ("therapeutic" OR "medical")',
        "category": "core",
        "descriptor_hint": "smart glasses therapy, therapeutic eyewear",
    },
    {
        "q": '"myopia control" AND "lens" AND "spectacle"',
        "category": "core",
        "descriptor_hint": "myopia control device, myopia progression treatment",
    },
    {
        "q": '"wearable" AND "ophthalmic" AND "light"',
        "category": "core",
        "descriptor_hint": "ophthalmic wearable, light therapy eye/ocular phototherapy",
    },
    {
        "q": '"waveguide" AND "AR" AND "prescription"',
        "category": "core",
        "descriptor_hint": "wavefront modulation device, adaptive optics eye device",
    },
    {
        "q": '"red light" AND "myopia" AND "device"',
        "category": "core",
        "descriptor_hint": "low level light therapy eye, myopia control device",
    },
    {
        "q": '"adaptive optics" AND "eye" AND "wearable"',
        "category": "core",
        "descriptor_hint": "adaptive optics eye device, ophthalmic wearable",
    },
    {
        "q": '"retinal stimulation" AND "near-infrared"',
        "category": "core",
        "descriptor_hint": "retinal stimulation therapy, near infrared stimulation",
    },
]

PATENT_QUERIES_COMPANY = [
    # Apple — eye health & ophthalmic
    {
        "q": '"myopia" OR "ophthalmic" OR "eye health" OR "retinal"',
        "assignee": "Apple",
        "category": "company",
        "descriptor_hint": "retinal imaging innovation, ophthalmic wearable",
    },
    {
        "q": '"smart glasses" AND ("therapeutic" OR "health" OR "eye")',
        "assignee": "Apple",
        "category": "company",
        "descriptor_hint": "smart glasses therapy, therapeutic eyewear",
    },
    # Meta — therapeutic smart glasses & light therapy
    {
        "q": '"smart glasses" AND ("health" OR "therapeutic" OR "eye" OR "ophthalmic")',
        "assignee": "Meta Platforms",
        "category": "company",
        "descriptor_hint": "smart glasses therapy, therapeutic eyewear",
    },
    {
        "q": '"near-infrared" OR "photobiomodulation" OR "light therapy" OR "retinal"',
        "assignee": "Meta Platforms",
        "category": "company",
        "descriptor_hint": "near infrared stimulation, photobiomodulation retina",
    },
    # Samsung — eye health & therapeutic
    {
        "q": '"myopia" OR "ophthalmic" OR "eye health" OR "retinal"',
        "assignee": "Samsung",
        "category": "company",
        "descriptor_hint": "ophthalmic wearable, retinal imaging innovation",
    },
    {
        "q": '"smart glasses" AND ("health" OR "therapeutic" OR "eye")',
        "assignee": "Samsung",
        "category": "company",
        "descriptor_hint": "smart glasses therapy, ophthalmic wearable",
    },
    # EssilorLuxottica — myopia & therapeutic lens
    {
        "q": '"myopia" OR "defocus" OR "axial elongation"',
        "assignee": "EssilorLuxottica",
        "category": "company",
        "descriptor_hint": "myopia control device, myopia progression treatment",
    },
    {
        "q": '("smart" OR "therapeutic") AND "lens"',
        "assignee": "EssilorLuxottica",
        "category": "company",
        "descriptor_hint": "therapeutic eyewear, myopia control device",
    },
    # Google/Alphabet — Verily eye health
    {
        "q": '"myopia" OR "ophthalmic" OR "retinal" OR "eye health"',
        "assignee": "Verily",
        "category": "company",
        "descriptor_hint": "retinal imaging innovation, ophthalmic device pipeline",
    },
    {
        "q": '"myopia" OR "ophthalmic" OR "retinal" OR "eye health"',
        "assignee": "Alphabet",
        "category": "company",
        "descriptor_hint": "retinal imaging innovation, ophthalmic device pipeline",
    },
    # TCL — therapeutic smart glasses
    {
        "q": '"smart glasses" AND ("health" OR "therapeutic" OR "eye" OR "ophthalmic")',
        "assignee": "TCL",
        "category": "company",
        "descriptor_hint": "smart glasses therapy, ophthalmic wearable",
    },
]

PATENT_QUERIES_CHINA = [
    {
        "q": "近视 AND 近红外 AND 眼镜",
        "country": "CN",
        "category": "china",
        "descriptor_hint": "near infrared stimulation, myopia progression treatment",
    },
    {
        "q": "光生物调节 AND 视网膜",
        "country": "CN",
        "category": "china",
        "descriptor_hint": "photobiomodulation retina, retinal stimulation therapy",
    },
    {
        "q": "智能眼镜 AND 治疗",
        "country": "CN",
        "category": "china",
        "descriptor_hint": "smart glasses therapy, therapeutic eyewear",
    },
]

PATENT_QUERIES_WHITESPACE = [
    {
        "q": '"smart glasses" AND "NIR" AND "therapeutic"',
        "category": "whitespace",
        "descriptor_hint": "smart glasses therapy, near infrared stimulation",
    },
    {
        "q": '"wearable" AND "near-infrared" AND "myopia" AND "glasses"',
        "category": "whitespace",
        "descriptor_hint": "ophthalmic wearable, near infrared stimulation, myopia control device",
    },
]

ALL_PATENT_QUERIES = (
    PATENT_QUERIES_CORE
    + PATENT_QUERIES_COMPANY
    + PATENT_QUERIES_CHINA
    + PATENT_QUERIES_WHITESPACE
)

# ── Post-Extraction Relevance Filter ───────────────────────────────────────────
# Two-tier system:
#   - TITLE must contain at least one STRONG keyword → patent is definitely relevant
#   - OR SNIPPET must contain at least 2 STRONG keywords → patent is relevant
#   - Generic mentions like "smart glasses" in a list of device types are NOT enough.

RELEVANCE_KEYWORDS_STRONG = [
    # Myopia pillar — high signal
    "myopia", "myopic", "nearsightedness", "near-sightedness",
    "axial elongation", "axial length", "myopia control", "myopia progression",
    "myopia management", "defocus incorporated", "lenslet",
    # NIR / light therapy pillar — high signal
    "photobiomodulation", "near-infrared", "nir therapy",
    "light therapy", "red light therapy", "low-level red light", "rlrl",
    "low-level light", "retinal stimulation", "phototherapy",
    "infrared therapy", "infrared led",
    # Therapeutic eyewear — high signal
    "therapeutic eyewear", "therapeutic lens", "therapeutic glasses",
    "ophthalmic wearable", "therapeutic spectacle",
    "ophthalmic light", "ocular light",
    # Eye health R&D — high signal
    "choroidal thickness", "choroidal", "retinal imaging",
    "ophthalmology", "ophthalmic device",
    "eye disease", "eye treatment", "ocular therapy",
    "spectacle lens", "vision correction",
]

# ── Google Scholar Queries ─────────────────────────────────────────────────────

# Queries designed to hit the intersection of at least 2 of the 3 pillars:
#   Pillar 1: Myopia
#   Pillar 2: Intelligent/smart glasses
#   Pillar 3: Near-infrared / light therapy
SCHOLAR_QUERIES = [
    # Myopia x NIR (Pillar 1+3)
    {"q": "myopia photobiomodulation red light therapy", "descriptor_hint": "photobiomodulation retina, myopia progression treatment"},
    {"q": "repeated low-level red light RLRL myopia control", "descriptor_hint": "low level light therapy eye, myopia control device"},
    {"q": "near-infrared myopia retinal stimulation", "descriptor_hint": "near infrared stimulation, retinal stimulation therapy"},
    {"q": "low-level light therapy myopia axial elongation choroidal", "descriptor_hint": "light therapy eye, myopia progression treatment"},
    {"q": "red light therapy myopia safety retinal damage", "descriptor_hint": "light therapy eye, infrared LED therapy"},
    # Myopia x Smart glasses (Pillar 1+2)
    {"q": "myopia control spectacle lens defocus lenslet smart", "descriptor_hint": "myopia control device, therapeutic eyewear"},
    {"q": "myopia smart glasses therapeutic eyewear wearable", "descriptor_hint": "smart glasses therapy, myopia control device"},
    {"q": "myopia intelligent glasses ophthalmic wearable", "descriptor_hint": "ophthalmic wearable, myopia control device"},
    # Smart glasses x NIR (Pillar 2+3)
    {"q": "smart glasses near-infrared light therapy eye", "descriptor_hint": "smart glasses therapy, near infrared stimulation"},
    {"q": "wearable photobiomodulation ophthalmic light therapy glasses", "descriptor_hint": "ophthalmic wearable, photobiomodulation retina"},
    # All three pillars
    {"q": "myopia near-infrared smart glasses therapeutic", "descriptor_hint": "smart glasses therapy, near infrared stimulation, myopia control device"},
    {"q": "myopia wearable light therapy NIR glasses", "descriptor_hint": "ophthalmic wearable, light therapy eye, myopia progression treatment"},
]

# Pillar keyword sets for the two-pillar relevance filter
SCHOLAR_PILLAR_MYOPIA = [
    "myopia", "myopic", "nearsightedness", "axial elongation", "axial length",
    "myopia control", "myopia progression", "myopia management",
    "defocus", "lenslet", "spectacle lens",
]
SCHOLAR_PILLAR_GLASSES = [
    "smart glasses", "intelligent glasses", "therapeutic eyewear",
    "ophthalmic wearable", "wearable", "eyewear", "glasses",
    "augmented reality", "ar glasses", "waveguide",
]
SCHOLAR_PILLAR_NIR = [
    "near-infrared", "nir", "photobiomodulation", "pbm",
    "red light", "light therapy", "rlrl", "low-level light",
    "retinal stimulation", "phototherapy", "infrared",
    "choroidal thickness", "choroidal",
]
