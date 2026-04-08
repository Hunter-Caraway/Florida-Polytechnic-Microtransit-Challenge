from nicegui import ui

# import backend logic directly
from backend_main import get_latest_location, get_location_history
from database import get_session

@ui.page('/')
def tracker_page():
    device_id = 'arduino_01'

    #UI stuff
    ui.label('GPS Tracker').classes('text-2xl font-bold')

    status = ui.label('Loading...')
    lat_label = ui.label('Latitude: --')
    lon_label = ui.label('Longitude: --')
    time_label = ui.label('Timestamp: --')

    #create map
    m = ui.leaflet(center=(20, 20), zoom=13).classes('w-full h-[600px]')
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
            timestamp = latest.timestamp or '--'

            #update UI labels
            status.set_text('Online')
            lat_label.set_text(f'Latitude: {lat}')
            lon_label.set_text(f'Longitude: {lon}')
            time_label.set_text(f'Timestamp: {timestamp}')


            #redraw map
            m.clear_layers()

            m.tile_layer(
                url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                options={'maxZoom': 19},
            )

            m.marker(latlng=(lat, lon))

            m.set_center((lat, lon))

        except Exception as e:
            status.set_text(f'Error: {e}')

    ui.button('Refresh', on_click=load_data)

    # auto-refresh every 5 seconds
    ui.timer(1, load_data)

print('starting frontend...')
ui.run(title="GPS Tracker", port=8080)