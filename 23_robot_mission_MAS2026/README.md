# Robot Mission — MAS 2025-2026

**Group 23** — Khalil Ben Gamra · Sarra Sakgi · Ali Baklouti  
CentraleSupélec

---

## Description

Multi-agent simulation of robots collecting radioactive waste on a grid divided into three zones of increasing radioactivity. Robots work in a processing chain: green robots collect and fuse waste in zone 1, yellow robots process it further in zone 2, and red robots transport the final waste to a disposal zone in zone 3.

## Structure

```
├── agents.py    # GreenAgent, YellowAgent, RedAgent
├── objects.py   # RadioactivityAgent, WasteAgent, WasteDisposalZone
├── model.py     # RobotMission — grid, scheduler, broadcasts, emergency cleanup
├── server.py    # Interactive Solara visualisation
└── run.py       # Headless runner + matplotlib charts + scenario comparison
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

# Run all 3 scenarios and compare
python run.py --compare
```

---

## Environment

### Grid & zones

The environment is a **12×8** `MultiGrid` (Mesa) divided into three equal vertical zones:

| Zone | Columns | Radioactivity | Contents |
|---|---|---|---|
| **z1** (low) | 0–3 | 0.00 – 0.33 | Green waste spawns here |
| **z2** (medium) | 4–7 | 0.33 – 0.66 | Yellow waste spawns here |
| **z3** (high) | 8–11 | 0.66 – 1.00 | Red waste spawns here; contains disposal zone |

Each cell holds a `RadioactivityAgent` with a random value within its zone's range. A single `WasteDisposalZone` is placed at a random row on the rightmost column (`x = 11`).

### Waste lifecycle

Waste follows a transformation chain:

```
2 × green  ──>  1 × yellow 
        (green robot) 
2 x yellow ──> 1 × red  ──>  disposal zone (removed)
       (yellow robot)  (red robot)
```

- **Green waste** is placed randomly in z1 at initialization.
- **Yellow waste** can be placed in z2 at initialization, or produced by green robots fusing two green wastes.
- **Red waste** can be placed in z3 at initialization, or produced by yellow robots fusing two yellow wastes.
- Red waste is permanently removed when a red robot drops it at the disposal zone.

### Agents

| Robot | Movement zone | Home zone | Role |
|---|---|---|---|
| **GreenAgent** | z1 | z1 | Picks up to 2 green wastes → fuses into 1 yellow → transports east and drops. Can also transport yellow waste found in z1. |
| **YellowAgent** | z1–z2 | z1 border – z2 | Picks up to 2 yellow wastes → fuses into 1 red → transports east and drops. Can also transport red waste found in its zone. |
| **RedAgent** | z1–z3 | z2 border – z3 | Picks 1 red waste → navigates to the disposal zone → drops it for permanent removal. In emergency mode, picks any waste type. |

Each robot follows the **perceive → update → deliberate → act** loop:

1. **Perceive**: scan the current cell and all 8 Moore neighbors (radius 1).
2. **Update**: refresh internal knowledge (visited cells, visible waste positions) and emit broadcasts for waste types the robot cannot handle itself.
3. **Deliberate**: choose an action based on priority rules (transform > drop > pick > move toward target > explore).
4. **Act**: execute the chosen action (pick, drop, transform, move).

### Communication — Broadcast system

Robots emit **broadcasts** when they detect waste they cannot or should not handle:
- A broadcast contains the **position**, **waste type**, and **compatible robot types**.
- The model assigns each open broadcast to the **closest free compatible robot** (Manhattan distance).
- Broadcasts have a TTL (4 steps) and are automatically renewed if the waste is still present.
- When a robot picks up the targeted waste, the broadcast is released.

### Feature flags (toggleable enhancements)

| Flag | Default | Effect |
|---|---|---|
| `ENABLE_DROP_PATIENCE` | `True` | A robot holding a single waste (waiting for a second to fuse) will probabilistically drop it after a patience threshold. Prevents indefinite retention deadlocks. |
| `ENABLE_EAST_BIAS` | `True` | A robot carrying waste prioritizes eastward movement, accelerating the west-to-east processing chain. |

### Emergency cleanup mode

When fewer than 2 green wastes **and** fewer than 2 yellow wastes remain in the system (grid + carried), no more fusions are possible. The model activates **emergency cleanup**:

- Green and yellow robots drop whatever they are carrying.
- Red robots are assigned all remaining waste positions via broadcasts.
- Red robots pick **any** waste type (not just red) and transport it directly to the disposal zone.
- Priority is given to the most radioactive locations.

### Exploration strategy

