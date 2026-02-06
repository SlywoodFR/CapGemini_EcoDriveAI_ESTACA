import pandas as pd
import numpy as np
import requests
import requests_cache
import urllib.parse
import json

cache_session = requests_cache.CachedSession('.cache', expire_after=3600)

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
            route = resp['routes'][0]
            geom = [(p['latitude'], p['longitude']) for leg in route['legs'] for p in leg['points']]
            return {'summary': route['summary'], 'geometry': geom}
        except: return None

class ChargingService:
    def __init__(self, files, nav_service):
        self.nav = nav_service
        self.stations = self._load_data(files)
    def _load_data(self, files):
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f, usecols=['nom_station', 'adresse_station', 'puissance_nominale', 'consolidated_latitude', 'consolidated_longitude'], low_memory=False)
                df['consolidated_latitude'] = pd.to_numeric(df['consolidated_latitude'], errors='coerce')
                df['consolidated_longitude'] = pd.to_numeric(df['consolidated_longitude'], errors='coerce')
                df['puissance_nominale'] = pd.to_numeric(df['puissance_nominale'], errors='coerce').fillna(22.0)
                dfs.append(df)
            except: pass
        master = pd.concat(dfs, ignore_index=True).dropna(subset=['consolidated_latitude', 'consolidated_longitude'])
        return master[(master['consolidated_latitude'] > 41) & (master['consolidated_latitude'] < 52) & (master['consolidated_longitude'] > -5)].copy()

    def find_best(self, lat, lon, radius=15):
        """Priorité au détour minimum (Distance)"""
        self.stations['dist'] = np.sqrt(((self.stations['consolidated_latitude']-lat)*111)**2 + ((self.stations['consolidated_longitude']-lon)*74)**2)
        # On filtre les bornes rapides (> 40kW) pour ne pas charger sur une prise maison
        nearby = self.stations[(self.stations['dist'] <= radius) & (self.stations['puissance_nominale'] >= 43)].copy()
        if nearby.empty: 
            nearby = self.stations[self.stations['dist'] <= radius].copy() # Fallback si pas de bornes rapides
        
        if nearby.empty: return None
        
        # TRI PAR DISTANCE (Le moins de détour possible)
        best = nearby.sort_values('dist', ascending=True).iloc[0]
        
        addr = f"{best['nom_station']}, {best['adresse_station']}"
        real_coords = self.nav.get_coords(addr)
        if real_coords:
            return {"nom": best['nom_station'], "lat": real_coords[0], "lon": real_coords[1], "puissance": best['puissance_nominale'], "dist": best['dist']}
        return None