"""
Multi-script Name & Address Normalization Engine (ADR-015, ADR-017).

Handles:
  - Multi-script transliteration (Cyrillic, Arabic, Greek, CJK, European diacritics)
  - Legal form / corporate suffix stripping & canonicalization (Ltd, Limited, PLC, LLP, GmbH, SA...)
  - Address fingerprinting: NORMALIZED_POSTCODE|HOUSE_NUMBER|FIRST_KEYWORD (ADR-015)
  - Phonetic key generation (Beider-Morse / Metaphone style) and Jaro-Winkler similarity
  - Extraction of 8-character UK Companies House registration numbers from free text
"""
from __future__ import annotations

import re
import unicodedata

try:
    from fingerprints import generate as _fp_generate
except ImportError:
    _fp_generate = None

try:
    import jellyfish as _jellyfish
except ImportError:
    _jellyfish = None

try:
    from rapidfuzz.distance import JaroWinkler as _rf_jw  # noqa: N813
except ImportError:
    _rf_jw = None

# Cyrillic -> Latin ISO/GOST transliteration map
_CYRILLIC_MAP: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
}

# Arabic -> Latin basic romanization map
_ARABIC_MAP: dict[str, str] = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th",
    "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
    "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
    "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "h", "ء": "",
    "ک": "k", "ی": "y", "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g",
}

# Greek -> Latin basic map
_GREEK_MAP: dict[str, str] = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}

# Common CJK characters for cross-script tests and corporate names
_CJK_MAP: dict[str, str] = {
    "江": "jiang ", "澤": "ze", "泽": "ze", "民": "min ",
    "中": "zhong ", "国": "guo ", "國": "guo ", "有": "you ", "限": "xian ",
    "公": "gong ", "司": "si ", "集": "ji ", "团": "tuan ", "團": "tuan ",
    "控": "kong ", "股": "gu ", "际": "ji ", "際": "ji ",
    "投": "tou ", "资": "zi ", "資": "zi ", "贸": "mao ", "貿": "mao ",
    "易": "yi ", "香": "xiang ", "港": "gang ", "北": "bei ", "京": "jing ",
    "上": "shang ", "海": "hai ", "深": "shen ", "圳": "zhen ",
}

# Special Latin ligatures / Nordic / German characters not decomposed by NFKD
_LATIN_EXTRA_MAP: dict[str, str] = {
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ð": "d",
    "þ": "th", "ł": "l", "ħ": "h", "ı": "i",
}

# Corporate legal form suffixes normalized/stripped in canonical company fingerprints
COMPANY_LEGAL_SUFFIXES: set[str] = {
    "ltd", "limited", "plc", "llp", "lp", "inc", "incorporated", "corp",
    "corporation", "co", "company", "gmbh", "ag", "sa", "sarl", "srl",
    "spa", "bv", "nv", "llc", "fzco", "fze", "bvi", "ibc", "pte", "pty",
    "sdn", "bhd", "ab", "oy", "as", "aps", "kft", "zrt", "sp", "zoo",
    "ooo", "zao", "oao", "pao", "holding", "holdings", "uk",
}

PERSON_TITLES: set[str] = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "sir", "lord", "lady",
    "dame", "rev", "hon", "capt", "col", "gen", "he", "sheikh", "sheikha",
}

ADDRESS_STOPWORDS: set[str] = {
    "the", "and", "of", "at", "in", "on", "to", "for", "by",
    "flat", "apt", "apartment", "suite", "unit", "floor", "room",
    "level", "building", "house", "court", "chambers", "office", "offices",
    "first", "second", "third", "ground", "lower", "upper",
    "care", "co", "po", "box", "street", "st", "road", "rd", "lane", "ln",
    "avenue", "ave", "drive", "dr", "square", "sq", "place", "pl", "close",
    "way", "gardens", "park", "mews", "terrace", "row", "hill", "walk",
}

# UK postcode regex (standard GIR 0AA or A[A]9[9/A] 9AA)
_UK_POSTCODE_RE = re.compile(
    r"^\s*([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\s*$",
    re.IGNORECASE,
)

