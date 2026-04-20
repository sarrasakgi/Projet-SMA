# Group: 23
# Date: 2026-03-16
# Members:
#   Khalil Ben Gamra
#   Sarra Sakgi
#   Ali Baklouti

import random as _random
from mesa import Agent
from objects import WasteAgent

# ------------------------------------------------------------------ #
#  Feature flags — toggle before each scenario run                    #
# ------------------------------------------------------------------ #
ENABLE_DROP_PATIENCE = True   # robots drop waste after holding too long
ENABLE_EAST_BIAS     = True   # robots drift east when carrying waste
DROP_MEMORY_STEPS    = 5      # after dropping, ignore that cell for 5 steps


class RobotAgent(Agent):
    """Base class shared by all robot types."""

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model)
        self.x_min = x_min
        self.x_max = x_max
        self.home_x_min = x_min if home_x_min is None else home_x_min
        self.home_x_max = x_max if home_x_max is None else home_x_max
        self.drop_cooldown = {}
        self.current_task = None
        self.carried_waste_type = None
        self.knowledge = {"visited": set()}

    def _tick_cooldowns(self):
        self.drop_cooldown = {
            pos: t - 1 for pos, t in self.drop_cooldown.items() if t > 1
        }

    def _is_on_cooldown(self, pos):
        return pos in self.drop_cooldown

    def perceive(self):
        """Return current cell contents and all 8 surrounding cells."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=True, include_center=False, radius=1
        )
        return {
            "current": self.model.grid.get_cell_list_contents([self.pos]),
            "neighbors": {
                p: self.model.grid.get_cell_list_contents([p])
                for p in neighbors
            },
        }

    def carried_load(self):
        return (
            getattr(self, "n_green_wastes", 0)
            + getattr(self, "n_yellow_wastes", 0)
            + getattr(self, "n_red_wastes", 0)
        )

    def _cell_free(self, pos):
        return not any(
            isinstance(a, RobotAgent) and a is not self
            for a in self.model.grid.get_cell_list_contents([pos])
        )

    def _has_waste_at(self, pos, waste_type):
        return any(
            isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == waste_type
            for a in self.model.grid.get_cell_list_contents([pos])
        )

    def _visible_positions(self, percepts, waste_type):
        positions = []

        if not self._is_on_cooldown(self.pos) and any(
            isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == waste_type
            for a in percepts["current"]
        ):
            positions.append(self.pos)

        for pos, contents in percepts["neighbors"].items():
            if self._is_on_cooldown(pos):
                continue
            if any(
                isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == waste_type
                for a in contents
            ):
                positions.append(pos)

        return sorted(
            positions,
            key=lambda p: (
                abs(p[0] - self.pos[0]) + abs(p[1] - self.pos[1]),
                -p[0],
                abs(p[1] - self.pos[1]),
            ),
        )

    def _sync_task_state(self):
        if self.current_task is None:
            return
        target = self.current_task.get("target_pos")
        waste_type = self.current_task.get("waste_type")
        if target is None or waste_type is None or not self._has_waste_at(target, waste_type):
            self.model.release_task(self)

    def move_random(self):
        """Prefer home-zone and unvisited cells when exploring."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid = [
            p for p in neighbors
            if self.x_min <= p[0] <= self.x_max and self._cell_free(p)
        ]
        visited = self.knowledge.get("visited", set())
        home = [p for p in valid if self.home_x_min <= p[0] <= self.home_x_max]
        unvisited_home = [p for p in home if p not in visited]
        unvisited_any = [p for p in valid if p not in visited]
        pool = unvisited_home or unvisited_any or home or valid
        if pool:
            self.model.grid.move_agent(self, self.random.choice(pool))

    def move_east_biased(self):
        """Prioritize eastward transport; never backtrack west while carrying."""
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid = [
            p for p in neighbors
            if self.x_min <= p[0] <= self.x_max and self._cell_free(p)
        ]
        east = [p for p in valid if p[0] > self.pos[0]]
        same_x = [p for p in valid if p[0] == self.pos[0]]
        if east:
            self.model.grid.move_agent(self, max(east, key=lambda p: p[0]))
        elif same_x:
            self.model.grid.move_agent(self, self.random.choice(same_x))
        else:
            self.move_random()

    def _move_toward(self, target):
        """One step of navigation toward target, with obstacle avoidance."""
        tx, ty = target
        neighbors = self.model.grid.get_neighborhood(
            self.pos, moore=False, include_center=False
        )
        valid = [
            p for p in neighbors
            if self.x_min <= p[0] <= self.x_max and self._cell_free(p)
        ]
        if valid:
            best = min(
                valid,
                key=lambda p: (
                    abs(p[0] - tx) + abs(p[1] - ty),
                    -p[0],
                    abs(p[1] - ty),
                ),
            )
            self.model.grid.move_agent(self, best)
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
            "position": None,
            "visible_green_positions": [],
            "visible_yellow_positions": [],
            "transportable_yellow_positions": [],
            "visible_red_positions": [],
        }

    @property
    def _patience(self):
        return self.model.width * 2

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self._sync_task_state()

        self.knowledge["visible_green_positions"] = self._visible_positions(percepts, "green")
        self.knowledge["visible_yellow_positions"] = self._visible_positions(percepts, "yellow")
        self.knowledge["transportable_yellow_positions"] = [
            pos for pos in self.knowledge["visible_yellow_positions"] if pos[0] < self.x_max
        ]
        self.knowledge["visible_red_positions"] = self._visible_positions(percepts, "red")

        if self.model.emergency_cleanup:
            return

        if self.knowledge["visible_green_positions"] and not (self.n_green_wastes < 2 and self.n_yellow_wastes == 0):
            for pos in self.knowledge["visible_green_positions"]:
                self.model.emit_broadcast(self, pos, "green", {"green"})

        if self.knowledge["transportable_yellow_positions"] and self.carried_load() > 0:
            for pos in self.knowledge["transportable_yellow_positions"]:
                self.model.emit_broadcast(self, pos, "yellow", {"green", "yellow"})

        for pos in self.knowledge["visible_yellow_positions"]:
            if pos[0] == self.x_max:
                self.model.emit_broadcast(self, pos, "yellow", {"yellow"})

        for pos in self.knowledge["visible_red_positions"]:
            self.model.emit_broadcast(self, pos, "red", {"yellow", "red"})

    def deliberate(self):
        if self.model.emergency_cleanup:
            if self.n_yellow_wastes == 1:
                return "drop"
            if self.n_green_wastes > 0:
                return "drop_green"
            return "move"

        if self.n_green_wastes == 2:
            return "transform"
        if self.n_yellow_wastes == 1:
            return "drop" if self.pos[0] == self.x_max else "move_east"
        if self.knowledge["visible_green_positions"] and self.knowledge["visible_green_positions"][0] == self.pos and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            return "pick_green"
        if self.knowledge["transportable_yellow_positions"] and self.knowledge["transportable_yellow_positions"][0] == self.pos and self.carried_load() == 0:
            return "pick_yellow"
        if ENABLE_DROP_PATIENCE and self.n_green_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_green / self._patience)
            if _random.random() < drop_prob:
                return "drop_green"
        if self.knowledge["visible_green_positions"] and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            return "move_toward_green"
        if self.knowledge["transportable_yellow_positions"] and self.carried_load() == 0:
            return "move_toward_yellow"
        if self.current_task and self.carried_load() == 0:
            return "move_to_task"
        if ENABLE_EAST_BIAS and self.n_green_wastes > 0:
            return "move_east"
        return "move"

    def act(self, action):
        if action == "pick_green":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "green"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_green_wastes += 1
                self.steps_holding_green = 0
                self.model.release_task(self)

        elif action == "pick_yellow":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_yellow_wastes = 1
                self.steps_holding_green = 0
                self.model.release_task(self)

        elif action == "transform":
            self.n_green_wastes = 0
            self.n_yellow_wastes = 1
            self.steps_holding_green = 0
            self.model.transformed_green_to_yellow += 1

        elif action == "drop_green":
            self.model.grid.place_agent(WasteAgent(self.model, "green"), self.pos)
            self.n_green_wastes = 0
            self.steps_holding_green = 0
            self.drop_cooldown[self.pos] = DROP_MEMORY_STEPS

        elif action == "drop":
            self.model.grid.place_agent(WasteAgent(self.model, "yellow"), self.pos)
            self.n_yellow_wastes = 0
            self.drop_cooldown[self.pos] = DROP_MEMORY_STEPS

        elif action == "move_toward_green":
            self._move_toward(self.knowledge["visible_green_positions"][0])

        elif action == "move_toward_yellow":
            self._move_toward(self.knowledge["transportable_yellow_positions"][0])

        elif action == "move_to_task":
            self._move_toward(self.current_task["target_pos"])

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

        if self.n_green_wastes == 1:
            self.steps_holding_green += 1

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
            "position": None,
            "visible_green_positions": [],
            "visible_yellow_positions": [],
            "visible_red_positions": [],
            "transportable_red_positions": [],
        }

    @property
    def _patience(self):
        return self.model.width * 2

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self._sync_task_state()

        self.knowledge["visible_green_positions"] = self._visible_positions(percepts, "green")
        self.knowledge["visible_yellow_positions"] = self._visible_positions(percepts, "yellow")
        self.knowledge["visible_red_positions"] = self._visible_positions(percepts, "red")
        self.knowledge["transportable_red_positions"] = [
            pos for pos in self.knowledge["visible_red_positions"] if pos[0] < self.x_max
        ]

        if self.model.emergency_cleanup:
            return

        for pos in self.knowledge["visible_green_positions"]:
            self.model.emit_broadcast(self, pos, "green", {"green"})

        if self.knowledge["visible_yellow_positions"] and not (self.n_yellow_wastes < 2 and self.n_red_wastes == 0):
            for pos in self.knowledge["visible_yellow_positions"]:
                self.model.emit_broadcast(self, pos, "yellow", {"yellow"})

        if self.knowledge["transportable_red_positions"] and self.carried_load() > 0:
            for pos in self.knowledge["transportable_red_positions"]:
                self.model.emit_broadcast(self, pos, "red", {"yellow", "red"})

        for pos in self.knowledge["visible_red_positions"]:
            if pos[0] == self.x_max:
                self.model.emit_broadcast(self, pos, "red", {"red"})

    def deliberate(self):
        if self.model.emergency_cleanup:
            if self.n_red_wastes == 1:
                return "drop"
            if self.n_yellow_wastes > 0:
                return "drop_yellow"
            return "move"

        if self.n_yellow_wastes == 2:
            return "transform"
        if self.n_red_wastes == 1:
            return "drop" if self.pos[0] == self.x_max else "move_east"
        if self.knowledge["visible_yellow_positions"] and self.knowledge["visible_yellow_positions"][0] == self.pos and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "pick_yellow"
        if self.knowledge["transportable_red_positions"] and self.knowledge["transportable_red_positions"][0] == self.pos and self.carried_load() == 0:
            return "pick_red"
        if ENABLE_DROP_PATIENCE and self.n_yellow_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_yellow / self._patience)
            if _random.random() < drop_prob:
                return "drop_yellow"
        if self.knowledge["visible_yellow_positions"] and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "move_toward_yellow"
        if self.knowledge["transportable_red_positions"] and self.carried_load() == 0:
            return "move_toward_red"
        if self.current_task and self.carried_load() == 0:
            return "move_to_task"
        if ENABLE_EAST_BIAS and (self.n_yellow_wastes > 0 or self.n_red_wastes > 0):
            return "move_east"
        return "move"

    def act(self, action):
        if action == "pick_yellow":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_yellow_wastes += 1
                self.steps_holding_yellow = 0
                self.model.release_task(self)

        elif action == "pick_red":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.steps_holding_yellow = 0
                self.model.release_task(self)

        elif action == "transform":
            self.n_yellow_wastes = 0
            self.n_red_wastes = 1
            self.steps_holding_yellow = 0
            self.model.transformed_yellow_to_red += 1

        elif action == "drop_yellow":
            self.model.grid.place_agent(WasteAgent(self.model, "yellow"), self.pos)
            self.n_yellow_wastes = 0
            self.steps_holding_yellow = 0
            self.drop_cooldown[self.pos] = DROP_MEMORY_STEPS

        elif action == "drop":
            self.model.grid.place_agent(WasteAgent(self.model, "red"), self.pos)
            self.n_red_wastes = 0
            self.drop_cooldown[self.pos] = DROP_MEMORY_STEPS

        elif action == "move_toward_yellow":
            self._move_toward(self.knowledge["visible_yellow_positions"][0])

        elif action == "move_toward_red":
            self._move_toward(self.knowledge["transportable_red_positions"][0])

        elif action == "move_to_task":
            self._move_toward(self.current_task["target_pos"])

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

        if self.n_yellow_wastes == 1:
            self.steps_holding_yellow += 1

    def step(self):
        self._tick_cooldowns()
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)


class RedAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, disposal_zone_pos=None, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_red_wastes = 0
        self.carried_waste_type = None
        self.disposal_zone_pos = disposal_zone_pos if disposal_zone_pos is not None else model.disposal_pos
        self.knowledge = {
            "visited": set(),
            "position": None,
            "visible_green_positions": [],
            "visible_yellow_positions": [],
            "visible_red_positions": [],
            "at_disposal_zone": False,
        }

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self._sync_task_state()

        self.knowledge["visible_green_positions"] = self._visible_positions(percepts, "green")
        self.knowledge["visible_yellow_positions"] = self._visible_positions(percepts, "yellow")
        self.knowledge["visible_red_positions"] = self._visible_positions(percepts, "red")
        self.knowledge["at_disposal_zone"] = (self.pos == self.disposal_zone_pos)

        if self.model.emergency_cleanup:
            return

        for pos in self.knowledge["visible_green_positions"]:
            self.model.emit_broadcast(self, pos, "green", {"green"})

        for pos in self.knowledge["visible_yellow_positions"]:
            self.model.emit_broadcast(self, pos, "yellow", {"yellow"})

        if self.knowledge["visible_red_positions"] and self.n_red_wastes == 1:
            for pos in self.knowledge["visible_red_positions"]:
                self.model.emit_broadcast(self, pos, "red", {"red"})

    def deliberate(self):
        if self.model.emergency_cleanup:
            if self.n_red_wastes == 1:
                return "drop" if self.knowledge["at_disposal_zone"] else "move_to_disposal"
            if self.current_task and self.carried_load() == 0:
                return "pick_target" if self.current_task["target_pos"] == self.pos else "move_to_task"
            visible_any = (
                self.knowledge["visible_red_positions"]
                + self.knowledge["visible_yellow_positions"]
                + self.knowledge["visible_green_positions"]
            )
            if visible_any:
                return "pick_any" if self.pos in visible_any else "move_to_any_waste"
            return "move"

        if self.n_red_wastes == 1:
            if self.knowledge["at_disposal_zone"]:
                return "drop"
            return "move_to_disposal"
        if self.knowledge["visible_red_positions"] and self.knowledge["visible_red_positions"][0] == self.pos:
            return "pick_red"
        if self.knowledge["visible_red_positions"] and self.n_red_wastes == 0:
            return "move_toward_red"
        if self.current_task and self.carried_load() == 0:
            return "move_to_task"
        return "move"

    def act(self, action):
        if action == "pick_red":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.carried_waste_type = "red"
                self.model.release_task(self)

        elif action in {"pick_target", "pick_any"}:
            desired = self.current_task["waste_type"] if action == "pick_target" and self.current_task else None
            order = [desired] if desired else []
            for waste_type in ["red", "yellow", "green"]:
                if waste_type not in order:
                    order.append(waste_type)

            waste = None
            for waste_type in order:
                waste = next(
                    (a for a in self.model.grid.get_cell_list_contents([self.pos])
                     if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == waste_type),
                    None,
                )
                if waste is not None:
                    self.carried_waste_type = waste_type
                    break

            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.model.release_task(self)

        elif action == "drop":
            self.n_red_wastes = 0
            self.carried_waste_type = None
            self.model.stored_red_waste += 1

        elif action == "move_to_disposal":
            self._move_toward(self.disposal_zone_pos)

        elif action == "move_toward_red":
            self._move_toward(self.knowledge["visible_red_positions"][0])

        elif action == "move_to_any_waste":
            candidates = list({
                *self.knowledge["visible_red_positions"],
                *self.knowledge["visible_yellow_positions"],
                *self.knowledge["visible_green_positions"],
            })
            if candidates:
                best = max(
                    candidates,
                    key=lambda p: (self.model._cell_radioactivity(p), p[0], -abs(p[1] - self.pos[1])),
                )
                self._move_toward(best)

        elif action == "move_to_task":
            self._move_toward(self.current_task["target_pos"])

        elif action == "move":
            self.move_random()

    def step(self):
        self._tick_cooldowns()
        percepts = self.perceive()
        self.update(percepts)
        action = self.deliberate()
        self.act(action)
        knowledge["yellow_wastes_here"] = (
            "yellow" in current_wastes and not self._is_on_cooldown(pos)
        )
        knowledge["yellow_waste_neighbor"] = next(
            (
                p for p in knowledge["neighbor_positions"]
                if not self._is_on_cooldown(p)
                and "yellow" in percepts["tiles"][p]["wastes"]
            ),
            None,
        )

    def _in_cleanup_mode(self, knowledge):
        return (
            knowledge["green_waste_total"] <= 1
            and knowledge["yellow_waste_total"] <= 1
        )

    def deliberate(self, knowledge):
        pos = knowledge["self_pos"]

        # Cleanup mode
        if self._in_cleanup_mode(knowledge) and knowledge["red_waste_count"] == 0:
            if self.n_red_wastes == 1:
                return {"type": "drop"}
            if self.n_yellow_wastes > 0:
                return {"type": "drop_yellow"}
            return {"type": "wait"}

        # 1. Hands full → transform
