import pandas as pd
import numpy as np
import requests
import requests_cache
import openmeteo_requests
import urllib.parse
import time
import json
import logging
from retry_requests import retry

# Configuration Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("APIs")

# ----------------------------------------------------------------------
# SERVICE MÉTÉO
# ----------------------------------------------------------------------
class WeatherService:
    def __init__(self):
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        self.client = openmeteo_requests.Client(session=retry_session)
        self.weather_url = "https://api.open-meteo.com/v1/forecast"

    def get_local_weather(self, lat, lon):
        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "wind_speed_10m", "relative_humidity_2m"],
            "timezone": "auto"
        }
        try:
            resp = self.client.weather_api(self.weather_url, params=params)
            curr = resp[0].Current()
            return {
                'temp': curr.Variables(0).Value(),
                'wind_ms': curr.Variables(1).Value() / 3.6,
                'humidity': curr.Variables(2).Value()
            }
        except:
            return {'temp': 20.0, 'wind_ms': 5.0, 'humidity': 50.0}

# ----------------------------------------------------------------------
# SERVICE NAVIGATION (TOMTOM + MAPBOX)
# ----------------------------------------------------------------------
class NavigationService:
    def __init__(self, tomtom_key, mapbox_token):
        self.key = tomtom_key
        self.mapbox_token = mapbox_token
        self.session = requests.Session()

    def get_coords(self, query):
        """Transforme une ville/adresse en coordonnées GPS"""
        url = f"https://api.tomtom.com/search/2/geocode/{urllib.parse.quote(query)}.json"
        try:
            resp = self.session.get(url, params={'key': self.key})
            data = resp.json()
            if 'results' in data and len(data['results']) > 0:
                pos = data['results'][0]['position']
                return pos['lat'], pos['lon']
            return None
        except:
            return None

    def calculate_route(self, start, end):
        """Calcule un itinéraire entre deux points (noms ou tuples lat/lon)"""
        # Si c'est du texte, on geocode. Si c'est un tuple, on garde.
        c1 = self.get_coords(start) if isinstance(start, str) else start
        c2 = self.get_coords(end) if isinstance(end, str) else end
        
        if not c1 or not c2:
            return None

        route_url = f"https://api.tomtom.com/routing/1/calculateRoute/{c1[0]},{c1[1]}:{c2[0]},{c2[1]}/json"
        try:
            resp = self.session.get(route_url, params={'key': self.key, 'traffic': 'true'})
            data = resp.json()
            if 'routes' in data:
                route = data['routes'][0]
                geometry = [(p['latitude'], p['longitude']) for leg in route['legs'] for p in leg['points']]
                return {'summary': route['summary'], 'geometry': geometry, 'waypoints': [c1, c2]}
            return None
        except:
            return None

    def generate_map(self, geometry, waypoints, filename="map.png"):
        if not self.mapbox_token or "VOTRE" in self.mapbox_token: return
        step = max(1, len(geometry) // 80)
        simplified = [[lon, lat] for lat, lon in geometry[::step]]
        features = [{"type": "Feature", "properties": {"stroke": "#0045ff", "stroke-width": 4}, "geometry": {"type": "LineString", "coordinates": simplified}}]
        for i, (lat, lon) in enumerate(waypoints):
            features.append({"type": "Feature", "properties": {"marker-color": "#ff0000", "marker-symbol": str(i+1)}, "geometry": {"type": "Point", "coordinates": [lon, lat]}})
        
        geojson = urllib.parse.quote(json.dumps({"type": "FeatureCollection", "features": features}))
        url = f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/geojson({geojson})/auto/800x600?access_token={self.mapbox_token}"
        try:
            resp = requests.get(url)
            with open(filename, 'wb') as f: f.write(resp.content)
            logger.info(f"🗺️ Carte sauvegardée : {filename}")
        except: pass

# ----------------------------------------------------------------------
# SERVICE BORNES DE RECHARGE
# ----------------------------------------------------------------------
class ChargingService:
    def __init__(self, files, nav_service):
        self.nav = nav_service
        self.stations = self._load_and_clean_data(files)
        print(f"   🔋 {len(self.stations)} bornes de recharge prêtes.")

    def _load_and_clean_data(self, files):
        cols = ['nom_station', 'adresse_station', 'puissance_nominale', 'consolidated_latitude', 'consolidated_longitude']
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f, usecols=cols, low_memory=False)
                df['consolidated_latitude'] = pd.to_numeric(df['consolidated_latitude'], errors='coerce')
                df['consolidated_longitude'] = pd.to_numeric(df['consolidated_longitude'], errors='coerce')
                df['puissance_nominale'] = pd.to_numeric(df['puissance_nominale'], errors='coerce').fillna(22.0)
                dfs.append(df)
            except: pass
        
        master = pd.concat(dfs, ignore_index=True).dropna(subset=['consolidated_latitude', 'consolidated_longitude'])
        # Filtre France Strict pour éviter les erreurs GPS
        return master[(master['consolidated_latitude'] > 41) & (master['consolidated_latitude'] < 52) & 
                      (master['consolidated_longitude'] > -5) & (master['consolidated_longitude'] < 10)].copy()

    def find_best_station(self, target_lat, target_lon, radius_km=25.0):
        # Recherche rapide
        dist_lat = (self.stations['consolidated_latitude'] - target_lat) * 111
        dist_lon = (self.stations['consolidated_longitude'] - target_lon) * 74
        self.stations['temp_dist'] = np.sqrt(dist_lat**2 + dist_lon**2)
        
        nearby = self.stations[self.stations['temp_dist'] <= radius_km].copy()
        if nearby.empty: return None
        
        best = nearby.sort_values(by='puissance_nominale', ascending=False).iloc[0]
        
        # Vérification d'adresse via TomTom pour corriger les coordonnées CSV erronées
        addr = f"{best['nom_station']}, {best['adresse_station']}"
        coords = self.nav.get_coords(addr)
        
        if coords:
            return {"nom": best['nom_station'], "lat": coords[0], "lon": coords[1], "puissance": best['puissance_nominale']}
        return None

# ----------------------------------------------------------------------
# SERVICE PLAQUE
# ----------------------------------------------------------------------
class LicensePlateService:
    def __init__(self, token):
        self.token = token
        self.url = "https://api.apiplaqueimmatriculation.com/plaque"

    def get_details(self, plate):
        params = {"immatriculation": plate.replace("-",""), "token": self.token, "pays": "FR"}
        try:
            resp = requests.get(self.url, params=params).json()
            if resp.get("code_erreur") == 200:
                data = resp["data"]
                poids_str = data.get("poids", "1700 KG")
                poids = float(poids_str.split(' ')[0])
                return {"model": data.get("modele"), "weight": poids}
        except: pass
        return {"model": "Standard EV", "weight": 1700.0}