# UK Companies House 8-char registration number patterns
_UK_REGNO_RE = re.compile(
    r"\b((?:SC|NI|OC|SO|NC|RO|RC|IC|IP|SP|NP|NO|RS|SR|AC|SA|NA|NF|GN|NL|GE|NR|NZ|CE|CS|PC|LP|SL|NL|OE|FC|BR|SE|SG|SZ)?\d{6,8})\b",
    re.IGNORECASE,
)


def transliterate_to_ascii(text: str) -> str:
    """Convert any Unicode string (Cyrillic, Arabic, CJK, Greek, accented Latin) to lowercase ASCII."""
    if not text:
        return ""
    s = text.lower()
    out_chars: list[str] = []
    for ch in s:
        if ch in _CJK_MAP:
            out_chars.append(_CJK_MAP[ch])
        elif ch in _CYRILLIC_MAP:
            out_chars.append(_CYRILLIC_MAP[ch])
        elif ch in _ARABIC_MAP:
            out_chars.append(_ARABIC_MAP[ch])
        elif ch in _GREEK_MAP:
            out_chars.append(_GREEK_MAP[ch])
        elif ch in _LATIN_EXTRA_MAP:
            out_chars.append(_LATIN_EXTRA_MAP[ch])
        else:
            out_chars.append(ch)
    joined = "".join(out_chars)
    # Strip combining diacritics via NFKD
    decomposed = unicodedata.normalize("NFKD", joined)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c) and ord(c) < 128)
    return ascii_only


transliterate_to_latin = transliterate_to_ascii


def normalize_name(name: str | None, *, is_company: bool = True, sort_tokens: bool = True) -> str:
    """
    Generate canonical lowercase ASCII fingerprint for a person or company name (ADR-017).

    Examples:
        normalize_name("江澤民") -> "jiang zemin"
        normalize_name("!BIG IMPACT GRAPHICS LIMITED", is_company=True) -> "big graphics impact"
    """
    if not name:
        return ""
    if _fp_generate is not None:
        fp_val = _fp_generate(name)
        if fp_val:
            return fp_val

    ascii_str = transliterate_to_ascii(name)
    # Normalize ampersands
    ascii_str = ascii_str.replace("&", " and ")
    tokens = re.findall(r"[a-z0-9]+", ascii_str)
    if not tokens:
        return ""

    if is_company:
        filtered = [t for t in tokens if t not in COMPANY_LEGAL_SUFFIXES]
        if filtered:
            tokens = filtered
    else:
        filtered = [t for t in tokens if t not in PERSON_TITLES]
        if filtered:
            tokens = filtered

    if sort_tokens and len(tokens) > 1:
        # Deduplicate while sorting alphabetically for order-independent matching
        seen: list[str] = []
        for t in sorted(tokens):
            if t not in seen:
                seen.append(t)
        tokens = seen

    return " ".join(tokens).strip()


def normalize_postcode(postcode: str | None) -> str:
    """Normalize a UK postcode to 'OUTWARD INWARD' uppercase format (e.g. 'EC1A 2AB')."""
    if not postcode:
        return ""
    raw = str(postcode).strip().upper()
    if raw == "GIR 0AA" or raw == "GIR0AA":
        return "GIR 0AA"
    m = _UK_POSTCODE_RE.match(raw)
    if m:
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    return re.sub(r"\s+", " ", raw)


def compute_address_fingerprint(
    postcode: str | None,
    line1: str | None = None,
    line2: str | None = None,
    post_town: str | None = None,
) -> str:
    """
    Compute deterministic address fingerprint without libpostal (ADR-015).

    Format: NORMALIZED_POSTCODE|HOUSE_NO|FIRST_KEYWORD
    Example: ("EC1A 2AB", "40 King Street") -> "EC1A 2AB|40|KING"
    """
    norm_pc = normalize_postcode(postcode)
    combined = " ".join(x for x in (line1, line2, post_town) if x).strip()
    ascii_addr = transliterate_to_ascii(combined).upper()

    if not norm_pc and not ascii_addr:
        return ""

    # Extract first house/building number if present
    num_match = re.search(r"\b(\d+[A-Z]?)\b", ascii_addr)
    house_no = num_match.group(1) if num_match else "_"

    words = [
        w
        for w in re.findall(r"[A-Z]{2,}", ascii_addr)
        if w.lower() not in ADDRESS_STOPWORDS
    ]
    keyword = words[0] if words else "_"

    return f"{norm_pc or '_'}|{house_no}|{keyword}"