=======
            "visited": set(),
            "position": None,
            "visible_green_positions": [],
            "visible_yellow_positions": [],
            "visible_red_positions": [],
            "transportable_red_positions": [],
        }

    @property
    def _patience(self):
        return self.model.width * 2

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self._sync_task_state()

        self.knowledge["visible_green_positions"] = self._visible_positions(percepts, "green")
        self.knowledge["visible_yellow_positions"] = self._visible_positions(percepts, "yellow")
        self.knowledge["visible_red_positions"] = self._visible_positions(percepts, "red")
        self.knowledge["transportable_red_positions"] = [
            pos for pos in self.knowledge["visible_red_positions"] if pos[0] < self.x_max
        ]

        if self.model.emergency_cleanup:
            return

        for pos in self.knowledge["visible_green_positions"]:
            self.model.emit_broadcast(self, pos, "green", {"green"})

        if self.knowledge["visible_yellow_positions"] and not (self.n_yellow_wastes < 2 and self.n_red_wastes == 0):
            for pos in self.knowledge["visible_yellow_positions"]:
                self.model.emit_broadcast(self, pos, "yellow", {"yellow"})

        if self.knowledge["transportable_red_positions"] and self.carried_load() > 0:
            for pos in self.knowledge["transportable_red_positions"]:
                self.model.emit_broadcast(self, pos, "red", {"yellow", "red"})

        for pos in self.knowledge["visible_red_positions"]:
            if pos[0] == self.x_max:
                self.model.emit_broadcast(self, pos, "red", {"red"})

    def deliberate(self):
        if self.model.emergency_cleanup:
            if self.n_red_wastes == 1:
                return "drop"
            if self.n_yellow_wastes > 0:
                return "drop_yellow"
            return "move"
