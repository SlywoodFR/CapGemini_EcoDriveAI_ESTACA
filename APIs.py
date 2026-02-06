import pandas as pd
import numpy as np
import requests
import requests_cache
import urllib.parse

class WeatherService:
    def __init__(self):
        self.url = "https://api.open-meteo.com/v1/forecast"
    def get_local_weather(self, lat, lon):
        params = {"latitude": lat, "longitude": lon, "current": ["temperature_2m", "relative_humidity_2m"], "timezone": "auto"}
        try:
            resp = requests.get(self.url, params=params).json()
            return {'temp': resp['current']['temperature_2m'], 'humidity': resp['current']['relative_humidity_2m']}
        except: return {'temp': 20.0, 'humidity': 50.0}

class NavigationService:
    def __init__(self, tomtom_key):
        self.key = tomtom_key
    def get_coords(self, query):
        if not query: return None
        url = f"https://api.tomtom.com/search/2/geocode/{urllib.parse.quote(query)}.json"
        try:
            resp = requests.get(url, params={'key': self.key}).json()
            if 'results' in resp and len(resp['results']) > 0:
                pos = resp['results'][0]['position']
                return pos['lat'], pos['lon']
            return None
        except: return None
    def calculate_route(self, start_coords, end_coords):
        url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_coords[0]},{start_coords[1]}:{end_coords[0]},{end_coords[1]}/json"
        try:
            resp = requests.get(url, params={'key': self.key, 'traffic': 'true'}).json()
            if 'routes' not in resp: return None
            route = resp['routes'][0]
            summary = route['summary']
            v_moy = (summary['lengthInMeters'] / summary['travelTimeInSeconds']) * 3.6
            geom = [(p['latitude'], p['longitude']) for leg in route['legs'] for p in leg['points']]
            return {'summary': summary, 'geometry': geom, 'vitesse_moy': v_moy, 'dist_km': summary['lengthInMeters']/1000}
        except: return None
    def get_suggestions(self, query, **kwargs): 
        if not query or len(query) < 3:
            return []
        
        # Le reste de ton code ne bouge pas
        url = f"https://api.tomtom.com/search/2/search/{urllib.parse.quote(query)}.json"
        params = {
            'key': self.key,
            'typeahead': 'true',
            'language': 'fr-FR',
            'countrySet': 'FR', 
            'limit': 5
        }
        
        try:
            resp = requests.get(url, params=params).json()
            suggestions = []
            if 'results' in resp:
                for r in resp['results']:
                    addr = r.get('address', {})
                    label = f"{addr.get('freeformAddress', '')}"
                    if label not in suggestions:
                        suggestions.append(label)
            return suggestions
        except:
            return []

class ChargingService:
    def __init__(self, files, nav_service):
        self.nav = nav_service
        self.stations = self._load_data(files)
    def _load_data(self, files):
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f, usecols=['nom_station', 'puissance_nominale', 'consolidated_latitude', 'consolidated_longitude'], low_memory=False)
                df['consolidated_latitude'] = pd.to_numeric(df['consolidated_latitude'], errors='coerce')
                df['consolidated_longitude'] = pd.to_numeric(df['consolidated_longitude'], errors='coerce')
                df['puissance_nominale'] = pd.to_numeric(df['puissance_nominale'], errors='coerce').fillna(22.0)
                dfs.append(df)
            except: pass
        return pd.concat(dfs, ignore_index=True).dropna(subset=['consolidated_latitude', 'consolidated_longitude'])
    def find_best(self, lat, lon, radius=35):
        self.stations['dist'] = np.sqrt(((self.stations['consolidated_latitude']-lat)*111)**2 + ((self.stations['consolidated_longitude']-lon)*74)**2)
        nearby = self.stations[(self.stations['dist'] <= radius) & (self.stations['puissance_nominale'] >= 50)].copy()
        if nearby.empty: return None
        best = nearby.sort_values(['dist', 'puissance_nominale'], ascending=[True, False]).iloc[0]
        return {"nom": str(best['nom_station']), "lat": best['consolidated_latitude'], "lon": best['consolidated_longitude'], "puissance": float(best['puissance_nominale'])}

class VehicleService:
    def __init__(self, file_path):
        self.file_path = file_path
        self.vehicles = self._load_data()
    def _load_data(self):
        try:
            df = pd.read_csv(self.file_path)
            # Correction TypeError logs : On nettoie les NaN avant le tri
            df['brand'] = df['brand'].fillna('Inconnu').astype(str)
            df['model'] = df['model'].fillna('Modèle inconnu').astype(str)
            df['display_name'] = (df['brand'] + " " + df['model']).astype(str)
            return df
        except: return pd.DataFrame(columns=['display_name', 'brand', 'battery_capacity_kWh', 'fast_charging_power_kw_dc'])
    def get_vehicle_list(self):
        names = self.vehicles['display_name'].dropna().unique().tolist()
        return sorted([str(n) for n in names])
    def get_details(self, display_name):
        match = self.vehicles[self.vehicles['display_name'] == display_name]
        return match.iloc[0].to_dict() if not match.empty else None
    def find_by_brand(self, brand):
        if not brand: return None
        match = self.vehicles[self.vehicles['brand'].str.contains(str(brand), case=False, na=False)]
        return match.iloc[0].to_dict() if not match.empty else None