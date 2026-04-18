# Robot Mission — MAS 2025-2026

**Group 23** — Khalil Ben Gamra · Sarra Sakgi · Ali Baklouti  
CentraleSupélec

---

## Description

Multi-agent simulation of robots collecting radioactive waste on a 12×8 grid divided into three zones. Robots work in sequence: collection in z1, transformation in z2, storage in z3.

## Structure

```
├── agents.py    # GreenAgent, YellowAgent, RedAgent
├── objects.py   # RadioactivityAgent, WasteAgent, WasteDisposalZone
├── model.py     # RobotMission — grid, scheduler, do()
├── server.py    # Interactive Solara visualisation
└── run.py       # Headless runner + matplotlib charts
```

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
# Headless simulation (matplotlib output)
python run.py

# Interactive visualisation (http://localhost:8521)
python run.py --viz
```

## Agents & behaviour

| Robot | Zone | Role |
|---|---|---|
| Green | z1 | Picks 2 green wastes → transforms into 1 yellow → drops |
| Yellow | z1–z2 | Picks 2 yellow wastes → transforms into 1 red → drops |
| Red | z1–z3 | Picks 1 red waste → carries it to the disposal zone |

Each robot follows the loop **perceive → update → deliberate → act**. Robots now scan the **8 surrounding cells** and can emit local broadcasts when they detect a waste they cannot or should not handle themselves.

A broadcast contains the waste position and type. The **closest compatible free robot** claims the task, and the interactive view shows this with a signal halo on the sender, a dashed outline on the target waste, and a dotted line from the robot that accepted the mission.

Additional mandatory rule: when a green robot is carrying a yellow waste, and when a yellow robot is carrying a red waste, it must first push that waste as far east as possible within its allowed area before dropping it.

## Design choices

- **Integer zone bounds** (`x_min`/`x_max`) instead of zone labels, to simplify move validation.
- **Model/agent separation**: the model handles all grid effects; agents manage their own inventory.
- **Memory-based exploration**: robots prefer unvisited cells to reduce redundant patrolling.
- **No physical disposal object**: when the red robot drops waste at the disposal zone, no `WasteAgent` is created, the waste is counted in `stored_red_waste`.

## Results (Step 1, default parameters)

With 2 green robots, 2 yellow, 1 red, 12 initial green wastes we observe:

- Green waste clears quickly once robots cover z1.
- Yellow waste briefly accumulates before yellow robots process it.
- Two robots of the same type can each carry one unit of waste and never meet again, permanently blocking transformation since it requires 2 units held by the same robot.
- If the initial green waste count is not divisible by 2, the last lone waste can never be transformed and persists indefinitely in a robot's inventory.
- The red robot moves randomly and tends to stay near z3, making it very slow to reach z1/z2 where red waste accumulates creating a significant bottleneck in the disposal phase.
- Without communication, robots occasionally duplicate effort: the main motivation for Step 2.

## Known issues

The following problems were identified during Step 1 and are to be addressed in Step 2:

- **Drop position after transform**: when a robot transforms a waste, it drops the resulting waste on its current cell rather than moving east to the zone boundary first, which slows down pick-up by the next agent type.
- **Cell sharing**: two robots can occupy the same cell simultaneously, which is physically unrealistic.
- **Indefinite waste retention**: a robot that picks up a waste but never finds a second unit to pair with can hold it forever, creating a permanent deadlock.
- **Red robot bottleneck**: the red robot spends a disproportionate amount of time navigating from where it picks up a red waste all the way to the disposal zone, making it the main throughput bottleneck.
- **Inventory overflow**: a robot can carry more than 2 waste units at once (e.g. a green robot was observed holding 2 green wastes and 1 yellow waste simultaneously), violating the intended capacity constraint.
- **Oscillating robots**: when two robots face each other on adjacent cells (e.g. one at (1, 2) and the other at (1, 3)), they can swap positions which is unrealistic.

## Roadmap

| Step | Status | Description |
|---|---|---|
| Step 1 | ✅ | Agents without communication |
| Step 2 | 🔲 | Agents with communication and collaborative strategy |

