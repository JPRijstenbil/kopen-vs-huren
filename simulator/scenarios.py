"""Standaard Nederlandse configuratie en drie scenario-varianten.

Alle fiscale percentages en drempels hieronder zijn indicatieve defaults voor
het Nederlandse belastingstelsel (indicatief 2025-2026). Controleer en pas ze
aan in de UI of hier — ze zijn bewust niet hardcoded in de rekenlogica.
"""
from __future__ import annotations

from .config import (
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
from .mortgage import Aflossingstype
from .tax import Box3Regels, Box3Stelsel, EigenWoningFiscaal


# Indicatieve Box 3 forfaits per kalenderjaar (controleer actuele waarden)
BOX3_REGELS = Box3Stelsel([
    Box3Regels(2024, 2024, 36.0, 1.03, 6.04, 57000.0),
    Box3Regels(2025, 2025, 36.0, 1.44, 6.27, 57684.0),
    Box3Regels(2026, None, 36.0, 1.44, 6.27, 57684.0),
])

# Eigen woning (Box 1): HRA-tarief, EWF-schijven (WOZ), Wet Hillen-afbouw 2026
EIGENWONING = EigenWoningFiscaal(
    hra_tarief_pct=37.0,
    ewf_schijven=[(0.0, 0.35), (1310000.0, 1.30)],
    wet_hillen_afbouw_pct=0.77,
)


def _fiscaal() -> FiscaleConfig:
    return FiscaleConfig(eigenwoning=EIGENWONING, box3=BOX3_REGELS, box3_werkelijk_rendement=False)


def _algemeen(**kwargs) -> AlgemeneConfig:
    base = dict(
        start_jaar=2026,
        horizon_jaar=30,
        inflatie_pct=2.0,
        maandbudget=2500.0,
        bestaand_spaargeld=100000.0,
        bestaand_belegging=50000.0,
        eigen_inbreng=100000.0,
        liquide_verkoop_waarde=True,
    )
    base.update(kwargs)
    return AlgemeneConfig(**base)


def basis_scenario(
    waarde_groei: float = 4.0,
    beleg_rendement: float = 6.0,
    huurverhoging: float = 3.0,
    hypotheekrente: float = 4.2,
    rente_na_rentevast: float = 5.0,
    inflatie: float = 2.0,
) -> Scenario:
    """Realistisch Nederlands basisscenario (één annuïtair leningdeel)."""
    return Scenario(
        naam="Basis",
        woning=WoningConfig(
            koopprijs=450000.0,
            initiele_woz=400000.0,
            waarde_groei_pct=waarde_groei,
            woz_groei_pct=3.0,
            erfpacht_canon_maand=0.0,
            erfpacht_stijging_pct=0.0,
        ),
        leningdelen=[
            LeningdeelConfig(
                hoofdsom=350000.0,
                rente_pct=hypotheekrente,
                aflossingstype=Aflossingstype.ANNUITAIR,
                looptijd_jaar=30,
                rentevaste_periode_jaar=10,
                rente_na_rentevast_pct=rente_na_rentevast,
                hra=True,
            )
        ],
        aankoopkosten=Aankoopkosten(
            overdrachtsbelasting_pct=2.0,
            startersvrijstelling=False,
            notaris_levering=750.0,
            notaris_hypotheek=500.0,
            hypotheekadvies=2000.0,
            taxatie=550.0,
            bouwkundige_keuring=400.0,
            aankoopmakelaar=0.0,
            nhg_premie_pct=0.0,
            overige=0.0,
            fiscaal_aftrekbaar_deel_pct=0.0,
        ),
        eigenaarskosten=Eigenaarskosten(
            onderhoud_pct_waarde=1.0,
            onderhoud_vast_jaar=None,
            vve_maand=0.0,
            ozb_pct_woz=0.05,
            lokale_heffingen_jaar=400.0,
            opstalverzekering_maand=35.0,
            erfpacht_maand=0.0,
            overige_maand=0.0,
        ),
        verkoopkosten=Verkoopkosten(
            makelaar_pct=1.5,
            makelaar_vast=None,
            overige=0.0,
            verkoopkorting_pct=0.0,
        ),
        huur=HuurConfig(
            initiele_maandhuur=1500.0,
            huurverhoging_pct=huurverhoging,
            servicekosten_maand=100.0,
            servicekosten_stijging_pct=2.5,
            overige_maand=0.0,
        ),
        belegging=BeleggingsConfig(
            bruto_rendement_pct=beleg_rendement,
            koersrendement_pct=None,
            dividend_pct=0.0,
            ter_pct=0.3,
        ),
        fiscaal=_fiscaal(),
        algemeen=_algemeen(inflatie_pct=inflatie),
    )


def drie_scenarios() -> list[Scenario]:
    """Pessimistisch, basis en optimistisch naast elkaar.

    Alleen de onzekere aannames verschillen; alles in het koopscenario
    (woning, lening, kosten) blijft gelijk zodat het zuiver om aannames gaat.
    """
    return [
        _variant("Pessimistisch", 2.0, 4.0, 4.5, 5.2, 6.0, 2.5),
        _variant("Basis", 4.0, 6.0, 3.0, 4.2, 5.0, 2.0),
        _variant("Optimistisch", 6.0, 8.0, 1.5, 3.5, 4.0, 1.5),
    ]


def _variant(naam, wg, br, hh, rente, rente_na, infl):
    s = basis_scenario(
        waarde_groei=wg, beleg_rendement=br, huurverhoging=hh,
        hypotheekrente=rente, rente_na_rentevast=rente_na, inflatie=infl,
    )
    s.naam = naam
    return s
