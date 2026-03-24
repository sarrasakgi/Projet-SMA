# Group: 23
# Date: 2026-03-16
# Members: 
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import random as _random
from mesa import Agent
from objects import WasteAgent

# ------------------------------------------------------------------ #
#  Feature flags — toggle before each scenario run                    #
# ------------------------------------------------------------------ #
ENABLE_DROP_PATIENCE = True   # robots drop waste after holding too long
ENABLE_EAST_BIAS     = True   # robots drift east when carrying waste


class RobotAgent(Agent):
    """Base class shared by all robot types."""

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model)
        self.x_min = x_min  # left boundary of allowed zone (inclusive)
        self.x_max = x_max  # right boundary of allowed zone (inclusive)
        self.home_x_min = home_x_min if home_x_min is not None else x_min
        self.home_x_max = home_x_max if home_x_max is not None else x_max
        self.drop_cooldown = {}   # pos -> steps until this cell is no longer ignored
        self.knowledge = {"visited": set(), "known_empty": set()}

    def _tick_cooldowns(self):
        self.drop_cooldown = {
            pos: t - 1 for pos, t in self.drop_cooldown.items() if t > 1
        }

    def _is_on_cooldown(self, pos):
        return pos in self.drop_cooldown

    def perceive(self):
        """Return current cell contents and immediate neighbor cell contents."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        return {
            "current": self.model.grid.get_cell_list_contents([self.pos]),
            "neighbors": {
                p: self.model.grid.get_cell_list_contents([p])
                for p in neighbors
            },
        }

    def move_random(self):
        """Prefer unvisited home-zone neighbors, fall back progressively."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid      = [p for p in neighbors if self.x_min <= p[0] <= self.x_max]
        not_cool   = [p for p in valid if not self._is_on_cooldown(p)]
        in_home    = [p for p in not_cool if self.home_x_min <= p[0] <= self.home_x_max]
        unvisited_home = [p for p in in_home if p not in self.knowledge["visited"]]
        unvisited_any  = [p for p in not_cool if p not in self.knowledge["visited"]]
        target_pool = unvisited_home or in_home or unvisited_any or not_cool or valid
        if target_pool:
            self.model.grid.move_agent(self, self.random.choice(target_pool))

    def move_east_biased(self):
        """Move east if possible, otherwise random. Used when carrying waste."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid = [p for p in neighbors if self.x_min <= p[0] <= self.x_max]
        east = [p for p in valid if p[0] > self.pos[0]]
        if east:
            self.model.grid.move_agent(self, self.random.choice(east))
        else:
            self.move_random()

    def _move_toward(self, target):
        """One step of greedy Manhattan navigation toward target, within zone."""
        x, y = self.pos
        tx, ty = target
        dx = (tx > x) - (tx < x)
        dy = (ty > y) - (ty < y)
        candidates = []
        if dx != 0:
            candidates.append((x + dx, y))
        if dy != 0:
            candidates.append((x, y + dy))
        valid = [p for p in candidates if self.x_min <= p[0] <= self.x_max]
        if valid:
            self.model.grid.move_agent(self, valid[0])
        else:
            self.move_random()


class GreenAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_green_wastes = 0
        self.n_yellow_wastes = 0
        self.steps_holding_green = 0
        self.knowledge = {
            "visited": set(),
            "known_empty": set(),
            "position": None,
            "green_wastes_here": [],
            "green_waste_neighbor_pos": None,
        }

    @property
    def _patience(self):
        return self.model.width * 2  # 50% drop prob reached after 2*width steps

    # ------------------------------------------------------------------ #
    #  Perception → Belief update                                          #
    # ------------------------------------------------------------------ #

    def update(self, percepts):
        """Refresh the agent's knowledge from raw perception."""
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        # Ignore waste on cooldown cells
        self.knowledge["green_wastes_here"] = (
            [] if self._is_on_cooldown(self.pos) else [
                a for a in percepts["current"]
                if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"
            ]
        )
        self.knowledge["green_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if not self._is_on_cooldown(pos)
             and any(isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"
                     for a in contents)),
            None,
        )
        # Memory: update known_empty based on what we see
        if self.knowledge["green_wastes_here"]:
            self.knowledge["known_empty"].discard(self.pos)
        else:
            self.knowledge["known_empty"].add(self.pos)
        for pos, contents in percepts["neighbors"].items():
            has_waste = any(
                isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"
                for a in contents
            )
            if has_waste:
                self.knowledge["known_empty"].discard(pos)
            else:
                self.knowledge["known_empty"].add(pos)

    # ------------------------------------------------------------------ #
    #  Deliberation → choose action                                        #
    # ------------------------------------------------------------------ #

    def _in_cleanup_mode(self):
        green_on_grid = self.model.count_green_waste()
        yellow_on_grid = self.model.count_yellow_waste()
        green_held = sum(getattr(a, "n_green_wastes", 0) for a in self.model.agents if isinstance(a, GreenAgent))
        yellow_held = sum(getattr(a, "n_yellow_wastes", 0) for a in self.model.agents if isinstance(a, YellowAgent))
        return (green_on_grid + green_held) <= 1 and (yellow_on_grid + yellow_held) <= 1

    def deliberate(self):
        """Return the highest-priority action given current knowledge."""
        # Stop during cleanup mode — but drop any held waste first
        if self._in_cleanup_mode() and self.model.count_red_waste() == 0:
            if self.n_yellow_wastes == 1:
                return "drop"
            if self.n_green_wastes > 0:
                return "drop_green"
            return "wait"
        # 1. Hands full → transform immediately
        if self.n_green_wastes == 2:
            return "transform"
        # 2. Carrying a yellow waste → move to rightmost col of z1 then drop
        if self.n_yellow_wastes == 1:
            if self.pos[0] == self.x_max:
                return "drop"
            return "move_east"
        # 3. Holding 1 green too long → probabilistic early drop
        if ENABLE_DROP_PATIENCE and self.n_green_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_green / self._patience)
            if _random.random() < drop_prob:
                return "drop_green"
        # 4. Green waste on current cell and capacity available → pick it up
        #    Never pick green while already holding yellow
        if self.knowledge["green_wastes_here"] and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            return "pick"
        # 5. Green waste spotted in a neighbor cell → move toward it
        if self.knowledge["green_waste_neighbor_pos"] and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            return "move_toward_waste"
        # 6. Nothing visible → drift east if carrying (and flag on), else explore
        if ENABLE_EAST_BIAS and self.n_green_wastes > 0:
            return "move_east"
        return "move"

    # ------------------------------------------------------------------ #
    #  Action execution                                                    #
    # ------------------------------------------------------------------ #

    def act(self, action):
        if action == "pick":
            waste = self.knowledge["green_wastes_here"][0]
            self.model.grid.remove_agent(waste)
            self.n_green_wastes += 1
            self.steps_holding_green = 0

        elif action == "transform":
            self.n_green_wastes = 0
            self.n_yellow_wastes = 1
            self.steps_holding_green = 0

        elif action == "drop_green":
            waste = WasteAgent(self.model, waste_type="green")
            self.model.grid.place_agent(waste, self.pos)
            self.n_green_wastes = 0
            self.steps_holding_green = 0
            self.drop_cooldown[self.pos] = self.model.width // 3

        elif action == "drop":
            waste = WasteAgent(self.model, waste_type="yellow")
            self.model.grid.place_agent(waste, self.pos)
            self.n_yellow_wastes = 0

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["green_waste_neighbor_pos"])

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

        elif action == "wait":
            pass

        if self.n_green_wastes == 1:
            self.steps_holding_green += 1

    # ------------------------------------------------------------------ #
    #  Mesa step                                                           #
    # ------------------------------------------------------------------ #

    def step(self):
        self._tick_cooldowns()
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)


class YellowAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_yellow_wastes = 0
        self.n_red_wastes = 0
        self.steps_holding_yellow = 0
        self.knowledge = {
            "visited": set(),
            "known_empty": set(),
            "position": None,
            "yellow_wastes_here": [],
            "yellow_waste_neighbor_pos": None,
        }

    @property
    def _patience(self):
        return self.model.width * 2  # 50% drop prob reached after 2*width steps

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self.knowledge["yellow_wastes_here"] = (
            [] if self._is_on_cooldown(self.pos) else [
                a for a in percepts["current"]
                if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"
            ]
        )
        self.knowledge["yellow_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if not self._is_on_cooldown(pos)
             and any(isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"
                     for a in contents)),
            None,
        )
        # Memory: update known_empty based on what we see
        if self.knowledge["yellow_wastes_here"]:
            self.knowledge["known_empty"].discard(self.pos)
        else:
            self.knowledge["known_empty"].add(self.pos)
        for pos, contents in percepts["neighbors"].items():
            has_waste = any(
                isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"
                for a in contents
            )
            if has_waste:
                self.knowledge["known_empty"].discard(pos)
            else:
                self.knowledge["known_empty"].add(pos)

    def _in_cleanup_mode(self):
        green_on_grid = self.model.count_green_waste()
        yellow_on_grid = self.model.count_yellow_waste()
        green_held = sum(getattr(a, "n_green_wastes", 0) for a in self.model.agents if isinstance(a, GreenAgent))
        yellow_held = sum(getattr(a, "n_yellow_wastes", 0) for a in self.model.agents if isinstance(a, YellowAgent))
        return (green_on_grid + green_held) <= 1 and (yellow_on_grid + yellow_held) <= 1

    def deliberate(self):
        # Stop during cleanup mode — but drop any held waste first
        if self._in_cleanup_mode() and self.model.count_red_waste() == 0:
            if self.n_red_wastes == 1:
                return "drop"
            if self.n_yellow_wastes > 0:
                return "drop_yellow"
            return "wait"
        if self.n_yellow_wastes == 2:
            return "transform"
        # Carrying red → move to rightmost col of z2 then drop
        if self.n_red_wastes == 1:
            if self.pos[0] == self.x_max:
                return "drop"
            return "move_east"
        if ENABLE_DROP_PATIENCE and self.n_yellow_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_yellow / self._patience)
            if _random.random() < drop_prob:
                return "drop_yellow"
        # Never pick yellow while already holding red
        if self.knowledge["yellow_wastes_here"] and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "pick"
        if self.knowledge["yellow_waste_neighbor_pos"] and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "move_toward_waste"
        if ENABLE_EAST_BIAS and (self.n_yellow_wastes > 0 or self.n_red_wastes > 0):
            return "move_east"
        return "move"

    def act(self, action):
        if action == "pick":
            waste = self.knowledge["yellow_wastes_here"][0]
            self.model.grid.remove_agent(waste)
            self.n_yellow_wastes += 1
            self.steps_holding_yellow = 0

        elif action == "transform":
            self.n_yellow_wastes = 0
            self.n_red_wastes = 1
            self.steps_holding_yellow = 0

        elif action == "drop_yellow":
            waste = WasteAgent(self.model, waste_type="yellow")
            self.model.grid.place_agent(waste, self.pos)
            self.n_yellow_wastes = 0
            self.steps_holding_yellow = 0
            self.drop_cooldown[self.pos] = self.model.width // 3

        elif action == "drop":
            waste = WasteAgent(self.model, waste_type="red")
            self.model.grid.place_agent(waste, self.pos)
            self.n_red_wastes = 0

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["yellow_waste_neighbor_pos"])

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

        elif action == "wait":
            pass

        if self.n_yellow_wastes == 1:
            self.steps_holding_yellow += 1

    def step(self):
        self._tick_cooldowns()
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)


class RedAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_red_wastes = 0
        self.n_cleanup_wastes = 0       # leftover green/yellow carried in cleanup mode
        self.cleanup_waste_type = None  # type of waste currently carried in cleanup
        self._sweep_col = 0             # current sweep column
        self._sweep_row = None          # current sweep row (None = start at top)
        self.knowledge = {
            "visited": set(),
            "known_empty": set(),
            "position": None,
            "red_wastes_here": [],
            "red_waste_neighbor_pos": None,
            "any_waste_here": [],       # any waste type, for cleanup mode
            "any_waste_neighbor_pos": None,
            "disposal_zone_pos": None,  # unknown until discovered
            "at_disposal_zone": False,
        }

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self.knowledge["red_wastes_here"] = [
            a for a in percepts["current"]
            if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"
        ]
        self.knowledge["red_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if any(isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"
                    for a in contents)),
            None,
        )
        # Discover disposal zone by seeing a WasteDisposalZone object
        from objects import WasteDisposalZone
        for obj in percepts["current"]:
            if isinstance(obj, WasteDisposalZone):
                self.knowledge["disposal_zone_pos"] = self.pos
        for pos, contents in percepts["neighbors"].items():
            for obj in contents:
                if isinstance(obj, WasteDisposalZone):
                    self.knowledge["disposal_zone_pos"] = pos
        self.knowledge["at_disposal_zone"] = (
            self.pos == self.knowledge["disposal_zone_pos"]
        )
        # Cleanup: see any waste regardless of type
        self.knowledge["any_waste_here"] = [
            a for a in percepts["current"] if isinstance(a, WasteAgent)
        ]
        self.knowledge["any_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if any(isinstance(a, WasteAgent) for a in contents)),
            None,
        )

    def _advance_sweep(self):
        """Zigzag sweep: even columns top→bottom, odd columns bottom→top."""
        H = self.model.height
        W = self.model.width
        if self._sweep_row is None:
            self._sweep_row = H - 1 if self._sweep_col % 2 == 0 else 0
            return
        if self._sweep_col % 2 == 0:
            self._sweep_row -= 1
            if self._sweep_row < 0:
                self._sweep_col += 1
                self._sweep_row = 0 if self._sweep_col % 2 == 0 else H - 1
        else:
            self._sweep_row += 1
            if self._sweep_row >= H:
                self._sweep_col += 1
                self._sweep_row = H - 1 if self._sweep_col % 2 == 0 else 0
        if self._sweep_col >= W:
            self._sweep_col = 0
            self._sweep_row = H - 1

    def _sweep_target(self):
        if self._sweep_row is None:
            self._sweep_row = self.model.height - 1 if self._sweep_col % 2 == 0 else 0
        return (self._sweep_col, self._sweep_row)

    def _cleanup_mode(self):
        """True when leftover waste can never be transformed further:
        - at most 1 green waste on grid AND no green robot holding green
        - at most 1 yellow waste on grid AND no yellow robot holding yellow
        """
        green_on_grid = self.model.count_green_waste()
        yellow_on_grid = self.model.count_yellow_waste()

        green_held = sum(
            getattr(a, "n_green_wastes", 0) for a in self.model.agents
            if isinstance(a, GreenAgent)
        )
        yellow_held = sum(
            getattr(a, "n_yellow_wastes", 0) for a in self.model.agents
            if isinstance(a, YellowAgent)
        )

        green_stuck = green_on_grid + green_held <= 1
        yellow_stuck = yellow_on_grid + yellow_held <= 1

        return green_stuck and yellow_stuck

    def deliberate(self):
        # Normal pipeline: carry red to disposal
        if self.n_red_wastes == 1:
            if self.knowledge["at_disposal_zone"]:
                return "drop"
            if self.knowledge["disposal_zone_pos"]:
                return "move_to_disposal"
            return "move_east"
        if self.knowledge["red_wastes_here"] and self.n_red_wastes == 0:
            return "pick"
        if self.knowledge["red_waste_neighbor_pos"] and self.n_red_wastes == 0:
            return "move_toward_waste"

        # Cleanup mode: only enter when red pipeline is also done
        if self._cleanup_mode() and self.model.count_red_waste() == 0 and self.n_red_wastes == 0:
            if self.n_cleanup_wastes > 0:
                if self.knowledge["at_disposal_zone"]:
                    return "cleanup_drop"
                if self.knowledge["disposal_zone_pos"]:
                    return "move_to_disposal"
                return "move_east"
            if self.knowledge["any_waste_here"]:
                return "cleanup_pick"
            # Sweep: move toward current sweep target
            target = self._sweep_target()
            if self.pos == target:
                return "sweep_advance"
            return "sweep_move"

        return "move"

    def act(self, action):
        if action == "pick":
            waste = self.knowledge["red_wastes_here"][0]
            self.model.grid.remove_agent(waste)
            self.n_red_wastes += 1

        elif action == "drop":
            self.n_red_wastes = 0
            self.model.stored_red_waste += 1

        elif action == "move_to_disposal":
            self._move_toward(self.knowledge["disposal_zone_pos"])

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["red_waste_neighbor_pos"])

        elif action == "cleanup_pick":
            waste = self.knowledge["any_waste_here"][0]
            self.cleanup_waste_type = waste.waste_type
            self.model.grid.remove_agent(waste)
            self.n_cleanup_wastes += 1

        elif action == "cleanup_drop":
            self.n_cleanup_wastes = 0
            self.cleanup_waste_type = None
            self.model.stored_red_waste += 1

        elif action == "sweep_advance":
            self._advance_sweep()

        elif action == "sweep_move":
            self._move_toward(self._sweep_target())

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

    def step(self):
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)