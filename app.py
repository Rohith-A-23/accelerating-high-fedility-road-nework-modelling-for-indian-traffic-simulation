import streamlit as st
import random
import time

# -----------------------------
# CONFIG
# -----------------------------
ROAD_LENGTH = 60

VEHICLE_TYPES = {
    "2W": {"speed": 2, "symbol": "🛵"},
    "AUTO": {"speed": 1.5, "symbol": "🛺"},
    "CAR": {"speed": 2, "symbol": "🚗"},
    "BUS": {"speed": 1, "symbol": "🚌"}
}

# -----------------------------
# VEHICLE CLASS
# -----------------------------
class Vehicle:
    def __init__(self, vtype):
        self.vtype = vtype
        self.speed = VEHICLE_TYPES[vtype]["speed"]
        self.symbol = VEHICLE_TYPES[vtype]["symbol"]
        self.pos = 0

    def move(self, road):
        next_pos = int(self.pos + self.speed)

        if next_pos < len(road) and road[next_pos] == ".":
            road[self.pos] = "."
            self.pos = next_pos
            road[self.pos] = self.symbol


# -----------------------------
# FUNCTIONS
# -----------------------------
def create_vehicle():
    r = random.random()
    if r < 0.4:
        return Vehicle("2W")
    elif r < 0.6:
        return Vehicle("AUTO")
    elif r < 0.9:
        return Vehicle("CAR")
    else:
        return Vehicle("BUS")


def initialize_road():
    return ["."] * ROAD_LENGTH


# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Indian Traffic Simulation", layout="wide")

st.title("🚦 Indian Traffic Simulation (Streamlit)")

st.sidebar.header("Controls")

speed = st.sidebar.slider("Simulation Speed", 0.1, 1.0, 0.3)
steps = st.sidebar.slider("Time Steps", 10, 100, 40)

start = st.sidebar.button("Start Simulation")

# Placeholder for animation
road_placeholder = st.empty()
stats_placeholder = st.empty()

# -----------------------------
# MAIN SIMULATION
# -----------------------------
if start:
    road = initialize_road()
    vehicles = []

    for t in range(steps):

        # Add vehicle at entry
        if road[0] == ".":
            v = create_vehicle()
            vehicles.append(v)
            road[0] = v.symbol

        # Move vehicles
        for v in vehicles:
            v.move(road)

        # Display road
        road_display = "".join(road)
        road_placeholder.markdown(f"### Time Step: {t}\n`{road_display}`")

        # Stats
        stats_placeholder.write(f"Total Vehicles: {len(vehicles)}")

        time.sleep(speed)

    st.success("Simulation Completed!")
