# Group: 23
# Date: 2026-03-16
# Members:
#     Khalil Ben Gamra
#     Sarra Sakgi
#     Ali Baklouti

import solara
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure

from mesa.visualization import SolaraViz, Slider
from mesa.visualization.utils import update_counter

from model import RobotMission
from agents import GreenAgent, YellowAgent, RedAgent
from objects import RadioactivityAgent, WasteAgent, WasteDisposalZone


# ------------------------------------------------------------------ #
#  Colour palette                                                      #
# ------------------------------------------------------------------ #

ZONE_COLORS    = {"z1": "#c8f0c8", "z2": "#faf0b0", "z3": "#f5c8c8"}
WASTE_COLORS   = {"green": "#00cc00", "yellow": "#e6b800", "red": "#dd0000"}
ROBOT_COLORS   = {"green": "#00bb00", "yellow": "#ddaa00", "red": "#ee1111"}
DISPOSAL_COLOR = "#333333"


# ------------------------------------------------------------------ #
#  Custom grid component                                               #
# ------------------------------------------------------------------ #

@solara.component
def GridView(model):
    update_counter.get()
    if model is None:
        return

    W, H = model.width, model.height
    third = W // 3

    fig = Figure(figsize=(W * 0.75, H * 0.75))
    ax = fig.add_subplot(111)
    ax.set_xlim(-0.5, W - 0.5)
    ax.set_ylim(-0.5, H - 0.5)
    ax.set_aspect("equal")
    ax.set_xticks(range(W))
    ax.set_yticks(range(H))
    ax.tick_params(labelsize=7)

    # ── Zone background: one big rect per zone ──────────────────────
    zone_spans = [
        ("z1", 0,         third),
        ("z2", third,     2 * third),
        ("z3", 2 * third, W),
    ]
    for zone, x0, x1 in zone_spans:
        rect = mpatches.FancyBboxPatch(
            (x0 - 0.5, -0.5), x1 - x0, H,
            boxstyle="square,pad=0",
            facecolor=ZONE_COLORS[zone], edgecolor="none", zorder=0,
        )
        ax.add_patch(rect)

    # ── Grid lines ───────────────────────────────────────────────────
    for x in range(W + 1):
        ax.axvline(x - 0.5, color="white", lw=0.6, zorder=1)
    for y in range(H + 1):
        ax.axhline(y - 0.5, color="white", lw=0.6, zorder=1)

    # ── Zone border lines ────────────────────────────────────────────
    for x in [third - 0.5, 2 * third - 0.5]:
        ax.axvline(x, color="#888888", lw=1.5, zorder=2)

    # ── Agents ──────────────────────────────────────────────────────
    robot_lookup = {}
    for contents, (x, y) in model.grid.coord_iter():
        wastes  = [a for a in contents if isinstance(a, WasteAgent)]
        robots  = [a for a in contents if isinstance(a, (GreenAgent, YellowAgent, RedAgent))]
        dispz   = [a for a in contents if isinstance(a, WasteDisposalZone)]

        # Disposal zone marker
        if dispz:
            ax.add_patch(mpatches.Rectangle(
                (x - 0.4, y - 0.4), 0.8, 0.8,
                facecolor=DISPOSAL_COLOR, edgecolor="white", lw=1, zorder=3,
            ))

        # Waste dots (small filled circle, centered in cell)
        n = len(wastes)
        for i, w in enumerate(wastes):
            # spread up to 4 wastes in a 2x2 grid centered on the cell
            offsets = [(0, 0), (0.2, 0), (0, 0.2), (0.2, 0.2)]
            ox, oy = offsets[i % 4]
            cx = x - (0.1 if n > 1 else 0) + ox
            cy = y - (0.1 if n > 1 else 0) + oy
            ax.add_patch(mpatches.Circle(
                (cx, cy), 0.13,
                facecolor=WASTE_COLORS.get(w.waste_type, "grey"),
                edgecolor="white", lw=0.5, zorder=4,
            ))

        # Robots: empty circle outline + small filled dot if carrying
        for robot in robots:
            robot_lookup[getattr(robot, "unique_id", None)] = (x, y)
            if isinstance(robot, GreenAgent):
                rcolor = ROBOT_COLORS["green"]
                carried = getattr(robot, "n_green_wastes", 0)
                ccolor  = WASTE_COLORS["green"]
                ctype   = "green" if carried else None
                # also might carry yellow after transform
                if getattr(robot, "n_yellow_wastes", 0):
                    ctype = "yellow"
            elif isinstance(robot, YellowAgent):
                rcolor = ROBOT_COLORS["yellow"]
                ctype  = None
                if getattr(robot, "n_yellow_wastes", 0):
                    ctype = "yellow"
                elif getattr(robot, "n_red_wastes", 0):
                    ctype = "red"
            else:  # RedAgent
                rcolor = ROBOT_COLORS["red"]
                ctype  = getattr(robot, "carried_waste_type", None) if getattr(robot, "n_red_wastes", 0) else None

            # Outer empty circle
            ax.add_patch(mpatches.Circle(
                (x, y), 0.38,
                facecolor="none", edgecolor=rcolor, lw=3.5, zorder=5,
            ))
            # Inner dot showing carried waste
            if ctype:
                ax.add_patch(mpatches.Circle(
                    (x, y), 0.18,
                    facecolor=WASTE_COLORS[ctype], edgecolor="none", zorder=6,
                ))

    # ── Broadcasts and task claims ──────────────────────────────────
    for msg in getattr(model, "active_broadcasts", []):
        tx, ty = msg["pos"]
        sx, sy = msg["sender_pos"]
        color = WASTE_COLORS.get(msg["waste_type"], "#444444")

        ax.add_patch(mpatches.Circle(
            (sx, sy), 0.48,
            facecolor="none", edgecolor=color, linestyle=":", lw=1.5,
            alpha=0.6, zorder=6,
        ))
        ax.add_patch(mpatches.Rectangle(
            (tx - 0.47, ty - 0.47), 0.94, 0.94,
            facecolor="none", edgecolor=color, linestyle="--", lw=1.8,
            alpha=0.8, zorder=7,
        ))

        claimer_pos = robot_lookup.get(msg.get("claimed_by"))
        if claimer_pos is not None:
            cx, cy = claimer_pos
            ax.plot([cx, tx], [cy, ty], color=color, linestyle=":", lw=1.3, alpha=0.85, zorder=7)

    # ── Legend ───────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(color=ZONE_COLORS["z1"],   label="Zone 1 (low)"),
        mpatches.Patch(color=ZONE_COLORS["z2"],   label="Zone 2 (med)"),
        mpatches.Patch(color=ZONE_COLORS["z3"],   label="Zone 3 (high)"),
        mpatches.Patch(color=WASTE_COLORS["green"],  label="Green waste"),
        mpatches.Patch(color=WASTE_COLORS["yellow"], label="Yellow waste"),
        mpatches.Patch(color=WASTE_COLORS["red"],    label="Red waste"),
        mpatches.Patch(facecolor="none", edgecolor=ROBOT_COLORS["green"],  lw=2, label="Green robot"),
        mpatches.Patch(facecolor="none", edgecolor=ROBOT_COLORS["yellow"], lw=2, label="Yellow robot"),
        mpatches.Patch(facecolor="none", edgecolor=ROBOT_COLORS["red"],    lw=2, label="Red robot"),
    ]
    ax.legend(handles=legend_handles, loc="upper left",
              bbox_to_anchor=(1.01, 1), fontsize=7, framealpha=0.8)

    fig.tight_layout()
    solara.FigureMatplotlib(fig, format="png")
    plt.close(fig)