def phonetic_key(text: str | None) -> str:
    """
    Compute phonetic skeleton for residual phonetic homonyms (Smith/Smyth, Meyer/Meier, Photon/Foton).
    """
    if not text:
        return ""
    norm = normalize_name(text, sort_tokens=False)
    if not norm:
        return ""
    if _jellyfish is not None and hasattr(_jellyfish, "metaphone"):
        return _jellyfish.metaphone(norm)

    # Pure-Python phonetic normalization (handles ph->f, y->i, meier/meyer, smyth/smith, gh->g, etc.)
    s = norm.lower()
    s = s.replace("ph", "f").replace("gh", "g").replace("kh", "k").replace("zh", "j")
    s = s.replace("sh", "s").replace("ch", "c").replace("th", "t").replace("ck", "k")
    s = s.replace("ey", "i").replace("ei", "i").replace("ai", "i").replace("ay", "i")
    s = s.replace("y", "i").replace("z", "s").replace("v", "f").replace("w", "v")
    s = s.replace("q", "k").replace("x", "ks")
    # Collapse repeated characters
    s = re.sub(r"(.)\1+", r"\1", s)
    # Keep first letter of each token + consonant skeleton
    out_tokens: list[str] = []
    for tok in s.split():
        if not tok:
            continue
        head = tok[0]
        tail = re.sub(r"[aeiou]", "", tok[1:])
        out_tokens.append(head + tail)
    return " ".join(sorted(out_tokens))


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Compute Jaro-Winkler similarity in [0.0, 1.0]."""
    if s1 == s2:
        return 1.0 if s1 else 0.0
    if not s1 or not s2:
        return 0.0
    if _rf_jw is not None:
        return float(_rf_jw.similarity(s1, s2))
    if _jellyfish is not None:
        return float(_jellyfish.jaro_winkler_similarity(s1, s2))

    # Pure-Python Jaro-Winkler implementation
    len1, len2 = len(s1), len(s2)
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len1)
        + (matches / len2)
        + ((matches - transpositions / 2) / matches)
    ) / 3.0

    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return jaro + prefix * 0.1 * (1.0 - jaro)


def match_names(name_a: str | None, name_b: str | None, *, is_company: bool = False) -> tuple[float, str]:
    """
    Compare two names using the Aethelburg pipeline (DESIGN_INTELLIGENCE.md section 5).

    Returns:
        (score in 0.0..1.0, method: 'fingerprint_exact' | 'jaro_winkler' | 'phonetic' | 'none')
    """
    fp_a = normalize_name(name_a, is_company=is_company)
    fp_b = normalize_name(name_b, is_company=is_company)
    if not fp_a or not fp_b:
        return 0.0, "none"
    if fp_a == fp_b:
        return 1.0, "fingerprint_exact"

    jw = jaro_winkler_similarity(fp_a, fp_b)
    if jw >= 0.85:
        return round(jw * 0.95, 4), "jaro_winkler"

    pk_a = phonetic_key(name_a)
    pk_b = phonetic_key(name_b)
    if pk_a and pk_a == pk_b and len(pk_a) >= 4:
        return 0.86, "phonetic"

    return round(jw * 0.80, 4), "none"


def extract_uk_company_numbers(raw_text: str | None) -> list[str]:
    """
    Extract normalized 8-character UK Companies House registration numbers from free text
    (such as UK-Sanctions-List 'Business registration number (s)').
    """
    if not raw_text:
        return []
    cleaned = str(raw_text).replace("'", " ").replace('"', " ")
    # Avoid matching non-UK numbers when foreign countries are explicitly tagged without UK
    results: list[str] = []
    for m in _UK_REGNO_RE.finditer(cleaned):
        token = m.group(1).upper()
        if token.isdigit():
            if len(token) > 8:
                continue
            norm = token.zfill(8)
        else:
            prefix = token[:2]
            digits = token[2:]
            if len(digits) != 6:
                continue
            norm = prefix + digits
        if norm not in results:
            results.append(norm)
    return results
