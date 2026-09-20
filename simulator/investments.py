"""Beleggingsrekening.

Houdt het belegde vermogen bij. Maandelijks wordt:
1. rendement toegevoegd over het beginvermogen van de maand (exclusief de
   storting van die maand, d.w.z. rendement op geïnvesteerd kapitaal),
2. TER (Total Expense Ratio) afgetrokken,
3. de vrije cashflow van die maand bijgestort,
4. eventuele Box 3-belasting afgerekend (jaarlijks, zie tax module).

Het model gebruikt bewust géén vaste 'netto rendement na Box 3'-parameter:
Box 3 wordt als aparte jaarlijkse heffing afgetrokken, zodat het fiscale
effect transparant blijft en per kalenderjaar configureerbaar is.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def jaarlijks_naar_maandelijks(jaarrente_pct: float) -> float:
    r = jaarrente_pct / 100.0
    return (1.0 + r) ** (1.0 / 12.0) - 1.0


@dataclass
class Beleggingsrekening:
    """Beleggingsrekening met maandelijks doorrekenend rendement.

    Optioneel wordt een onderscheid gemaakt tussen koersrendement en
    dividend/uitkering (beide jaarlijks %). Wanneer alleen een enkel
    bruto rendement is gegeven, wordt dit als koersrendement gebruikt en
    staat dividend op 0. Dit onderscheid is van belang voor het 'werkelijk
    rendement'-pad van Box 3.
    """
    koersrendement_pct: float
    dividend_pct: float = 0.0
    ter_pct: float = 0.0  # jaarlijkse Total Expense Ratio

    vermogen: float = field(init=False, default=0.0)
    _maand_koers: float = field(init=False)
    _maand_dividend: float = field(init=False)
    _maand_ter: float = field(init=False)

    def __post_init__(self) -> None:
        self._maand_koers = jaarlijks_naar_maandelijks(self.koersrendement_pct)
        self._maand_dividend = jaarlijks_naar_maandelijks(self.dividend_pct)
        self._maand_ter = jaarlijks_naar_maandelijks(self.ter_pct)

    def beginwaarde(self, bedrag: float) -> None:
        """Zet het aanvangsvermogen (bestaande belegging of kas dat wordt belegd)."""
        self.vermogen = bedrag

    def draai_maand(self, storting: float) -> tuple[float, float, float]:
        """Draai één maand met een bijstorting (vrije cashflow, kan 0 zijn).

        Retourneert (koers_winst, dividend_winst, kosten) van deze maand.
        Het rendement wordt over het beginvermogen gerekend, vóór de storting,
        zodat een storting van die maand niet direct rendeert.
        """
        begin = self.vermogen
        renderend = max(begin, 0.0)
        koers_winst = renderend * self._maand_koers
        dividend_winst = renderend * self._maand_dividend
        kosten = (renderend + koers_winst + dividend_winst) * self._maand_ter
        self.vermogen = begin + koers_winst + dividend_winst - kosten + storting
        return koers_winst, dividend_winst, kosten

    def stort(self, bedrag: float) -> None:
        """Stort een bedrag bij (of onttrek, indien negatief) zonder rendement."""
        self.vermogen += bedrag

    def betaal_belasting(self, belasting: float) -> None:
        """Trek een belastingheffing (bv. Box 3) af van het vermogen."""
        self.vermogen -= belasting
