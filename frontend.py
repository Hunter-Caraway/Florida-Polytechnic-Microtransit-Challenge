from nicegui import ui
from geopy.geocoders import Nominatim
from datetime import datetime
import asyncio
import os

from backend_main import get_latest_location
from database import get_session

@ui.page('/')
def tracker_page():
    device_id = 'arduino_01'
    geolocation = Nominatim(user_agent='arduino_01')

    # UI
    ui.label('GPS Tracker').classes('text-2xl font-bold')
    status = ui.label('Loading...')
    location_label = ui.label('Location: --')
    time_label = ui.label('Timestamp: --')

    # Map
    m = ui.leaflet(center=(0, 0), zoom=2).classes('w-full h-[600px]')
    m.tile_layer(
        url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        options={'maxZoom': 19},
    )

    # State
    current_marker = None
    last_lat = None
    last_lon = None
    last_location_text = 'Location: --'

    # Blocking DB work moved off event loop
    def fetch_latest():
        session = next(get_session())
        return get_latest_location(device_id, session)

    # Blocking reverse geocoding moved off event loop
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

            # Only reverse geocode if the location actually changed
            if last_lat != lat or last_lon != lon:
                location = await asyncio.to_thread(reverse_lookup, lat, lon)
                last_location_text = f'Location: {location}'
                last_lat = lat
                last_lon = lon

            # Update labels
            status.set_text('Online')
            location_label.set_text(last_location_text)
            time_label.set_text(f'Timestamp: {timestamp}')

            # Remove only old marker, keep tiles
            if current_marker is not None:
                m.remove_layer(current_marker)

            current_marker = m.marker(latlng=(lat, lon))

            # Center on newest point
            m.set_center((lat, lon))
            m.set_zoom(17)

        except Exception as e:
            status.set_text(f'Error: {e}')

    ui.button('Refresh', on_click=load_data)

    # Refresh every 10 seconds
    ui.timer(10, load_data)

print('starting frontend...')
ui.run(
    title='GPS Tracker',
    host='0.0.0.0',
    port=int(os.getenv('PORT', 8080)),
)