# ------------------------------------------------------------------ #
#  Chart components                                                    #
# ------------------------------------------------------------------ #

@solara.component
def WasteChart(model):
    update_counter.get()
    if model is None or not hasattr(model, "datacollector"):
        return
    df = model.datacollector.get_model_vars_dataframe()
    fig = Figure(figsize=(5, 3))
    ax = fig.subplots()
    for col, color in [
        ("Green waste",  WASTE_COLORS["green"]),
        ("Yellow waste", WASTE_COLORS["yellow"]),
        ("Red waste",    WASTE_COLORS["red"]),
    ]:
        if col in df.columns:
            ax.plot(df[col], label=col, color=color, lw=1.5)
    ax.set_title("Waste in environment", fontsize=9)
    ax.set_xlabel("Step", fontsize=8)
    ax.legend(fontsize=7)
    fig.tight_layout()
    solara.FigureMatplotlib(fig, format="png")
    plt.close(fig)


@solara.component
def StorageChart(model):
    update_counter.get()
    if model is None or not hasattr(model, "datacollector"):
        return
    df = model.datacollector.get_model_vars_dataframe()
    fig = Figure(figsize=(5, 3))
    ax = fig.subplots()
    if "Stored red waste" in df.columns:
        ax.plot(df["Stored red waste"], color=ROBOT_COLORS["red"],
                label="Stored red waste", lw=1.5)
    ax.set_title("Stored red waste", fontsize=9)
    ax.set_xlabel("Step", fontsize=8)
    ax.legend(fontsize=7)
    fig.tight_layout()
    solara.FigureMatplotlib(fig, format="png")
    plt.close(fig)


@solara.component
def EventLog(model):
    update_counter.get()
    if model is None:
        return

    entries = list(reversed(getattr(model, "event_log", [])[-8:]))
    heading = "### Broadcasts and claims"
    if getattr(model, "emergency_cleanup", False):
        heading += "\n**Emergency cleanup active:** red robots are disposing the remaining waste."
    if not entries:
        solara.Markdown(heading + "\n_No signal emitted yet._")
        return

    content = "\n".join(f"- {entry}" for entry in entries)
    solara.Markdown(f"{heading}\n{content}")


# ------------------------------------------------------------------ #
#  Model params                                                        #
# ------------------------------------------------------------------ #

model_params = {
    "width":               Slider("Grid width",          value=12, min=6,  max=24, step=3),
    "height":              Slider("Grid height",         value=8,  min=4,  max=16, step=2),
    "n_green_robots":      Slider("Green robots",        value=2,  min=1,  max=6,  step=1),
    "n_yellow_robots":     Slider("Yellow robots",       value=2,  min=1,  max=6,  step=1),
    "n_red_robots":        Slider("Red robots",          value=1,  min=1,  max=4,  step=1),
    "initial_green_waste": Slider("Initial green waste", value=12, min=2,  max=30, step=2),
    "seed":                None,
}

# ------------------------------------------------------------------ #
#  App entry point                                                     #
# ------------------------------------------------------------------ #

initial_model = RobotMission()


@solara.component
def Page():
    SolaraViz(
        initial_model,
        components=[
            (GridView, 0),
            (WasteChart, 0),
            (StorageChart, 0),
            (EventLog, 0),
        ],
        model_params=model_params,
        name="Robot Mission — Group 23",
    )


app = Page
