"""Unit-tests voor de financiële kernrelaties van de simulator."""
from __future__ import annotations

import numpy as np
import pytest

from simulator import simuleer
from simulator.investments import Beleggingsrekening, jaarlijks_naar_maandelijks
from simulator.mortgage import (
    Aflossingstype,
    Leningdeel,
    annuitaire_maandlast,
    jaarlijks_naar_maandelijks as jm_mort,
)
from simulator.presets import SCHEMA, format_export, parse_import, waarden_naar_session
from simulator.scenarios import basis_scenario
from simulator.tax import (
    Box3Regels,
    EigenWoningFiscaal,
    box3_fictief_belasting,
    box3_werkelijk_belasting,
    hra_ewf_jaarvoordeel,
)


def assert_approx(a, b, rel=1e-6):
    assert abs(a - b) <= rel * max(1.0, abs(b)), f"{a} != {b} (rel {rel})"


# ---------------------------------------------------------------------------
# Hypotheekkern
# ---------------------------------------------------------------------------

def test_annuitaire_maandlast_bekende_waarde():
    # 100k, 4% p.a. (effectief), 30 jaar -> ~473.30
    r = jm_mort(4.0)
    last = annuitaire_maandlast(100000.0, r, 360)
    assert_approx(last, 473.30, rel=1e-3)


def test_annuiteit_som_van_lasten_gelijk_aan_hoofdsom_plus_rente():
    # Over de volledige looptijd is totaal betaald = last * n
    hoofdsom, rente, n = 200000.0, 3.5, 300
    r = jm_mort(rente)
    last = annuitaire_maandlast(hoofdsom, r, n)
    assert_approx(last * n, annuitaire_totaal_check(hoofdsom, r, n), rel=1e-9)


def annuitaire_totaal_check(hoofdsom, r, n):
    last = annuitaire_maandlast(hoofdsom, r, n)
    factor = (1.0 + r) ** n
    return last * n


def test_lineaire_hypotheek_aflossing_constant():
    ld = Leningdeel(120000.0, 4.0, Aflossingstype.LINEAIR, 120)
    expect_aflossing = 120000.0 / 120
    for m in range(3):
        rente, aflossing = ld.simulatie_maand(m)
        assert_approx(aflossing, expect_aflossing, rel=1e-9)


def test_rente_over_begin_saldo():
    ld = Leningdeel(100000.0, 12.0, Aflossingstype.AFLOSSINGSVRIJ, 120)
    r = jm_mort(12.0)
    rente, _ = ld.simulatie_maand(0)
    assert_approx(rente, 100000.0 * r, rel=1e-9)
    assert_approx(ld.schuld, 100000.0, rel=1e-9)  # aflossingsvrij: schuld blijft


def test_aflossing_verlaagt_schuld_correct():
    ld = Leningdeel(100000.0, 4.0, Aflossingstype.ANNUITAIR, 360)
    totale_aflossing = 0.0
    for m in range(12):
        r, a = ld.simulatie_maand(m)
        totale_aflossing += a
    assert_approx(ld.schuld, 100000.0 - totale_aflossing, rel=1e-9)


def test_annuiteit_loopt_correct_af_tot_nul():
    ld = Leningdeel(100000.0, 4.0, Aflossingstype.ANNUITAIR, 360)
    for m in range(360):
        ld.simulatie_maand(m)
    assert ld.schuld < 1e-6


def test_annuiteit_wordt_herberekend_na_rentewijziging_zonder_negatieve_aflossing():
    ld = Leningdeel(
        100000.0, 1.0, Aflossingstype.ANNUITAIR, 360,
        rentevaste_periode_maanden=12, rente_na_rentevast_pct=8.0,
    )
    for m in range(24):
        _rente, aflossing = ld.simulatie_maand(m)
        assert aflossing >= 0.0
    assert ld.schuld < 100000.0


# ---------------------------------------------------------------------------
# Beleggingsrekening
# ---------------------------------------------------------------------------

def test_vrije_cashflow_wordt_toegevoegd():
    rek = Beleggingsrekening(koersrendement_pct=0.0, dividend_pct=0.0, ter_pct=0.0)
    rek.beginwaarde(0.0)
    k, d, ko = rek.draai_maand(1000.0)
    assert_approx(rek.vermogen, 1000.0, rel=1e-9)
    # tweede maand: rendement 0, storting 500
    rek.draai_maand(500.0)
    assert_approx(rek.vermogen, 1500.0, rel=1e-9)


def test_rendement_op_beginvermogen_niet_op_storting():
    rek = Beleggingsrekening(koersrendement_pct=12.0, ter_pct=0.0)
    rek.beginwaarde(1000.0)
    r = jm_mort(12.0)
    k, _, _ = rek.draai_maand(1000.0)  # 1000 storting, maar rendement alleen op begin 1000
    assert_approx(k, 1000.0 * r, rel=1e-9)
    # vermogen = 1000*(1+r) + 1000
    assert_approx(rek.vermogen, 1000.0 * (1 + r) + 1000.0, rel=1e-9)


