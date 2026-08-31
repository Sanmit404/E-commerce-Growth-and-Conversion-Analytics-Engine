"""Small matplotlib helpers so the notebooks stay readable."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config

PALETTE = ["#2b6cb0", "#dd6b20", "#38a169", "#805ad5", "#e53e3e", "#718096"]


def setup() -> None:
    plt.rcParams.update(
        {
            "figure.figsize": (9, 5),
            "figure.dpi": 110,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "font.size": 10,
        }
    )


def save(fig, name: str) -> str:
    config.ensure_dirs()
    path = config.FIGURES_DIR / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    return str(path.relative_to(config.ROOT))


def funnel_chart(funnel: pd.DataFrame, title: str = "Session funnel"):
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(funnel))[::-1]
    ax.barh(y, funnel["sessions"], color=PALETTE[0], alpha=0.85)
    for pos, (_, row) in zip(y, funnel.iterrows()):
        label = f"{row['sessions']:,.0f}"
        if not np.isnan(row["step_conversion"]):
            label += f"   step {row['step_conversion']:.1%} | total {row['cumulative_conversion']:.2%}"
        ax.text(row["sessions"] * 1.02, pos, label, va="center", fontsize=9)
    ax.set_yticks(y, funnel["step"])
    ax.set_xlim(0, funnel["sessions"].max() * 1.45)
    ax.set_xlabel("Sessions")
    ax.set_title(title)
    return fig


def grouped_bars(df: pd.DataFrame, label_col: str, value_cols: list[str], title: str, ylabel: str, percent: bool = True):
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(df))
    width = 0.8 / len(value_cols)
    for i, col in enumerate(value_cols):
        ax.bar(x + i * width, df[col], width, label=col.replace("_", " "), color=PALETTE[i % len(PALETTE)])
    ax.set_xticks(x + width * (len(value_cols) - 1) / 2, df[label_col], rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    if percent:
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    return fig


def heatmap(matrix: pd.DataFrame, title: str, fmt: str = "{:.0%}", cmap: str = "Blues"):
    fig, ax = plt.subplots(figsize=(min(1.0 * matrix.shape[1] + 3, 14), 0.45 * matrix.shape[0] + 2))
    data = matrix.to_numpy(dtype=float)
    ax.imshow(np.ma.masked_invalid(data), cmap=cmap, aspect="auto")
    ax.set_xticks(range(matrix.shape[1]), matrix.columns)
    ax.set_yticks(range(matrix.shape[0]), [str(i)[:10] for i in matrix.index])
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            if not np.isnan(data[i, j]):
                ax.text(j, i, fmt.format(data[i, j]), ha="center", va="center", fontsize=7.5,
                        color="white" if data[i, j] > np.nanmax(data) * 0.55 else "black")
    ax.set_title(title)
    ax.grid(False)
    return fig


def scatter_quadrant(df: pd.DataFrame, x: str, y: str, label: str, title: str, xlabel: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.scatter(df[x], df[y], s=90, color=PALETTE[0], alpha=0.75)
    for _, row in df.iterrows():
        ax.annotate(row[label], (row[x], row[y]), textcoords="offset points", xytext=(7, 4), fontsize=9)
    ax.axvline(df[x].median(), color="grey", ls="--", lw=1)
    ax.axhline(df[y].median(), color="grey", ls="--", lw=1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return fig
