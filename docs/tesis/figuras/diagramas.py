#!/usr/bin/env python3
"""Diagramas de la tesis: topología, pipeline de datos y lazo cerrado.

  python docs/tesis/figuras/diagramas.py   -> topologia.png, pipeline.png, lazo_cerrado.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})

# paleta sobria, legible en impresión en escala de grises
C_CTRL = "#dbe7f3"   # control
C_NET = "#e8eef0"    # conmutadores
C_HOST = "#f4f4f4"   # hosts
C_ATK = "#f6dcdc"    # atacante / ataque
C_ML = "#e3f0e0"     # aprendizaje automático
C_EDGE = "#333333"


def box(ax, x, y, w, h, text, fc, fs=9, bold=False, ls="-"):
    p = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                       fc=fc, ec=C_EDGE, lw=1.0, ls=ls)
    ax.add_patch(p)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal",
            wrap=True)


def arrow(ax, p0, p1, ls="-", color=C_EDGE, lw=1.1, style="-|>", rad=0.0, label=None, lpos=0.5,
          loff=(0, 0.12), fs=8):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=11, lw=lw, color=color, ls=ls,
                        connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2)
    ax.add_patch(a)
    if label:
        mx = p0[0] + (p1[0] - p0[0]) * lpos + loff[0]
        my = p0[1] + (p1[1] - p0[1]) * lpos + loff[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs, style="italic",
                bbox=dict(fc="white", ec="none", pad=0.5))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def topologia():
    fig, ax = canvas(12, 6.2)
    ax.set_xlim(-0.6, 12)  # margen para la curva del espejo
    # controlador
    box(ax, 6, 5.7, 4.3, 0.6, "Controlador Ryu (OpenFlow 1.3)\nL2 + mitigación + anti-spoofing + REST",
        C_CTRL, fs=8.5, bold=True)
    # spines
    spines = [(4.2, 4.5), (7.8, 4.5)]
    for i, (x, y) in enumerate(spines, 1):
        box(ax, x, y, 1.6, 0.5, f"s_spine_{i}", C_NET, bold=True)
    # leafs
    zonas = [("s_iot_0", "Infraestructura", "6 servidores\n+ atacante"),
             ("s_iot_1", "Hogar", "15 disp."), ("s_iot_2", "Industrial", "12 disp."),
             ("s_iot_3", "Salud", "8 disp."), ("s_iot_4", "Ciudad", "8 disp."),
             ("s_iot_5", "Vestibles", "6 disp."), ("s_iot_6", "Agricultura", "6 disp."),
             ("s_iot_7", "Comercio", "5 disp.")]
    xs = [0.85 + i * 1.47 for i in range(8)]
    for x, (sw, zona, hosts) in zip(xs, zonas):
        for sx, sy in spines:
            ax.plot([sx, x], [sy - 0.25, 2.95], color="#888888", lw=0.7, zorder=0)
        box(ax, x, 2.7, 1.25, 0.5, sw, C_NET, fs=8.5, bold=True)
        fc = C_ATK if sw == "s_iot_0" else C_HOST
        box(ax, x, 1.55, 1.3, 0.95, f"Zona {sw[-1]}\n{zona}\n{hosts}", fc, fs=7.8)
        ax.plot([x, x], [2.45, 2.03], color=C_EDGE, lw=0.9)
    # canal de control
    for sx, sy in spines:
        ax.plot([6, sx], [5.4, sy + 0.25], color="#1f5a8a", lw=0.9, ls="--")
    ax.text(9.9, 5.15, "canal OpenFlow a los\n10 conmutadores", fontsize=7.5, color="#1f5a8a",
            style="italic", ha="center")
    # espejo
    box(ax, xs[0], 0.35, 1.3, 0.42, "mon0 (espejo)\ntcpdump", C_ML, fs=7.5)
    arrow(ax, (xs[0] - 0.63, 2.7), (xs[0] - 0.66, 0.35), ls=":", rad=0.45, color="#2d6a2d")
    ax.text(xs[0] + 0.75, 0.35, "puerto espejo de s_iot_0 (solo ingreso)", fontsize=7.5, color="#2d6a2d",
            style="italic", va="center")
    ax.text(6, 3.55, "malla completa spine-leaf con RSTP", fontsize=7.5, color="#555555", ha="center",
            style="italic", bbox=dict(fc="white", ec="none", pad=1))
    fig.savefig(OUT / "topologia.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def pipeline():
    fig, ax = canvas(12, 3.4)
    y1, y2 = 2.55, 0.85
    top = [(1.1, "Simuladores IoT\n(60 disp.) +\n13 ataques × 6 episodios", C_ATK),
           (3.55, "Captura tcpdump\nen puerto espejo\n(PCAP)", C_NET),
           (6.0, "Extracción de flujos\n(quíntupla, streaming,\nagregados O(1))", C_HOST),
           (8.45, "Etiquetado\n(manifiestos de ataque:\norigen, objetivo, episodio)", C_HOST),
           (10.9, "Ingeniería de\ncaracterísticas\n(50 por flujo)", C_HOST)]
    bot = [(10.9, "Tope 50.000\nflujos/clase\n(semilla 42)", C_HOST),
           (8.45, "Validación cruzada\nagrupada por episodio\n(StratifiedGroupKFold, 5)", C_ML),
           (6.0, "Modelos: RF, XGB, MLP\n+ Isolation Forest,\nAutoEncoder", C_ML),
           (3.55, "Análisis: SHAP, UMAP,\ncalibración, robustez,\nprevalencia", C_ML),
           (1.1, "Validación externa\nCIC-IoT-2023\n(39 caract. comunes)", C_CTRL)]
    for x, t, c in top:
        box(ax, x, y1, 2.1, 1.0, t, c, fs=8)
    for x, t, c in bot:
        box(ax, x, y2, 2.1, 1.0, t, c, fs=8)
    for (a, _, _), (b, _, _) in zip(top, top[1:]):
        arrow(ax, (a + 1.08, y1), (b - 1.08, y1))
    arrow(ax, (10.9, y1 - 0.52), (10.9, y2 + 0.52))
    for (a, _, _), (b, _, _) in zip(bot, bot[1:]):
        arrow(ax, (a - 1.08, y2), (b + 1.08, y2))
    fig.savefig(OUT / "pipeline.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def lazo():
    fig, ax = canvas(12, 4.6)
    y = 3.4
    steps = [(1.1, "Red IoT emulada\n(Mininet + OVS)", C_HOST),
             (3.4, "Captura continua\ntcpdump (espejo\ns_iot_0)", C_NET),
             (5.7, "Extractor en vivo\nsnapshots cada 5 s\n+ 50 características", C_HOST),
             (8.0, "Etapa 1: XGBoost\ndetección\n(2 umbrales)", C_ML),
             (10.3, "Etapa 2: Random Forest\natribución del tipo", C_ML)]
    for x, t, c in steps:
        box(ax, x, y, 2.0, 1.0, t, c, fs=8.2)
    for (a, _, _), (b, _, _) in zip(steps, steps[1:]):
        arrow(ax, (a + 1.03, y), (b - 1.03, y))
    box(ax, 10.3, 1.35, 2.3, 1.25,
        "Política de mitigación\n• origen único → DROP origen\n• origen distribuido → LIMIT\n  64 kbps al destino\n"
        "• amplificación → LIMIT\n  consultas al reflector", C_ATK, fs=7.4)
    box(ax, 6.9, 1.35, 2.2, 0.95, "POST /iot/mitigate\n(REST del controlador)", C_CTRL, fs=8)
    box(ax, 3.5, 1.35, 2.4, 0.95, "Ryu instala reglas OpenFlow\nen los 10 conmutadores\n(tabla 0, vigencia 60 s)",
        C_CTRL, fs=8)
    arrow(ax, (10.3, y - 0.52), (10.3, 1.35 + 0.64), label="incidente", lpos=0.5, loff=(0.45, 0))
    arrow(ax, (10.3 - 1.17, 1.35), (6.9 + 1.12, 1.35))
    arrow(ax, (6.9 - 1.12, 1.35), (3.5 + 1.22, 1.35))
    arrow(ax, (3.5 - 1.22, 1.35), (1.1, y - 0.52), rad=-0.25, label="contención", lpos=0.45,
          loff=(-0.45, 0))
    ax.text(6.0, 0.25, "Resultado (5 corridas): 65/65 ataques mitigados · TTM mediana 5,3 s · 0 falsas alarmas · "
            "reducción mediana 94,6 %", ha="center", fontsize=8.5, style="italic", color="#333333")
    fig.savefig(OUT / "lazo_cerrado.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    topologia()
    pipeline()
    lazo()
    print("OK:", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))
