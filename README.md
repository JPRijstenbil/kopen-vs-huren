# Kopen vs Huren — Nederlands vermogensdashboard

Eerlijke maandelijkse vermogens- en cashflowsimulatie voor de vraag
**"kopen of huren?"** in Nederland. Geen simpele maandlastencalculator — een
volledige simulatie van netto vermogen en cashflow over de tijd.

## Kernidee

Beide scenario's starten met **hetzelfde startvermogen en maandbudget**.
Alles dat na de woonlasten overblijft wordt belegd. Het antwoord is simpelweg:
welk scenario heeft op tijdstip T het hoogste **netto vermogen**?

- **Kopen** = woningwaarde − hypotheekschuld + beleggingen + cash
  (optioneel rekening houdend met verkoopkosten alsof je nu verkoopt)
- **Huren** = beleggingen + cash

De vergelijking is eerlijk omdat:
- aflossing **geen kostenpost** is maar vermogensopbouw (equity),
- de eigen inbreng bij kopen **opportunity cost** heeft (hij kan niet renderen),
- Box 3 (sparen/beleggen) en Box 1 (HRA/EWF/Wet Hillen) **expliciet** worden
  geheven, niet verdisconteerd in een "netto rendement"-aanname.

## Starten

```bash
cd ~/ai-projects/kopen-vs-huren
source .venv/bin/activate
streamlit run app.py
```

Open **http://localhost:8501**. Voor mobiel: draai dit op de laptop en open
`http://<laptop-ip>:8501` in de browser op je telefoon (op hetzelfde netwerk,
of via Tailscale).

## Tests

```bash
cd ~/ai-projects/kopen-vs-huren
source .venv/bin/activate
pytest tests/ -q
```

## Architectuur

De rekenlogica staat los van de presentatie:

```
simulator/
  engine.py        # maandelijkse vermogens- en cashflowsimulatie (beide scenario's)
  mortgage.py      # annuïtair / lineair / aflossingsvrij leningdelen
  investments.py   # beleggingsrekening (maandelijks rendement + TER)
  tax.py           # Box 1 (HRA/EWF/Wet Hillen) + Box 3 (fictief & werkelijk rendement)
  config.py        # dataclasses voor alle invoerparameters
  scenarios.py     # Nederlandse defaults + pessimistisch/basis/optimistisch
  plotting.py      # Plotly-grafieken
app.py             # Streamlit-dashboard (UI)
tests/test_engine.py
```

## Fiscale basis (2026)

- Box 3: tarief 36%, heffingsvrij vermogen €59.357 p.p., bankforfait voorlopig
  1,28% en beleggingsforfait 6,00%. De tegenbewijsoptie kiest jaarlijks de
  laagste heffing van fictief en werkelijk rendement; bij werkelijk rendement
  geldt geen vrijstelling en geen verliesverrekening tussen jaren.
- Eigenwoningforfait: 0,35% tot €1.350.000, daarna €4.725 plus 2,35% over het
  meerdere. Wet Hillen resteert in 2026 voor 71,867% en bouwt verder af.
- Maximale hypotheekrenteaftrek hoge inkomens: 37,56% in 2026.
- Startersvrijstelling: woningwaarde maximaal €555.000; daarnaast gelden
  leeftijds-, gebruiks- en eenmaligheidsvoorwaarden.
- NHG 2026: grens €470.000 en borgtochtprovisie 0,4%.

Bronnen: Belastingdienst en NHG; laatst gecontroleerd september 2026.

## Modelkeuzes en beperkingen

- **Eén leningdeel** in de UI, maar de engine ondersteunt meerdere (de structuur
  in `LeningdeelConfig`/`Leningdeel` is al meervoudig).
- **Nieuwe aflossingsvrije delen** krijgen alleen HRA als je dat per leningdeel
  aanvinkt (`hra`-vlag) — geen automatische HRA.
- **Box 3 fictief rendement** is de basis; de tegenbewijsoptie vergelijkt dit
  met werkelijk rendement inclusief ongerealiseerde koerswinst.
- **Geen eigen inflatiebonus op de hypotheekschuld** als winstpost; het effect
  van nominale schuld komt al terug via de overige nominale kosten.
- Alle fiscale percentages/drempels zijn **configuratie** (in `scenarios.py` en
  de UI), niet hardcoded — jaarlijkse wijzigingen zijn daarmee eenvoudig.
- Monte Carlo en historische datasets zijn bewust nog niet toegevoegd; de
  engine is zo opgezet dat ze later eenvoudig kunnen worden toegevoegd.

## Disclaimer

Indicatieve Nederlandse fiscale defaults (2026). Geen financieel advies —
controleer actuele wetgeving en je eigen cijfers.
