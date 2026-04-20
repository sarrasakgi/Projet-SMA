# Group: 23
# Date: 2026-03-16
# Members:
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import random as _random
from mesa import Agent

# ------------------------------------------------------------------ #
#  Feature flags — toggle before each scenario run                   #
# ------------------------------------------------------------------ #
ENABLE_DROP_PATIENCE = True   # robots drop waste after holding too long
ENABLE_EAST_BIAS     = True   # robots drift east when carrying waste


class RobotAgent(Agent):
    """Base class shared by all robot types."""

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model)
        self.x_min = x_min
        self.x_max = x_max
        self.home_x_min = home_x_min if home_x_min is not None else x_min
        self.home_x_max = home_x_max if home_x_max is not None else x_max
        self.drop_cooldown = {}   # pos -> steps remaining until cell is no longer ignored

    def _tick_cooldowns(self):
        self.drop_cooldown = {
            pos: t - 1 for pos, t in self.drop_cooldown.items() if t > 1
        }

    def _is_on_cooldown(self, pos):
        return pos in self.drop_cooldown

    # ------------------------------------------------------------------ #
    #  Movement helpers — return a target position, do NOT execute moves  #
    # ------------------------------------------------------------------ #

    def _get_random_move(self, knowledge):
        """
        Return a position to move to (home-zone preferred, unvisited preferred).
        Returns None if no valid neighbor exists.
        """
        pos = knowledge["self_pos"]
        visited = knowledge.get("visited", set())
        neighbors = [
            p for p in knowledge["neighbor_positions"]
            if self.x_min <= p[0] <= self.x_max
        ]
        not_cool   = [p for p in neighbors if not self._is_on_cooldown(p)]
        in_home    = [p for p in not_cool if self.home_x_min <= p[0] <= self.home_x_max]
        unvisited_home = [p for p in in_home if p not in visited]
        unvisited_any  = [p for p in not_cool if p not in visited]
        pool = unvisited_home or in_home or unvisited_any or not_cool or neighbors
        return self.random.choice(pool) if pool else None

    def _get_east_move(self, knowledge):
        """Return an east neighbor if available, else fall back to random move."""
        pos = knowledge["self_pos"]
        neighbors = [
            p for p in knowledge["neighbor_positions"]
            if self.x_min <= p[0] <= self.x_max
        ]
        east = [p for p in neighbors if p[0] > pos[0]]
        if east:
            return self.random.choice(east)
        return self._get_random_move(knowledge)

    def _get_toward_move(self, target, knowledge):
        """One step of greedy Manhattan navigation toward target, within zone."""
        pos = knowledge["self_pos"]
        x, y = pos
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
            return valid[0]
        return self._get_random_move(knowledge)


class GreenAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_green_wastes  = 0
        self.n_yellow_wastes = 0
        self.steps_holding_green = 0
        self._patience_value = model.width * 2  # 50% drop prob at 2*width steps held
        self.knowledge = {
            "visited":               set(),
            "self_pos":              None,
            "neighbor_positions":    [],
            "green_wastes_here":     False,  # bool: green waste on current cell
            "green_waste_neighbor":  None,   # pos of neighbor with green waste, or None
            "green_waste_total":     999,
            "yellow_waste_total":    999,
            "red_waste_count":       999,
            "disposal_pos":          None,
            "action_success":        False,
        }

    # ------------------------------------------------------------------ #
    #  Belief update — called AFTER model.do() returns percepts           #
    # ------------------------------------------------------------------ #

    def update(self, knowledge, percepts):
        pos = percepts["self_pos"]
        knowledge["self_pos"] = pos
        knowledge["visited"].add(pos)
        knowledge["neighbor_positions"] = [
            p for p in percepts["tiles"] if p != pos
        ]
        # Discover disposal zone only if visible in current tiles
        for p, tile in percepts["tiles"].items():
            if tile["is_disposal"]:
                knowledge["disposal_pos"] = p
                break
        knowledge["green_waste_total"]  = percepts["green_waste_total"]
        knowledge["yellow_waste_total"] = percepts["yellow_waste_total"]
        knowledge["red_waste_count"]    = percepts["red_waste_count"]
        knowledge["action_success"]     = percepts.get("action_success", False)

        # Green waste on current cell (ignore cooldown cells)
        current_wastes = percepts["tiles"][pos]["wastes"]
        knowledge["green_wastes_here"] = (
            "green" in current_wastes and not self._is_on_cooldown(pos)
        )

        # Green waste in a neighbor cell
        knowledge["green_waste_neighbor"] = next(
            (
                p for p in knowledge["neighbor_positions"]
                if not self._is_on_cooldown(p)
                and "green" in percepts["tiles"][p]["wastes"]
            ),
            None,
        )

    # ------------------------------------------------------------------ #
    #  Deliberation — reads ONLY knowledge, no self.model.* calls        #
    # ------------------------------------------------------------------ #

    def _in_cleanup_mode(self, knowledge):
        return (
            knowledge["green_waste_total"] <= 1
            and knowledge["yellow_waste_total"] <= 1
        )

    def deliberate(self, knowledge):
        pos = knowledge["self_pos"]

        # Cleanup mode: drop held waste then wait
        if self._in_cleanup_mode(knowledge) and knowledge["red_waste_count"] == 0:
            if self.n_yellow_wastes == 1:
                return {"type": "drop"}
            if self.n_green_wastes > 0:
                return {"type": "drop_green"}
            return {"type": "wait"}

        # 1. Hands full → transform immediately
        if self.n_green_wastes == 2:
            return {"type": "transform"}

        # 2. Carrying yellow → move to rightmost col of z1 (x_max) then drop
        if self.n_yellow_wastes == 1:
            if pos[0] == self.x_max:
                return {"type": "drop"}
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}
            return {"type": "wait"}

        # 3. Holding 1 green too long → probabilistic early drop
        if ENABLE_DROP_PATIENCE and self.n_green_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_green / self._patience_value)
            if _random.random() < drop_prob:
                return {"type": "drop_green"}

        # 4. Green waste on current cell and capacity available
        if knowledge["green_wastes_here"] and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            return {"type": "pick"}

        # 5. Green waste spotted in a neighbor → move toward it
        neighbor = knowledge["green_waste_neighbor"]
        if neighbor and self.n_green_wastes < 2 and self.n_yellow_wastes == 0:
            target = self._get_toward_move(neighbor, knowledge)
            if target:
                return {"type": "move", "to": target}

        # 6. East-bias when carrying waste
        if ENABLE_EAST_BIAS and self.n_green_wastes > 0:
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}

        # 7. Explore
        target = self._get_random_move(knowledge)
        if target:
            return {"type": "move", "to": target}
        return {"type": "wait"}

    # ------------------------------------------------------------------ #
    #  Act — updates inventory only, no grid calls                        #
    # ------------------------------------------------------------------ #

    def act(self, action):
        atype = action.get("type") if isinstance(action, dict) else action

        if atype == "pick":
            if self.knowledge["action_success"]:
                self.n_green_wastes += 1
                self.steps_holding_green = 0

        elif atype == "transform":
            self.n_green_wastes  = 0
            self.n_yellow_wastes = 1
            self.steps_holding_green = 0

        elif atype == "drop_green":
            self.n_green_wastes = 0
            self.steps_holding_green = 0
            self.drop_cooldown[self.knowledge["self_pos"]] = self.model.width // 3

        elif atype == "drop":
            self.n_yellow_wastes = 0

        if self.n_green_wastes == 1:
            self.steps_holding_green += 1

    # ------------------------------------------------------------------ #
    #  Mesa step                                                           #
    # ------------------------------------------------------------------ #

    def step(self):
        self._tick_cooldowns()
        action   = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts)
        self.act(action)


