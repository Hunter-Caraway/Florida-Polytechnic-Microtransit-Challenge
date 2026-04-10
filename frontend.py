from nicegui import ui
from geopy.geocoders import Nominatim
from datetime import datetime
import os

# import backend logic directly
from backend_main import get_latest_location
from database import get_session, create_db_and_tables

@ui.page('/')
def tracker_page():
    device_id = 'arduino_01'
    geolocation = Nominatim(user_agent='arduino_01')
    #UI stuff
    ui.label('GPS Tracker').classes('text-2xl font-bold')

    status = ui.label('Loading...')
    location_label = ui.label('Location: --')
    time_label = ui.label('Timestamp: --')

    #create map
    m = ui.leaflet(center=(0, 0), zoom=2).classes('w-full h-[600px]')
    m.tile_layer(
        url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        options={'maxZoom': 19},
    )

    async def load_data():
        try:
            #get DB session
            session = next(get_session())

            #call backend functions directly
            latest = get_latest_location(device_id, session)

            lat = latest.lat
            lon = latest.lon
            if latest.timestamp:
                # convert to datetime if it's a string
                if isinstance(latest.timestamp, str):
                    dt = datetime.fromisoformat(latest.timestamp)
                else:
                    dt = latest.timestamp

                timestamp = dt.strftime("%m/%d/%Y %I:%M:%S %p")
            else:
                timestamp = "--"

            #reverse geocoding to get address
            location = geolocation.reverse(f"{lat}, {lon}")

            #update UI labels
            status.set_text('Online')
            location_label.set_text(f'Location: {location}')
            time_label.set_text(f'Timestamp: {timestamp}')


            #redraw map
            m.clear_layers()

            m.tile_layer(
                url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                options={'maxZoom': 19},
            )

            m.marker(latlng=(lat, lon))

            m.set_center((lat, lon))
            m.set_zoom(17)

        except Exception as e:
            status.set_text(f'Error: {e}')

    ui.button('Refresh', on_click=load_data)

    # auto-refresh every 5 seconds
    ui.timer(1, load_data)

print('starting frontend...')
create_db_and_tables()
ui.run(title="GPS Tracker",
       host='0.0.0.0',
       port=int(os.getenv('PORT', 10000)),
       )