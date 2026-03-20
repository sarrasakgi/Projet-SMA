# Group: 23
# Date: 2026-03-16
# Members:
    # Khalil Ben Gamra
    # Sarra Sakgi
    # Ali Baklouti

from mesa.visualization.modules import CanvasGrid, ChartModule
from mesa.visualization.ModularServer import ModularServer
from mesa.visualization.UserParam import Slider, StaticText

from model import RobotMission
from agents import GreenAgent, YellowAgent, RedAgent
from objects import RadioactivityAgent, WasteAgent, WasteDisposalZone

# ------------------------------------------------------------------ #
#  Portrayal function                                                  #
# ------------------------------------------------------------------ #
# Called once per agent per cell.  Layer ordering:
#   0 – radioactivity background
#   1 – waste disposal zone marker
#   2 – waste objects
#   3 – robots (drawn on top)

def agent_portrayal(agent):

    # -- Background: zone radioactivity level -------------------------
    if isinstance(agent, RadioactivityAgent):
        intensity = agent.radioactivity          # value in [0, 1] for zones 1-3
        if agent.zone == "z1":
            color = f"rgba(0,200,0,{0.15 + 0.4 * intensity})"
        elif agent.zone == "z2":
            color = f"rgba(255,200,0,{0.15 + 0.4 * intensity})"
        else:  # z3
            color = f"rgba(220,0,0,{0.15 + 0.4 * intensity})"
        return {
            "Shape": "rect",
            "Color": color,
            "Filled": "true",
            "w": 1,
            "h": 1,
            "Layer": 0,
        }

    # -- Disposal zone ------------------------------------------------
    if isinstance(agent, WasteDisposalZone):
        return {
            "Shape": "rect",
            "Color": "#222222",
            "Filled": "true",
            "w": 0.95,
            "h": 0.95,
            "Layer": 1,
            "text": "DZ",
            "text_color": "white",
        }

    # -- Waste objects ------------------------------------------------
    if isinstance(agent, WasteAgent):
        colors = {"green": "#00cc00", "yellow": "#e6b800", "red": "#cc0000"}
        return {
            "Shape": "circle",
            "Color": colors.get(agent.waste_type, "grey"),
            "Filled": "true",
            "r": 0.25,
            "Layer": 2,
        }

    # -- Robots -------------------------------------------------------
    if isinstance(agent, GreenAgent):
        label = f"G({agent.n_green_wastes},{agent.n_yellow_wastes})"
        return {
            "Shape": "circle",
            "Color": "#005500",
            "Filled": "true",
            "r": 0.45,
            "Layer": 3,
            "text": label,
            "text_color": "white",
        }

    if isinstance(agent, YellowAgent):
        label = f"Y({agent.n_yellow_wastes},{agent.n_red_wastes})"
        return {
            "Shape": "circle",
            "Color": "#806000",
            "Filled": "true",
            "r": 0.45,
            "Layer": 3,
            "text": label,
            "text_color": "white",
        }

    if isinstance(agent, RedAgent):
        label = f"R({agent.n_red_wastes})"
        return {
            "Shape": "circle",
            "Color": "#660000",
            "Filled": "true",
            "r": 0.45,
            "Layer": 3,
            "text": label,
            "text_color": "white",
        }

    return {}   # unknown agent type → invisible


# ------------------------------------------------------------------ #
#  Grid                                                                #
# ------------------------------------------------------------------ #

GRID_WIDTH  = 12
GRID_HEIGHT = 8
PIXELS_PER_CELL = 60

grid = CanvasGrid(
    agent_portrayal,
    GRID_WIDTH,
    GRID_HEIGHT,
    GRID_WIDTH  * PIXELS_PER_CELL,
    GRID_HEIGHT * PIXELS_PER_CELL,
)

# ------------------------------------------------------------------ #
#  Charts                                                              #
# ------------------------------------------------------------------ #

waste_chart = ChartModule(
    [
        {"Label": "Green waste",  "Color": "#00cc00"},
        {"Label": "Yellow waste", "Color": "#e6b800"},
        {"Label": "Red waste",    "Color": "#cc0000"},
    ],
    data_collector_name="datacollector",
)

storage_chart = ChartModule(
    [{"Label": "Stored red waste", "Color": "#660000"}],
    data_collector_name="datacollector",
)

# ------------------------------------------------------------------ #
#  User-adjustable parameters                                          #
# ------------------------------------------------------------------ #

model_params = {
    "title":           StaticText("<b>Robot Mission — Group 23</b>"),
    "width":           GRID_WIDTH,
    "height":          GRID_HEIGHT,
    "n_green_robots":  Slider("Green robots",  value=2, min_val=1, max_val=6, step=1),
    "n_yellow_robots": Slider("Yellow robots", value=2, min_val=1, max_val=6, step=1),
    "n_red_robots":    Slider("Red robots",    value=1, min_val=1, max_val=4, step=1),
    "initial_green_waste": Slider("Initial green waste", value=12, min_val=2, max_val=30, step=2),
}

# ------------------------------------------------------------------ #
#  Server                                                              #
# ------------------------------------------------------------------ #

server = ModularServer(
    RobotMission,
    [grid, waste_chart, storage_chart],
    "Robot Mission — Group 23",
    model_params,
)

server.port = 8521

if __name__ == "__main__":
    server.launch()
