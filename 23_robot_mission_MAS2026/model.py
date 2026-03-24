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
    """
    Modèle principal de la mission des robots.

    Responsabilités :
    - créer et gérer la grille (radioactivité, déchets, zone de dépôt)
    - instancier les robots avec les bons paramètres de zone
    - exposer do() pour que les agents puissent agir sur l'environnement
    - collecter des statistiques via DataCollector
    """

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

        # Position de la zone de dépôt final (colonne la plus à l'est)
        self.disposal_pos = None

        # Statistiques globales
        self.stored_red_waste = 0
        self.transformed_green_to_yellow = 0
        self.transformed_yellow_to_red = 0

        # DataCollector
        self.datacollector = DataCollector(
            model_reporters={
                "Green waste":      self.count_green_waste,
                "Yellow waste":     self.count_yellow_waste,
                "Red waste":        self.count_red_waste,
                "Stored red waste": lambda m: m.stored_red_waste,
            }
        )

        # Construction de l'environnement
        self._create_radioactivity_map()
        self._create_disposal_zone()
        self._create_initial_green_waste(initial_green_waste)
        self._create_initial_waste(initial_yellow_waste, "yellow", {"z2"})
        self._create_initial_waste(initial_red_waste, "red", {"z3"})
        self._create_robots(n_green_robots, n_yellow_robots, n_red_robots)

        # Collecte initiale
        self.datacollector.collect(self)

 
    #  Utilitaires internes                                          


    def get_zone_from_x(self, x):
        """
        Découpe la grille en 3 bandes verticales égales :
          z1 (ouest)  → x < width//3
          z2 (milieu) → width//3 <= x < 2*width//3
          z3 (est)    → x >= 2*width//3
        """
        third = self.width // 3
        if x < third:
            return "z1"
        elif x < 2 * third:
            return "z2"
        return "z3"

    def _zone_x_bounds(self, zone):
        """Retourne (x_min, x_max) inclus pour une zone donnée."""
        third = self.width // 3
        if zone == "z1":
            return 0, third - 1
        elif zone == "z2":
            return third, 2 * third - 1
        else:  # z3
            return 2 * third, self.width - 1

    def get_random_position(self, allowed_zones=None):
        """
        Renvoie une position aléatoire dans la grille,
        éventuellement limitée à certaines zones (ensemble de chaînes).
        Plusieurs objets peuvent partager la même case (MultiGrid).
        """
        candidates = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if allowed_zones is None or self.get_zone_from_x(x) in allowed_zones
        ]
        return random.choice(candidates) if candidates else None


    #  Construction de l'environnement                                     


    def _create_radioactivity_map(self):
        """Place un RadioactivityAgent sur chaque case de la grille."""
        for x in range(self.width):
            for y in range(self.height):
                zone = self.get_zone_from_x(x)
                obj = RadioactivityAgent(model=self, zone=zone)
                self.grid.place_agent(obj, (x, y))

    def _create_disposal_zone(self):
        """
        Place la zone de dépôt sur une case aléatoire
        de la colonne la plus à l'est (x = width - 1).
        """
        x = self.width - 1
        y = random.randrange(self.height)
        self.disposal_pos = (x, y)
        obj = WasteDisposalZone(model=self)
        self.grid.place_agent(obj, self.disposal_pos)

    def _create_initial_green_waste(self, n):
        """Place n déchets verts aléatoirement en zone z1."""
        for _ in range(n):
            pos = self.get_random_position(allowed_zones={"z1"})
            waste = WasteAgent(model=self, waste_type="green")
            self.grid.place_agent(waste, pos)

    def _create_initial_waste(self, n, waste_type, zones):
        """Place n déchets d'un type donné dans les zones spécifiées."""
        for _ in range(n):
            pos = self.get_random_position(allowed_zones=zones)
            waste = WasteAgent(model=self, waste_type=waste_type)
            self.grid.place_agent(waste, pos)

    def _create_robots(self, n_green, n_yellow, n_red):
        """
        Instancie les robots avec les bornes de zone correctes
        et les ajoute au scheduler.

        Signatures des constructeurs (agents.py) :
          GreenAgent(model, x_min, x_max)
          YellowAgent(model, x_min, x_max)
          RedAgent(model, x_min, x_max, disposal_zone_pos)
        """
        # Bornes de chaque zone
        z1_xmin, z1_xmax = self._zone_x_bounds("z1")
        z2_xmin, z2_xmax = self._zone_x_bounds("z2")
        z3_xmin, z3_xmax = self._zone_x_bounds("z3")

        # Green : home = z1, spawn on leftmost column of z1
        for _ in range(n_green):
            agent = GreenAgent(self, x_min=z1_xmin, x_max=z1_xmax,
                               home_x_min=z1_xmin, home_x_max=z1_xmax)
            y = random.randrange(self.height)
            self.grid.place_agent(agent, (z1_xmin, y))

        # Yellow : home = handoff col of z1 + z2, spawn on leftmost column of z2
        for _ in range(n_yellow):
            agent = YellowAgent(self, x_min=z1_xmin, x_max=z2_xmax,
                                home_x_min=z1_xmax, home_x_max=z2_xmax)
            y = random.randrange(self.height)
            self.grid.place_agent(agent, (z2_xmin, y))

        # Red : home = handoff col of z2 + z3, spawn on leftmost column of z3
        for _ in range(n_red):
            agent = RedAgent(self, x_min=z1_xmin, x_max=z3_xmax,
                             home_x_min=z2_xmax, home_x_max=z3_xmax)
            y = random.randrange(self.height)
            self.grid.place_agent(agent, (z3_xmin, y))


    #  Boucle de simulation                                               
 

    def step(self):
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)
        if (
            self.count_green_waste() == 0
            and self.count_yellow_waste() == 0
            and self.count_red_waste() == 0
            and all(
                getattr(a, "n_green_wastes", 0) == 0
                and getattr(a, "n_yellow_wastes", 0) == 0
                and getattr(a, "n_red_wastes", 0) == 0
                and getattr(a, "n_cleanup_wastes", 0) == 0
                for a in self.agents
            )
        ):
            self.running = False

 
    #  Percepts                                                           
 

    def build_percepts(self, agent):
        """
        Construit le dictionnaire de percepts renvoyé à un robot.
        Contenu pour chaque case visible (case courante + voisins Von Neumann) :
          - wastes       : liste des types de déchets présents
          - robots       : liste des types de robots présents
          - zone         : identifiant de zone ("z1" / "z2" / "z3")
          - radioactivity: niveau de radioactivité (float)
          - is_disposal  : booléen, True si c'est la zone de dépôt
        """
        visible = [agent.pos] + list(
            self.grid.get_neighborhood(agent.pos, moore=False, include_center=False)
        )

        tiles = {}
        for pos in visible:
            wastes, robots = [], []
            zone, radioactivity, is_disposal = None, None, False

            for obj in self.grid.get_cell_list_contents([pos]):
                if isinstance(obj, WasteAgent):
                    wastes.append(obj.waste_type)
                elif isinstance(obj, (GreenAgent, YellowAgent, RedAgent)):
                    robot_type = (
                        "green" if isinstance(obj, GreenAgent)
                        else "yellow" if isinstance(obj, YellowAgent)
                        else "red"
                    )
                    robots.append(robot_type)
                elif isinstance(obj, RadioactivityAgent):
                    zone = obj.zone
                    radioactivity = obj.radioactivity
                elif isinstance(obj, WasteDisposalZone):
                    is_disposal = True

            tiles[pos] = {
                "wastes":        wastes,
                "robots":        robots,
                "zone":          zone,
                "radioactivity": radioactivity,
                "is_disposal":   is_disposal,
            }

        return {
            "self_pos":     agent.pos,
            "current_zone": tiles[agent.pos]["zone"],
            "disposal_pos": self.disposal_pos,
            "tiles":        tiles,
        }

    #  Exécution des actions — méthode do()                               
  

    def do(self, agent, action):
        """
        Point d'entrée unique pour toute action d'un robot.

        Le modèle est responsable des effets sur la grille
        (ajouter/supprimer des WasteAgent).
        Les robots gèrent eux-mêmes leur inventaire interne
        (n_*_wastes) dans agents.py.

        Retourne les nouveaux percepts après exécution.
        """
        if action is None:
            return self.build_percepts(agent)

        dispatch = {
            "move":      self._do_move,
            "pick":      self._do_pick,
            "transform": self._do_transform,
            "drop":      self._do_drop,
            "wait":      lambda a, act: None,
        }

        handler = dispatch.get(action if isinstance(action, str) else action.get("type"))
        if handler:
            handler(agent, action)

        return self.build_percepts(agent)

    # MOVE 

    def _do_move(self, agent, action):
        """
        Déplace l'agent vers une case adjacente autorisée.
        action : {"type": "move", "to": (x, y)}
        """
        new_pos = action.get("to") if isinstance(action, dict) else None
        if new_pos is None:
            return

        # Vérification : case dans la grille
        if self.grid.out_of_bounds(new_pos):
            return

        # Vérification : case adjacente (distance de Manhattan == 1)
        if not self._is_adjacent(agent.pos, new_pos):
            return

        # Vérification : case dans les bornes de zone de l'agent
        nx = new_pos[0]
        if not (agent.x_min <= nx <= agent.x_max):
            return

        self.grid.move_agent(agent, new_pos)

    #  PICK 

    def _do_pick(self, agent, action=None):
        """
        Retire un déchet de la grille sur la case de l'agent.
        L'inventaire est mis à jour par l'agent lui-même dans act().
        
        Le modèle vérifie qu'il existe bien un déchet ramassable
        avant de le supprimer de la grille.
        """
        # Détermine le type de déchet attendu selon le type de robot
        if isinstance(agent, GreenAgent):
            target = "green"
        elif isinstance(agent, YellowAgent):
            target = "yellow"
        elif isinstance(agent, RedAgent):
            target = "red"
        else:
            return

        for obj in self.grid.get_cell_list_contents([agent.pos]):
            if isinstance(obj, WasteAgent) and obj.waste_type == target:
                self.grid.remove_agent(obj)
                return  # on ne retire qu'un seul déchet par action

    # TRANSFORM

    def _do_transform(self, agent, action=None):
        """
        Transformation : pas d'effet sur la grille.
        L'inventaire est modifié par l'agent dans act().
        On incrémente uniquement les compteurs globaux du modèle.
        """
        if isinstance(agent, GreenAgent) and agent.n_green_wastes >= 2:
            self.transformed_green_to_yellow += 1
        elif isinstance(agent, YellowAgent) and agent.n_yellow_wastes >= 2:
            self.transformed_yellow_to_red += 1

    # DROP 
    def _do_drop(self, agent, action=None):
        """
        Dépose un déchet transformé sur la grille.

        - GreenAgent  : dépose un déchet yellow sur sa case courante
        - YellowAgent : dépose un déchet red sur sa case courante
        - RedAgent    : si sur la disposal zone, le déchet est mis de côté
                        (stored_red_waste++) sans créer d'objet sur la grille
        """
        if isinstance(agent, GreenAgent):
            if agent.n_yellow_wastes >= 1:
                waste = WasteAgent(model=self, waste_type="yellow")
                self.grid.place_agent(waste, agent.pos)

        elif isinstance(agent, YellowAgent):
            if agent.n_red_wastes >= 1:
                waste = WasteAgent(model=self, waste_type="red")
                self.grid.place_agent(waste, agent.pos)

        elif isinstance(agent, RedAgent):
            if agent.pos == self.disposal_pos and agent.n_red_wastes >= 1:
                self.stored_red_waste += 1
                # Pas de WasteAgent créé : le déchet est définitivement stocké


    #  Statistiques                                                      
  

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

   
    #  Outils statiques                                                    


    @staticmethod
    def _is_adjacent(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) == 1