"""Maandelijkse vermogens- en cashflowsimulatie voor kopen vs huren.

De engine simuleert beide scenario's op exact dezelfde tijdsas, met identiek
startvermogen en identiek maandbudget, zodat de vergelijking eerlijk is:

- Kopen: eigen inbreng + aankoopkosten verlaten het liquide vermogen; de
  woning wordt vermogen (equity = waarde - schuld); aflossing is géén kosten-
  post maar vermogensopbouw; vrije cashflow na woonlasten wordt belegd.
- Huren: het volledige startvermogen blijft beschikbaar en wordt belegd;
  vrije cashflow na huur+service wordt belegd.

Belastingen worden apart en expliciet geheven (Box 3 jaarlijks op beleggingen,
Box 1 HRA/EWF jaarlijks bij kopen). Netto vermogen = het bedrag dat je op
tijdstip T werkelijk bezit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import (
    BeleggingsConfig,
    Scenario,
)
from .investments import Beleggingsrekening
from .mortgage import Aflossingstype, Leningdeel
from .tax import box3_fictief_belasting, box3_werkelijk_belasting, hra_ewf_jaarvoordeel


def _build_beleggingsrekening(cfg: BeleggingsConfig) -> Beleggingsrekening:
    koers = cfg.koersrendement_pct if cfg.koersrendement_pct is not None else cfg.bruto_rendement_pct
    dividend = cfg.dividend_pct
    return Beleggingsrekening(koers, dividend, cfg.ter_pct)


def _dek_tekort_uit_cash(rekening: Beleggingsrekening, cash: float) -> float:
    """Gebruik eerst beschikbare cash voordat een negatief saldo ontstaat."""
    if rekening.vermogen < 0.0 and cash > 0.0:
        opname = min(cash, -rekening.vermogen)
        cash -= opname
        rekening.vermogen += opname
    return cash


def _aankoopkosten_totaal(scenario: Scenario, hypotheekbedrag: float) -> float:
    a = scenario.aankoopkosten
    w = scenario.woning
    overdracht = 0.0 if a.startersvrijstelling else w.koopprijs * a.overdrachtsbelasting_pct / 100.0
    nhg = hypotheekbedrag * a.nhg_premie_pct / 100.0
    transactie = overdracht + a.notaris_levering + a.aankoopmakelaar
    transactie += a.bouwkundige_keuring
    financiering = a.notaris_hypotheek + a.hypotheekadvies + a.taxatie + nhg
    return transactie + financiering + a.overige, transactie, financiering


@dataclass
class Resultaat:
    """Resultaten per maand (numpy arrays), voor beide scenario's."""

    maanden: np.ndarray
    kalenderjaren: np.ndarray
    jaren: np.ndarray  # 0-based jaar sinds start

    # Kopen
    woningwaarde: np.ndarray
    woz: np.ndarray
    schuld: np.ndarray
    rente: np.ndarray
    aflossing: np.ndarray
    hypotheeklast: np.ndarray
    eigenaarskosten: np.ndarray
    onderhoud: np.ndarray
    ozb: np.ndarray
    hra_voordeel: np.ndarray          # Box 1 eigen woning (jaarlijks toegepast)
    box3_kopen: np.ndarray
    belegging_kopen: np.ndarray
    cash_kopen: np.ndarray
    equity: np.ndarray
    netto_kopen_bezit: np.ndarray     # waarde zonder verkoopkosten
    netto_kopen_liquide: np.ndarray   # waarde alsof je nu verkoopt
    transactiekosten: np.ndarray      # cumulatief? maandelijks 0, jaar1 = aankoopkosten

    # Huren
    huur: np.ndarray
    service: np.ndarray
    overige_huur: np.ndarray
    box3_huren: np.ndarray
    belegging_huren: np.ndarray
    cash_huren: np.ndarray
    netto_huren: np.ndarray

    # Algemeen
    inflatie: np.ndarray  # cumulatieve inflatiefactor

    aankoopkosten_totaal: float = 0.0

    def jaar_indices(self) -> np.ndarray:
        """Indices van de laatste maand van elk kalenderjaar (en laatste maand)."""
        einde = np.where((self.maanden % 12) == 11)[0]
        if len(einde) == 0 or einde[-1] != len(self.maanden) - 1:
            einde = np.append(einde, len(self.maanden) - 1)
        return einde


