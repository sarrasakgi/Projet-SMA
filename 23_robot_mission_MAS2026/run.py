# Group: 23
# Date: 2026-03-16
# Members:
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import random
import matplotlib.pyplot as plt
import agents as _agents_module
from datetime import datetime
from model import RobotMission

# ------------------------------------------------------------------ #
#  Parameters                                                          #
# ------------------------------------------------------------------ #

def make_params():
    return dict(
        width=12,
        height=8,
        n_green_robots=random.randint(1, 6),
        n_yellow_robots=random.randint(1, 6),
        n_red_robots=random.randint(1, 4),
        initial_green_waste=random.randint(2, 30),
        initial_yellow_waste=random.randint(0, 20),
        initial_red_waste=random.randint(0, 10),
        seed=None,
    )

PARAMS = make_params()

MAX_STEPS = 500

# ------------------------------------------------------------------ #
#  Run                                                                 #
# ------------------------------------------------------------------ #

def run_simulation(params=PARAMS, max_steps=MAX_STEPS, verbose=True):
    model = RobotMission(**params)

    for step in range(max_steps):
        # Stop early if all waste has been stored
        if (
            model.count_green_waste() == 0
            and model.count_yellow_waste() == 0
            and model.count_red_waste() == 0
        ):
            if verbose:
                print(f"All waste cleared at step {step}.")
            break
        model.step()

    if verbose:
        print(f"\n=== Final state after {step + 1} steps ===")
        print(f"  Green waste remaining : {model.count_green_waste()}")
        print(f"  Yellow waste remaining: {model.count_yellow_waste()}")
        print(f"  Red waste remaining   : {model.count_red_waste()}")
        print(f"  Stored red waste      : {model.stored_red_waste}")
        print(f"  Green→Yellow transforms: {model.transformed_green_to_yellow}")
        print(f"  Yellow→Red transforms  : {model.transformed_yellow_to_red}")

    return model


def _conditions_text(params):
    return (
        f"Grid: {params['width']}×{params['height']}  |  "
        f"Robots: {params['n_green_robots']} green, {params['n_yellow_robots']} yellow, {params['n_red_robots']} red  |  "
        f"Initial green waste: {params['initial_green_waste']}"
    )


def plot_results(model, params=PARAMS):
    df = model.datacollector.get_model_vars_dataframe()

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    fig.suptitle(_conditions_text(params), fontsize=9, color="#444444")

    ax1 = axes[0][0]
    for col, color in [("Green waste", "green"), ("Yellow waste", "goldenrod"), ("Red waste", "red")]:
        ax1.plot(df.index, df[col], label=col, color=color)
    ax1.set_ylabel("Waste count on grid")
    ax1.set_title("Waste on grid over time")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2 = axes[0][1]
    ax2.plot(df.index, df["Stored red waste"], color="darkred", label="Stored red waste")
    ax2.set_ylabel("Cumulative stored")
    ax2.set_title("Cumulative red waste stored")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    ax3 = axes[1][0]
    ax3.plot(df.index, df["Total waste"], color="#555555", label="Total waste (grid + robots)")
    ax3.set_ylabel("Waste units")
    ax3.set_xlabel("Step")
    ax3.set_title("Total waste in system (grid + robots)")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    ax4 = axes[1][1]
    ax4.plot(df.index, df["Weighted waste"], color="#7700cc", label="Weighted (×1/×2/×4)")
    ax4.set_ylabel("Weighted sum")
    ax4.set_xlabel("Step")
    ax4.set_title("Weighted waste: green×1 + yellow×2 + red×4")
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    filename = f"simulation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(filename, dpi=120)
    print(f"\nSaved → {filename}")
    plt.show()


SCENARIOS = [
    {"name": "Baseline (no enhancements)",      "drop": False, "east": False},
    {"name": "With patience drop",               "drop": True,  "east": False},
    {"name": "With patience drop + east bias",   "drop": True,  "east": True},
]


def run_all_scenarios(params=None, max_steps=MAX_STEPS):
    if params is None:
        params = make_params()
    results = []
    for scenario in SCENARIOS:
        # Set feature flags
        _agents_module.ENABLE_DROP_PATIENCE = scenario["drop"]
        _agents_module.ENABLE_EAST_BIAS     = scenario["east"]

        print(f"\n--- {scenario['name']} ---")
        model = run_simulation(params=params, max_steps=max_steps, verbose=True)
        df = model.datacollector.get_model_vars_dataframe()
        results.append({"name": scenario["name"], "df": df})

    # Reset flags to defaults
    _agents_module.ENABLE_DROP_PATIENCE = True
    _agents_module.ENABLE_EAST_BIAS     = True

    return results


def plot_comparison(results, params=PARAMS):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=False)
    fig.suptitle(f"Scenario comparison  —  {_conditions_text(params)}", fontsize=9, color="#444444")

    for col, (scenario) in enumerate(results):
        df   = scenario["df"]
        name = scenario["name"]

        ax1 = axes[0][col]
        for series, color in [
            ("Green waste",  "green"),
            ("Yellow waste", "goldenrod"),
            ("Red waste",    "red"),
        ]:
            ax1.plot(df.index, df[series], label=series, color=color)
        ax1.set_title(name, fontsize=8)
        ax1.set_ylabel("Waste on grid")
        ax1.legend(fontsize=7)
        ax1.grid(True, alpha=0.3)

        ax2 = axes[1][col]
        ax2.plot(df.index, df["Stored red waste"], color="darkred")
        ax2.set_ylabel("Stored red waste")
        ax2.set_xlabel("Step")
        ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    filename = f"scenario_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(filename, dpi=120)
    print(f"\nSaved → {filename}")
    plt.show()


if __name__ == "__main__":
    import sys
    if "--viz" in sys.argv:
        import subprocess
        subprocess.run([sys.executable, "-m", "solara", "run", "server.py", "--port", "8521"])
    elif "--compare" in sys.argv:
        results = run_all_scenarios()
        plot_comparison(results)
    else:
        model = run_simulation()
        plot_results(model)

