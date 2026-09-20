"""Nederlands fiscaal model voor de koopwoning en Box 3.

Deze module bevat uitsluitend rekenlogica, los van de simulatie-engine. Alle
percentages en drempels zitten in ``FiscaleConfig`` (een dataclass) zodat
jaarlijkse wijzigingen in de belastingwetgeving zonder aanpassing van de
rekenlogica kunnen worden bijgewerkt.

Box 1 (eigen woning):
    Netto voordeel = (aftrekbare_rente - EWF) * tarief, met de Wet Hillen-demping
    wanneer het EWF de rente overtreft (wordt afgebouwd tot 2048).

Box 3 (sparen en beleggen):
    Twee heffingsmethoden, configureerbaar:
      - fictief rendement (huidig systeem): heffing over een forfaitair
        rendement op het vermogen boven het heffingsvrije vermogen.
      - werkelijk rendement: heffing over het werkelijk behaalde rendement
        (koerswinst + dividend - kosten) van het jaar, incl. ongerealiseerde
        waardeveranderingen.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Box 1: eigen woning
# ---------------------------------------------------------------------------

@dataclass
class EigenWoningFiscaal:
    """Box-1 regels voor de eigen woning.

    - hra_tarief_pct: effectief marginaal tarief waartegen renteaftrek werkt.
    - ewf_percentage_pct: eigenwoningforfait als % van de WOZ-waarde.
      Wordt gemodelleerd als een (ondergrens, percentage)-tabel; het percentage
      van de eerste schijf geldt boven de laatste vermelde ondergrens, tenzij
      een expliciete bovengrens is bereikt.
    - wet_hillen_afbouw_pct: 1.0 = Wet Hillen volledig van kracht (EWF boven
      rente onbelast), 0.0 = volledig afgebouwd. Default ~2019-2025 waarde.
    """
    hra_tarief_pct: float = 37.0
    box1_marginaal_tarief_pct: float = 37.0
    ewf_schijven: list[tuple[float, float]] = field(
        default_factory=lambda: [(0.0, 0.35)]
    )
    ewf_hoge_grens: float | None = None
    ewf_hoog_pct: float = 2.35
    wet_hillen_afbouw_pct: float = 1.0
    wet_hillen_basisjaar: int = 2026
    wet_hillen_afbouw_per_jaar: float = 0.048

    def ewf_percentage(self, woz_waarde: float) -> float:
        """EWF-percentage passend bij de WOZ-waarde (laatste schijf die geldt)."""
        pct = self.ewf_schijven[0][1]
        for ondergrens, p in self.ewf_schijven:
            if woz_waarde >= ondergrens:
                pct = p
        return pct

    def ewf_bedrag(self, woz_waarde: float) -> float:
        """Eigenwoningforfait in euro's, inclusief correcte villabelasting."""
        basiswaarde = min(woz_waarde, self.ewf_hoge_grens or woz_waarde)
        basis_pct = self.ewf_percentage(basiswaarde)
        if self.ewf_hoge_grens is None or woz_waarde <= self.ewf_hoge_grens:
            return woz_waarde * basis_pct / 100.0
        return (
            self.ewf_hoge_grens * basis_pct / 100.0
            + (woz_waarde - self.ewf_hoge_grens) * self.ewf_hoog_pct / 100.0
        )

    def wet_hillen_factor(self, jaar: int | None) -> float:
        if jaar is None:
            return self.wet_hillen_afbouw_pct
        verstreken = max(jaar - self.wet_hillen_basisjaar, 0)
        return max(self.wet_hillen_afbouw_pct - verstreken * self.wet_hillen_afbouw_per_jaar, 0.0)