def simuleer(scenario: Scenario) -> Resultaat:
    """Simuleer beide scenario's maandelijks over de horizon."""
    h = scenario.algemeen.horizon_jaar
    n = h * 12
    start_jaar = scenario.algemeen.start_jaar

    # ---- initiële vermogensverdeling (eerlijk: zelfde startvermogen) ----
    w = scenario.woning
    hypotheekbedrag = sum(ld.hoofdsom for ld in scenario.leningdelen)
    aankoopkosten, _trans, _fin = _aankoopkosten_totaal(scenario, hypotheekbedrag)

    # Kopen: eigen inbreng + aankoopkosten verlaten het liquide vermogen
    cash_k = scenario.algemeen.bestaand_spaargeld
    belegging_k = Beleggingsrekening(0, 0, 0)  # placeholder, wordt gevuld
    begin_k = scenario.algemeen.bestaand_belegging
    uitgaven = scenario.algemeen.eigen_inbreng + aankoopkosten
    if uitgaven > cash_k:
        begin_k -= (uitgaven - cash_k)
        cash_k = 0.0
    else:
        cash_k -= uitgaven
    # Een tekort blijft zichtbaar als negatief liquide vermogen; geen gratis afkap.
    belegging_k = _build_beleggingsrekening(scenario.belegging)
    belegging_k.beginwaarde(begin_k)

    # Huren: volledig startvermogen blijft beschikbaar
    cash_h = scenario.algemeen.bestaand_spaargeld
    belegging_h = _build_beleggingsrekening(scenario.belegging)
    belegging_h.beginwaarde(scenario.algemeen.bestaand_belegging)

    # Leningdelen
    leningdelen = [
        Leningdeel(
            hoofdsom=ld.hoofdsom,
            rente_pct=ld.rente_pct,
            aflossingstype=ld.aflossingstype,
            looptijd_maanden=ld.looptijd_jaar * 12,
            rentevaste_periode_maanden=(
                ld.rentevaste_periode_jaar * 12 if ld.rentevaste_periode_jaar else None
            ),
            rente_na_rentevast_pct=ld.rente_na_rentevast_pct,
            hra_toepassen=ld.hra,
        )
        for ld in scenario.leningdelen
    ]

    # ---- accumulatoren ----
    def _arr():
        return np.zeros(n)

    woningwaarde = _arr(); woz = _arr(); schuld = _arr()
    rente = _arr(); aflossing = _arr(); hypotheeklast = _arr()
    eigenaarskosten = _arr(); onderhoud = _arr(); ozb = _arr()
    hra_voordeel = _arr(); box3_k = _arr()
    belegging_k_arr = _arr(); cash_k_arr = _arr(); equity = _arr()
    netto_k_bezit = _arr(); netto_k_liq = _arr()
    transactiekosten = _arr()
    huur = _arr(); service = _arr(); overige_huur = _arr(); box3_h = _arr()
    belegging_h_arr = _arr(); cash_h_arr = _arr(); netto_h = _arr()
    inflatie = _arr()

    ww = w.koopprijs
    woz_v = w.initiele_woz
    infl_accum = 1.0

    # fiscale eenmalige aftrek (financieringskosten, jaar 1)
    financ_aftrek_jaar1 = _fin * (scenario.aankoopkosten.fiscaal_aftrekbaar_deel_pct / 100.0)

    ew = scenario.fiscaal.eigenwoning
    box3_stelsel = scenario.fiscaal.box3

    # per-kalenderjaar accumulatoren voor belastingen
    jaar_start_maand = 0
    afgetrokken_rente_jaar = 0.0
    werkelijk_rend_jaar_k = 0.0
    werkelijk_rend_jaar_h = 0.0
    maand_spaarrente = (1.0 + scenario.belegging.spaarrente_pct / 100.0) ** (1.0 / 12.0) - 1.0
    # Fictieve box 3 kijkt naar het vermogen op 1 januari, niet naar 31 december.
    box3_peildatum_k_beleg = belegging_k.vermogen
    box3_peildatum_k_cash = cash_k
    box3_peildatum_h_beleg = belegging_h.vermogen
    box3_peildatum_h_cash = cash_h

    e = scenario.eigenaarskosten

    for m in range(n):
        jaar_index = m // 12
        kalenderjaar = start_jaar + jaar_index
        is_jaarstart = (m % 12 == 0)
        is_jaareinde = (m % 12 == 11)

        if is_jaarstart and m > 0:
            # jaarlijkse groei/indexatie aan het begin van het kalenderjaar
            ww *= (1.0 + w.waarde_groei_pct / 100.0)
            woz_v *= (1.0 + (w.woz_groei_pct if w.woz_groei_pct is not None
                             else w.waarde_groei_pct) / 100.0)
            infl_accum *= (1.0 + scenario.algemeen.inflatie_pct / 100.0)
            box3_peildatum_k_beleg = belegging_k.vermogen
            box3_peildatum_k_cash = cash_k
            box3_peildatum_h_beleg = belegging_h.vermogen
            box3_peildatum_h_cash = cash_h

        woningwaarde[m] = ww
        woz[m] = woz_v
        inflatie[m] = infl_accum

        spaarrente_k = max(cash_k, 0.0) * maand_spaarrente
        spaarrente_h = max(cash_h, 0.0) * maand_spaarrente
        cash_k += spaarrente_k
        cash_h += spaarrente_h
        werkelijk_rend_jaar_k += spaarrente_k
        werkelijk_rend_jaar_h += spaarrente_h

        # ---- KOPEN ----
        rente_m, aflossing_m, hra_rente_m = 0.0, 0.0, 0.0
        for ld in leningdelen:
            r, a = ld.simulatie_maand(m)
            rente_m += r
            aflossing_m += a
            if ld.hra_toepassen:
                hra_rente_m += r
        hypotheek_m = rente_m + aflossing_m
        afgetrokken_rente_jaar += hra_rente_m

        # eigenaarskosten (maandelijks, met indexatie voor nominale posten)
        onderhoud_m = (
            (e.onderhoud_vast_jaar / 12.0) if e.onderhoud_vast_jaar is not None
            else (ww * e.onderhoud_pct_waarde / 100.0 / 12.0)
        )
        ozb_m = woz_v * e.ozb_pct_woz / 100.0 / 12.0
        vve_m = e.vve_maand * infl_accum
        verzekering_m = e.opstalverzekering_maand * infl_accum
        lokale_m = e.lokale_heffingen_jaar / 12.0 * infl_accum
        erfpacht_m = (e.erfpacht_maand + w.erfpacht_canon_maand) * infl_accum
        overige_m = e.overige_maand * infl_accum
        eigenaar_m = onderhoud_m + ozb_m + vve_m + verzekering_m + lokale_m + erfpacht_m + overige_m
        afgetrokken_rente_jaar += erfpacht_m  # periodieke canon is aftrekbaar in box 1

        vrije_k = scenario.algemeen.maandbudget - hypotheek_m - eigenaar_m
        _k, _d, _kos = belegging_k.draai_maand(vrije_k)
        cash_k = _dek_tekort_uit_cash(belegging_k, cash_k)
        werkelijk_rend_jaar_k += _k + _d

        # aankoopkosten zijn eenmalig in maand 0 (cash reeds betaald), geen maandpost
        # ---- HUREN ----
        huur_m = scenario.huur.initiele_maandhuur * (1.0 + scenario.huur.huurverhoging_pct / 100.0) ** jaar_index
        service_m = scenario.huur.servicekosten_maand * (1.0 + scenario.huur.servicekosten_stijging_pct / 100.0) ** jaar_index
        overige_h_m = scenario.huur.overige_maand * infl_accum
        vrije_h = scenario.algemeen.maandbudget - huur_m - service_m - overige_h_m
        _k, _d, _kos = belegging_h.draai_maand(vrije_h)
        cash_h = _dek_tekort_uit_cash(belegging_h, cash_h)
        werkelijk_rend_jaar_h += _k + _d

        # ---- jaareinde: belastingen ----
        if is_jaareinde:
            regels = box3_stelsel.voor_jaar(kalenderjaar)

            # Box 3 kopen
            totaal_k = box3_peildatum_k_beleg + box3_peildatum_k_cash
            fictief_k = box3_fictief_belasting(totaal_k, box3_peildatum_k_cash, regels)
            werkelijk_k = box3_werkelijk_belasting(werkelijk_rend_jaar_k, regels)
            bel = min(fictief_k, werkelijk_k) if scenario.fiscaal.box3_werkelijk_rendement else fictief_k
            belegging_k.betaal_belasting(bel)
            cash_k = _dek_tekort_uit_cash(belegging_k, cash_k)
            box3_k[m] = bel

            # Box 3 huren
            totaal_h = box3_peildatum_h_beleg + box3_peildatum_h_cash
            fictief_h = box3_fictief_belasting(totaal_h, box3_peildatum_h_cash, regels)
            werkelijk_h = box3_werkelijk_belasting(werkelijk_rend_jaar_h, regels)
            belh = min(fictief_h, werkelijk_h) if scenario.fiscaal.box3_werkelijk_rendement else fictief_h
            belegging_h.betaal_belasting(belh)
            cash_h = _dek_tekort_uit_cash(belegging_h, cash_h)
            box3_h[m] = belh

            # Box 1 eigen woning: HRA/EWF over dit kalenderjaar
            aftrekbare = afgetrokken_rente_jaar + financ_aftrek_jaar1 if jaar_index == 0 else afgetrokken_rente_jaar
            hra = hra_ewf_jaarvoordeel(aftrekbare, woz_v, ew, kalenderjaar)
            belegging_k.stort(hra)  # positief voordeel = bijstorting, negatief = kosten
            hra_voordeel[m] = hra

            # reset jaaraccumulatoren
            afgetrokken_rente_jaar = 0.0
            werkelijk_rend_jaar_k = 0.0
            werkelijk_rend_jaar_h = 0.0

        # boekhouding per maand
        schuld[m] = sum(ld.schuld for ld in leningdelen)
        rente[m] = rente_m
        aflossing[m] = aflossing_m
        hypotheeklast[m] = hypotheek_m
        eigenaarskosten[m] = eigenaar_m
        onderhoud[m] = onderhoud_m
        ozb[m] = ozb_m

        belegging_k_arr[m] = belegging_k.vermogen
        cash_k_arr[m] = cash_k
        equity[m] = ww - schuld[m]
        netto_k_bezit[m] = equity[m] + belegging_k.vermogen + cash_k
        # liquide: alsof nu verkocht (verkoopkosten + korting verwerkt)
        vk = scenario.verkoopkosten
        verkoopwaarde = ww * (1.0 - vk.verkoopkorting_pct / 100.0)
        makelaar = vk.makelaar_vast if vk.makelaar_vast is not None else verkoopwaarde * vk.makelaar_pct / 100.0
        netto_k_liq[m] = verkoopwaarde - schuld[m] - makelaar - vk.overige + belegging_k.vermogen + cash_k

        huur[m] = huur_m
        service[m] = service_m
        overige_huur[m] = overige_h_m
        belegging_h_arr[m] = belegging_h.vermogen
        cash_h_arr[m] = cash_h
        netto_h[m] = belegging_h.vermogen + cash_h

        # transactiekosten: eenmalig in maand 0 (aankoop) — geen maandelijkse kosten
        if m == 0:
            transactiekosten[m] = aankoopkosten

    return Resultaat(
        maanden=np.arange(n),
        kalenderjaren=np.array([start_jaar + i // 12 for i in range(n)]),
        jaren=np.arange(n) // 12,
        woningwaarde=woningwaarde, woz=woz, schuld=schuld,
        rente=rente, aflossing=aflossing, hypotheeklast=hypotheeklast,
        eigenaarskosten=eigenaarskosten, onderhoud=onderhoud, ozb=ozb,
        hra_voordeel=hra_voordeel, box3_kopen=box3_k,
        belegging_kopen=belegging_k_arr, cash_kopen=cash_k_arr,
        equity=equity, netto_kopen_bezit=netto_k_bezit,
        netto_kopen_liquide=netto_k_liq, transactiekosten=transactiekosten,
        huur=huur, service=service, overige_huur=overige_huur,
        box3_huren=box3_h, belegging_huren=belegging_h_arr,
        cash_huren=cash_h_arr, netto_huren=netto_h,
        inflatie=inflatie, aankoopkosten_totaal=aankoopkosten,
    )


def break_even_jaar(resultaat: Resultaat, liquide: bool = True) -> float | None:
    """Eerste jaar waarin kopen (netto vermogen) huren inhaalt. None als nooit."""
    k = resultaat.netto_kopen_liquide if liquide else resultaat.netto_kopen_bezit
    h = resultaat.netto_huren
    indices = resultaat.jaar_indices()
    for i in indices:
        if k[i] >= h[i]:
            return float(resultaat.jaren[i] + 1)
    return None


def aggregeer_jaarlijks(resultaat: Resultaat) -> dict[str, np.ndarray]:
    """Selecteer de laatste maand van elk kalenderjaar (netto vermogen per jaar)."""
    indices = resultaat.jaar_indices()
    out: dict[str, Any] = {}
    for veld in [
        "kalenderjaren", "jaren", "woningwaarde", "schuld", "rente", "aflossing",
        "hypotheeklast", "eigenaarskosten", "hra_voordeel", "box3_kopen",
        "belegging_kopen", "cash_kopen", "equity", "netto_kopen_bezit",
        "netto_kopen_liquide", "huur", "service", "box3_huren",
        "belegging_huren", "cash_huren", "netto_huren",
    ]:
        arr = getattr(resultaat, veld)
        out[veld] = arr[indices]
    out["indices"] = indices
    out["jaren_labels"] = resultaat.kalenderjaren[indices]
    return out
