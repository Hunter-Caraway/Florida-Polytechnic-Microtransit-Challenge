from nicegui import ui
from geopy.geocoders import Nominatim
from datetime import datetime
import asyncio
import os

from sqlmodel import Session
from backend_main import get_latest_location
from database import engine

@ui.page('/')
def tracker_page():
    device_id = 'arduino_01'
    geolocation = Nominatim(user_agent='arduino_01')

    ui.label('GPS Tracker').classes('text-2xl font-bold')
    status = ui.label('Loading...')
    location_label = ui.label('Location: --')
    time_label = ui.label('Timestamp: --')

    m = ui.leaflet(center=(0, 0), zoom=2).classes('w-full h-[600px]')
    m.tile_layer(
        url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        options={'maxZoom': 19},
    )

    current_marker = None
    last_lat = None
    last_lon = None
    last_location_text = 'Location: --'

    def fetch_latest():
        with Session(engine) as session:
            return get_latest_location(device_id, session)

    def reverse_lookup(lat, lon):
        return geolocation.reverse(f'{lat}, {lon}')

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
                timestamp = '--'

            if last_lat != lat or last_lon != lon:
                location = await asyncio.to_thread(reverse_lookup, lat, lon)
                last_location_text = f'Location: {location}'
                last_lat = lat
                last_lon = lon

            status.set_text('Online')
            location_label.set_text(last_location_text)
            time_label.set_text(f'Timestamp: {timestamp}')

            if current_marker is not None:
                m.remove_layer(current_marker)

            current_marker = m.marker(latlng=(lat, lon))
            m.set_center((lat, lon))
            m.set_zoom(17)

        except Exception as e:
            status.set_text(f'Error: {e}')

    ui.button('Refresh', on_click=load_data)
    ui.timer(10, load_data)

print('starting frontend...')
ui.run(
    title='GPS Tracker',
    host='0.0.0.0',
    port=int(os.getenv('PORT', 8080)),
)