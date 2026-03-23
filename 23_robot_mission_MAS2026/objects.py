# Group: 23
# Date: 2026-03-16
# Members: 
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

import random
from mesa import Agent

class RadioactivityAgent(Agent):
    def __init__(self, model, zone):
        super().__init__(model)
        self.zone = zone

        if zone == "z1":
            self.radioactivity = random.uniform(0, 0.33)
        elif zone == "z2":
            self.radioactivity = random.uniform(0.33, 0.66)
        elif zone == "z3":
            self.radioactivity = random.uniform(0.66, 1.0)


class WasteAgent(Agent):
    def __init__(self, model, waste_type):
        super().__init__(model)
        self.waste_type = waste_type  # "green", "yellow", or "red"


class WasteDisposalZone(Agent):
    RADIOACTIVITY = 2.0

    def __init__(self, model):
        super().__init__(model)
        self.radioactivity = WasteDisposalZone.RADIOACTIVITY