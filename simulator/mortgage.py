"""Hypotheekleningmodellen.

Elk leningdeel wordt per maand gesimuleerd. Het leningdeel houdt de
resterende hoofdsom, betaalde rente en aflossing per maand bij. Op deze
manier kunnen meerdere leningdelen (annuïtair, lineair, aflossingsvrij,
verschillende rentes/looptijden) later eenvoudig naast elkaar draaien.

Alle bedragen zijn in euro's. Rentes zijn jaarlijks (percentage) en worden
per maand omgerekend via een effectief maandtarief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Aflossingstype(str, Enum):
    ANNUITAIR = "annuïtair"
    LINEAIR = "lineair"
    AFLOSSINGSVRIJ = "aflossingsvrij"


def jaarlijks_naar_maandelijks(jaarrente_pct: float) -> float:
    """Zet een effectieve jaarrente (in %) om naar een maandrente-fractie."""
    r = jaarrente_pct / 100.0
    return (1.0 + r) ** (1.0 / 12.0) - 1.0


def annuitaire_maandlast(hoofdsom: float, maandrente: float, looptijd_maanden: int) -> float:
    """Vaste maandlast voor een annuïteitenhypotheek (rente + aflossing).

    Formule: M = P * r * (1+r)^n / ((1+r)^n - 1)
    """
    if looptijd_maanden <= 0:
        return 0.0
    if maandrente == 0.0:
        return hoofdsom / looptijd_maanden
    factor = (1.0 + maandrente) ** looptijd_maanden
    return hoofdsom * maandrente * factor / (factor - 1.0)


@dataclass
class Leningdeel:
    """Eén leningdeel. Simuleert maandelijks rente en aflossing.

    - annuïtair: vaste maandlast, aflossing neemt toe over tijd
    - lineair: vaste aflossing, maandlast neemt af over tijd
    - aflossingsvrij: alleen rente, schuld blijft gelijk
    """
    hoofdsom: float
    rente_pct: float
    aflossingstype: Aflossingstype
    looptijd_maanden: int
    rentevaste_periode_maanden: int | None = None
    rente_na_rentevast_pct: float | None = None
    hra_toepassen: bool = True  # recht op hypotheekrenteaftrek ja/nee

    schuld: float = field(init=False)
    maandrente: float = field(init=False)
    _vast_maandbedrag: float = field(init=False, default=0.0)
    _vaste_aflossing: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.schuld = self.hoofdsom
        self.maandrente = jaarlijks_naar_maandelijks(self.rente_pct)
        if self.aflossingstype == Aflossingstype.ANNUITAIR:
            self._vast_maandbedrag = annuitaire_maandlast(
                self.hoofdsom, self.maandrente, self.looptijd_maanden
            )
        elif self.aflossingstype == Aflossingstype.LINEAIR:
            self._vaste_aflossing = (
                self.hoofdsom / self.looptijd_maanden if self.looptijd_maanden > 0 else 0.0
            )

    def _current_rente(self, maand_index: int) -> float:
        """Rente geldend in maand_index (0-gebaseerd), rekening houdend met
        het einde van de rentevaste periode."""
        if (
            self.rente_na_rentevast_pct is not None
            and self.rentevaste_periode_maanden is not None
            and maand_index >= self.rentevaste_periode_maanden
        ):
            return jaarlijks_naar_maandelijks(self.rente_na_rentevast_pct)
        return self.maandrente

    def simulatie_maand(self, maand_index: int) -> tuple[float, float]:
        """Draai één maand. Retourneert (betaalde_rente, aflossing).

        De rente wordt altijd over de schuld aan het begin van de maand
        berekend; daarna volgt de aflossing (of niet).
        """
        if self.schuld <= 0.0:
            return 0.0, 0.0

        rente = self.schuld * self._current_rente(maand_index)

        if self.aflossingstype == Aflossingstype.ANNUITAIR:
            aflossing = min(self._vast_maandbedrag - rente, self.schuld)
        elif self.aflossingstype == Aflossingstype.LINEAIR:
            aflossing = min(self._vaste_aflossing, self.schuld)
        else:  # aflossingsvrij
            aflossing = 0.0

        self.schuld -= aflossing
        # Null-afronding: vermijd -0.0 / negatieve schuld door drijvende-kommafouten
        if self.schuld < 1e-9:
            self.schuld = 0.0
        return rente, aflossing

    def maandlast(self, maand_index: int) -> float:
        """Totale maandlast (rente + aflossing) in een gegeven maand."""
        if self.aflossingstype == Aflossingstype.ANNUITAIR:
            return self._vast_maandbedrag
        if self.aflossingstype == Aflossingstype.LINEAIR:
            return self._vaste_aflossing + self.schuld * self._current_rente(maand_index)
        # aflossingsvrij
        return self.schuld * self._current_rente(maand_index)
