# Group: 23
# Date: 2026-03-16
# Members: 
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti



import random
from mesa import Model
from mesa.space import MultiGrid
from mesa.time import RandomActivation
from mesa.datacollection import DataCollector

from agents import GreenAgent, YellowAgent, RedAgent
from objects import RadioactivityAgent, WasteAgent, WasteDisposalZone


class RobotMission(Model):
    """
    Modèle principal de la mission des robots.
    Il contient :
    - la grille
    - les agents robots
    - les objets passifs (déchets, radioactivité, zone de dépôt)
    - la logique d'exécution des actions via do()
    """

    def __init__(
        self,
        width=12,
        height=8,
        n_green_robots=2,
        n_yellow_robots=2,
        n_red_robots=1,
        initial_green_waste=12,
        seed=None
    ):
        super().__init__()

        if seed is not None:
            random.seed(seed)

        self.width = width
        self.height = height
        self.grid = MultiGrid(width, height, torus=False)
        self.schedule = RandomActivation(self)
        self.running = True

        self.current_id = 0

        # Position de la zone finale de dépôt
        self.disposal_pos = None

        # Statistiques utiles
        self.stored_red_waste = 0
        self.transformed_green_to_yellow = 0
        self.transformed_yellow_to_red = 0

        # DataCollector pour les graphiques
        self.datacollector = DataCollector(
            model_reporters={
                "Green waste": self.count_green_waste,
                "Yellow waste": self.count_yellow_waste,
                "Red waste": self.count_red_waste,
                "Stored red waste": lambda m: m.stored_red_waste
            }
        )

        # Créer le fond de carte : radioactivité / zones
        self._create_radioactivity_map()

        # Créer la case de dépôt finale
        self._create_disposal_zone()

        # Ajouter les déchets verts initiaux
        self._create_initial_green_waste(initial_green_waste)

        # Ajouter les robots
        self._create_robots(n_green_robots, n_yellow_robots, n_red_robots)

        # Collecte initiale
        self.datacollector.collect(self)

    # OUTILS GÉNÉRAUX
 
    def next_id(self):
        self.current_id += 1
        return self.current_id

    def get_zone_from_x(self, x):
        """
        Découpe la grille en 3 bandes verticales :
        - z1 à l'ouest
        - z2 au milieu
        - z3 à l'est
        """
        third = self.width // 3

        if x < third:
            return "z1"
        elif x < 2 * third:
            return "z2"
        return "z3"

    def get_random_empty_position(self, allowed_zones=None):
        """
        Renvoie une position aléatoire, éventuellement limitée à certaines zones.
        """
        candidates = []

        for x in range(self.width):
            for y in range(self.height):
                zone = self.get_zone_from_x(x)
                if allowed_zones is not None and zone not in allowed_zones:
                    continue
                candidates.append((x, y))

        return random.choice(candidates) if candidates else None


    # CRÉATION DE L'ENVIRONNEMENT
  
    def _create_radioactivity_map(self):
        """
        Place un objet RadioactivityAgent sur chaque case.
        Chaque objet indique :
        - sa zone
        - son niveau de radioactivité
        """
        for x in range(self.width):
            for y in range(self.height):
                zone = self.get_zone_from_x(x)

                if zone == "z1":
                    radioactivity = random.uniform(0.0, 0.33)
                elif zone == "z2":
                    radioactivity = random.uniform(0.33, 0.66)
                else:
                    radioactivity = random.uniform(0.66, 1.0)

                radio_obj = RadioactivityAgent(
                    unique_id=self.next_id(),
                    model=self,
                    zone=zone,
                    radioactivity=radioactivity
                )
                self.grid.place_agent(radio_obj, (x, y))

    def _create_disposal_zone(self):
        """
        La zone de dépôt final doit être le plus à l'est possible.
        On choisit une case aléatoire dans la dernière colonne.
        """
        x = self.width - 1
        y = random.randrange(self.height)
        self.disposal_pos = (x, y)

        disposal = WasteDisposalZone(
            unique_id=self.next_id(),
            model=self
        )
        self.grid.place_agent(disposal, self.disposal_pos)

    def _create_initial_green_waste(self, n):
        """
        Les déchets initiaux verts sont placés en z1.
        """
        for _ in range(n):
            pos = self.get_random_empty_position(allowed_zones={"z1"})
            waste = WasteAgent(
                unique_id=self.next_id(),
                model=self,
                waste_type="green"
            )
            self.grid.place_agent(waste, pos)

    def _create_robots(self, n_green, n_yellow, n_red):
        """
        Place les robots dans des zones cohérentes avec leurs déplacements.
        """
        for _ in range(n_green):
            agent = GreenAgent(self.next_id(), self)
            pos = self.get_random_empty_position(allowed_zones={"z1"})
            self.grid.place_agent(agent, pos)
            self.schedule.add(agent)
            agent.percepts = self.build_percepts(agent)

        for _ in range(n_yellow):
            agent = YellowAgent(self.next_id(), self)
            pos = self.get_random_empty_position(allowed_zones={"z1", "z2"})
            self.grid.place_agent(agent, pos)
            self.schedule.add(agent)
            agent.percepts = self.build_percepts(agent)

        for _ in range(n_red):
            agent = RedAgent(self.next_id(), self)
            pos = self.get_random_empty_position(allowed_zones={"z1", "z2", "z3"})
            self.grid.place_agent(agent, pos)
            self.schedule.add(agent)
            agent.percepts = self.build_percepts(agent)

    # BOUCLE DE SIMULATION
 
    def step(self):
        self.schedule.step()
        self.datacollector.collect(self)

   
    # PERCEPTS
 
    def build_percepts(self, agent):
        """
        Construit le dictionnaire des percepts renvoyé au robot.
        On inclut :
        - la position du robot
        - la zone actuelle
        - la position de la disposal zone
        - le contenu de la case courante et des cases adjacentes
        """
        visible_positions = [agent.pos]
        visible_positions += self.grid.get_neighborhood(
            agent.pos,
            moore=False,
            include_center=False
        )

        tiles = {}

        for pos in visible_positions:
            contents = self.grid.get_cell_list_contents([pos])

            wastes = []
            robots = []
            zone = None
            is_disposal = False
            radioactivity = None

            for obj in contents:
                if isinstance(obj, WasteAgent):
                    wastes.append(obj.waste_type)
                elif isinstance(obj, (GreenAgent, YellowAgent, RedAgent)):
                    robots.append(obj.robot_type)
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
                "is_disposal": is_disposal
            }

        current_zone = tiles[agent.pos]["zone"]

        return {
            "self_pos": agent.pos,
            "current_zone": current_zone,
            "disposal_pos": self.disposal_pos,
            "tiles": tiles
        }


    # EXÉCUTION DES ACTIONS

    def do(self, agent, action):
        """
        Exécute une action demandée par un robot.
        Le modèle vérifie si l'action est faisable.
        Ensuite il modifie l'environnement et/ou l'inventaire du robot.
        Puis il renvoie les nouveaux percepts.
        """
        if action is None:
            return self.build_percepts(agent)

        action_type = action.get("type")

        if action_type == "move":
            self._do_move(agent, action)

        elif action_type == "pick":
            self._do_pick(agent)

        elif action_type == "transform":
            self._do_transform(agent)

        elif action_type == "drop":
            self._do_drop(agent)

        elif action_type == "wait":
            pass

        return self.build_percepts(agent)


    # ACTION : MOVE
    
    def _do_move(self, agent, action):
        new_pos = action.get("to")

        if new_pos is None:
            return

        # vérifier que la case cible est dans la grille
        if not self.grid.out_of_bounds(new_pos):
            pass
        else:
            return

        # vérifier que la case est adjacente
        if not self.is_adjacent(agent.pos, new_pos):
            return

        # vérifier que la zone cible est autorisée
        new_zone = self.get_zone_from_x(new_pos[0])
        if new_zone not in agent.allowed_zones:
            return

        #  si tout est bon, on déplace l'agent
        self.grid.move_agent(agent, new_pos)


    # ACTION : PICK
  
    def _do_pick(self, agent):
        """
        Le robot ramasse un déchet du type qu'il cherche.
        """
        cell_contents = self.grid.get_cell_list_contents([agent.pos])

        # si le robot a déjà la quantité max du déchet cible, il ne prend plus
        if agent.inventory[agent.target_waste] >= agent.capacity:
            return

        for obj in cell_contents:
            if isinstance(obj, WasteAgent) and obj.waste_type == agent.target_waste:
                self.grid.remove_agent(obj)
                agent.inventory[agent.target_waste] += 1
                return


    # ACTION : TRANSFORM

    def _do_transform(self, agent):
        """
        Green robot : 2 green -> 1 yellow
        Yellow robot : 2 yellow -> 1 red
        Red robot : rien
        """
        if agent.robot_type == "green":
            if agent.inventory["green"] >= 2:
                agent.inventory["green"] -= 2
                agent.inventory["yellow"] += 1
                self.transformed_green_to_yellow += 1

        elif agent.robot_type == "yellow":
            if agent.inventory["yellow"] >= 2:
                agent.inventory["yellow"] -= 2
                agent.inventory["red"] += 1
                self.transformed_yellow_to_red += 1

    # ACTION : DROP

    def _do_drop(self, agent):
        """
        Cas principaux :
        - Green robot : dépose un yellow sur sa case
        - Yellow robot : dépose un red sur sa case
        - Red robot : dépose le red dans la disposal zone
        """
        if agent.robot_type == "green":
            if agent.inventory["yellow"] >= 1:
                agent.inventory["yellow"] -= 1
                waste = WasteAgent(
                    unique_id=self.next_id(),
                    model=self,
                    waste_type="yellow"
                )
                self.grid.place_agent(waste, agent.pos)

        elif agent.robot_type == "yellow":
            if agent.inventory["red"] >= 1:
                agent.inventory["red"] -= 1
                waste = WasteAgent(
                    unique_id=self.next_id(),
                    model=self,
                    waste_type="red"
                )
                self.grid.place_agent(waste, agent.pos)

        elif agent.robot_type == "red":
            if agent.pos == self.disposal_pos and agent.inventory["red"] >= 1:
                agent.inventory["red"] -= 1
                self.stored_red_waste += 1

 
    # OUTILS
  
    @staticmethod
    def is_adjacent(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) == 1

    def count_green_waste(self):
        return self._count_waste_type("green")

    def count_yellow_waste(self):
        return self._count_waste_type("yellow")

    def count_red_waste(self):
        return self._count_waste_type("red")

    def _count_waste_type(self, waste_type):
        count = 0
        for cell_content, x, y in self.grid.coord_iter():
            for obj in cell_content:
                if isinstance(obj, WasteAgent) and obj.waste_type == waste_type:
                    count += 1
        return count