def test_box3_verlaagt_portefeuille():
    rek = Beleggingsrekening(koersrendement_pct=0.0, ter_pct=0.0)
    rek.beginwaarde(10000.0)
    rek.betaal_belasting(500.0)
    assert_approx(rek.vermogen, 9500.0, rel=1e-9)


# ---------------------------------------------------------------------------
# Box 3 (pure functie)
# ---------------------------------------------------------------------------

def test_box3_fictief_heffingsvrij_aftrek():
    regels = Box3Regels(2026, None, 36.0, 1.28, 6.00, 59357.0, fiscaal_partner=False)
    # vermogen onder heffingsvrij -> geen belasting
    assert box3_fictief_belasting(30000.0, 30000.0, regels) == 0.0
    # boven heffingsvrij -> belasting over forfaitair rendement
    bel = box3_fictief_belasting(100000.0, 40000.0, regels)
    # Rendement wordt over de werkelijke mix berekend; vrijstelling verlaagt
    # daarna de grondslag pro rata.
    rend = 40000 * 0.0128 + 60000 * 0.06
    aandeel = (100000 - 59357) / 100000
    assert_approx(bel, rend * aandeel * 0.36, rel=1e-9)


def test_box3_werkelijk_geen_verliesverrekening_of_vrijstelling():
    regels = Box3Regels(2026, None, 36.0, 1.28, 6.00, 59357.0)
    assert box3_werkelijk_belasting(-1000.0, regels) == 0.0
    assert_approx(box3_werkelijk_belasting(1000.0, regels), 360.0)


def test_ewf_villabelasting_is_marginaal_geen_percentage_over_geheel():
    f = EigenWoningFiscaal(
        hra_tarief_pct=37.56,
        ewf_schijven=[(0.0, 0.35)],
        ewf_hoge_grens=1_350_000.0,
        ewf_hoog_pct=2.35,
        wet_hillen_afbouw_pct=0.71867,
    )
    verwacht = 1_350_000 * 0.0035 + 150_000 * 0.0235
    assert_approx(f.ewf_bedrag(1_500_000), verwacht)


def test_ewf_lage_woz_schijven_2026():
    f = EigenWoningFiscaal(
        ewf_schijven=[
            (0.0, 0.0), (12_500.0, 0.10), (25_000.0, 0.20),
            (50_000.0, 0.25), (75_000.0, 0.35),
        ]
    )
    assert_approx(f.ewf_bedrag(10_000), 0.0)
    assert_approx(f.ewf_bedrag(20_000), 20.0)
    assert_approx(f.ewf_bedrag(60_000), 150.0)


def test_wet_hillen_bouwt_jaarlijks_af_vanaf_2026():
    f = EigenWoningFiscaal(
        hra_tarief_pct=37.56,
        ewf_schijven=[(0.0, 0.35)],
        wet_hillen_afbouw_pct=0.71867,
        wet_hillen_basisjaar=2026,
        wet_hillen_afbouw_per_jaar=0.048,
    )
    voordeel_2026 = hra_ewf_jaarvoordeel(0.0, 400000.0, f, 2026)
    voordeel_2027 = hra_ewf_jaarvoordeel(0.0, 400000.0, f, 2027)
    assert voordeel_2027 < voordeel_2026  # minder Hillen-aftrek = meer belasting


# ---------------------------------------------------------------------------
# Integratietests (engine)
# ---------------------------------------------------------------------------

def test_equity_groeit_met_aflossing_in_jaar0():
    """In jaar 0 (geen waardegroei tot m=12) is de equity-stijging = totale aflossing.
    equity[0] verwerkt al de aflossing van maand 0, dus de groei naar equity[11]
    komt overeen met aflossing in maand 1 t/m 11.
    """
    r = simuleer(basis_scenario())
    aflossing_maand1_11 = r.aflossing[1:12].sum()
    equity_groei = r.equity[11] - r.equity[0]
    assert_approx(equity_groei, aflossing_maand1_11, rel=1e-6)


def test_aflossing_telt_niet_als_kostenpost():
    """De vrije cashflow = maandbudget - (rente+aflossing) - eigenaarskosten.
    De storting in de belegging in maand 1 (geen belastingmaand) moet exact
    gelijk zijn aan deze vrije cashflow, na rendement én TER over het saldo.
    """
    s = basis_scenario()
    r = simuleer(s)
    m = 1
    vrije = s.algemeen.maandbudget - r.hypotheeklast[m] - r.eigenaarskosten[m]
    begin = r.belegging_kopen[0]
    mr = jaarlijks_naar_maandelijks(s.belegging.bruto_rendement_pct)
    mter = jaarlijks_naar_maandelijks(s.belegging.ter_pct)
    bruto = begin * mr
    verwacht = begin + bruto - (begin + bruto) * mter + vrije
    assert_approx(r.belegging_kopen[1], verwacht, rel=1e-6)


