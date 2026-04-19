from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import APIKeyHeader
from geopy.geocoders import Nominatim
from nicegui import app, ui
from sqlmodel import Session, select

from database import create_db_and_tables, engine, get_session
from models import Location, LocationCreate, LocationRead


#fastapi
API_KEY_NAME = "X_API_KEY"
EXPECTED_API_KEY = os.getenv("TRACKER_API_KEY", "FortniteBattlePassTier27")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def verify_api_key(api_key: str = Depends(api_key_header)) -> None:
    if api_key != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


fastapi_app = FastAPI(
    title="GPS Tracker",
    lifespan=lifespan,
)


def get_latest_location_record(device_id: str, session: Session) -> Location:
    statement = (
        select(Location)
        .where(Location.device_id == device_id)
        .order_by(Location.timestamp.desc())
    )
    record = session.exec(statement).first()

    if record is None:
        raise HTTPException(status_code=404, detail="No location found for this device")

    return record


#routing
@fastapi_app.get("/health")
def health():
    return {"status": "ok"}


@fastapi_app.post(
    "/devices/{device_id}/location",
    response_model=LocationRead,
    status_code=201,
)
def create_location(
    device_id: str,
    payload: LocationCreate,
    session: Session = Depends(get_session),
    _: None = Depends(verify_api_key),
):
    record = Location(
        device_id=device_id,
        lat=payload.lat,
        lon=payload.lon,
        source=payload.source,
    )

    if payload.timestamp is not None:
        record.timestamp = payload.timestamp

    print(
        f"Received from {device_id}: "
        f"lat={payload.lat}, lon={payload.lon}, "
        f"timestamp={payload.timestamp}, source={payload.source}"
    )

    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@fastapi_app.get(
    "/devices/{device_id}/location/latest",
    response_model=LocationRead,
)
def get_latest_location(
    device_id: str,
    session: Session = Depends(get_session),
):
    return get_latest_location_record(device_id, session)


@fastapi_app.get(
    "/devices/{device_id}/location/history",
    response_model=list[LocationRead],
)
def get_location_history(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
):
    statement = (
        select(Location)
        .where(Location.device_id == device_id)
        .order_by(Location.timestamp.desc())
        .limit(limit)
    )
    return session.exec(statement).all()


#frontend
@ui.page("/")
def tracker_page():
    device_id = "arduino_01"
    geolocation = Nominatim(user_agent="arduino_01")

    ui.label("GPS Tracker").classes("text-2xl font-bold")
    status_label = ui.label("Loading...")
    location_label = ui.label("Location: --")
    time_label = ui.label("Timestamp: --")

    m = ui.leaflet(center=(0, 0), zoom=2).classes("w-full h-[600px]")
    m.tile_layer(
        url_template="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        options={"maxZoom": 19},
    )

    current_marker = None
    last_lat = None
    last_lon = None
    last_location_text = "Location: --"

    def fetch_latest():
        with Session(engine) as session:
            return get_latest_location_record(device_id, session)

    def reverse_lookup(lat: float, lon: float):
        return geolocation.reverse(f"{lat}, {lon}")

    async def load_data():
        nonlocal current_marker, last_lat, last_lon, last_location_text

        try:
            latest = await asyncio.to_thread(fetch_latest)

            lat = latest.lat
            lon = latest.lon

            if latest.timestamp:
                if isinstance(latest.timestamp, str):
                    dt = datetime.fromisoformat(latest.timestamp)
                else:
                    dt = latest.timestamp
                timestamp = dt.strftime("%m/%d/%Y %I:%M:%S %p")
            else:
                timestamp = "--"

            if last_lat != lat or last_lon != lon:
                location = await asyncio.to_thread(reverse_lookup, lat, lon)
                last_location_text = f"Location: {location}"
                last_lat = lat
                last_lon = lon

            status_label.set_text("Online")
            location_label.set_text(last_location_text)
            time_label.set_text(f"Timestamp: {timestamp}")

            if current_marker is not None:
                m.remove_layer(current_marker)

            current_marker = m.marker(latlng=(lat, lon))
            m.set_center((lat, lon))
            m.set_zoom(17)

        except Exception as e:
            status_label.set_text(f"Error: {e}")

    ui.button("Refresh", on_click=load_data)
    ui.timer(10, load_data)

#deploy
ui.run_with(
    fastapi_app,
    title="GPS Tracker",
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "change-this-secret"),
)