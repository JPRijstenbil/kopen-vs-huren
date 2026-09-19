"""Parameterprofielen: alle instellingen exporteren naar / importeren uit tekst.

Het geëxporteerde bestand is een platte tekst met één parameter per regel in
het formaat:

    waarde_stijging = 4.0     # Woningwaardestijging (%/jr)

Regels die met '#' beginnen zijn commentaar en worden bij importeren genegeerd.
Zo is het bestand goed leesbaar in een teksteditor én terug te importeren.
"""
from __future__ import annotations

from datetime import datetime

# (key, omschrijving, type) — in vaste, logische volgorde
SCHEMA: list[tuple[str, str, str]] = [
    # --- Aannames (macro) ---
    ("waarde_stijging", "Woningwaardestijging (%/jr)", "float"),
    ("beleg_rendement", "Bruto beleggingsrendement (%/jr)", "float"),
    ("huur_verhoging", "Huurverhoging (%/jr)", "float"),
    ("rente", "Hypotheekrente (%)", "float"),
    ("rente_na", "Rente na rentevaste periode (%)", "float"),
    ("inflatie", "Inflatie (%/jr)", "float"),
    # --- Kopen: woning ---
    ("koopprijs", "Koopprijs (€)", "float"),
    ("woz", "Initiële WOZ-waarde (€)", "float"),
    ("eigen_inbreng", "Eigen inbreng (€)", "float"),
    ("woz_apart", "WOZ groeit anders dan marktwaarde (ja/nee)", "bool"),
    ("woz_groei", "WOZ-groei (%/jr)", "float"),
    # --- Financiering ---
    ("hoofdsom", "Hoofdsom hypotheek (€)", "float"),
    ("aflossingstype", "Aflossingstype (annuïtair/lineair/aflossingsvrij)", "str"),
    ("looptijd", "Looptijd (jr)", "int"),
    ("rentevast", "Rentevaste periode (jr)", "int"),
    ("hra", "Hypotheekrenteaftrek (ja/nee)", "bool"),
    # --- Aankoopkosten ---
    ("overdrachtsbelasting", "Overdrachtsbelasting (%)", "float"),
    ("startersvrijstelling", "Startersvrijstelling (ja/nee)", "bool"),
    ("notaris_levering", "Notaris levering (€)", "float"),
    ("notaris_hypotheek", "Notaris hypotheek (€)", "float"),
    ("hypotheekadvies", "Hypotheekadvies (€)", "float"),
    ("taxatie", "Taxatie (€)", "float"),
    ("keuring", "Bouwkundige keuring (€)", "float"),
    ("makelaar_koop", "Aankoopmakelaar (€)", "float"),
    ("nhg", "NHG-premie (%)", "float"),
    # --- Lopende eigenaarskosten ---
    ("onderhoud", "Onderhoud (% van woningwaarde/jr)", "float"),
    ("vve", "VvE-bijdrage (€/mnd)", "float"),
    ("ozb", "OZB (% van WOZ/jr)", "float"),
    ("lokale_heffingen", "Lokale heffingen (€/jr)", "float"),
    ("verzekering", "Opstalverzekering (€/mnd)", "float"),
    ("erfpacht", "Erfpacht canon (€/mnd)", "float"),
    ("overig_eigenaar", "Overige eigenaarskosten (€/mnd)", "float"),
    # --- Verkoop ---
    ("makelaar_verkoop", "Verkoopmakelaar (% van opbrengst)", "float"),
    ("verkoopkorting", "Verkoopkorting op modelwaarde (%)", "float"),
    ("verkoop_overig", "Overige verkoopkosten (€)", "float"),
    # --- Huren ---
    ("huur", "Initiële maandhuur (€)", "float"),
    ("service", "Servicekosten (€/mnd)", "float"),
    ("service_stijging", "Stijging servicekosten (%/jr)", "float"),
    ("huur_overig", "Overige huurderskosten (€/mnd)", "float"),
    # --- Beleggen & fiscaal ---
    ("dividend", "Dividendrendement (%/jr)", "float"),
    ("ter", "Beleggingskosten / TER (%)", "float"),
    ("hra_tarief", "HRA-tarief (marginaal, %)", "float"),
    ("ewf", "Eigenwoningforfait (% van WOZ)", "float"),
    ("wet_hillen", "Wet Hillen afbouwfactor (0-1)", "float"),
    ("b3_tarief", "Box 3 tarief (%)", "float"),
    ("b3_spaar", "Box 3 spaarforfait (%)", "float"),
    ("b3_beleg", "Box 3 beleggingsforfait (%)", "float"),
    ("b3_heffingsvrij", "Heffingsvrij vermogen (€/persoon)", "float"),
    ("b3_partner", "Fiscaal partner (ja/nee)", "bool"),
    ("b3_werkelijk", "Werkelijk rendement i.p.v. fictief (ja/nee)", "bool"),
    # --- Algemeen ---
    ("horizon", "Horizon (jr)", "int"),
    ("startjaar", "Startjaar", "int"),
    ("maandbudget", "Beschikbaar maandbudget (€/mnd)", "float"),
    ("spaargeld", "Bestaand spaargeld (€)", "float"),
    ("beleg_start", "Bestaand beleggingsvermogen (€)", "float"),
    ("liquide", "Netto vermogen kopen: 'Alsof nu verkocht' of 'Woning in bezit'", "str"),
    ("vandaag", "Toon in euro's van vandaag (ja/nee)", "bool"),
    ("vergelijk_jaar", "Vergelijk na X jaar", "int"),
]