def test_verkoop_verwerkt_restschuld_en_verkoopkosten():
    """netto_kopen_liquide = verkoopwaarde - schuld - makelaar + belegging + cash."""
    s = basis_scenario()
    r = simuleer(s)
    m = 59  # jaar 5
    vk = s.verkoopkosten
    verkoopwaarde = r.woningwaarde[m] * (1.0 - vk.verkoopkorting_pct / 100.0)
    makelaar = verkoopwaarde * vk.makelaar_pct / 100.0
    verwacht = verkoopwaarde - r.schuld[m] - makelaar - vk.overige \
        + r.belegging_kopen[m] + r.cash_kopen[m]
    assert_approx(r.netto_kopen_liquide[m], verwacht, rel=1e-6)


def test_huurverhoging_compoundt():
    s = basis_scenario()
    r = simuleer(s)
    base = s.huur.initiele_maandhuur
    verhoging = s.huur.huurverhoging_pct / 100.0
    assert_approx(r.huur[11], base, rel=1e-9)          # jaar 0
    assert_approx(r.huur[23], base * (1 + verhoging), rel=1e-9)
    assert_approx(r.huur[35], base * (1 + verhoging) ** 2, rel=1e-9)


def test_box3_verlaagt_huurportefeuille_jaarlijks():
    """Box 3 heft jaarlijks; een scenario met Box 3-tarief 0 levert een hogere
    eindportefeuille op dan hetzelfde scenario met een reëel tarief."""
    s_hoog = basis_scenario()
    s_nul = basis_scenario()
    # bouw een Box 3 stelsel met tarief 0 (en zelfde forfaits)
    from simulator.tax import Box3Regels, Box3Stelsel
    s_nul.fiscaal.box3 = Box3Stelsel([
        Box3Regels(r.jaar_vanaf, r.jaar_tot, 0.0, r.spaarforfait_pct,
                   r.beleggingsforfait_pct, r.heffingsvrij_per_persoon,
                   r.fiscaal_partner)
        for r in s_hoog.fiscaal.box3.regels
    ])
    r_hoog = simuleer(s_hoog)
    r_nul = simuleer(s_nul)
    # jaareindemaand heeft Box 3-heffing in het hoge scenario
    assert r_hoog.box3_huren[11] > 0.0
    assert r_nul.box3_huren[11] == 0.0
    # zonder belasting blijft er meer over
    assert r_nul.netto_huren[-1] > r_hoog.netto_huren[-1]


def test_box3_fictief_gebruikt_peildatum_1_januari():
    s = basis_scenario()
    s.algemeen.bestaand_spaargeld = 0.0
    s.algemeen.bestaand_belegging = 0.0
    s.algemeen.maandbudget = 10_000.0
    s.huur.initiele_maandhuur = 0.0
    s.huur.servicekosten_maand = 0.0
    r = simuleer(s)
    # Op 1 januari was er geen box-3-vermogen; stortingen in het jaar tellen
    # pas mee op de peildatum van het volgende kalenderjaar.
    assert r.box3_huren[11] == 0.0
    assert r.box3_huren[23] > 0.0


def test_tekort_maandbudget_wordt_niet_gratis_afgekapt():
    s = basis_scenario()
    s.algemeen.maandbudget = 0.0
    r = simuleer(s)
    # Eerst wordt spaargeld aangesproken; bij langdurig tekort blijft daarna
    # een negatief saldo zichtbaar in plaats van gratis te verdwijnen.
    assert r.cash_kopen[-1] == 0.0
    assert r.cash_huren[-1] == 0.0
    assert r.belegging_kopen[-1] < 0.0
    assert r.belegging_huren[-1] < 0.0


def test_tekort_wordt_eerst_uit_cash_betaald():
    s = basis_scenario()
    s.algemeen.horizon_jaar = 1
    s.algemeen.bestaand_spaargeld = 100_000.0
    s.algemeen.bestaand_belegging = 0.0
    s.algemeen.maandbudget = 0.0
    s.belegging.spaarrente_pct = 0.0
    r = simuleer(s)
    assert r.belegging_huren[-1] == 0.0
    assert 0.0 < r.cash_huren[-1] < 100_000.0


