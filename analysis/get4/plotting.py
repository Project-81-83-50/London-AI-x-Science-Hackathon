"""Figures: per-image segmentation and SE-versus-window plots, and the batch forest plot with its budget.

matplotlib is imported lazily (in `_style`), so the analysis runs without it when no figure is drawn.
"""

from pathlib import Path

import numpy as np

from .constants import Z95

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
PHASE_COLORS = {0: "#2a78d6", 1: "#eb6834", 2: "#1baf7a"}
BUDGET_COLORS = {"area": "#2a78d6", "regularity": "#eb6834", "between images": "#1baf7a"}


def _style():
    """matplotlib.pyplot with the report's colours applied (imported lazily: plotting is optional)."""
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK2,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "axes.edgecolor": GRID,
        }
    )
    return plt


def plot_image_report(labels: np.ndarray, result: dict, unit_len: float, out_png: Path) -> None:
    """Segmentation map plus SE-versus-window-size curves for every class of one image."""
    plt = _style()
    from matplotlib.colors import ListedColormap

    fig = plt.figure(figsize=(14, 8.5), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.35], hspace=0.35, wspace=0.25)

    ax = fig.add_subplot(gs[0, :])
    step = max(1, max(labels.shape) // 2000)
    class_names = result["class_names"]
    cmap = ListedColormap([PHASE_COLORS[k] for k in class_names])
    ax.imshow(labels[::step, ::step], cmap=cmap, interpolation="nearest", vmin=-0.5, vmax=len(class_names) - 0.5)
    ax.set_title(
        f"Segmentation: {result['image']}  (check this before trusting any number below)", loc="left", color=INK
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for k, name in class_names.items():
        ax.plot(
            [],
            [],
            "s",
            color=PHASE_COLORS[k],
            markersize=10,
            label=f"{name}  fraction={result['phases'][name]['phi']:.3f}",
        )
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)

    full_side = np.sqrt(labels.size) * unit_len
    for i, (k, name) in enumerate(class_names.items()):
        r = result["phases"][name]
        ax = fig.add_subplot(gs[1, i], facecolor=SURFACE)
        c = PHASE_COLORS[k]
        side = np.array([t["side"] for t in r["tiles"]]) * unit_len
        ax.plot(side, [t["naive_se"] for t in r["tiles"]], "--", color=INK2, lw=1.5, label="naive (pixels independent)")
        ax.plot(side, [t["predicted_se"] for t in r["tiles"]], "-", color=c, lw=2, label="predicted from C(r)")
        ax.plot(
            np.array([t["side"] for t in r["extrapolated"]]) * unit_len,
            [t["predicted_se"] for t in r["extrapolated"]],
            ":",
            color=c,
            lw=2,
            label="extrapolated (no tile check)",
        )
        ax.errorbar(
            side,
            [t["observed_se"] for t in r["tiles"]],
            yerr=[t["observed_se_err"] for t in r["tiles"]],
            fmt="o",
            color=c,
            mfc=SURFACE,
            mew=2,
            ms=8,
            elinewidth=1.5,
            capsize=0,
            label="observed spread across tiles",
        )
        ax.axvline(full_side, color=INK2, lw=1, ls=":")
        ax.plot([full_side], [r["se_image"]], "o", color=c, ms=8)
        ax.annotate(
            f"full image\n+-{Z95 * r['se_image']:.4f}",
            (full_side, r["se_image"]),
            xytext=(-6, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            color=INK2,
            fontsize=9,
        )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.grid(True, which="major", color=GRID, lw=0.8)
        ax.set_xlabel(f"window side length ({result['unit']})")
        if i == 0:
            metric = "phase fraction" if result["detector"] == "BSE" else "intensity-class fraction"
            ax.set_ylabel(f"standard error of {metric}")
            ax.legend(loc="lower left", frameon=False, fontsize=9)
        d = r["dispersion"]
        ax.set_title(f"{name}:  N_eff ~ {r['n_eff']:,.0f},  D = {d['D']:.2f}" if d else name, loc="left", color=INK)
        for s in ax.spines.values():
            s.set_visible(False)

    fig.savefig(out_png, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def plot_batch_report(batch: dict, out_png: Path, fraction_label: str = "phase fraction") -> None:
    """Forest plot per phase (each field, pooled CI, next-field interval) + uncertainty budget."""
    plt = _style()
    names = list(batch)
    n_img = batch[names[0]]["n_images"]
    fig = plt.figure(figsize=(14, 4.5 + 0.35 * n_img), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 3, height_ratios=[max(2.5, 0.35 * n_img + 1), 1.4], hspace=0.55, wspace=0.12)

    for i, name in enumerate(names):
        b = batch[name]
        ax = fig.add_subplot(gs[0, i], facecolor=SURFACE)
        ax.set_axisbelow(True)
        ys = np.arange(n_img, 0, -1) + 1
        for y, im in zip(ys, b["images"], strict=True):
            ax.errorbar(im["phi"], y, xerr=Z95 * im["se"], fmt="o", color=INK2, ms=7, elinewidth=2, capsize=0)
        lo, hi = b["ci95"]
        ax.fill([lo, b["phi"], hi, b["phi"]], [1, 1.25, 1, 0.75], color=INK, lw=0)
        ticks, ticklabels = list(ys) + [1], [im["image"] for im in b["images"]] + ["batch mean (95% CI)"]
        if b["prediction_interval_new_field"]:
            plo, phi_ = b["prediction_interval_new_field"]
            ax.errorbar(
                (plo + phi_) / 2, 0, xerr=(phi_ - plo) / 2, fmt="none", color=INK2, elinewidth=1.5, capsize=4, ls="none"
            )
            ticks.append(0)
            ticklabels.append("next field (95%)")
        ax.set_yticks(ticks)
        ax.set_yticklabels(ticklabels if i == 0 else [""] * len(ticks))
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(-0.7, n_img + 1.7)
        ax.grid(True, axis="x", color=GRID, lw=0.8)
        ax.set_xlabel(fraction_label)
        ax.set_title(f"{name}:  tau = {b['tau']:.4f},  I2 = {100 * b['I2']:.0f}%", loc="left", color=INK)
        for s in ax.spines.values():
            s.set_visible(False)

    ax = fig.add_subplot(gs[1, :], facecolor=SURFACE)
    for row, name in enumerate(names):
        bud = batch[name]["budget"]
        total = sum(bud.values())
        left = 0.0
        for comp, val in bud.items():
            share = val / total
            ax.barh(
                row,
                share,
                left=left,
                color=BUDGET_COLORS[comp],
                edgecolor=SURFACE,
                linewidth=2,
                height=0.6,
                label=comp if row == 0 else None,
            )
            if share > 0.06:
                ax.text(
                    left + share / 2, row, f"{100 * share:.0f}%", ha="center", va="center", color=SURFACE, fontsize=9
                )
            left += share
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("What drives the batch error bar (share of variance)", loc="left", color=INK)
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), frameon=False, ncol=3, fontsize=9)
    for s in ax.spines.values():
        s.set_visible(False)

    fig.savefig(out_png, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