>>>>>>> optimisation
        if self.n_yellow_wastes == 2:
            return {"type": "transform"}

        # 2. Carrying red → move to rightmost col of z2 (x_max) then drop
        if self.n_red_wastes == 1:
<<<<<<< HEAD
            if pos[0] == self.x_max:
                return {"type": "drop"}
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}
            return {"type": "wait"}

        # 3. Patience drop
=======
            return "drop" if self.pos[0] == self.x_max else "move_east"
        if self.knowledge["visible_yellow_positions"] and self.knowledge["visible_yellow_positions"][0] == self.pos and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "pick_yellow"
        if self.knowledge["transportable_red_positions"] and self.knowledge["transportable_red_positions"][0] == self.pos and self.carried_load() == 0:
            return "pick_red"
>>>>>>> optimisation
        if ENABLE_DROP_PATIENCE and self.n_yellow_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_yellow / self._patience_value)
            if _random.random() < drop_prob:
<<<<<<< HEAD
                return {"type": "drop_yellow"}

        # 4. Yellow waste on current cell
        if knowledge["yellow_wastes_here"] and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return {"type": "pick"}

        # 5. Yellow waste in neighbor
        neighbor = knowledge["yellow_waste_neighbor"]
        if neighbor and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            target = self._get_toward_move(neighbor, knowledge)
            if target:
                return {"type": "move", "to": target}

        # 6. East-bias when carrying
