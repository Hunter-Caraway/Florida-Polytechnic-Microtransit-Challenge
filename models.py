from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

#input from device
class LocationCreate(SQLModel):
    lat: float
    lon: float
    timestamp: Optional[datetime] = None
    source: Optional[str] = None

#database table
class Location(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    lat: float
    lon: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    source: Optional[str] = None

#output
class LocationRead(SQLModel):
    id: int
    device_id: str
    lat: float
    lon: float
    timestamp: datetime
    source: Optional[str] = None