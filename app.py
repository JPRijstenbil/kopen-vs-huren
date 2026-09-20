"""Kopen vs huren — Nederlands vermogensdashboard (Streamlit).

Run:  streamlit run app.py   (dan open http://localhost:8501)
Mobiel: open <laptop-ip>:8501 in de browser op je telefoon.
Elke parameter heeft een help-tooltip (het "?"-icoon) die toont bij hover.
"""
from __future__ import annotations

import copy

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from simulator import Aflossingstype, break_even_jaar, simuleer
from simulator.config import (
    Aankoopkosten,
    AlgemeneConfig,
    BeleggingsConfig,
    Eigenaarskosten,
    FiscaleConfig,
    HuurConfig,
    LeningdeelConfig,
    Scenario,
    Verkoopkosten,
    WoningConfig,
)
from simulator.plotting import (
    GREEN,
    bestemming_geld_figuur,
    heatmap_figuur,
    net_vermogen_figuur,
    tornado_figuur,
)
from simulator.presets import format_export, parse_import, waarden_naar_session
from simulator.tax import Box3Regels, Box3Stelsel, EigenWoningFiscaal

st.set_page_config(
    page_title="Kopen vs Huren — Nederland",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    :root { --brand:#155eef; --ink:#172b4d; --muted:#5d6b82; }
    .block-container { max-width: 1180px; padding-top: 1rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.025em; }
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff 0%, #f7f9fc 100%);
        border: 1px solid #e4e9f2; border-radius: 14px; padding: 14px 16px;
        box-shadow: 0 3px 14px rgba(23,43,77,.05);
    }
    div[data-testid="stMetricLabel"] { color: var(--muted); }
    div[data-testid="stMetricValue"] { color: var(--ink); font-size: 1.55rem; }
    .hero { padding: 1rem 1.25rem; border: 1px solid #dbe5ff; border-radius: 18px;
        background: linear-gradient(135deg,#f5f8ff 0%,#fff 70%); margin-bottom: .55rem; }
    .hero-kicker { color: var(--brand); font-weight: 700; font-size:.82rem; letter-spacing:.08em; }
    .hero p { color:var(--muted); margin:.4rem 0 0; max-width:820px; }
    @media (max-width: 640px) {
        .block-container { padding: .55rem .7rem 2rem; }
        h1 { font-size: 1.8rem !important; }
        .hero { padding: .8rem .9rem; border-radius: 14px; }
        div[data-testid="stMetric"] { padding: 11px 12px; }
        div[data-testid="stMetricValue"] { font-size: 1.25rem; }
        div[data-testid="stPlotlyChart"] { margin-left:-.5rem; margin-right:-.5rem; }
    }
</style>
""", unsafe_allow_html=True)


def geld(x: float) -> str:
    neg = x < 0
    s = f"{abs(x):,.0f}".replace(",", ".")
    return f"-€{s}" if neg else f"€{s}"


AANNAMES = {
    "Pessimistisch": dict(waarde=2.0, beleg=4.0, huur=4.5, rente=5.4, rente_na=6.0, inflatie=2.5),
    "Basis": dict(waarde=4.0, beleg=6.0, huur=3.0, rente=4.2, rente_na=5.0, inflatie=2.0),
    "Optimistisch": dict(waarde=6.0, beleg=8.0, huur=1.5, rente=3.5, rente_na=4.0, inflatie=1.5),
}

# ---------------------------------------------------------------------------
st.markdown("""
<div class="hero">
  <div class="hero-kicker">NEDERLAND · VERMOGENSSIMULATIE 2026</div>
  <h1 style="margin:.2rem 0 0">Kopen of huren?</h1>
  <p>Vergelijk het netto vermogen bij een gelijk startvermogen en maandbudget.
  Inclusief hypotheek, onderhoud, transactiekosten, Box 1 en Box 3.</p>
</div>
""", unsafe_allow_html=True)
st.caption("Indicatief rekenmodel — geen financieel of fiscaal advies. Open Parameters om je eigen situatie in te vullen.")

# ===========================================================================
# PARAMETERS
# ===========================================================================
with st.expander("⚙️ Parameters — pas aan naar wens", expanded=False):
    tab_a, tab_k, tab_h, tab_f, tab_g, tab_p = st.tabs(
        ["Aannames", "Kopen", "Huren", "Beleggen & Fiscaal", "Algemeen", "Profiel"]
    )

    # ---- Aannames ----
    with tab_a:
        c1, c2 = st.columns(2)
        scen_keuze = c1.radio(
            "Aannames-scenario",
            ["Basis", "Pessimistisch", "Optimistisch", "Eigen waarden"],
            horizontal=True, key="scen_keuze",
            help="Kies een vooraf ingesteld scenario of start zelf met eigen waarden.",
        )
        if scen_keuze == "Eigen waarden":
            a = {
                "waarde": c2.slider(
                    "Woningwaardestijging (%/jr)", 0.0, 10.0, 4.0, 0.1, key="waarde_stijging",
                    help="Verwachte jaarlijkse stijging van de marktwaarde van je woning. Deze waardestijging is in Nederland onbelast (groot voordeel van kopen)."),
                "beleg": c2.slider(
                    "Koersrendement beleggingen (%/jr)", -10.0, 15.0, 6.0, 0.1, key="beleg_rendement",
                    help="Verwachte jaarlijkse koersstijging vóór TER en Box 3. Dividend stel je apart in."),
                "huur": c2.slider(
                    "Huurverhoging (%/jr)", 0.0, 8.0, 3.0, 0.1, key="huur_verhoging",
                    help="Jaarlijkse stijging van de huurprijs. Huur loopt op, terwijl een hypotheeklast vastelast/afnemend is."),
                "rente": c2.slider(
                    "Hypotheekrente (%)", 1.0, 8.0, 4.2, 0.1, key="rente",
                    help="Effectieve jaarrente op de hypotheek (%)."),
                "rente_na": c2.slider(
                    "Rente na rentevaste periode (%)", 1.0, 9.0, 5.0, 0.1, key="rente_na",
                    help="De rente die geldt na afloop van de rentevaste periode."),
                "inflatie": c2.slider(
                    "Inflatie (%/jr)", 0.0, 5.0, 2.0, 0.1, key="inflatie",
                    help="Algemene prijsstijging. Indexeert onderhoud, verzekeringen, lokale heffingen en servicekosten over de tijd."),
            }
        else:
            a = AANNAMES[scen_keuze]
            c2.write("Vaste aannames voor dit scenario:")
            c2.markdown(
                f"- Woningwaardestijging: **{a['waarde']}%**\n"
                f"- Beleggingsrendement: **{a['beleg']}%**\n"
                f"- Huurverhoging: **{a['huur']}%**\n"
                f"- Hypotheekrente: **{a['rente']}%** → **{a['rente_na']}%** na rentevast\n"
                f"- Inflatie: **{a['inflatie']}%**"
            )

    # ---- Kopen ----
    with tab_k:
        k1, k2, k3 = st.columns(3)
        p_koopprijs = k1.number_input(
            "Koopprijs (€)", 10000.0, 5_000_000.0, 450000.0, 5000.0, key="koopprijs",
            help="Aankoopprijs van de woning (de marktwaarde).")
        p_woz = k1.number_input(
            "WOZ-waarde (€)", 10000.0, 5_000_000.0, 400000.0, 5000.0, key="woz",
            help="WOZ-waarde bij aankoop; basis voor OZB-belasting en het eigenwoningforfait (Box 1).")
        p_inbreng = k1.number_input(
            "Eigen inbreng (€)", 0.0, 5_000_000.0, 100000.0, 5000.0, key="eigen_inbreng",
            help="Eigen geld dat je in de woning stopt (= koopprijs − hypotheek). Wordt direct woning-equity (vermogen). Inbreng + hoofdsom moet ≈ koopprijs zijn.")
        p_woz_apart = k1.checkbox(
            "WOZ groeit anders dan marktwaarde", False, key="woz_apart",
            help="Zet aan als de WOZ-groei los van de marktwaarde-groei moet lopen.")
        p_woz_groei = k1.slider(
            "WOZ-groei (%/jr)", 0.0, 10.0, a["waarde"], 0.1, disabled=not p_woz_apart, key="woz_groei",
            help="Jaarlijkse groei van de WOZ-waarde (werkt door op OZB en eigenwoningforfait).")

        st.markdown("**Leningdeel (1 in deze versie)**")
        p_hoofdsom = k2.number_input(
            "Hoofdsom hypotheek (€)", 0.0, 5_000_000.0, 350000.0, 5000.0, key="hoofdsom",
            help="Het bedrag dat je leent (hoofdsom). Meestal koopprijs − eigen inbreng.")
        p_type = k2.selectbox(
            "Aflossingstype", [t.value for t in Aflossingstype], key="aflossingstype",
            help="annuïtair = vaste maandlast (rente+aflossing); lineair = vaste aflossing, last daalt; aflossingsvrij = alleen rente, schuld blijft gelijk.")
        p_looptijd = k2.slider(
            "Looptijd (jr)", 1, 40, 30, key="looptijd",
            help="Aantal jaar om de hypotheek af te lossen.")
        p_rentevast = k2.slider(
            "Rentevaste periode (jr)", 0, 40, 10, key="rentevast",
            help="Aantal jaar dat de rente vaststaat. Daarna geldt 'rente na rentevaste periode'.")
        p_hra = k2.checkbox(
            "Hypotheekrenteaftrek van toepassing", True, key="hra",
            help="Of je op dit leningdeel hypotheekrenteaftrek toepast. Nieuwe aflossingsvrije delen geven geen automatisch recht op HRA.")

        st.markdown("**Aankoopkosten**")
        p_odt = k3.slider(
            "Overdrachtsbelasting (%)", 0.0, 12.0, 2.0, 0.1, key="overdrachtsbelasting",
            help="Belasting bij aankoop: 2% voor bewoners, 0% starters, 10,4% belegger of tweede woning.")
        p_starter = k3.checkbox(
            "Startersvrijstelling (0%)", False, key="startersvrijstelling",
            help="2026: eenmalig, 18 t/m 34 jaar, zelf bewonen en woningwaarde maximaal €555.000.")
        p_not_levering = k3.number_input(
            "Notaris levering (€)", 0.0, 5000.0, 750.0, 50.0, key="notaris_levering",
            help="Kosten van de transportakte (eigendomsoverdracht).")
        p_not_hyp = k3.number_input(
            "Notaris hypotheek (€)", 0.0, 5000.0, 500.0, 50.0, key="notaris_hypotheek",
            help="Kosten van het verlijden van de hypotheekakte.")
        p_advies = k3.number_input(
            "Hypotheekadvies (€)", 0.0, 10000.0, 2000.0, 100.0, key="hypotheekadvies",
            help="Kosten van hypotheekadvies.")
        p_tax = k3.number_input(
            "Taxatie (€)", 0.0, 5000.0, 550.0, 50.0, key="taxatie",
            help="Kosten van een taxatierapport (vaak verplicht voor de hypotheek).")
        p_keuring = k3.number_input(
            "Bouwkundige keuring (€)", 0.0, 5000.0, 400.0, 50.0, key="keuring",
            help="Kosten van een bouwtechnische keuring (optioneel).")
        p_makelaar_koop = k3.number_input(
            "Aankoopmakelaar (€)", 0.0, 10000.0, 0.0, 100.0, key="makelaar_koop",
            help="Kosten van een aankoopmakelaar (optioneel).")
        p_nhg = k3.slider(
            "NHG-premie (%)", 0.0, 1.5, 0.0, 0.1, key="nhg",
            help="2026: 0,4% borgtochtprovisie; NHG-grens €470.000 (zonder extra verduurzamingsruimte).")

        k4, k5 = st.columns(2)
        st.markdown("**Lopende eigenaarskosten**")
        p_onderhoud_pct = k4.slider(
            "Onderhoud (% van woningwaarde/jr)", 0.0, 3.0, 1.0, 0.1, key="onderhoud",
            help="Gemiddeld jaarlijks onderhoud (dak, CV, schilderwerk); ~1% van de woningwaarde per jaar is een gangbare regel. Voorkom dubbeltelling met de VvE-bijdrage.")
        p_vve = k4.number_input(
            "VvE-bijdrage (€/mnd)", 0.0, 2000.0, 0.0, 10.0, key="vve",
            help="Maandelijkse VvE-bijdrage. Als de VvE het onderhoud dekt, voeg de onderhoudpost niet dubbel toe.")
        p_ozb = k4.slider(
            "OZB (% van WOZ/jr)", 0.0, 0.5, 0.05, 0.01, key="ozb",
            help="Onroerendezaakbelasting, als % van de WOZ per jaar.")
        p_lokaal = k4.number_input(
            "Lokale heffingen (€/jr)", 0.0, 3000.0, 400.0, 25.0, key="lokale_heffingen",
            help="Gemeentelijke heffingen (riool, afval e.d.) per jaar. Indexeert met inflatie.")
        p_verzekering = k5.number_input(
            "Opstalverzekering (€/mnd)", 0.0, 500.0, 35.0, 5.0, key="verzekering",
            help="Maandelijkse opstalverzekering. Indexeert met inflatie.")
        p_erfpacht = k5.number_input(
            "Erfpacht canon (€/mnd)", 0.0, 2000.0, 0.0, 10.0, key="erfpacht",
            help="Maandelijkse erfpachtcanon (bij grond in erfpacht). Indexeert met inflatie.")
        p_overig_eig = k5.number_input(
            "Overige eigenaarskosten (€/mnd)", 0.0, 1000.0, 0.0, 10.0, key="overig_eigenaar",
            help="Vaste, overige maandelijkse eigenaarskosten die niet elders zijn meegeteld.")

        st.markdown("**Verkoop**")
        k6, k7 = st.columns(2)
        p_makelaar_verkoop = k6.slider(
            "Verkoopmakelaar (% van opbrengst)", 0.0, 5.0, 1.5, 0.1, key="makelaar_verkoop",
            help="Kosten van de verkoopmakelaar, als % van de verkoopopbrengst.")
        p_korting = k7.slider(
            "Verkoopkorting op modelwaarde (%)", 0.0, 10.0, 0.0, 0.5, key="verkoopkorting",
            help="Korting op de modelmatig gerekende marktwaarde; realistischer dan de getaxeerde opbrengst.")
        p_verkoop_overig = k7.number_input(
            "Overige verkoopkosten (€)", 0.0, 5000.0, 0.0, 50.0, key="verkoop_overig",
            help="Overige kosten bij verkoop (bijv. eindafrekening).")

    # ---- Huren ----
    with tab_h:
        h1, h2 = st.columns(2)
        p_huur = h1.number_input(
            "Initiële maandhuur (€)", 0.0, 5000.0, 1500.0, 25.0, key="huur",
            help="Initiële maandhuur. Stijgt jaarlijks met de huurverhoging.")
        p_service = h2.number_input(
            "Servicekosten (€/mnd)", 0.0, 1000.0, 100.0, 10.0, key="service",
            help="Maandelijkse servicekosten van de huurwoning.")
        p_service_stijging = h2.slider(
            "Stijging servicekosten (%/jr)", 0.0, 8.0, 2.5, 0.1, key="service_stijging",
            help="Jaarlijkse stijging van de servicekosten.")
        p_huur_overig = h2.number_input(
            "Overige huurderskosten (€/mnd)", 0.0, 1000.0, 0.0, 10.0, key="huur_overig",
            help="Vaste overige huurderskosten per maand.")

    # ---- Beleggen & Fiscaal ----
    with tab_f:
        b1, b2, b3 = st.columns(3)
        p_dividend = b1.slider(
            "Dividendrendement (%/jr)", 0.0, 5.0, 0.0, 0.1, key="dividend",
            help="Verwacht jaarlijks dividend / uitkering op je beleggingen (naast het koersrendement).")
        p_spaarrente = b1.slider(
            "Spaarrente (%/jr)", 0.0, 6.0, 1.5, 0.1, key="spaarrente",
            help="Rente op het deel dat als spaargeld/cash wordt aangehouden.")
        p_ter = b1.slider(
            "Beleggingskosten / TER (%)", 0.0, 2.0, 0.3, 0.05, key="ter",
            help="Total Expense Ratio: jaarlijkse kosten van het fonds/ETF, als % van je belegde vermogen.")
        p_hra_tarief = b2.slider(
            "HRA-tarief (effectief, %)", 20.0, 50.0, 37.56, 0.01, key="hra_tarief",
            help="In 2026 is de aftrek voor hoge inkomens gemaximeerd op 37,56%; het werkelijke effect hangt af van inkomen.")
        p_ewf = b2.slider(
            "Eigenwoningforfait (% van WOZ)", 0.0, 1.5, 0.35, 0.01, key="ewf",
            help="Eigenwoningforfait: een bijtelling (inkomen) op je woning. ~0.35% van WOZ voor gewone woningen; hoger boven een WOZ-drempel.")
        p_wet_hillen = b2.slider(
            "Wet Hillen-factor in startjaar", 0.0, 1.0, 0.71867, 0.001, key="wet_hillen",
            help="In 2026 resteert 71,867% aftrek. Het model verlaagt deze factor daarna jaarlijks met 4,8 procentpunt.")
        p_b3_tarief = b3.slider(
            "Box 3 tarief (%)", 0.0, 50.0, 36.0, 1.0, key="b3_tarief",
            help="Belastingtarief in Box 3 (sparen & beleggen), geheven over het (fictieve) rendement.")
        p_b3_spaar = b3.slider(
            "Spaarforfait (%)", 0.0, 5.0, 1.28, 0.01, key="b3_spaar",
            help="Voorlopig forfait banktegoeden 2026: 1,28%; definitief begin 2027.")
        p_b3_beleg = b3.slider(
            "Beleggingsforfait (%)", 0.0, 10.0, 6.00, 0.01, key="b3_beleg",
            help="Vast forfait beleggingen en overige bezittingen in 2026: 6,00%.")
        p_b3_vrij = b3.number_input(
            "Heffingsvrij vermogen (€/persoon)", 0.0, 300000.0, 59357.0, 100.0, key="b3_heffingsvrij",
            help="Vrijgesteld vermogen per persoon in Box 3, vóór dit belast wordt.")
        p_b3_partner = b3.checkbox(
            "Fiscaal partner (2x heffingsvrij)", False, key="b3_partner",
            help="Met een fiscaal partner wordt het heffingsvrije vermogen verdubbeld.")
        p_b3_werkelijk = b3.checkbox(
            "Pas tegenbewijs toe indien gunstiger", True, key="b3_werkelijk",
            help="Gebruikt jaarlijks de laagste heffing van fictief en werkelijk rendement. Bij werkelijk rendement geldt geen vrijstelling of verliesverrekening tussen jaren.")

    # ---- Algemeen ----
    with tab_g:
        g1, g2, g3 = st.columns(3)
        p_horizon = g1.slider(
            "Horizon (jr)", 1, 40, 30, key="horizon",
            help="Aantal jaar dat je wilt simuleren (netto vermogen door de tijd).")
        p_startjaar = g1.number_input(
            "Startjaar", 2000, 2050, 2026, key="startjaar",
            help="Startjaar van de simulatie. Bepaalt welke fiscale regels worden toegepast.")
        p_budget = g2.number_input(
            "Beschikbaar maandbudget (€)", 0.0, 20000.0, 2500.0, 100.0, key="maandbudget",
            help="Netto bedrag dat je per maand beschikbaar hebt voor wonen + beleggen, gelijk in beide scenario's. Wat na de woonlast overblijft, wordt belegd.")
        p_spaar = g2.number_input(
            "Bestaand spaargeld (€)", 0.0, 5_000_000.0, 100000.0, 5000.0, key="spaargeld",
            help="Beschikbaar spaargeld. Bij kopen wordt hieruit de eigen inbreng + aankoopkosten betaald; de rest blijft belegd. Bij huren wordt alles belegd.")
        p_beleg_start = g2.number_input(
            "Bestaand beleggingsvermogen (€)", 0.0, 5_000_000.0, 50000.0, 5000.0, key="beleg_start",
            help="Al aanwezig belegd vermogen naast het spaargeld.")
        st.markdown("**Weergave**")
        p_liquide = g3.radio(
            "Netto vermogen kopen:", ["Alsof nu verkocht (liquide)", "Woning in bezit"],
            horizontal=True, key="liquide",
            help="'Alsof nu verkocht' trekt nu de verkoopkosten af (liquide positie). 'Woning in bezit' telt de volle waarde zonder te verkopen.")
        p_vandaag = g3.checkbox(
            "Toon bedragen in euro's van vandaag (inflatiegecorrigeerd)", False, key="vandaag",
            help="Deelt alle bedragen door de opgelopen inflatie, zodat je ze in koopkracht van vandaag ziet.")
        p_vergelijk = g3.slider(
            "Vergelijk na X jaar", 1, p_horizon, min(10, p_horizon), key="vergelijk_jaar",
            help="Op welk jaar na de start je de resultaten (KPI's + break-even) bekijkt.")

# ===========================================================================
# PROFIEL (copy-paste)
# ===========================================================================
def _huidige_waarden() -> dict:
    w = {
        "waarde_stijging": a["waarde"], "beleg_rendement": a["beleg"],
        "huur_verhoging": a["huur"], "rente": a["rente"],
        "rente_na": a["rente_na"], "inflatie": a["inflatie"],
        "koopprijs": p_koopprijs, "woz": p_woz, "eigen_inbreng": p_inbreng,
        "woz_apart": p_woz_apart, "woz_groei": p_woz_groei,
        "hoofdsom": p_hoofdsom, "aflossingstype": p_type,
        "looptijd": p_looptijd, "rentevast": p_rentevast, "hra": p_hra,
        "overdrachtsbelasting": p_odt, "startersvrijstelling": p_starter,
        "notaris_levering": p_not_levering, "notaris_hypotheek": p_not_hyp,
        "hypotheekadvies": p_advies, "taxatie": p_tax, "keuring": p_keuring,
        "makelaar_koop": p_makelaar_koop, "nhg": p_nhg,
        "onderhoud": p_onderhoud_pct, "vve": p_vve, "ozb": p_ozb,
        "lokale_heffingen": p_lokaal, "verzekering": p_verzekering,
        "erfpacht": p_erfpacht, "overig_eigenaar": p_overig_eig,
        "makelaar_verkoop": p_makelaar_verkoop, "verkoopkorting": p_korting,
        "verkoop_overig": p_verkoop_overig,
        "huur": p_huur, "service": p_service,
        "service_stijging": p_service_stijging, "huur_overig": p_huur_overig,
        "dividend": p_dividend, "spaarrente": p_spaarrente, "ter": p_ter, "hra_tarief": p_hra_tarief,
        "ewf": p_ewf, "wet_hillen": p_wet_hillen,
        "b3_tarief": p_b3_tarief, "b3_spaar": p_b3_spaar, "b3_beleg": p_b3_beleg,
        "b3_heffingsvrij": p_b3_vrij, "b3_partner": p_b3_partner,
        "b3_werkelijk": p_b3_werkelijk,
        "horizon": p_horizon, "startjaar": p_startjaar,
        "maandbudget": p_budget, "spaargeld": p_spaar, "beleg_start": p_beleg_start,
        "liquide": p_liquide, "vandaag": p_vandaag, "vergelijk_jaar": p_vergelijk,
    }
    return w


def _toepassen():
    tekst = st.session_state.get("plak_veld", "").strip()
    if not tekst:
        st.session_state["import_status"] = ("error", "Plak eerst een profiel in het veld.")
        return
    profiel = parse_import(tekst)
    if not profiel:
        st.session_state["import_status"] = ("error", "Geen geldige parameters gevonden. Controleer het formaat (naam = waarde).")
        return
    st.session_state["scen_keuze"] = "Eigen waarden"
    mapping = waarden_naar_session(profiel)
    for key, val in mapping.items():
        st.session_state[key] = val
    st.session_state["import_status"] = ("ok", f"{len(mapping)} parameters toegepast.")


with tab_p:
    st.markdown("**📋 Alle instellingen kopiëren**")
    st.caption("Druk op het kopieer-icoon rechtsboven in het tekstvak om alles te kopiëren.")
    st.code(format_export(_huidige_waarden()), language=None)
    st.divider()
    st.markdown("**📥 Instellingen plakken & toepassen**")
    st.caption("Plak een eerder gekopieerd profiel hieronder en druk op 'Toepassen'. Dit zet alle parameters in één keer.")
    st.text_area("Geplakte parameters", "", height=220, key="plak_veld",
                 help="Plak hier een eerder gekopieerd parameterprofiel.")
    st.button("✅ Toepassen", on_click=_toepassen)
    _status = st.session_state.pop("import_status", None)
    if _status:
        if _status[0] == "ok":
            st.success(_status[1])
        else:
            st.error(_status[1])

# ===========================================================================
# Scenario bouwen
# ===========================================================================
afl_type = Aflossingstype(p_type)

scenario = Scenario(
    naam=scen_keuze,
    woning=WoningConfig(
        koopprijs=p_koopprijs,
        initiele_woz=p_woz,
        waarde_groei_pct=a["waarde"],
        woz_groei_pct=p_woz_groei if p_woz_apart else a["waarde"],
        erfpacht_canon_maand=p_erfpacht,
        erfpacht_stijging_pct=a["inflatie"],
    ),
    leningdelen=[
        LeningdeelConfig(
            hoofdsom=p_hoofdsom,
            rente_pct=a["rente"],
            aflossingstype=afl_type,
            looptijd_jaar=p_looptijd,
            rentevaste_periode_jaar=p_rentevast if p_rentevast > 0 else None,
            rente_na_rentevast_pct=a["rente_na"],
            hra=p_hra,
        )
    ],
    aankoopkosten=Aankoopkosten(
        overdrachtsbelasting_pct=p_odt,
        startersvrijstelling=p_starter,
        notaris_levering=p_not_levering,
        notaris_hypotheek=p_not_hyp,
        hypotheekadvies=p_advies,
        taxatie=p_tax,
        bouwkundige_keuring=p_keuring,
        aankoopmakelaar=p_makelaar_koop,
        nhg_premie_pct=p_nhg,
        overige=0.0,
        fiscaal_aftrekbaar_deel_pct=100.0,
    ),
    eigenaarskosten=Eigenaarskosten(
        onderhoud_pct_waarde=p_onderhoud_pct,
        onderhoud_vast_jaar=None,
        vve_maand=p_vve,
        ozb_pct_woz=p_ozb,
        lokale_heffingen_jaar=p_lokaal,
        opstalverzekering_maand=p_verzekering,
        erfpacht_maand=0.0,
        overige_maand=p_overig_eig,
    ),
    verkoopkosten=Verkoopkosten(
        makelaar_pct=p_makelaar_verkoop,
        makelaar_vast=None,
        overige=p_verkoop_overig,
        verkoopkorting_pct=p_korting,
    ),
    huur=HuurConfig(
        initiele_maandhuur=p_huur,
        huurverhoging_pct=a["huur"],
        servicekosten_maand=p_service,
        servicekosten_stijging_pct=p_service_stijging,
        overige_maand=p_huur_overig,
    ),
    belegging=BeleggingsConfig(
        bruto_rendement_pct=a["beleg"],
        koersrendement_pct=None,
        dividend_pct=p_dividend,
        ter_pct=p_ter,
        spaarrente_pct=p_spaarrente,
    ),
    fiscaal=FiscaleConfig(
        eigenwoning=EigenWoningFiscaal(
            hra_tarief_pct=p_hra_tarief,
            box1_marginaal_tarief_pct=p_hra_tarief,
            ewf_schijven=[
                (0.0, 0.0), (12_500.0, 0.10), (25_000.0, 0.20),
                (50_000.0, 0.25), (75_000.0, p_ewf),
            ],
            ewf_hoge_grens=1_350_000.0,
            ewf_hoog_pct=2.35,
            wet_hillen_afbouw_pct=p_wet_hillen,
            wet_hillen_basisjaar=p_startjaar,
            wet_hillen_afbouw_per_jaar=0.048,
        ),
        box3=Box3Stelsel([
            Box3Regels(
                jaar_vanaf=p_startjaar, jaar_tot=None,
                tarief_pct=p_b3_tarief,
                spaarforfait_pct=p_b3_spaar,
                beleggingsforfait_pct=p_b3_beleg,
                heffingsvrij_per_persoon=p_b3_vrij,
                fiscaal_partner=p_b3_partner,
            )]),
        box3_werkelijk_rendement=p_b3_werkelijk,
    ),
    algemeen=AlgemeneConfig(
        start_jaar=p_startjaar,
        horizon_jaar=p_horizon,
        inflatie_pct=a["inflatie"],
        maandbudget=p_budget,
        bestaand_spaargeld=p_spaar,
        bestaand_belegging=p_beleg_start,
        eigen_inbreng=p_inbreng,
        liquide_verkoop_waarde=True,
    ),
)

som = p_inbreng + p_hoofdsom
if abs(som - p_koopprijs) > 0.01:
    st.error(
        f"Eigen inbreng ({geld(p_inbreng)}) + hoofdsom ({geld(p_hoofdsom)}) = {geld(som)}, "
        f"maar de koopprijs is {geld(p_koopprijs)}. Corrigeer de financiering om resultaten te tonen."
    )
    st.stop()

hypotheekbedrag = sum(ld.hoofdsom for ld in scenario.leningdelen)
aankoop_indic = p_koopprijs * (0.0 if p_starter else p_odt / 100.0) + p_not_levering + p_not_hyp + p_advies + p_tax + p_keuring + p_makelaar_koop + hypotheekbedrag * p_nhg / 100.0
start_vermogen = p_spaar + p_beleg_start
if p_inbreng + aankoop_indic > start_vermogen:
    st.error(
        f"Eigen inbreng ({geld(p_inbreng)}) + aankoopkosten (~{geld(aankoop_indic)}) "
        f"overschrijden je startvermogen ({geld(start_vermogen)}). Corrigeer dit om resultaten te tonen."
    )
    st.stop()
if p_starter and p_koopprijs > 555_000:
    st.error("Startersvrijstelling 2026 is niet geldig boven een woningwaarde van €555.000.")
    st.stop()
if p_hra and afl_type == Aflossingstype.AFLOSSINGSVRIJ:
    st.warning("Een nieuw aflossingsvrij leningdeel geeft normaal geen HRA. Laat dit alleen aan bij overgangsrecht van een bestaande schuld.")
if p_hra and (p_looptijd > 30 or afl_type == Aflossingstype.AFLOSSINGSVRIJ):
    st.warning("Voor een nieuwe eigenwoningschuld vanaf 2013 vereist HRA minimaal annuïtair/lineair aflossen binnen 30 jaar.")
if p_nhg > 0 and p_koopprijs > 470_000:
    st.warning("De standaard NHG-kostengrens is in 2026 €470.000; met energiebesparende voorzieningen kan een hogere grens gelden.")

# ===========================================================================
# Simuleren
# ===========================================================================
try:
    resultaat = simuleer(scenario)
except ValueError as exc:
    st.error(f"Scenario is financieel niet haalbaar: {exc}")
    st.stop()
liquide = p_liquide.startswith("Alsof")
breakeven = break_even_jaar(resultaat, liquide=liquide)
limit = p_vergelijk * 12
inflatie_cum = resultaat.inflatie
jaar_labels = np.array(
    [scenario.algemeen.start_jaar + i // 12 for i in range(0, len(resultaat.maanden), 12)]
)

st.caption(f"RESULTAAT NA {p_vergelijk} JAAR")

netto_k = resultaat.netto_kopen_liquide[limit - 1] if liquide else resultaat.netto_kopen_bezit[limit - 1]
netto_h = resultaat.netto_huren[limit - 1]
if p_vandaag:
    factor = inflatie_cum[limit - 1]
    netto_k_v = netto_k / factor
    netto_h_v = netto_h / factor
    equity_v = resultaat.equity[limit - 1] / factor
    schuld_v = resultaat.schuld[limit - 1] / factor
    beleg_k_v = resultaat.belegging_kopen[limit - 1] / factor
    beleg_h_v = resultaat.belegging_huren[limit - 1] / factor
else:
    netto_k_v, netto_h_v = netto_k, netto_h
    equity_v = resultaat.equity[limit - 1]
    schuld_v = resultaat.schuld[limit - 1]
    beleg_k_v = resultaat.belegging_kopen[limit - 1]
    beleg_h_v = resultaat.belegging_huren[limit - 1]
diff = netto_k_v - netto_h_v

winnaar = "Kopen" if diff > 0 else "Huren" if diff < 0 else "Gelijk"
st.markdown(f"### {winnaar} ligt na {p_vergelijk} jaar **{geld(abs(diff))}** voor")
kol = st.columns(3)
kol[0].metric("Netto vermogen · kopen", geld(netto_k_v))
kol[1].metric("Netto vermogen · huren", geld(netto_h_v))
kol[2].metric("Verschil kopen − huren", geld(diff))
kol2 = st.columns(3)
kol2[0].metric("Break-even", f"na {breakeven:g} jaar" if breakeven is not None else "niet binnen horizon")
kol2[1].metric("Woning-equity", geld(equity_v))
kol2[2].metric("Resterende hypotheek", geld(schuld_v))
st.markdown(
    f"Beleggingen: kopen **{geld(beleg_k_v)}** · huren **{geld(beleg_h_v)}**."
    + (" In euro's van vandaag." if p_vandaag else " In nominale euro's.")
)

fig_hoofd = net_vermogen_figuur(resultaat, jaar_labels, liquide, breakeven, p_vergelijk, p_vandaag, inflatie_cum)
st.plotly_chart(fig_hoofd, width="stretch")

fig_k, fig_h = bestemming_geld_figuur(resultaat, limit)
if p_vandaag:
    st.caption("De cumulatieve kasstromen hieronder zijn nominale betaalde bedragen; vermogens-KPI's en de hoofdgrafiek zijn in euro's van vandaag.")
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(fig_k, width="stretch")
with c2:
    st.plotly_chart(fig_h, width="stretch")

with st.expander("🔀 Scenario-vergelijking (pessimistisch / basis / optimistisch)", expanded=False):
    varianten = [
        ("Pessimistisch", 2.0, 4.0, 4.5, 5.4, 6.0, 2.5),
        ("Basis", 4.0, 6.0, 3.0, 4.2, 5.0, 2.0),
        ("Optimistisch", 6.0, 8.0, 1.5, 3.5, 4.0, 1.5),
    ]
    fig_sc = go.Figure()
    for naam, waarde, beleg, huur_groei, rente, rente_na, inflatie_pct in varianten:
        sc = copy.deepcopy(scenario)
        sc.naam = naam
        sc.woning.waarde_groei_pct = waarde
        sc.belegging.bruto_rendement_pct = beleg
        sc.huur.huurverhoging_pct = huur_groei
        sc.leningdelen[0].rente_pct = rente
        sc.leningdelen[0].rente_na_rentevast_pct = rente_na
        sc.algemeen.inflatie_pct = inflatie_pct
        try:
            r = simuleer(sc)
        except ValueError:
            continue  # variant is met het gekozen budget niet haalbaar
        k = r.netto_kopen_liquide if liquide else r.netto_kopen_bezit
        j = r.jaar_indices()
        diff_v = k[j] - r.netto_huren[j]
        if p_vandaag:
            diff_v = diff_v / r.inflatie[j]
        fig_sc.add_trace(go.Scatter(x=jaar_labels, y=diff_v, name=sc.naam, mode="lines"))
    fig_sc.add_hline(y=0, line_color=GREEN, line_dash="dot")
    fig_sc.update_layout(title="Netto voordeel kopen − huren per scenario", template="plotly_white", height=400,
                         yaxis=dict(title="Voordeel kopen (€)", tickformat=",.0f"))
    st.plotly_chart(fig_sc, width="stretch")

with st.expander("🌀 Sensitiviteit (tornado) — welke aanname telt het meest?", expanded=False):
    def hersimuleer(**overrides):
        s2 = copy.deepcopy(scenario)
        if "waarde" in overrides:
            s2.woning.waarde_groei_pct = overrides["waarde"]
        if "beleg" in overrides:
            s2.belegging.bruto_rendement_pct = overrides["beleg"]
        if "rente" in overrides:
            s2.leningdelen[0].rente_pct = overrides["rente"]
        if "huur" in overrides:
            s2.huur.huurverhoging_pct = overrides["huur"]
        if "onderhoud" in overrides:
            s2.eigenaarskosten.onderhoud_pct_waarde = overrides["onderhoud"]
        if "inflatie" in overrides:
            s2.algemeen.inflatie_pct = overrides["inflatie"]
        try:
            r = simuleer(s2)
        except ValueError:
            return float("nan")
        k = r.netto_kopen_liquide if liquide else r.netto_kopen_bezit
        waarde = float(k[limit - 1] - r.netto_huren[limit - 1])
        return waarde / r.inflatie[limit - 1] if p_vandaag else waarde

    basis_diff = float(diff)
    span = 0.2
    tornado = {}
    for label, (key, base) in {
        "Woningwaardestijging": ("waarde", a["waarde"]),
        "Beleggingsrendement": ("beleg", a["beleg"]),
        "Hypotheekrente": ("rente", a["rente"]),
        "Huurverhoging": ("huur", a["huur"]),
        "Onderhoud": ("onderhoud", p_onderhoud_pct),
        "Inflatie": ("inflatie", a["inflatie"]),
    }.items():
        lo = hersimuleer(**{key: base * (1 - span)})
        hi = hersimuleer(**{key: base * (1 + span)})
        tornado[label] = (lo, hi)
    fig_t = tornado_figuur(tornado, basis_diff)
    st.plotly_chart(fig_t, width="stretch")

with st.expander("🗺️ Heatmap — onder welke aannames wint kopen?", expanded=False):
    x_vals = np.round(np.linspace(2.0, 10.0, 12), 1)
    y_vals = np.round(np.linspace(0.0, 8.0, 12), 1)
    z = np.zeros((len(y_vals), len(x_vals)))
    for i, yv in enumerate(y_vals):
        for j, xv in enumerate(x_vals):
            s2 = copy.deepcopy(scenario)
            s2.belegging.bruto_rendement_pct = float(xv)
            s2.woning.waarde_groei_pct = float(yv)
            try:
                r = simuleer(s2)
                k = r.netto_kopen_liquide if liquide else r.netto_kopen_bezit
                waarde = k[limit - 1] - r.netto_huren[limit - 1]
                z[i, j] = waarde / r.inflatie[limit - 1] if p_vandaag else waarde
            except ValueError:
                z[i, j] = np.nan
    fig_hmap = heatmap_figuur(x_vals, y_vals, z)
    st.plotly_chart(fig_hmap, width="stretch")
    st.caption(f"Rood = huren gunstiger, groen = kopen gunstiger. De zwarte lijn is het break-even-punt na {p_vergelijk} jaar.")

st.caption("Alle fiscale percentages zijn indicatieve Nederlandse defaults (2025-2026) en configureerbaar. Geen financieel advies — controleer actuele wetgeving en eigen cijfers.")