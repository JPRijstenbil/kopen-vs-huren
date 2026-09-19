"""Plot-functies voor het dashboard (Plotly, responsive voor mobiel)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from .engine import Resultaat

BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
GRIJS = "#7f7f7f"


def _leeg() -> go.Figure:
    return go.Figure()


def _basis_layout(fig: go.Figure, titel: str, ylabel: str = "") -> go.Figure:
    fig.update_layout(
        title=titel,
        template="plotly_white",
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(ticksuffix="  ", tickformat=",.0f")
    fig.update_yaxes(title=ylabel)
    return fig


def net_vermogen_figuur(
    resultaat: Resultaat,
    jaar_labels: np.ndarray,
    liquide: bool,
    breakeven: float | None,
    vergelijk_jaar: int,
    in_vandaag: bool,
    inflatie_cum: np.ndarray,
) -> go.Figure:
    k_all = resultaat.netto_kopen_liquide if liquide else resultaat.netto_kopen_bezit
    h_all = resultaat.netto_huren
    j = resultaat.jaar_indices()
    x = jaar_labels
    k = k_all[j]
    h = h_all[j]

    if in_vandaag:
        k = k / inflatie_cum[j]
        h = h / inflatie_cum[j]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=h, name="Huren", line=dict(color=ORANGE, width=3),
                             mode="lines"))
    fig.add_trace(go.Scatter(x=x, y=k, name="Kopen", line=dict(color=BLUE, width=3),
                             mode="lines"))
    # vergelijkingshorizon (op kalenderjaar-schaal)
    vergelijk_jaar_cal = float(x[0]) + float(vergelijk_jaar)
    fig.add_vline(x=vergelijk_jaar_cal, line_dash="dot", line_color=GRIJS, opacity=0.7)
    # break-even punt (op kalenderjaar-schaal, niet jaar-index)
    if breakeven is not None:
        breakeven_jaar = float(x[0]) + float(breakeven)
        if x[0] <= breakeven_jaar <= x[-1]:
            i = int(np.argmin(np.abs(x - breakeven_jaar)))
            fig.add_trace(go.Scatter(
                x=[breakeven_jaar], y=[k[i]], mode="markers+text",
                marker=dict(color=GREEN, size=12, symbol="star"),
                text=["Break-even"], textposition="top center",
                name="Break-even",
            ))
    fig.update_layout(
        title="Netto vermogen door de tijd",
        template="plotly_white", height=440,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(title="Netto vermogen (€)" if not in_vandaag else "Netto vermogen (€ van vandaag)",
                     tickformat=",.0f")
    fig.update_xaxes(title="Jaar")
    return fig


def bestemming_geld_figuur(resultaat: Resultaat, limit: int) -> go.Figure:
    """Cumulatieve bestemming van het geld over de gekozen horizon.

    Kosten = geld dat verdwijnt (negatief of apart), opbouw = vermogensgroei.
    """
    r = resultaat
    s = limit

    kopen_kosten = {
        "Hypotheekrente (netto)": float(r.rente[:s].sum() - np.maximum(r.hra_voordeel[:s], 0).sum()),
        "Onderhoud": float(r.onderhoud[:s].sum()),
        "Overige eigenaarskosten": float(
            (r.eigenaarskosten[:s] - r.onderhoud[:s] - r.ozb[:s]).sum()
            + r.ozb[:s].sum()
        ),
        "Belastingen (Box 3)": float(r.box3_kopen[:s].sum()),
        "Netto eigenwoningslast (EWF)": float(np.maximum(-r.hra_voordeel[:s], 0).sum()),
        "Transactiekosten (aankoop)": float(r.transactiekosten[:s].sum()),
    }
    kopen_opbouw = {
        "Aflossing → woning-equity": float(r.aflossing[:s].sum()),
        "Beleggingen → vermogen": float(r.belegging_kopen[s - 1]),
    }
    huren_kosten = {
        "Huur": float(r.huur[:s].sum()),
        "Servicekosten": float(r.service[:s].sum()),
        "Overige huurkosten": float(r.overige_huur[:s].sum()),
        "Belastingen (Box 3)": float(r.box3_huren[:s].sum()),
    }
    huren_opbouw = {
        "Beleggingen → vermogen": float(r.belegging_huren[s - 1]),
    }

    fig = go.Figure()
    for label, val in kopen_kosten.items():
        fig.add_trace(go.Bar(y=[label], x=[val], orientation="h", name=label,
                             marker_color=RED, legendgroup="kopen_kosten"))
    for label, val in kopen_opbouw.items():
        fig.add_trace(go.Bar(y=[label], x=[val], orientation="h", name=label,
                             marker_color=GREEN, legendgroup="kopen_opbouw"))

    fig2 = go.Figure()
    for label, val in huren_kosten.items():
        fig2.add_trace(go.Bar(y=[label], x=[val], orientation="h", name=label,
                              marker_color=RED, legendgroup="huren_kosten"))
    for label, val in huren_opbouw.items():
        fig2.add_trace(go.Bar(y=[label], x=[val], orientation="h", name=label,
                              marker_color=GREEN, legendgroup="huren_opbouw"))

    for f, titel in [(fig, "Kopen — bestemming van het geld"), (fig2, "Huren — bestemming van het geld")]:
        f.update_layout(
            title=titel, template="plotly_white", height=360,
            barmode="stack",
            margin=dict(l=10, r=10, t=50, b=10),
            showlegend=False,
            xaxis=dict(title="Cumulatief bedrag (€)", tickformat=",.0f"),
        )

    return fig, fig2


def tornado_figuur(resultaten: dict[str, tuple[float, float]], basis_verschil: float) -> go.Figure:
    """Tornado: effect van ±variantie per aanname op het netto vermogensverschil."""
    labels = list(resultaten.keys())
    lo = [resultaten[k][0] - basis_verschil for k in labels]
    hi = [resultaten[k][1] - basis_verschil for k in labels]
    order = sorted(range(len(labels)), key=lambda i: max(abs(lo[i]), abs(hi[i])))

    fig = go.Figure()
    for i in order:
        fig.add_trace(go.Bar(
            y=[labels[i]], x=[lo[i]], base=[0], orientation="h", name="Lager",
            marker_color=RED, offsetgroup=i, showlegend=False,
        ))
        fig.add_trace(go.Bar(
            y=[labels[i]], x=[hi[i]], base=[0], orientation="h", name="Hoger",
            marker_color=BLUE, offsetgroup=i, showlegend=False,
        ))
    fig.add_vline(x=0, line_color=GREEN, line_width=2)
    fig.update_layout(
        title="Sensitiviteit — effect op (kopen − huren) na de gekozen horizon",
        template="plotly_white", height=380, barmode="overlay",
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(title="Verandering in netto voordeel (€) t.o.v. basis", tickformat=",.0f"),
        showlegend=False,
    )
    return fig


def heatmap_figuur(x_vals, y_vals, z: np.ndarray) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        x=x_vals, y=y_vals, z=z,
        colorscale=[[0, "red"], [0.5, "white"], [1, "green"]],
        zmid=0,
        colorbar=dict(title="Voordeel (€)"),
        hovertemplate="Belegrendement %{x:.1f}%<br>Woninggroei %{y:.1f}%<br>Voordeel €%{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title="Waar wint kopen? (na gekozen horizon)",
        template="plotly_white", height=480,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(title="Beleggingsrendement (%)"),
        yaxis=dict(title="Woningwaardestijging (%)"),
    )
    # nul-contour
    cs = go.Contour(
        x=x_vals, y=y_vals, z=z,
        showscale=False, contours=dict(start=0, end=0, showlines=True),
        line=dict(color="black", width=2), opacity=0.7, contours_coloring="none",
        hovertemplate="",
    )
    fig.add_trace(cs)
    return fig
