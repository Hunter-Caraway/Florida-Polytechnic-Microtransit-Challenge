import math
import time
from fastapi.testclient import TestClient

from backend_main import app, API_KEY_NAME, EXPECTED_API_KEY
from models import LocationCreate
from database import create_db_and_tables

# config, fake device settings
HEADERS = {API_KEY_NAME: EXPECTED_API_KEY}
DEVICE_ID = "arduino_01"
SEND_INTERVAL = 1.0
NUM_MESSAGES = 10

START_LAT = 20.0
START_LON = 20.0

#create database
create_db_and_tables()

# test client to call FastAPI routes
client = TestClient(app)

# move the coordinates little by little
def generate_fake_path(step: int) -> tuple[float, float]:
    lat = START_LAT + 0.0005 * math.sin(step / 5)
    lon = START_LON + 0.0005 * math.cos(step / 5)
    return round(lat, 6), round(lon, 6)

# make a fake UART line exactly like Arduino might send
def make_uart_line(step: int) -> str:
    lat, lon = generate_fake_path(step)
    return f"{lat},{lon}"

# look through the uart
def parse_uart_line(line: str) -> tuple[float, float]:
    parts = line.strip().split(",")
    if len(parts) != 2:
        raise ValueError("Expected 'lat,lon'")
    lat = float(parts[0])
    lon = float(parts[1])

    if not (-90 <= lat <= 90):
        raise ValueError("Latitude out of range")
    if not (-180 <= lon <= 180):
        raise ValueError("Longitude out of range")

    return lat, lon

# test logic
def main():
    print("Generating fake UART messages and sending them through FastAPI...\n")

    # simulate Arduino transmitting GPS using UART-style lines
    for step in range(NUM_MESSAGES):
        uart_line = make_uart_line(step)
        print(f"UART -> {uart_line}")

        # convert uart to numeric values and create the request payload
        try:
            lat, lon = parse_uart_line(uart_line)

            payload = LocationCreate(
                lat=lat,
                lon=lon,
                source="uart_test"
            )

            # send the data to FastAPI
            response = client.post(
                f"/devices/{DEVICE_ID}/location",
                json=payload.model_dump(mode="json"),
                headers = HEADERS
            )

            print(f"POST -> {response.status_code} {response.json()}")

        except Exception as e:
            print(f"Skipped: {e}")

        time.sleep(SEND_INTERVAL)

    print("\nDone.")

    # verify latest location
    latest = client.get(f"/devices/{DEVICE_ID}/location/latest")
    print("\nLatest location:")
    print(latest.status_code, latest.json())

    # verify history
    history = client.get(f"/devices/{DEVICE_ID}/location/history?limit=5")
    print("\nRecent history:")
    print(history.status_code, history.json())

if __name__ == "__main__":
    main()