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
# SERVICE MÉTÉO & ALTITUDE
# ----------------------------------------------------------------------
class WeatherService:
    def __init__(self):
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        self.client = openmeteo_requests.Client(session=retry_session)
        self.weather_url = "https://api.open-meteo.com/v1/forecast"
        self.elevation_url = "https://api.open-meteo.com/v1/elevation"

    def get_local_weather(self, lat, lon):
        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "wind_speed_10m"],
            "timezone": "auto"
        }
        try:
            resp = self.client.weather_api(self.weather_url, params=params)
            curr = resp[0].Current()
            return {
                'temp': curr.Variables(0).Value(),
                'wind_ms': curr.Variables(1).Value() / 3.6
            }
        except:
            return {'temp': 20.0, 'wind_ms': 5.0}

    def get_elevations(self, coordinates):
        elevations = []
        chunk_size = 100
        for i in range(0, len(coordinates), chunk_size):
            chunk = coordinates[i:i+chunk_size]
            lats = [str(c[0]) for c in chunk]
            lons = [str(c[1]) for c in chunk]
            try:
                resp = requests.get(self.elevation_url, params={"latitude": ",".join(lats), "longitude": ",".join(lons)})
                data = resp.json()
                elevations.extend(data.get("elevation", [0.0]*len(chunk)))
                time.sleep(0.1)
            except:
                elevations.extend([0.0]*len(chunk))
        return elevations

# ----------------------------------------------------------------------
# SERVICE NAVIGATION (TOMTOM + MAPBOX)
# ----------------------------------------------------------------------
class NavigationService:
    def __init__(self, tomtom_key, mapbox_token):
        self.key = tomtom_key
        self.mapbox_token = mapbox_token
        self.session = requests.Session()

    def get_coords(self, city):
        # On encode proprement les villes (espaces -> %20)
        url = f"https://api.tomtom.com/search/2/geocode/{urllib.parse.quote(city)}.json"
        try:
            resp = self.session.get(url, params={'key': self.key})
            if resp.status_code != 200:
                logger.error(f"Geocoding Failed ({resp.status_code}): {resp.text}")
                return None
            
            data = resp.json()
            if 'results' in data and len(data['results']) > 0:
                res = data['results'][0]['position']
                return res['lat'], res['lon']
            else:
                logger.warning(f"Aucune coordonnée trouvée pour : {city}")
                return None
        except Exception as e:
            logger.error(f"Erreur Connexion Geocoding: {e}")
            return None

    def calculate_route(self, start, end):
        # 1. Geocoding
        c1 = self.get_coords(start)
        c2 = self.get_coords(end)
        
        if not c1 or not c2: 
            logger.error("❌ Arrêt : Coordonnées introuvables pour le départ ou l'arrivée.")
            return None

        logger.info(f"📍 Points : {c1} -> {c2}")

        # 2. Routing
        route_url = f"https://api.tomtom.com/routing/1/calculateRoute/{c1[0]},{c1[1]}:{c2[0]},{c2[1]}/json"
        
        try:
            # traffic: false (minuscule pour l'API string)
            resp = self.session.get(route_url, params={'key': self.key, 'traffic': 'false'})
            
            # --- DEBUG IMPORTANTE ---
            if resp.status_code != 200:
                logger.error(f"❌ Erreur TomTom API ({resp.status_code}) :")
                logger.error(resp.text)  # AFFICHE LE VRAI PROBLÈME (Clé, Quota, etc.)
                return None
            # ------------------------

            data = resp.json()
            
            if 'routes' in data:
                route = data['routes'][0]
                geometry = []
                for leg in route['legs']:
                    for p in leg['points']:
                        geometry.append((p['latitude'], p['longitude']))
                
                return {
                    'summary': route['summary'],
                    'geometry': geometry,
                    'waypoints': [c1, c2]
                }
            else:
                logger.error(f"Pas de clé 'routes' dans la réponse : {data}")
                return None

        except Exception as e:
            logger.error(f"TomTom Exception: {e}")
            return None

    def generate_map(self, geometry, waypoints, filename="trip_map.png"):
        """Génère une image statique via Mapbox"""
        if not self.mapbox_token or "VOTRE" in self.mapbox_token:
            logger.warning("⚠️ Pas de Token Mapbox valide, carte ignorée.")
            return

        # Simplification (Max ~80 points)
        step = max(1, len(geometry) // 80)
        simplified = geometry[::step]
        line_coords = [[lon, lat] for lat, lon in simplified]
        
        features = [{
            "type": "Feature",
            "properties": {"stroke": "#0045ff", "stroke-width": 4},
            "geometry": {"type": "LineString", "coordinates": line_coords}
        }]

        for i, (lat, lon) in enumerate(waypoints):
            features.append({
                "type": "Feature",
                "properties": {"marker-color": "#ff0000", "marker-symbol": str(i+1)},
                "geometry": {"type": "Point", "coordinates": [lon, lat]}
            })

        geojson = json.dumps({"type": "FeatureCollection", "features": features})
        encoded = urllib.parse.quote(geojson)
        
        url = f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/geojson({encoded})/auto/800x600"
        
        try:
            resp = requests.get(url, params={"access_token": self.mapbox_token, "padding": 50})
            if resp.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(resp.content)
                logger.info(f"🗺️ Carte sauvegardée : {filename}")
            else:
                logger.error(f"Erreur Mapbox: {resp.text}")
        except Exception as e:
            logger.error(f"Erreur téléchargement carte: {e}")

# ----------------------------------------------------------------------
# SERVICE VÉHICULE
# ----------------------------------------------------------------------
class LicensePlateService:
    def __init__(self, token):
        self.token = token
        self.url = "https://api.apiplaqueimmatriculation.com/plaque"

    