from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import APIKeyHeader
from sqlmodel import Session, select
import os
from database import create_db_and_tables, get_session
from models import Location, LocationCreate, LocationRead

#api key to make sure nobody can just send data
API_KEY_NAME = "X_API_KEY"
EXPECTED_API_KEY = os.getenv("TRACKER_API_KEY", "FortniteBattlePassTier27")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

#verify that the device sent the right api key
def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

#make sure the database exists before further requests
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

#create the fastapi
app = FastAPI(title="GPS Tracker Backend", lifespan=lifespan)

#check connection
@app.get("/health")
def health():
    return {"status": "ok"}

#get input from the arduino
@app.post("/devices/{device_id}/location", response_model=LocationRead, status_code=201)
def create_location(
    device_id: str,
    payload: LocationCreate,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    record = Location(
        device_id=device_id,
        lat=payload.lat,
        lon=payload.lon,
        timestamp=payload.timestamp or None,
        source=payload.source,
    )
    print(f'Received from {device_id}: lat={payload.lat}, lon={payload.lon}, timestamp={payload.timestamp} and source={payload.source}')

    session.add(record)
    session.commit()
    session.refresh(record)
    return record

#get the arduinos last location
@app.get("/devices/{device_id}/location/latest", response_model=LocationRead)
def get_latest_location(
    device_id: str,
    session: Session = Depends(get_session),
):
    statement = (
        select(Location)
        .where(Location.device_id == device_id)
        .order_by(Location.timestamp.desc())
    )
    record = session.exec(statement).first()

    if not record:
        raise HTTPException(status_code=404, detail="No location found for this device")

    return record

#get a list of recent points the arduino has been
@app.get("/devices/{device_id}/location/history", response_model=list[LocationRead])
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
    records = session.exec(statement).all()
    return records