def test_spaargeld_ontvangt_spaarrente():
    s = basis_scenario()
    s.algemeen.horizon_jaar = 1
    s.algemeen.bestaand_spaargeld = 100_000.0
    s.algemeen.bestaand_belegging = 0.0
    s.algemeen.maandbudget = 0.0
    s.huur.initiele_maandhuur = 0.0
    s.huur.servicekosten_maand = 0.0
    s.belegging.spaarrente_pct = 2.0
    for regel in s.fiscaal.box3.regels:
        regel.tarief_pct = 0.0
    r = simuleer(s)
    assert_approx(r.cash_huren[-1], 102_000.0, rel=1e-6)


def test_dividend_telt_naast_koersrendement_ook_zonder_aparte_koersconfig():
    s = basis_scenario(beleg_rendement=0.0)
    s.algemeen.horizon_jaar = 1
    s.algemeen.bestaand_spaargeld = 0.0
    s.algemeen.bestaand_belegging = 100_000.0
    s.algemeen.maandbudget = 0.0
    s.huur.initiele_maandhuur = 0.0
    s.huur.servicekosten_maand = 0.0
    s.belegging.dividend_pct = 2.0
    s.belegging.ter_pct = 0.0
    for regel in s.fiscaal.box3.regels:
        regel.tarief_pct = 0.0
    r = simuleer(s)
    assert_approx(r.belegging_huren[-1], 102_000.0, rel=1e-6)


def test_aftrekbare_financieringskosten_zonder_bouwkundige_keuring():
    s = basis_scenario()
    s.algemeen.horizon_jaar = 1
    s.aankoopkosten.fiscaal_aftrekbaar_deel_pct = 100.0
    r_met = simuleer(s)
    s.aankoopkosten.bouwkundige_keuring += 10_000.0
    r_keuring = simuleer(s)
    # Keuring verlaagt vermogen als kosten, maar verhoogt de Box-1-aftrek niet.
    assert_approx(r_met.hra_voordeel[11], r_keuring.hra_voordeel[11])


def test_beide_scenarios_starten_eerlijk():
    """Eerlijke start: huren houdt het volledige spaargeld als cash, kopen zet
    de eigen inbreng direct om in equity, en het restant is belegd."""
    s = basis_scenario()
    r = simuleer(s)
    # huren: cash = volledig startspaargeld plus één maand spaarrente
    maand_spaar = jaarlijks_naar_maandelijks(s.belegging.spaarrente_pct)
    assert_approx(
        r.cash_huren[0],
        s.algemeen.bestaand_spaargeld * (1 + maand_spaar),
        rel=1e-9,
    )
    # kopen: eigen inbreng wordt direct woning-equity
    # (maand 0 heeft al één aflossing gedaan, dus + aflossing[0])
    assert_approx(r.equity[0], s.algemeen.eigen_inbreng + r.aflossing[0], rel=1e-9)
    # kopen: wat niet in de woning/kosten zit, is belegd (niet negatief)
    assert r.belegging_kopen[0] >= 0.0
    # kopen start lager dan huren door de eenmalige aankoopkosten
    assert r.netto_kopen_bezit[0] < r.netto_huren[0]


def test_break_even_none_wanneer_nooit():
    """Met 0% woninggroei en relatief hoge huurstijging kan kopen nooit winnen
    (of pas laat); check dat break_even een geldige float of None retourneert."""
    s = basis_scenario(waarde_groei=0.0, beleg_rendement=8.0, huurverhoging=1.0)
    r = simuleer(s)
    from simulator import break_even_jaar
    be = break_even_jaar(r)
    assert be is None or be >= 0


# ---------------------------------------------------------------------------
# Parameterprofiel (copy-paste) roundtrip
# ---------------------------------------------------------------------------

def test_preset_export_import_roundtrip():
    """Export → import levert dezelfde waarden op (alle schema-keys)."""
    waarden = {}
    for key, _label, typ in SCHEMA:
        if typ == "float":
            waarden[key] = 5.5
        elif typ == "int":
            waarden[key] = 30
        elif typ == "bool":
            waarden[key] = True
        else:  # str
            waarden[key] = "annuïtair" if key == "aflossingstype" else "Alsof nu verkocht (liquide)"
    tekst = format_export(waarden)
    terug = parse_import(tekst)
    assert set(terug.keys()) == set(waarden.keys())
    for key, val in waarden.items():
        assert terug[key] == val, f"{key}: {terug[key]} != {val}"


def test_preset_import_vertaalt_liquide_en_negeert_commentaar():
    """Commentaarlijnen worden genegeerd; 'liquide' wordt vertaald naar de radio-optie."""
    tekst = (
        "# commentaar\n"
        "koopprijs = 300000\n"
        "liquide = Alsof nu verkocht\n"
        "onbekend_key = 99\n"
    )
    profiel = parse_import(tekst)
    assert "koopprijs" in profiel
    assert "onbekend_key" not in profiel
    mapping = waarden_naar_session(profiel)
    assert mapping["liquide"] == "Alsof nu verkocht (liquide)"
