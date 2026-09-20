"""Configuratie-dataclasses voor de simulatie.

Alle invoerparameters zitten hier. De engine leest uitsluitend deze
dataclasses, zodat de rekenlogica los blijft van de UI en de fiscale regels
(configuratie) los van de rekenkunde.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .mortgage import Aflossingstype
from .tax import Box3Stelsel, EigenWoningFiscaal


# ---------------------------------------------------------------------------
# Koopscenario
# ---------------------------------------------------------------------------

@dataclass
class LeningdeelConfig:
    hoofdsom: float
    rente_pct: float
    aflossingstype: Aflossingstype
    looptijd_jaar: int
    rentevaste_periode_jaar: int | None = None
    rente_na_rentevast_pct: float | None = None
    hra: bool = True


@dataclass
class WoningConfig:
    koopprijs: float
    initiele_woz: float
    waarde_groei_pct: float
    woz_groei_pct: float | None = None  # None -> zelfde groei als waarde
    erfpacht_canon_maand: float = 0.0   # maandelijkse canon (ook als lopende post)
    erfpacht_stijging_pct: float = 0.0


@dataclass
class Aankoopkosten:
    """Eenmalige kosten bij aankoop. Onderscheid transactie- vs financieringskosten.

    - transactiekosten: overdrachtsbelasting, notaris levering, aankoopmakelaar
    - financieringskosten: notaris hypotheek, hypotheekadvies, taxatie, NHG
    `fiscaal_aftrekbaar_deel_pct` geeft aan welk deel van de financieringskosten
    in het eerste jaar fiscaal aftrekbaar is (aftrekbaar naast de hypotheekrente).
    """
    overdrachtsbelasting_pct: float = 2.0
    startersvrijstelling: bool = False
    startersvrijstelling_max_waarde: float = 555000.0
    notaris_levering: float = 750.0
    notaris_hypotheek: float = 500.0
    hypotheekadvies: float = 2000.0
    taxatie: float = 550.0
    bouwkundige_keuring: float = 400.0
    aankoopmakelaar: float = 0.0
    nhg_premie_pct: float = 0.0
    overige: float = 0.0
    fiscaal_aftrekbaar_deel_pct: float = 0.0  # van financieringskosten


@dataclass
class Eigenaarskosten:
    """Lopende maandelijkse/jaarlijkse kosten van de eigen woning.

    Voorkom dubbeltelling: ofwel VvE-bijdrage (die onderhoud dekt) ofwel
    onderhoud direct rekenen. Het model telt beide op, dus kies bewust.
    """
    onderhoud_pct_waarde: float = 1.0   # % van woningwaarde per jaar
    onderhoud_vast_jaar: float | None = None  # overschrijft percentage indien gegeven
    vve_maand: float = 0.0
    ozb_pct_woz: float = 0.05           # % van WOZ per jaar
    lokale_heffingen_jaar: float = 400.0
    opstalverzekering_maand: float = 35.0
    erfpacht_maand: float = 0.0         # canon, als niet in woning config
    overige_maand: float = 0.0
    inflatie_gevoelig: list[str] = field(default_factory=lambda: [
        "vve", "verzekering", "lokale", "overige", "erfpacht"
    ])


@dataclass
class Verkoopkosten:
    makelaar_pct: float = 1.5
    makelaar_vast: float | None = None
    overige: float = 0.0
    verkoopkorting_pct: float = 0.0  # korting op modelmatige marktwaarde


# ---------------------------------------------------------------------------
# Huurscenario
# ---------------------------------------------------------------------------

@dataclass
class HuurConfig:
    initiele_maandhuur: float
    huurverhoging_pct: float = 3.0
    servicekosten_maand: float = 0.0
    servicekosten_stijging_pct: float = 2.5
    overige_maand: float = 0.0


# ---------------------------------------------------------------------------
# Beleggingen
# ---------------------------------------------------------------------------

@dataclass
class BeleggingsConfig:
    """Bruto rendement op beleggingen. Optioneel gesplitst in koers en dividend.

    Indien `koersrendement_pct` niet is ingevuld, wordt het volledige
    `bruto_rendement_pct` als koersrendement gebruikt. Box 3 wordt apart en
    expliciet geheven (niet verdisconteerd in dit rendement).
    """
    bruto_rendement_pct: float
    koersrendement_pct: float | None = None
    dividend_pct: float = 0.0
    ter_pct: float = 0.3
    spaarrente_pct: float = 1.5


# ---------------------------------------------------------------------------
# Fiscaal
# ---------------------------------------------------------------------------

@dataclass
class FiscaleConfig:
    eigenwoning: EigenWoningFiscaal
    box3: Box3Stelsel
    box3_werkelijk_rendement: bool = False


# ---------------------------------------------------------------------------
# Algemeen / scenario-overstijgend
# ---------------------------------------------------------------------------

@dataclass
class AlgemeneConfig:
    start_jaar: int = 2026
    horizon_jaar: int = 30
    inflatie_pct: float = 2.0
    # Beschikbaar budget per maand (wonen + beleggen), identiek in beide scenario's
    maandbudget: float = 2500.0
    # Startvermogen (vóór aankoop), identiek in beide scenario's
    bestaand_spaargeld: float = 50000.0
    bestaand_belegging: float = 0.0
    # Eigen inbreng in de woning (koopscenario)
    eigen_inbreng: float = 100000.0
    # Netto vermogen bij kopen: rekening houden met verkoopkosten alsof je nu verkoopt
    liquide_verkoop_waarde: bool = True


# ---------------------------------------------------------------------------
# Complete scenario-bundel
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    naam: str
    woning: WoningConfig
    leningdelen: list[LeningdeelConfig]
    aankoopkosten: Aankoopkosten
    eigenaarskosten: Eigenaarskosten
    verkoopkosten: Verkoopkosten
    huur: HuurConfig
    belegging: BeleggingsConfig
    fiscaal: FiscaleConfig
    algemeen: AlgemeneConfig