- Robots track visited cells in their `knowledge["visited"]` set.
- When exploring, they prefer **unvisited cells in their home zone**, then unvisited cells anywhere in their movement zone, then any valid cell.
- This reduces redundant patrolling and improves coverage.

---

## Design choices

- **Integer zone bounds** (`x_min`/`x_max`) per robot instead of zone labels, for fast move validation.
- **Model/agent separation**: agents manage their own inventory and deliberation; the model handles grid effects, broadcasts, and emergency activation.
- **No collision**: robots avoid cells occupied by other robots (`_cell_free` check).
- **Drop cooldown**: after dropping waste, the cell is ignored for `DROP_MEMORY_STEPS` (5) to prevent pick-drop loops.
- **No physical disposal**: when a red robot drops waste at the disposal zone, no `WasteAgent` is created — the count increments `stored_red_waste` directly.

---

## Simulation results

### Scenario comparison

All scenarios use the same parameters for a fair comparison:  
**Grid**: 12×8 | **Robots**: 3 green, 3 yellow, 2 red | **Waste**: 20 green, 10 yellow, 5 red | **seed**: 123

| Scenario | Steps to clear | Red waste stored | Waste remaining at step 500 |
|---|---|---|---|
| Baseline (no enhancements) | 500 (timeout) | 13 | **5 (not cleared)** |
| Patience drop only | **127** | 15 | 0 |
| Patience drop + east bias | 184 | 15 | 0 |

**Key observations:**

- The **baseline** fails to clear all waste within 500 steps. 5 waste units remain stuck — this is the deadlock scenario where robots hold a single waste indefinitely waiting for a second one to fuse.
- **Patience drop** is the most impactful enhancement: it resolves the deadlock by allowing robots to probabilistically release waste they have been holding too long, making it available for other robots. This alone reduces completion time from 500+ to **127 steps**.
- **East bias** combined with patience drop takes slightly longer (184 steps) in this configuration. The east bias helps transport waste faster toward the next zone, but can sometimes push robots away from nearby waste they could pick up. Its benefit is more visible in configurations with high initial waste counts.

### Performance across configurations (all enhancements enabled)

| Config | Robots | Initial waste | Steps to clear | Stored |
|---|---|---|---|---|
| 1 | 2G 2Y 1R | 10G 5Y 2R | 186 | 7 |
| 2 | 4G 4Y 2R | 30G 15Y 8R | 152 | 23 |
| 3 | 1G 1Y 1R | 15G 5Y 3R | 261 | 10 |
| 4 | 6G 3Y 2R | 25G 0Y 0R | 112 | 7 |

**Observations:**

- **All configurations terminate successfully** with 0 remaining waste, demonstrating the robustness of the communication + patience drop + emergency cleanup combination.
- **More robots = faster convergence**: config 2 processes 53 total waste units in just 152 steps, while config 3 (1 robot per type) takes 261 steps for 23 waste units.
- **Pure green waste** (config 4, 25 green, 0 yellow, 0 red): the full transformation chain works correctly — 25 green → 12 yellow (via fusion) → 7 red (via fusion) → 7 stored. Completed in only 112 steps thanks to 6 green robots working in parallel.
- **Compression ratio**: 2 green → 1 yellow → 0.5 red, meaning the waste volume is divided by 4 through the chain. In config 4: 25 green waste becomes 7 stored red waste units.
- The **broadcast system** effectively coordinates robots: when a green robot spots yellow waste it can't handle, it broadcasts the location, and a nearby yellow robot claims and processes it.
- **Emergency cleanup** activates automatically when fusion is no longer possible, ensuring no waste is permanently stranded.

---

## Known issues (Step 1, now resolved in Step 2)

The following problems were identified during Step 1 and have been addressed:

| Issue | Solution in Step 2 |
|---|---|
| Indefinite waste retention (deadlock) | Patience drop mechanism — robots probabilistically release waste after holding too long |
| Drop position after transform | East bias — robots carry transformed waste eastward before dropping |
| Red robot bottleneck | Broadcast system — red robots are directed to waste locations instead of exploring randomly |
| No communication | Full broadcast system with TTL, priority, and closest-robot assignment |
| Blocked end-states | Emergency cleanup mode — red robots collect any remaining waste directly |

### Remaining limitations

- **Cell sharing**: two robots cannot occupy the same cell (enforced), but the grid remains a simplification of physical space.
- **Oscillation**: robots on adjacent cells can still swap positions in some edge cases.
- **East bias trade-off**: the east bias can sometimes delay pickup of nearby waste by pushing the robot away from it.

## Roadmap

| Step | Status | Description |
|---|---|---|
| Step 1 | ✅ | Agents without communication |
| Step 2 | ✅ | Agents with communication, broadcasts, patience drop, east bias, and emergency cleanup |