=======
                return "drop_yellow"
        if self.knowledge["visible_yellow_positions"] and self.n_yellow_wastes < 2 and self.n_red_wastes == 0:
            return "move_toward_yellow"
        if self.knowledge["transportable_red_positions"] and self.carried_load() == 0:
            return "move_toward_red"
        if self.current_task and self.carried_load() == 0:
            return "move_to_task"
>>>>>>> optimisation
        if ENABLE_EAST_BIAS and (self.n_yellow_wastes > 0 or self.n_red_wastes > 0):
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}

        # 7. Explore
        target = self._get_random_move(knowledge)
        if target:
            return {"type": "move", "to": target}
        return {"type": "wait"}

    def act(self, action):
<<<<<<< HEAD
        atype = action.get("type") if isinstance(action, dict) else action
=======
        if action == "pick_yellow":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "yellow"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_yellow_wastes += 1
                self.steps_holding_yellow = 0
                self.model.release_task(self)

        elif action == "pick_red":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.steps_holding_yellow = 0
                self.model.release_task(self)
>>>>>>> optimisation

        if atype == "pick":
            if self.knowledge["action_success"]:
                self.n_yellow_wastes += 1
                self.steps_holding_yellow = 0

        elif atype == "transform":
            self.n_yellow_wastes = 0
            self.n_red_wastes    = 1
            self.steps_holding_yellow = 0
            self.model.transformed_yellow_to_red += 1

        elif atype == "drop_yellow":
            self.n_yellow_wastes = 0
            self.steps_holding_yellow = 0
            self.drop_cooldown[self.knowledge["self_pos"]] = self.model.width // 3

        elif atype == "drop":
            self.n_red_wastes = 0

