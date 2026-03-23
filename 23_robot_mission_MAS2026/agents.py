# Group: 23
# Date: 2026-03-16
# Members: 
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

from mesa import Agent
from objects import WasteAgent


class RobotAgent(Agent):
    """Base class shared by all robot types."""

    def __init__(self, model, x_min, x_max):
        super().__init__(model)
        self.x_min = x_min  # left boundary of allowed zone (inclusive)
        self.x_max = x_max  # right boundary of allowed zone (inclusive)
        self.knowledge = {"visited": set()}

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

    def _cell_free(self, pos):
        """Return True if no other robot occupies pos."""
        return not any(
            isinstance(a, RobotAgent) and a is not self
            for a in self.model.grid.get_cell_list_contents([pos])
        )

    def move_random(self):
        """Prefer unvisited neighbors; fall back to any valid neighbor."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid = [p for p in neighbors if self.x_min <= p[0] <= self.x_max and self._cell_free(p)]
        unvisited = [p for p in valid if p not in self.knowledge.get("visited", set())]
        target_pool = unvisited if unvisited else valid
        if target_pool:
            self.model.grid.move_agent(self, self.random.choice(target_pool))

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
        valid = [p for p in candidates if self.x_min <= p[0] <= self.x_max and self._cell_free(p)]
        if valid:
            self.model.grid.move_agent(self, valid[0])
        else:
            self.move_random()


class GreenAgent(RobotAgent):

    def __init__(self, model, x_min, x_max):
        super().__init__(model, x_min, x_max)
        self.n_green_wastes = 0
        self.n_yellow_wastes = 0
        self.knowledge = {
            "visited": set(),
            "position": None,
            "green_wastes_here": [],
            "green_waste_neighbor_pos": None,
        }

    # ------------------------------------------------------------------ #
    #  Perception → Belief update                                          #
    # ------------------------------------------------------------------ #

    def update(self, percepts):
        """Refresh the agent's knowledge from raw perception."""
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self.knowledge["green_wastes_here"] = [
            a for a in percepts["current"]
            if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"
        ]
        self.knowledge["green_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if any(isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"
                    for a in contents)),
            None,
        )

    # ------------------------------------------------------------------ #
    #  Deliberation → choose action                                        #
    # ------------------------------------------------------------------ #

    def deliberate(self):
        """Return the highest-priority action given current knowledge."""
        # 1. Hands full → transform immediately
        if self.n_green_wastes == 2:
            return "transform"
        # 2. Carrying a yellow waste → drop it for YellowAgents to collect
        if self.n_yellow_wastes == 1:
            return "drop"
        # 3. Green waste on current cell and capacity available → pick it up
        if self.knowledge["green_wastes_here"] and self.n_green_wastes < 2:
            return "pick"
        # 4. Green waste spotted in a neighbor cell → move toward it
        if self.knowledge["green_waste_neighbor_pos"] and self.n_green_wastes < 2:
            return "move_toward_waste"
        # 5. Nothing visible → explore, preferring unvisited cells
        return "move"

    # ------------------------------------------------------------------ #
    #  Action execution                                                    #
    # ------------------------------------------------------------------ #

    def act(self, action):
        if action == "pick":
            waste = self.knowledge["green_wastes_here"][0]
            self.model.grid.remove_agent(waste)
            self.n_green_wastes += 1

        elif action == "transform":
            self.n_green_wastes = 0
            self.n_yellow_wastes = 1

        elif action == "drop":
            waste = WasteAgent(self.model, waste_type="yellow")
            self.model.grid.place_agent(waste, self.pos)
            self.n_yellow_wastes = 0

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["green_waste_neighbor_pos"])

        elif action == "move":
            self.move_random()

    # ------------------------------------------------------------------ #
    #  Mesa step                                                           #
    # ------------------------------------------------------------------ #

    def step(self):
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)


class YellowAgent(RobotAgent):

    def __init__(self, model, x_min, x_max):
        super().__init__(model, x_min, x_max)
        self.n_yellow_wastes = 0
        self.n_red_wastes = 0
        self.knowledge = {
            "visited": set(),
            "position": None,
            "yellow_wastes_here": [],
            "yellow_waste_neighbor_pos": None,
        }

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self.knowledge["yellow_wastes_here"] = [
            a for a in percepts["current"]
            if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"
        ]
        self.knowledge["yellow_waste_neighbor_pos"] = next(
            (pos for pos, contents in percepts["neighbors"].items()
             if any(isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"
                    for a in contents)),
            None,
        )

    def deliberate(self):
        if self.n_yellow_wastes == 2:
            return "transform"
        if self.n_red_wastes == 1:
            return "drop"
        if self.knowledge["yellow_wastes_here"] and self.n_yellow_wastes < 2:
            return "pick"
        if self.knowledge["yellow_waste_neighbor_pos"] and self.n_yellow_wastes < 2:
            return "move_toward_waste"
        return "move"

    def act(self, action):
        if action == "pick":
            waste = self.knowledge["yellow_wastes_here"][0]
            self.model.grid.remove_agent(waste)
            self.n_yellow_wastes += 1

        elif action == "transform":
            self.n_yellow_wastes = 0
            self.n_red_wastes = 1

        elif action == "drop":
            waste = WasteAgent(self.model, waste_type="red")
            self.model.grid.place_agent(waste, self.pos)
            self.n_red_wastes = 0

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["yellow_waste_neighbor_pos"])

        elif action == "move":
            self.move_random()

    def step(self):
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)


class RedAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, disposal_zone_pos):
        super().__init__(model, x_min, x_max)
        self.n_red_wastes = 0
        self.disposal_zone_pos = disposal_zone_pos  # passed by the model at creation
        self.knowledge = {
            "visited": set(),
            "position": None,
            "red_wastes_here": [],
            "red_waste_neighbor_pos": None,
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
        self.knowledge["at_disposal_zone"] = (self.pos == self.disposal_zone_pos)

    def deliberate(self):
        if self.n_red_wastes == 1:
            if self.knowledge["at_disposal_zone"]:
                return "drop"
            return "move_to_disposal"
        if self.knowledge["red_wastes_here"] and self.n_red_wastes == 0:
            return "pick"
        if self.knowledge["red_waste_neighbor_pos"] and self.n_red_wastes == 0:
            return "move_toward_waste"
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
            self._move_toward(self.disposal_zone_pos)

        elif action == "move_toward_waste":
            self._move_toward(self.knowledge["red_waste_neighbor_pos"])

        elif action == "move":
            self.move_random()

    def step(self):
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)