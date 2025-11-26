import json
import logging
import math
import time
import urllib.parse
from typing import List, Tuple, Optional, Dict, Any

import openmeteo_requests
import requests
import requests_cache
from retry_requests import retry

# ----------------------------------------------------------------------
# Configuration & Setup
# ----------------------------------------------------------------------

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Constants
TOMTOM_API_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
MAPBOX_ACCESS_TOKEN = "pk.eyJ1Ijoic2x5d29vZGZyIiwiYSI6ImNtaWc0dWo3ODAzMjUzZnF4anlyM2UydjgifQ.GZvrtjfqUJo4jmPh-oTp_w"
LICENSE_PLATE_TOKEN = "TokenDemo2025A"

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great-circle distance between two points on Earth in meters.
    """
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def calculate_mean_slope(geometry: List[Tuple[float, float]], elevations: List[float]) -> float:
    """
    Calculates the MEAN positive slope percentage between consecutive points.
    Slope % = (change_in_elevation / distance) * 100
    """
    if not geometry or not elevations or len(geometry) != len(elevations):
        return 0.0

    total_positive_slope = 0.0
    count = 0

    for i in range(len(geometry) - 1):
        lat1, lon1 = geometry[i]
        lat2, lon2 = geometry[i+1]
        
        elev1 = elevations[i]
        elev2 = elevations[i+1]

        dist = haversine_distance(lat1, lon1, lat2, lon2)
        
        # Avoid division by zero and very small segments which cause noise
        if dist > 5.0: 
            elevation_change = elev2 - elev1
            
            # We strictly check for positive slope (uphill). 
            if elevation_change > 0:
                slope = (elevation_change / dist) * 100
                total_positive_slope += slope
                count += 1

    if count == 0:
        return 0.0
        
    return total_positive_slope / count

# ----------------------------------------------------------------------
# Service Classes
# ----------------------------------------------------------------------

class WeatherService:
    """
    Handles interactions with the Open-Meteo API (Weather & Elevation).
    """
    def __init__(self, cache_expire_after: int = 3600):
        # Initialize session with caching and retries once during instantiation
        cache_session = requests_cache.CachedSession('.cache', expire_after=cache_expire_after)
        self.retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        
        # Client for the binary Weather API
        self.client = openmeteo_requests.Client(session=self.retry_session)
        
        self.weather_url = "https://api.open-meteo.com/v1/forecast"
        self.elevation_url = "https://api.open-meteo.com/v1/elevation"

    def get_current_temperature(self, latitude: float, longitude: float) -> Optional[float]:
        """
        Fetches the current temperature (2m) for specific coordinates.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m",
            "timezone": "auto",
        }

        try:
            responses = self.client.weather_api(self.weather_url, params=params)
            response = responses[0]
            current = response.Current()
            return current.Variables(0).Value()
        except Exception as e:
            logger.error(f"Weather API Error: {e}")
            return None

    def get_elevations(self, coordinates: List[Tuple[float, float]]) -> List[float]:
        """
        Fetches elevation data for a list of (lat, lon) tuples using Open-Meteo.
        Handles chunking to respect URL length limits and includes rate-limit delays.
        """
        elevations = []
        # Chunk size ~100 points per request to keep URL length safe
        chunk_size = 100
        
        logger.info(f"Fetching elevations for {len(coordinates)} points (chunked)...")

        for i in range(0, len(coordinates), chunk_size):
            chunk = coordinates[i:i + chunk_size]
            lats = [c[0] for c in chunk]
            lons = [c[1] for c in chunk]

            params = {
                "latitude": ",".join(map(str, lats)),
                "longitude": ",".join(map(str, lons)),
            }

            try:
                # We use the JSON API for elevation as it's simpler for lists
                response = self.retry_session.get(self.elevation_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if "elevation" in data:
                    elevations.extend(data["elevation"])
                else:
                    logger.warning("No elevation data in response")
                
                # IMPORTANT: Sleep to prevent 429 Too Many Requests errors
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Elevation API Error on chunk {i}: {e}")
                # Append 0.0s to maintain alignment if a chunk fails
                elevations.extend([0.0] * len(chunk))

        return elevations


class NavigationService:
    """
    Handles interactions with TomTom Geocoding, Routing, and Mapbox Static Images.
    """
    def __init__(self, tomtom_key: str, mapbox_token: str):
        self.tomtom_key = tomtom_key
        self.mapbox_token = mapbox_token
        self.session = requests.Session()
        self.base_geocode_url = "https://api.tomtom.com/search/2/geocode/"
        self.base_routing_url = "https://api.tomtom.com/routing/1/calculateRoute/"

    def get_coordinates(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Geocodes a single address string to (latitude, longitude).
        """
        encoded_address = urllib.parse.quote(address)
        url = f"{self.base_geocode_url}{encoded_address}.json"
        
        try:
            response = self.session.get(url, params={'key': self.tomtom_key}, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("results"):
                position = data["results"][0]["position"]
                return position['lat'], position['lon']
            else:
                logger.warning(f"Geocoding failed: No results for '{address}'")
                return None

        except requests.RequestException as e:
            logger.error(f"Geocoding connection error for '{address}': {e}")
            return None

    def calculate_route(self, addresses: List[str]) -> Dict[str, Any]:
        """
        Calculates a route between a list of addresses using TomTom.
        """
        if len(addresses) < 2:
            return {"status": "error", "message": "At least two addresses are required."}

        # 1. Geocode all addresses
        logger.info(f"Geocoding {len(addresses)} addresses...")
        coordinates = []
        
        for address in addresses:
            coords = self.get_coordinates(address)
            if not coords:
                return {
                    "status": "error", 
                    "message": f"Could not geocode address: {address}"
                }
            coordinates.append(coords)

        # 2. Format coordinates for Routing API (lat,lon:lat,lon)
        coords_string = ":".join([f"{lat},{lon}" for lat, lon in coordinates])
        url = f"{self.base_routing_url}{coords_string}/json"

        # 3. Request Route
        logger.info("Requesting route calculation...")
        try:
            response = self.session.get(url, params={'key': self.tomtom_key}, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('routes'):
                route_data = data['routes'][0]
                summary = route_data['summary']
                
                # Extract detailed route geometry (legs -> points)
                route_geometry = []
                if 'legs' in route_data:
                    for leg in route_data['legs']:
                        if 'points' in leg:
                            for point in leg['points']:
                                route_geometry.append((point['latitude'], point['longitude']))

                return {
                    "status": "success",
                    "distance_meters": summary.get('lengthInMeters'),
                    "travel_time_seconds": summary.get('travelTimeInSeconds'),
                    "departure_time": summary.get('departureTime'),
                    "arrival_time": summary.get('arrivalTime'),
                    "coordinates": coordinates,  # Waypoints (lat, lon)
                    "route_geometry": route_geometry  # Detailed path (lat, lon)
                }
            
            return {"status": "error", "message": "No route found."}

        except requests.RequestException as e:
            logger.error(f"Routing API error: {e}")
            return {"status": "error", "message": str(e)}

    def generate_mapbox_map(self, route_geometry: List[Tuple[float, float]], waypoints: List[Tuple[float, float]], filename: str = "mapbox_trip.png") -> bool:
        """
        Generates a static map image using Mapbox, overlaying the route line and markers.
        """
        if not route_geometry or not waypoints:
            logger.warning("Missing geometry or waypoints for map generation.")
            return False

        logger.info("Generating Mapbox GeoJSON overlay...")

        # OPTIMIZATION: Simplify Geometry to prevent HTTP 414 Errors
        MAX_POINTS = 80
        total_points = len(route_geometry)
        
        if total_points > MAX_POINTS:
            step = total_points // MAX_POINTS
            simplified_geometry = route_geometry[::step]
            if simplified_geometry[-1] != route_geometry[-1]:
                simplified_geometry.append(route_geometry[-1])
            logger.info(f"Simplified route geometry from {total_points} to {len(simplified_geometry)} points for URL safety.")
            route_geometry = simplified_geometry

        # Convert (lat, lon) to (lon, lat) for GeoJSON
        line_coords_geojson = [[round(lon, 5), round(lat, 5)] for lat, lon in route_geometry]
        
        features = []
        features.append({
            "type": "Feature",
            "properties": {
                "stroke": "#0045ff",      
                "stroke-width": 4,
                "stroke-opacity": 0.8
            },
            "geometry": {
                "type": "LineString",
                "coordinates": line_coords_geojson
            }
        })

        for i, (lat, lon) in enumerate(waypoints):
            features.append({
                "type": "Feature",
                "properties": {
                    "marker-color": "#ff0000",
                    "marker-size": "small",
                    "marker-symbol": str(i + 1)
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 5), round(lat, 5)]
                }
            })

        geojson_payload = {"type": "FeatureCollection", "features": features}
        geojson_str = json.dumps(geojson_payload)
        encoded_geojson = urllib.parse.quote(geojson_str, safe='')

        username = "mapbox"
        style_id = "streets-v12"
        overlay = f"geojson({encoded_geojson})"
        viewport = "auto"
        width = 800
        height = 600
        
        url = f"https://api.mapbox.com/styles/v1/{username}/{style_id}/static/{overlay}/{viewport}/{width}x{height}"
        params = {"padding": 50, "access_token": self.mapbox_token}

        try:
            response = self.session.get(url, params=params, stream=True)
            if response.status_code != 200:
                logger.error(f"Mapbox API Error: {response.status_code} - {response.text}")
                return False

            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"✅ Map successfully saved to: {filename}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to download map: {e}")
            return False

class LicensePlateService:
    """
    Handles interactions with the API Plaque Immatriculation.
    """
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.apiplaqueimmatriculation.com/plaque"
        self.headers = {'Accept': 'application/json'}

    def get_vehicle_details(self, license_plate: str) -> Optional[Dict[str, Any]]:
        """
        Fetches vehicle details (brand, model, weight) from a French license plate.
        """
        # The API expects params in the URL but called via POST
        params = {
            'immatriculation': license_plate,
            'token': self.api_token,
            'pays': 'FR'
        }
        
        logger.info(f"Fetching details for license plate: {license_plate}")

        try:
            # Using POST as requested in the snippet
            response = requests.post(self.base_url, params=params, headers=self.headers, data={})
            response.raise_for_status()
            
            data = response.json()
            
            if "data" in data:
                return data["data"]
            else:
                logger.warning(f"API returned successfully but no 'data' field found: {data}")
                return data

        except requests.RequestException as e:
            logger.error(f"License Plate API Error: {e}")
            return None

# ----------------------------------------------------------------------
# Main Application Logic
# ----------------------------------------------------------------------

def main():
    # Instantiate Services
    weather_service = WeatherService()
    nav_service = NavigationService(tomtom_key=TOMTOM_API_KEY, mapbox_token=MAPBOX_ACCESS_TOKEN)
    plate_service = LicensePlateService(api_token=LICENSE_PLATE_TOKEN)

    # --- Task 1: Check Weather ---
    lat, lon = 48.0713667, -0.7778768
    
    weather_start_time = time.time()
    temp = weather_service.get_current_temperature(lat, lon)
    weather_latency = time.time() - weather_start_time
    
    if temp is not None:
        print(f"\n🌤️  Weather Report")
        print(f"   Location: ({lat}, {lon})")
        print(f"   Temperature: {temp:.2f} °C")
    
    print(f"   (Weather API Latency: {weather_latency:.4f}s)")

    # --- Task 2: Calculate Route ---
    trip_plan = [
        "Rennes, France",
        "Laval, France", 
    ]

    print(f"\n🚗  Route Calculation")
    print(f"   Waypoints: {len(trip_plan)}")
    
    route_start_time = time.time()
    result = nav_service.calculate_route(trip_plan)
    route_latency = time.time() - route_start_time

    if result["status"] == "success":
        dist_km = result['distance_meters'] / 1000
        time_min = result['travel_time_seconds'] / 60
        print(f"   Total Distance: {dist_km:.2f} km")
        print(f"   Est. Travel Time: {time_min:.0f} min")
        print(f"   Arrival: {result['arrival_time']}")
        print(f"   (Routing API Latency: {route_latency:.4f}s)")
        
        # --- Task 3: Slope Analysis (New) ---
        if 'route_geometry' in result:
            full_geometry = result['route_geometry']
            
            # SAMPLING FIX: Prevent 429 Errors
            sampled_geometry = full_geometry[::10]
            
            print(f"\n⛰️  Slope Analysis (Open-Meteo)")
            print(f"   Original Points: {len(full_geometry)} -> Sampled Points: {len(sampled_geometry)}")
            
            elevation_start_time = time.time()
            elevations = weather_service.get_elevations(sampled_geometry)
            elevation_latency = time.time() - elevation_start_time
            
            if elevations and len(elevations) == len(sampled_geometry):
                mean_slope = calculate_mean_slope(sampled_geometry, elevations)
                print(f"   Mean Positive Slope: {mean_slope:.2f}%")
            else:
                print("   Could not calculate slope (elevation data mismatch).")
            
            print(f"   (Elevation API Latency: {elevation_latency:.4f}s)")

        # --- Task 4: Generate Mapbox Map ---
        print(f"\n🗺️  Map Generation (Mapbox)")
        if 'route_geometry' in result and 'coordinates' in result:
            map_start_time = time.time()
            success = nav_service.generate_mapbox_map(
                route_geometry=result['route_geometry'], 
                waypoints=result['coordinates'],
                filename="mapbox_trip.png"
            )
            map_latency = time.time() - map_start_time
            
            if success:
                print(f"   Map image saved as 'mapbox_trip.png'. Check your folder!")
            
            print(f"   (Mapbox API Latency: {map_latency:.4f}s)")
    else:
        print(f"   ❌ Error: {result['message']}")

    

    # --- Task 5: License Plate Lookup (Updated) ---
    print(f"\n🇫🇷 License Plate Analysis")
    sample_plate = "AA-123-BC" # Example plate to test
    
    plate_start_time = time.time()
    vehicle_data = plate_service.get_vehicle_details(sample_plate)
    plate_latency = time.time() - plate_start_time
    
    if vehicle_data:
        # Extract fields based on the user provided JSON structure
        # JSON keys: 'marque', 'modele', 'poids' (e.g. "1670 KG")
        marque = vehicle_data.get('marque', 'Unknown')
        modele = vehicle_data.get('modele', 'Unknown')
        poids_raw = vehicle_data.get('poids', 'Unknown')
        
        # Clean up weight string (remove " KG")
        if isinstance(poids_raw, str) and " KG" in poids_raw:
            poids_clean = poids_raw.replace(" KG", "").strip()
        else:
            poids_clean = poids_raw

        print(f"   Plate: {sample_plate}")
        print(f"   Vehicle: {marque} {modele}")
        print(f"   Weight (poids): {poids_clean} kg")
    else:
        print("   Failed to retrieve vehicle details.")
        
    print(f"   (License Plate API Latency: {plate_latency:.4f}s)")

if __name__ == "__main__":
    main()