class YellowAgent(RobotAgent):

    def __init__(self, model, x_min, x_max, home_x_min=None, home_x_max=None):
        super().__init__(model, x_min, x_max, home_x_min, home_x_max)
        self.n_yellow_wastes = 0
        self.n_red_wastes    = 0
        self.steps_holding_yellow = 0
        self._patience_value = model.width * 2
        self.knowledge = {
            "visited":                set(),
            "self_pos":               None,
            "neighbor_positions":     [],
            "yellow_wastes_here":     False,
            "yellow_waste_neighbor":  None,
            "green_waste_total":      999,
            "yellow_waste_total":     999,
            "red_waste_count":        999,
            "disposal_pos":           None,
            "action_success":         False,
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
        knowledge["green_waste_total"]   = percepts["green_waste_total"]
        knowledge["yellow_waste_total"]  = percepts["yellow_waste_total"]
        knowledge["red_waste_count"]     = percepts["red_waste_count"]
        knowledge["action_success"]      = percepts.get("action_success", False)

        current_wastes = percepts["tiles"][pos]["wastes"]
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
        if self.n_yellow_wastes == 2:
            return {"type": "transform"}

        # 2. Carrying red → move to rightmost col of z2 (x_max) then drop
        if self.n_red_wastes == 1:
            if pos[0] == self.x_max:
                return {"type": "drop"}
            target = self._get_east_move(knowledge)
            if target:
                return {"type": "move", "to": target}
            return {"type": "wait"}

        # 3. Patience drop
        if ENABLE_DROP_PATIENCE and self.n_yellow_wastes == 1:
            drop_prob = 1 - 1 / (1 + self.steps_holding_yellow / self._patience_value)
            if _random.random() < drop_prob:
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
        atype = action.get("type") if isinstance(action, dict) else action

        if atype == "pick":
            if self.knowledge["action_success"]:
                self.n_yellow_wastes += 1
                self.steps_holding_yellow = 0

        elif atype == "transform":
            self.n_yellow_wastes = 0
            self.n_red_wastes    = 1
            self.steps_holding_yellow = 0

        elif atype == "drop_yellow":
            self.n_yellow_wastes = 0
            self.steps_holding_yellow = 0
            self.drop_cooldown[self.knowledge["self_pos"]] = self.model.width // 3

        elif atype == "drop":
            self.n_red_wastes = 0

        if self.n_yellow_wastes == 1:
            self.steps_holding_yellow += 1

    def step(self):
        self._tick_cooldowns()
        action   = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts)
        self.act(action)


class RedAgent(RobotAgent):

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

        if atype == "pick":
            if self.knowledge["action_success"]:
                self.n_red_wastes += 1

        elif atype == "drop":
            self.n_red_wastes = 0

        elif atype == "cleanup_pick":
            if self.knowledge["action_success"]:
                self.cleanup_waste_type = action.get("waste_type") if isinstance(action, dict) else None
                self.n_cleanup_wastes += 1

        elif atype == "cleanup_drop":
            self.n_cleanup_wastes   = 0
            self.cleanup_waste_type = None

        # sweep_advance: _advance_sweep() is called by model._do_sweep_advance
        # move / wait: no inventory change

    def step(self):
        action   = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts)
        self.act(action)