<<<<<<< HEAD
=======
        elif action == "move_toward_yellow":
            self._move_toward(self.knowledge["visible_yellow_positions"][0])

        elif action == "move_toward_red":
            self._move_toward(self.knowledge["transportable_red_positions"][0])

        elif action == "move_to_task":
            self._move_toward(self.current_task["target_pos"])

        elif action == "move_east":
            self.move_east_biased()

        elif action == "move":
            self.move_random()

>>>>>>> optimisation
        if self.n_yellow_wastes == 1:
            self.steps_holding_yellow += 1

    def step(self):
        self._tick_cooldowns()
        action   = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts)
        self.act(action)


class RedAgent(RobotAgent):

<<<<<<< HEAD
    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_red_wastes      = 0
        self.n_cleanup_wastes  = 0        # leftover green/yellow in cleanup mode
        self.cleanup_waste_type = None    # type of waste currently carried in cleanup
        self._sweep_col = 0
        self._sweep_row = None
        self.knowledge = {
            "visited":               set(),
            "self_pos":              None,
            "neighbor_positions":    [],
            "red_wastes_here":       False,
            "red_waste_neighbor":    None,
            "any_waste_here":        False,   # any waste type (cleanup mode)
            "any_waste_here_type":   None,    # type of that waste
            "any_waste_neighbor":    None,
            "disposal_pos":          None,
            "at_disposal_zone":      False,
            "green_waste_total":     999,
            "yellow_waste_total":    999,
            "red_waste_count":       999,
            "action_success":        False,
        }

    def update(self, knowledge, percepts):
        pos = percepts["self_pos"]
        knowledge["self_pos"] = pos
        knowledge["visited"].add(pos)
        knowledge["neighbor_positions"] = [
            p for p in percepts["tiles"] if p != pos
        ]
        for p, tile in percepts["tiles"].items():
            if tile["is_disposal"]:
                knowledge["disposal_pos"] = p
                break
        knowledge["green_waste_total"]  = percepts["green_waste_total"]
        knowledge["yellow_waste_total"] = percepts["yellow_waste_total"]
        knowledge["red_waste_count"]    = percepts["red_waste_count"]
        knowledge["at_disposal_zone"]   = (pos == knowledge["disposal_pos"])
        knowledge["action_success"]     = percepts.get("action_success", False)

        current_wastes = percepts["tiles"][pos]["wastes"]
        knowledge["red_wastes_here"] = "red" in current_wastes
        knowledge["red_waste_neighbor"] = next(
            (
                p for p in knowledge["neighbor_positions"]
                if "red" in percepts["tiles"][p]["wastes"]
            ),
            None,
        )

        # Cleanup: any waste at current cell
        if current_wastes:
            knowledge["any_waste_here"]      = True
            knowledge["any_waste_here_type"] = current_wastes[0]
        else:
            knowledge["any_waste_here"]      = False
            knowledge["any_waste_here_type"] = None

        knowledge["any_waste_neighbor"] = next(
            (
                p for p in knowledge["neighbor_positions"]
                if percepts["tiles"][p]["wastes"]
            ),
            None,
        )

    def _in_cleanup_mode(self, knowledge):
        return (
            knowledge["green_waste_total"] <= 1
            and knowledge["yellow_waste_total"] <= 1
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

    def deliberate(self, knowledge):
        pos = knowledge["self_pos"]

        # Normal pipeline: carry red waste to disposal
        if self.n_red_wastes == 1:
            if knowledge["at_disposal_zone"]:
                return {"type": "drop"}
            disposal = knowledge["disposal_pos"]
            if disposal:
                target = self._get_toward_move(disposal, knowledge)
                if target:
                    return {"type": "move", "to": target}
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}
            return {"type": "wait"}

        if knowledge["red_wastes_here"] and self.n_red_wastes == 0:
            return {"type": "pick"}

        neighbor = knowledge["red_waste_neighbor"]
        if neighbor and self.n_red_wastes == 0:
            target = self._get_toward_move(neighbor, knowledge)
            if target:
                return {"type": "move", "to": target}

        # Cleanup mode: only when red pipeline is done too
        if (
            self._in_cleanup_mode(knowledge)
            and knowledge["red_waste_count"] == 0
            and self.n_red_wastes == 0
        ):
            if self.n_cleanup_wastes > 0:
                if knowledge["at_disposal_zone"]:
                    return {"type": "cleanup_drop"}
                disposal = knowledge["disposal_pos"]
                if disposal:
                    target = self._get_toward_move(disposal, knowledge)
                    if target:
                        return {"type": "move", "to": target}
                target = self._get_east_move(knowledge)
                if target:
                    return {"type": "move", "to": target}
                return {"type": "wait"}

            if knowledge["any_waste_here"]:
                return {"type": "cleanup_pick", "waste_type": knowledge["any_waste_here_type"]}

            # Sweep toward next target
            sweep_tgt = self._sweep_target()
            if pos == sweep_tgt:
                return {"type": "sweep_advance"}
            target = self._get_toward_move(sweep_tgt, knowledge)
            if target:
                return {"type": "move", "to": target}

        # Default: explore
        target = self._get_random_move(knowledge)
        if target:
            return {"type": "move", "to": target}
        return {"type": "wait"}

    def act(self, action):
        atype = action.get("type") if isinstance(action, dict) else action
