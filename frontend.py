import httpx
from nicegui import ui

@ui.page('/')
def tracker_page():
    device_id = 'arduino_01'

    #labels for the website
    ui.label('GPS Tracker').classes('text-2xl font-bold')
    status = ui.label('Loading...')
    lat_label = ui.label('Latitude: --')
    lon_label = ui.label('Longitude: --')
    time_label = ui.label('Timestamp: --')

    m = ui.leaflet(center=(20, 20), zoom=13).classes('w-full h-[600px]')
    m.tile_layer(
        url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        options={'maxZoom': 19},
    )

    async def load_data():
        try:
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8000') as client:
                latest_resp = await client.get(f'/devices/{device_id}/location/latest')
                history_resp = await client.get(f'/devices/{device_id}/location/history?limit=100')

            if latest_resp.status_code != 200:
                status.set_text('No data yet')
                return

            #if we get a response, pull the data from it and put it on the website
            latest = latest_resp.json()
            history = history_resp.json() if history_resp.status_code == 200 else []

            lat = latest['lat']
            lon = latest['lon']
            timestamp = latest.get('timestamp', '--')

            status.set_text('Online')
            lat_label.set_text(f'Latitude: {lat}')
            lon_label.set_text(f'Longitude: {lon}')
            time_label.set_text(f'Timestamp: {timestamp}')

            points = [(p['lat'], p['lon']) for p in history if 'lat' in p and 'lon' in p]

            #make a point on the map for the tracker.
            m.clear_layers()
            m.tile_layer(
                url_template='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                options={'maxZoom': 19},
            )
            m.marker(latlng=(lat, lon))
            if points:
                m.generic_layer(name='polyline', args=[points])
            m.set_center((lat, lon))

        except Exception as e:
            status.set_text(f'Error: {e}')

    ui.button('Refresh', on_click=load_data)
    ui.timer(5.0, load_data)

#run the website
print('starting frontend...')
ui.run(title="GPS Tracker")