GROUPEN = [
    "Aannames (macro)",
    "Kopen: woning",
    "Financiering",
    "Aankoopkosten",
    "Lopende eigenaarskosten",
    "Verkoop",
    "Huren",
    "Beleggen & fiscaal",
    "Algemeen",
]


def format_export(waarden: dict[str, object]) -> str:
    """Bouw een zelfdocumenterend tekstprofiel uit een key->waarde dict."""
    lines = [
        "# Kopen vs Huren — parameterprofiel",
        f"# Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "#",
        "# Formaat: naam = waarde   (regels die met '#' beginnen zijn commentaar)",
        "# Pas waarden aan en importeer dit bestand terug om alle parameters te laden.",
        "#",
    ]
    current_group = None
    for key, label, typ in SCHEMA:
        if key not in waarden:
            continue
        # groepsheader (op basis van volgorde in GROUPEN)
        grp = _group_for(key)
        if grp != current_group:
            current_group = grp
            lines.append("")
            lines.append(f"### {grp} ###")
        val = waarden[key]
        if typ == "bool":
            val = "ja" if val else "nee"
        elif isinstance(val, float):
            val = round(val, 6)
        line = f"{key} = {val}"
        lines.append(f"{line:<42} # {label}")
    return "\n".join(lines)


def _group_for(key: str) -> str:
    idx = [k for (k, *_rest) in SCHEMA].index(key)
    groups = {
        "Aannames (macro)": 0,
        "Kopen: woning": 0,
    }
    # eenvoudige mapping via volgorde in SCHEMA
    if idx < 6:
        return GROUPEN[0]  # Aannames
    if idx < 11:
        return GROUPEN[1]  # Kopen: woning
    if idx < 16:
        return GROUPEN[2]  # Financiering
    if idx < 25:
        return GROUPEN[3]  # Aankoopkosten
    if idx < 32:
        return GROUPEN[4]  # Eigenaarskosten
    if idx < 35:
        return GROUPEN[5]  # Verkoop
    if idx < 39:
        return GROUPEN[6]  # Huren
    if idx < 51:
        return GROUPEN[7]  # Beleggen & fiscaal
    return GROUPEN[8]  # Algemeen


def parse_import(text: str) -> dict[str, object]:
    """Parse een tekstprofiel terug naar een key->waarde dict."""
    schema_map = {k: (label, typ) for (k, label, typ) in SCHEMA}
    result: dict[str, object] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=")[0].strip()
        val = line.split("=", 1)[1].split("#")[0].strip()
        if key not in schema_map:
            continue
        _, typ = schema_map[key]
        result[key] = _convert(val, typ)
    return result


def _convert(val: str, typ: str):
    if typ == "bool":
        return val.strip().lower() in ("ja", "true", "1", "yes", "y")
    if typ == "int":
        try:
            return int(float(val.replace(",", ".")))
        except ValueError:
            return 0
    if typ == "float":
        try:
            return float(val.replace(",", "."))
        except ValueError:
            return 0.0
    return val.strip()


def waarden_naar_session(waarden: dict[str, object]) -> dict[str, object]:
    """Vertaal een profiel-dict naar Streamlit widget-keys.

    De geretourneerde mapping past de waarden aan naar wat de widgets verwachten
    (bijv. de 'liquide'-radio en het aflossingstype).
    """
    mapping = dict(waarden)
    # liquide-radio vertaalt 'Alsof'/'Bezit'/'liquide' naar de exacte opties
    if "liquide" in mapping:
        lq = str(mapping["liquide"]).strip().lower()
        mapping["liquide"] = "Alsof nu verkocht (liquide)" if lq.startswith(("alsof", "liquide", "verkocht", "ja")) \
            else "Woning in bezit"
    return mapping