=======
    def __init__(self, model, x_min, x_max, disposal_zone_pos):
        super().__init__(model, x_min, x_max)
        self.n_red_wastes = 0
        self.carried_waste_type = None
        self.disposal_zone_pos = disposal_zone_pos
        self.knowledge = {
            "visited": set(),
            "position": None,
            "visible_green_positions": [],
            "visible_yellow_positions": [],
            "visible_red_positions": [],
            "at_disposal_zone": False,
        }

    def update(self, percepts):
        self.knowledge["visited"].add(self.pos)
        self.knowledge["position"] = self.pos
        self._sync_task_state()

        self.knowledge["visible_green_positions"] = self._visible_positions(percepts, "green")
        self.knowledge["visible_yellow_positions"] = self._visible_positions(percepts, "yellow")
        self.knowledge["visible_red_positions"] = self._visible_positions(percepts, "red")
        self.knowledge["at_disposal_zone"] = (self.pos == self.disposal_zone_pos)

        if self.model.emergency_cleanup:
            return

        for pos in self.knowledge["visible_green_positions"]:
            self.model.emit_broadcast(self, pos, "green", {"green"})

        for pos in self.knowledge["visible_yellow_positions"]:
            self.model.emit_broadcast(self, pos, "yellow", {"yellow"})

        if self.knowledge["visible_red_positions"] and self.n_red_wastes == 1:
            for pos in self.knowledge["visible_red_positions"]:
                self.model.emit_broadcast(self, pos, "red", {"red"})

    def deliberate(self):
        if self.model.emergency_cleanup:
            if self.n_red_wastes == 1:
                return "drop" if self.knowledge["at_disposal_zone"] else "move_to_disposal"
            if self.current_task and self.carried_load() == 0:
                return "pick_target" if self.current_task["target_pos"] == self.pos else "move_to_task"
            visible_any = (
                self.knowledge["visible_red_positions"]
                + self.knowledge["visible_yellow_positions"]
                + self.knowledge["visible_green_positions"]
            )
            if visible_any:
                return "pick_any" if self.pos in visible_any else "move_to_any_waste"
            return "move"
        if self.n_red_wastes == 1:
            if self.knowledge["at_disposal_zone"]:
                return "drop"
            return "move_to_disposal"
        if self.knowledge["visible_red_positions"] and self.knowledge["visible_red_positions"][0] == self.pos:
            return "pick_red"
        if self.knowledge["visible_red_positions"] and self.n_red_wastes == 0:
            return "move_toward_red"
        if self.current_task and self.carried_load() == 0:
            return "move_to_task"
        return "move"

    def act(self, action):
        if action == "pick_red":
            waste = next(
                (a for a in self.model.grid.get_cell_list_contents([self.pos])
                 if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == "red"),
                None,
            )
            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.carried_waste_type = "red"
                self.model.release_task(self)

        elif action in {"pick_target", "pick_any"}:
            desired = self.current_task["waste_type"] if action == "pick_target" and self.current_task else None
            order = [desired] if desired else []
            for waste_type in ["red", "yellow", "green"]:
                if waste_type not in order:
                    order.append(waste_type)

            waste = None
            for waste_type in order:
                waste = next(
                    (a for a in self.model.grid.get_cell_list_contents([self.pos])
                     if isinstance(a, WasteAgent) and getattr(a, "waste_type", None) == waste_type),
                    None,
                )
                if waste is not None:
                    self.carried_waste_type = waste_type
                    break

            if waste is not None:
                self.model.grid.remove_agent(waste)
                self.n_red_wastes = 1
                self.model.release_task(self)
