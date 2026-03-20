# Group: 23
# Date: 2026-03-16
# Members:
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import matplotlib.pyplot as plt
from model import RobotMission

# ------------------------------------------------------------------ #
#  Parameters                                                          #
# ------------------------------------------------------------------ #

PARAMS = dict(
    width=12,
    height=8,
    n_green_robots=2,
    n_yellow_robots=2,
    n_red_robots=1,
    initial_green_waste=12,
    seed=42,
)

MAX_STEPS = 200

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


def plot_results(model):
    df = model.datacollector.get_model_vars_dataframe()

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    # Waste counts over time
    ax1 = axes[0]
    for col, color in [("Green waste", "green"), ("Yellow waste", "goldenrod"), ("Red waste", "red")]:
        ax1.plot(df.index, df[col], label=col, color=color)
    ax1.set_ylabel("Waste count on grid")
    ax1.set_title("Waste evolution over time")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Stored red waste (cumulative)
    ax2 = axes[1]
    ax2.plot(df.index, df["Stored red waste"], color="darkred", label="Stored red waste")
    ax2.set_ylabel("Cumulative stored")
    ax2.set_xlabel("Step")
    ax2.set_title("Cumulative red waste stored in disposal zone")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("simulation_results.png", dpi=120)
    plt.show()


if __name__ == "__main__":
    model = run_simulation()
    plot_results(model)

