# Group: 23
# Date: 2026-03-16
# Members:
#   Khalil Ben Gamra
#   Sarra Sakgi
#   Ali Baklouti

import random
from mesa import Model
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector

from agents import GreenAgent, YellowAgent, RedAgent
from objects import RadioactivityAgent, WasteAgent, WasteDisposalZone


class RobotMission(Model):
    """Main model for the robot mission simulation."""

    def __init__(
        self,
        width=12,
        height=8,
        n_green_robots=2,
        n_yellow_robots=2,
        n_red_robots=1,
        initial_green_waste=12,
        initial_yellow_waste=0,
        initial_red_waste=0,
        seed=None,
    ):
        super().__init__()

        if seed is not None:
            random.seed(seed)

        self.width = width
        self.height = height
        self.grid = MultiGrid(width, height, torus=False)
        self.running = True

        self.disposal_pos = None

        self.stored_red_waste = 0
        self.transformed_green_to_yellow = 0
        self.transformed_yellow_to_red = 0

        self.step_count = 0
        self.broadcast_ttl = 4
        self._next_broadcast_id = 1
        self.active_broadcasts = []
        self.event_log = []
        self.emergency_cleanup = False

        self.datacollector = DataCollector(
            model_reporters={
                "Green waste": self.count_green_waste,
                "Yellow waste": self.count_yellow_waste,
                "Red waste": self.count_red_waste,
                "Stored red waste": lambda m: m.stored_red_waste,
                "Active broadcasts": lambda m: len(m.active_broadcasts),
                "Total waste": self.count_total_waste,
                "Weighted waste": self.count_weighted_waste,
            }
        )

        self._create_radioactivity_map()
        self._create_disposal_zone()
        self._create_initial_waste(initial_green_waste, "green", {"z1"})
        self._create_initial_waste(initial_yellow_waste, "yellow", {"z2"})
        self._create_initial_waste(initial_red_waste, "red", {"z3"})
        self._create_robots(n_green_robots, n_yellow_robots, n_red_robots)

        self.datacollector.collect(self)

    def get_zone_from_x(self, x):
        third = self.width // 3
        if x < third:
            return "z1"
        if x < 2 * third:
            return "z2"
        return "z3"

    def _zone_x_bounds(self, zone):
        third = self.width // 3
        if zone == "z1":
            return 0, third - 1
        if zone == "z2":
            return third, 2 * third - 1
        return 2 * third, self.width - 1

    def get_random_position(self, allowed_zones=None):
        candidates = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if allowed_zones is None or self.get_zone_from_x(x) in allowed_zones
        ]
        return random.choice(candidates) if candidates else None

    def _create_radioactivity_map(self):
        for x in range(self.width):
            for y in range(self.height):
                zone = self.get_zone_from_x(x)
                self.grid.place_agent(RadioactivityAgent(model=self, zone=zone), (x, y))

    def _create_disposal_zone(self):
        x = self.width - 1
        y = random.randrange(self.height)
        self.disposal_pos = (x, y)
        self.grid.place_agent(WasteDisposalZone(model=self), self.disposal_pos)

    def _create_initial_waste(self, n, waste_type, zones):
        for _ in range(n):
            pos = self.get_random_position(allowed_zones=zones)
            if pos is not None:
                self.grid.place_agent(WasteAgent(model=self, waste_type=waste_type), pos)

    def _create_robots(self, n_green, n_yellow, n_red):
        z1_xmin, z1_xmax = self._zone_x_bounds("z1")
        z2_xmin, z2_xmax = self._zone_x_bounds("z2")
        z3_xmin, z3_xmax = self._zone_x_bounds("z3")

        for _ in range(n_green):
            agent = GreenAgent(self, x_min=z1_xmin, x_max=z1_xmax, home_x_min=z1_xmin, home_x_max=z1_xmax)
            self.grid.place_agent(agent, (z1_xmin, random.randrange(self.height)))

        for _ in range(n_yellow):
            agent = YellowAgent(self, x_min=z1_xmin, x_max=z2_xmax, home_x_min=z1_xmax, home_x_max=z2_xmax)
            self.grid.place_agent(agent, (z2_xmin, random.randrange(self.height)))

        for _ in range(n_red):
            agent = RedAgent(
                self,
                x_min=z1_xmin,
                x_max=z3_xmax,
                disposal_zone_pos=self.disposal_pos,
                home_x_min=z2_xmax,
                home_x_max=z3_xmax,
            )
            self.grid.place_agent(agent, (z3_xmin, random.randrange(self.height)))

    def step(self):
        self.step_count += 1
        self._activate_emergency_cleanup_if_needed()
        if self.emergency_cleanup:
            self._publish_emergency_cleanup_targets()
        self._assign_open_broadcasts()
        self.agents.shuffle_do("step")
        self._activate_emergency_cleanup_if_needed()
        if self.emergency_cleanup:
            self._publish_emergency_cleanup_targets()
        self._assign_open_broadcasts()
        self._decay_broadcasts()
        self.datacollector.collect(self)

        if (
            self.count_green_waste() == 0
            and self.count_yellow_waste() == 0
            and self.count_red_waste() == 0
            and all(
                getattr(a, "n_green_wastes", 0) == 0
                and getattr(a, "n_yellow_wastes", 0) == 0
                and getattr(a, "n_red_wastes", 0) == 0
                for a in self.agents
            )
        ):
            self.running = False

    def build_percepts(self, agent):
        visible = [agent.pos] + list(
            self.grid.get_neighborhood(agent.pos, moore=True, include_center=False, radius=1)
        )

        tiles = {}
        for pos in visible:
            wastes, robots = [], []
            zone, radioactivity, is_disposal = None, None, False

            for obj in self.grid.get_cell_list_contents([pos]):
                if isinstance(obj, WasteAgent):
                    wastes.append(obj.waste_type)
                elif isinstance(obj, (GreenAgent, YellowAgent, RedAgent)):
                    robots.append(self._robot_type(obj))
                elif isinstance(obj, RadioactivityAgent):
                    zone = obj.zone
                    radioactivity = obj.radioactivity
                elif isinstance(obj, WasteDisposalZone):
                    is_disposal = True

            tiles[pos] = {
                "wastes": wastes,
                "robots": robots,
                "zone": zone,
                "radioactivity": radioactivity,
                "is_disposal": is_disposal,
            }

        green_held = sum(getattr(a, "n_green_wastes", 0) for a in self.agents if isinstance(a, GreenAgent))
        yellow_held = sum(getattr(a, "n_yellow_wastes", 0) for a in self.agents if isinstance(a, YellowAgent))

        return {
            "self_pos": agent.pos,
            "current_zone": tiles[agent.pos]["zone"],
            "disposal_pos": self.disposal_pos,
            "tiles": tiles,
            "active_broadcasts": list(self.active_broadcasts),
            "green_waste_total": self.count_green_waste() + green_held,
            "yellow_waste_total": self.count_yellow_waste() + yellow_held,
            "red_waste_count": self.count_red_waste(),
        }

    def _robot_type(self, agent):
        if agent is None:
            return "system"
        if isinstance(agent, GreenAgent):
            return "green"
        if isinstance(agent, YellowAgent):
            return "yellow"
        if isinstance(agent, RedAgent):
            return "red"
        return "unknown"

    def _robot_label(self, agent):
        if agent is None:
            return "system"
        return f"{self._robot_type(agent)}#{getattr(agent, 'unique_id', '?')}"

    def _robot_is_free(self, agent):
        carried = (
            getattr(agent, "n_green_wastes", 0)
            + getattr(agent, "n_yellow_wastes", 0)
            + getattr(agent, "n_red_wastes", 0)
        )
        return carried == 0 and getattr(agent, "current_task", None) is None

    def _waste_exists(self, pos, waste_type):
        return any(
            isinstance(obj, WasteAgent) and obj.waste_type == waste_type
            for obj in self.grid.get_cell_list_contents([pos])
        )

    def _cell_radioactivity(self, pos):
        for obj in self.grid.get_cell_list_contents([pos]):
            if isinstance(obj, RadioactivityAgent):
                return getattr(obj, "radioactivity", 0.0)
        return 0.0

    def _count_carried_waste(self, attr_name):
        return sum(getattr(agent, attr_name, 0) for agent in self.agents)

    def _activate_emergency_cleanup_if_needed(self):
        if self.emergency_cleanup:
            return

        green_units = self.count_green_waste() + self._count_carried_waste("n_green_wastes")
        yellow_units = self.count_yellow_waste() + self._count_carried_waste("n_yellow_wastes")
        red_units = self.count_red_waste() + self._count_carried_waste("n_red_wastes")

        if green_units + yellow_units + red_units == 0:
            return

        if green_units < 2 and yellow_units < 2:
            self.emergency_cleanup = True
            for agent in self.agents:
                if not isinstance(agent, RedAgent):
                    self.release_task(agent)
            self.log_event("Emergency cleanup activated: red robots dispose remaining waste")

    def _publish_emergency_cleanup_targets(self):
        seen = set()
        for contents, pos in self.grid.coord_iter():
            for obj in contents:
                if isinstance(obj, WasteAgent):
                    key = (pos, obj.waste_type)
                    if key in seen:
                        continue
                    seen.add(key)
                    self.emit_broadcast(None, pos, obj.waste_type, {"red"})

    def log_event(self, message):
        self.event_log.append(f"S{self.step_count}: {message}")
        self.event_log = self.event_log[-12:]

    def emit_broadcast(self, sender, pos, waste_type, target_types):
        if not self._waste_exists(pos, waste_type):
            return

        sender_pos = sender.pos if sender is not None else pos
        target_types = tuple(sorted(target_types))
        priority = self._cell_radioactivity(pos)

        for msg in self.active_broadcasts:
            if msg["pos"] == pos and msg["waste_type"] == waste_type:
                msg["ttl"] = self.broadcast_ttl
                msg["sender_pos"] = sender_pos
                msg["sender_type"] = self._robot_type(sender)
                msg["target_types"] = target_types
                msg["priority"] = priority
                return

        msg = {
            "id": self._next_broadcast_id,
            "pos": pos,
            "waste_type": waste_type,
            "sender_pos": sender_pos,
            "sender_type": self._robot_type(sender),
            "target_types": target_types,
            "ttl": self.broadcast_ttl,
            "priority": priority,
            "claimed_by": None,
            "claimed_by_type": None,
        }
        self._next_broadcast_id += 1
        self.active_broadcasts.append(msg)
        self.log_event(f"{self._robot_label(sender)} broadcasts {waste_type} waste at {pos}")

    def release_task(self, agent):
        task = getattr(agent, "current_task", None)
        if task is None:
            return
        for msg in self.active_broadcasts:
            if msg["id"] == task.get("broadcast_id") and msg.get("claimed_by") == agent.unique_id:
                msg["claimed_by"] = None
                msg["claimed_by_type"] = None
        agent.current_task = None

    def _assign_open_broadcasts(self):
        for msg in sorted(self.active_broadcasts, key=lambda m: (-m.get("priority", 0.0), m["id"])):
            if msg.get("claimed_by") is not None:
                continue

            candidates = []
            for agent in self.agents:
                if self._robot_type(agent) in msg["target_types"] and self._robot_is_free(agent):
                    distance = abs(agent.pos[0] - msg["pos"][0]) + abs(agent.pos[1] - msg["pos"][1])
                    candidates.append((distance, -agent.pos[0], agent.unique_id, agent))

            if not candidates:
                continue

            _, _, _, chosen = min(candidates)
            chosen.current_task = {
                "target_pos": msg["pos"],
                "waste_type": msg["waste_type"],
                "broadcast_id": msg["id"],
            }
            msg["claimed_by"] = chosen.unique_id
            msg["claimed_by_type"] = self._robot_type(chosen)
            self.log_event(f"{self._robot_label(chosen)} claims {msg['waste_type']} at {msg['pos']}")

    def _decay_broadcasts(self):
        kept = []
        for msg in self.active_broadcasts:
            if not self._waste_exists(msg["pos"], msg["waste_type"]):
                if msg.get("claimed_by") is not None:
                    for agent in self.agents:
                        if getattr(agent, "unique_id", None) == msg["claimed_by"]:
                            agent.current_task = None
                continue

            if msg.get("claimed_by") is not None:
                msg["ttl"] = max(msg.get("ttl", 1), 1)
                kept.append(msg)
                continue

            msg["ttl"] -= 1
            if msg["ttl"] > 0:
                kept.append(msg)

        self.active_broadcasts = kept

    def do(self, agent, action):
        if action is None:
            return self.build_percepts(agent)

        action_type = action.get("type") if isinstance(action, dict) else action
        dispatch = {
            "move": self._do_move,
            "pick": self._do_pick,
            "transform": self._do_transform,
            "drop": self._do_drop,
            "drop_green": self._do_drop_green,
            "drop_yellow": self._do_drop_yellow,
            "wait": lambda a, act: None,
        }

        handler = dispatch.get(action_type)
        action_success = False
        if handler:
            result = handler(agent, action)
            action_success = result is True

        percepts = self.build_percepts(agent)
        percepts["action_success"] = action_success
        return percepts

    def _do_move(self, agent, action):
        new_pos = action.get("to") if isinstance(action, dict) else None
        if new_pos is None:
            return
        if self.grid.out_of_bounds(new_pos):
            return
        if not self._is_adjacent(agent.pos, new_pos):
            return
        if not (agent.x_min <= new_pos[0] <= agent.x_max):
            return
        self.grid.move_agent(agent, new_pos)

    def _do_pick(self, agent, action=None):
        if isinstance(agent, GreenAgent):
            target = "green"
        elif isinstance(agent, YellowAgent):
            target = "yellow"
        elif isinstance(agent, RedAgent):
            target = "red"
        else:
            return False

        for obj in self.grid.get_cell_list_contents([agent.pos]):
            if isinstance(obj, WasteAgent) and obj.waste_type == target:
                self.grid.remove_agent(obj)
                return True
        return False

    def _do_transform(self, agent, action=None):
        if isinstance(agent, GreenAgent) and agent.n_green_wastes >= 2:
            self.transformed_green_to_yellow += 1
        elif isinstance(agent, YellowAgent) and agent.n_yellow_wastes >= 2:
            self.transformed_yellow_to_red += 1

    def _do_drop(self, agent, action=None):
        if isinstance(agent, GreenAgent) and agent.n_yellow_wastes >= 1:
            self.grid.place_agent(WasteAgent(model=self, waste_type="yellow"), agent.pos)
        elif isinstance(agent, YellowAgent) and agent.n_red_wastes >= 1:
            self.grid.place_agent(WasteAgent(model=self, waste_type="red"), agent.pos)
        elif isinstance(agent, RedAgent) and agent.pos == self.disposal_pos and agent.n_red_wastes >= 1:
            self.stored_red_waste += 1

    def _do_drop_green(self, agent, action=None):
        if isinstance(agent, GreenAgent) and agent.n_green_wastes >= 1:
            self.grid.place_agent(WasteAgent(model=self, waste_type="green"), agent.pos)

    def _do_drop_yellow(self, agent, action=None):
        if isinstance(agent, YellowAgent) and agent.n_yellow_wastes >= 1:
            self.grid.place_agent(WasteAgent(model=self, waste_type="yellow"), agent.pos)

    def count_green_waste(self):
        return self._count_waste_type("green")

    def count_yellow_waste(self):
        return self._count_waste_type("yellow")

    def count_red_waste(self):
        return self._count_waste_type("red")

    def _count_waste_type(self, waste_type):
        return sum(
            1
            for contents, _ in self.grid.coord_iter()
            for obj in contents
            if isinstance(obj, WasteAgent) and obj.waste_type == waste_type
        )

    def count_total_waste(self):
        grid = self.count_green_waste() + self.count_yellow_waste() + self.count_red_waste()
        carried = sum(
            getattr(a, "n_green_wastes", 0)
            + getattr(a, "n_yellow_wastes", 0)
            + getattr(a, "n_red_wastes", 0)
            for a in self.agents
            if isinstance(a, (GreenAgent, YellowAgent, RedAgent))
        )
        return grid + carried

    def count_weighted_waste(self):
        weights = {"green": 1, "yellow": 2, "red": 4}
        grid_w = sum(
            weights.get(obj.waste_type, 0)
            for contents, _ in self.grid.coord_iter()
            for obj in contents
            if isinstance(obj, WasteAgent)
        )

        carried_w = 0
        for agent in self.agents:
            if isinstance(agent, GreenAgent):
                carried_w += getattr(agent, "n_green_wastes", 0) * 1
                carried_w += getattr(agent, "n_yellow_wastes", 0) * 2
            elif isinstance(agent, YellowAgent):
                carried_w += getattr(agent, "n_yellow_wastes", 0) * 2
                carried_w += getattr(agent, "n_red_wastes", 0) * 4
            elif isinstance(agent, RedAgent):
                carried_type = getattr(agent, "carried_waste_type", None) or "red"
                carried_w += getattr(agent, "n_red_wastes", 0) * weights.get(carried_type, 4)

        return grid_w + carried_w

    @staticmethod
    def _is_adjacent(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) == 1
