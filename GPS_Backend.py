from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
# GPS_Backend.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
import math
import sqlite3
import httpx
import os
from dotenv import load_dotenv

# ----------------------------
# Config
# ----------------------------
load_dotenv()

MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN")
DATABASE_NAME = "gps_tracker.db"

app = FastAPI()

#Database setup
# ---------------- #
# SET UP LATER
# ---------------- #
conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS location_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    speed_mps REAL,
    heading_deg REAL,
    gps_timestamp TEXT,
    received_at TEXT NOT NULL
)
""")
conn.commit()

#Data Models
class LocationUpdate(BaseModel):
    device_id: str
    lat: float
    lon: float
    speed_mps: float | None = None
    heading_deg: float | None = None
    gps_timestamp: str | None = None

class ETARequest(BaseModel):
    device_id: str
    user_lat: float
    user_lon: float

#Coordinates and ETA
def validate_coordinates(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180

def haversine_distance_m(lat1, lon1, lat2, lon2):
    r = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def estimate_eta_seconds(distance_m: float, speed_mps: float | None):
    if speed_mps is None or speed_mps <= 0:
        return None
    return distance_m / speed_mps

#Storage Functions
def save_location_update(data: LocationUpdate):
    received_at = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO location_updates
        (device_id, lat, lon, speed_mps, heading_deg, gps_timestamp, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.device_id,
        data.lat,
        data.lon,
        data.speed_mps,
        data.heading_deg,
        data.gps_timestamp,
        received_at
    ))
    conn.commit()

def get_latest_location(device_id: str):
    cursor.execute("""
        SELECT device_id, lat, lon, speed_mps, heading_deg, gps_timestamp, received_at
        FROM location_updates
        WHERE device_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (device_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return {
        "device_id": row[0],
        "lat": row[1],
        "lon": row[2],
        "speed_mps": row[3],
        "heading_deg": row[4],
        "gps_timestamp": row[5],
        "received_at": row[6]
    }

#Working with Mapbox
# ----------------------- #
# SET UP LATER DO NOT FORGET
# ----------------------- #
async def get_mapbox_eta(start_lat, start_lon, end_lat, end_lon):
    if not MAPBOX_ACCESS_TOKEN:
        return None

    url = (
        f"https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )

    params = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "overview": "false",
        "geometries": "geojson"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    if response.status_code != 200:
        return None

    data = response.json()
    routes = data.get("routes", [])
    if not routes:
        return None

    return routes[0].get("duration")

#api routes
@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/locations")
def post_location(data: LocationUpdate):
    if not validate_coordinates(data.lat, data.lon):
        raise HTTPException(status_code=400, detail="Invalid coordinates")

    save_location_update(data)
    return {"message": "Location update stored"}

@app.get("/api/v1/devices/{device_id}/latest")
def latest_location(device_id: str):
    location = get_latest_location(device_id)
    if not location:
        raise HTTPException(status_code=404, detail="Device not found")
    return location

@app.post("/api/v1/eta")
async def eta(request: ETARequest):
    location = get_latest_location(request.device_id)
    if not location:
        raise HTTPException(status_code=404, detail="Device not found")

    distance_m = haversine_distance_m(
        location["lat"], location["lon"],
        request.user_lat, request.user_lon
    )

    straight_line_eta = estimate_eta_seconds(distance_m, location["speed_mps"])
    mapbox_eta = await get_mapbox_eta(
        location["lat"], location["lon"],
        request.user_lat, request.user_lon
    )

    return {
        "device_id": request.device_id,
        "distance_m": distance_m,
        "straight_line_eta_seconds": straight_line_eta,
        "mapbox_eta_seconds": mapbox_eta
    }