>>>>>>> optimisation

        if atype == "pick":
            if self.knowledge["action_success"]:
                self.n_red_wastes += 1

        elif atype == "drop":
            self.n_red_wastes = 0
<<<<<<< HEAD
=======
            self.carried_waste_type = None
            self.model.stored_red_waste += 1
>>>>>>> optimisation

        elif atype == "cleanup_pick":
            if self.knowledge["action_success"]:
                self.cleanup_waste_type = action.get("waste_type") if isinstance(action, dict) else None
                self.n_cleanup_wastes += 1

<<<<<<< HEAD
        elif atype == "cleanup_drop":
            self.n_cleanup_wastes   = 0
            self.cleanup_waste_type = None
=======
        elif action == "move_toward_red":
            self._move_toward(self.knowledge["visible_red_positions"][0])

        elif action == "move_to_any_waste":
            candidates = list({
                *self.knowledge["visible_red_positions"],
                *self.knowledge["visible_yellow_positions"],
                *self.knowledge["visible_green_positions"],
            })
            if candidates:
                best = max(candidates, key=lambda p: (self.model._cell_radioactivity(p), p[0], -abs(p[1] - self.pos[1])))
                self._move_toward(best)

        elif action == "move_to_task":
            self._move_toward(self.current_task["target_pos"])
>>>>>>> optimisation

        # sweep_advance: _advance_sweep() is called by model._do_sweep_advance
        # move / wait: no inventory change

    def step(self):
        action   = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts)
        self.act(action)
