# Group: 23
# Date: 2026-03-16
# Members: 
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import random
from mesa import Agent

class RadioactivityAgent(Agent):
    def __init__(self, unique_id, model, zone):
        super().__init__(unique_id, model)
        self.zone = zone
        
        if zone == "z1":
            self.radioactivity = random.uniform(0, 0.33)
        elif zone == "z2":
            self.radioactivity = random.uniform(0.33, 0.66)
        elif zone == "z3":
            self.radioactivity = random.uniform(0.66, 1.0)


class WasteAgent(Agent):
    def __init__(self, unique_id, model, waste_type):
        super().__init__(unique_id, model)
        self.waste_type = waste_type  # "green", "yellow", or "red"


class WasteDisposalZone(Agent):
    RADIOACTIVITY = 2.0

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.radioactivity = WasteDisposalZone.RADIOACTIVITY