def hra_ewf_jaarvoordeel(
    aftrekbare_rente: float,
    woz_waarde: float,
    fiscaal: EigenWoningFiscaal,
    jaar: int | None = None,
) -> float:
    """Netto jaarlijks belastingvoordeel uit eigen woning (positief = voordeel).

    - pos voordeel = netto renteaftrek (rente > EWF)
    - negatief = netto bijtelling (EWF > rente), gedempt door Wet Hillen.
    """
    ewf = fiscaal.ewf_bedrag(woz_waarde)
    aftrektarief = fiscaal.hra_tarief_pct / 100.0
    marginaal_tarief = fiscaal.box1_marginaal_tarief_pct / 100.0
    voordeel = aftrekbare_rente * aftrektarief - ewf * marginaal_tarief
    if aftrekbare_rente < ewf:
        voordeel += (
            (ewf - aftrekbare_rente)
            * marginaal_tarief
            * fiscaal.wet_hillen_factor(jaar)
        )
    return voordeel


# ---------------------------------------------------------------------------
# Box 3: sparen en beleggen
# ---------------------------------------------------------------------------

@dataclass
class Box3Regels:
    """Box-3 regels geldig voor een reeks kalenderjaren.

    - tarief_pct: belastingtarief op het (fictieve of werkelijke) rendement.
    - spaarforfait_pct: forfaitair rendement op spaargeld (fictief systeem).
    - beleggingsforfait_pct: forfaitair rendement op beleggingen (fictief).
    - heffingsvrij: vrijgesteld vermogen per persoon (x 2 bij fiscaal partner).
    """
    jaar_vanaf: int
    jaar_tot: int | None
    tarief_pct: float
    spaarforfait_pct: float
    beleggingsforfait_pct: float
    heffingsvrij_per_persoon: float
    fiscaal_partner: bool = False

    @property
    def heffingsvrij_totaal(self) -> float:
        return self.heffingsvrij_per_persoon * (2 if self.fiscaal_partner else 1)


@dataclass
class Box3Stelsel:
    """Een reeks Box-3 regels per kalenderjaar, met fallback naar de laatste."""

    regels: list[Box3Regels]

    def voor_jaar(self, jaar: int) -> Box3Regels:
        gevonden = self.regels[-1]
        for r in self.regels:
            if r.jaar_vanaf <= jaar:
                if r.jaar_tot is None or jaar <= r.jaar_tot:
                    gevonden = r
        return gevonden


def box3_fictief_belasting(
    totaal_vermogen: float,
    spaar_deel: float,
    regels: Box3Regels,
) -> float:
    """Belasting (in euro's) onder het fictieve-rendement-systeem.

    Het heffingsvrije vermogen verlaagt de grondslag pro rata, conform de
    Overbruggingswet box 3.
    """
    if totaal_vermogen <= 0:
        return 0.0
    belastbaar = max(totaal_vermogen - regels.heffingsvrij_totaal, 0.0)
    if belastbaar <= 0:
        return 0.0

    spaar = min(max(spaar_deel, 0.0), totaal_vermogen)
    belegging = max(totaal_vermogen - spaar, 0.0)
    forfaitair_rendement = (
        spaar * regels.spaarforfait_pct / 100.0
        + belegging * regels.beleggingsforfait_pct / 100.0
    )
    return forfaitair_rendement * (belastbaar / totaal_vermogen) * regels.tarief_pct / 100.0


def box3_werkelijk_belasting(
    werkelijk_rendement: float,
    regels: Box3Regels,
) -> float:
    """Belasting onder het werkelijk-rendement-systeem.

    Werkelijk rendement = koerswinst + dividend over het jaar
    (inclusief ongerealiseerde waardeveranderingen).

    Onder de tegenbewijsregeling is er geen heffingsvrij vermogen en geen
    jaaroverschrijdende verliesverrekening.
    """
    return max(werkelijk_rendement, 0.0) * regels.tarief_pct / 100.0


# ---------------------------------------------------------------------------
# Belasting op vermogensgroei die de 'verkoop' van een woning raakt
# ---------------------------------------------------------------------------

def verkoopwinst_is_onbelast() -> bool:
    """In Nederland is de meerwaarde op de eigen woning vrijgesteld (Box 1).
    Beleggingen vallen echter in Box 3 en worden jaarlijks belast via de
    bovenstaande heffingsmethoden.
    """
    return True
