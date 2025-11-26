import openmeteo_requests
import time
import urllib.parse
import pandas as pd
import requests_cache
import requests
from retry_requests import retry

# ----------------------------------------------------------------------
# Open-Meteo API Function
# ----------------------------------------------------------------------

def Temperature_API(latitude, longitude):
    """Fetches the current temperature for given coordinates using Open-Meteo."""
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m",
        "timezone": "auto",
    }
    
    try:
        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]

        # Process current data.
        current = response.Current()
        current_temperature_2m = current.Variables(0).Value()

        return current_temperature_2m
    except Exception as e:
        print(f"Open-Meteo API Error: {e}")
        return None

# ----------------------------------------------------------------------
# TomTom Geocoding API Function (Refactored)
# ----------------------------------------------------------------------

def Coordinates_API(address):
    """
    Converts an address into geographic coordinates (latitude, longitude) 
    using the TomTom Geocoding API.
    """

    key = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
    
    encoded_address = urllib.parse.quote(address)

    url = f"https://api.tomtom.com/search/2/geocode/{encoded_address}.json?key={key}"

    # Note: Error handling has been removed as per the requested reformatting.
    response = requests.get(url, timeout=10)
    # Raise HTTPError for bad status codes (4xx or 5xx)
    response.raise_for_status() 
    data = response.json()

    # Check for the presence of the 'results' key and ensure it's not empty
    if data and "results" in data and len(data["results"]) > 0:
        first_result = data["results"][0]
            
        # Extract Lat/Lon
        latitude = first_result['position']['lat']
        longitude = first_result['position']['lon']
        
        return latitude, longitude

    else:
        # This handles cases where the request succeeds but returns an empty result set
        print("[TomTom] Geocoding failed: No coordinates found for the address.")
        return None, None

# ----------------------------------------------------------------------
# TomTom Routing API Function
# ----------------------------------------------------------------------

def Routing_API(address_list: list) -> dict:
    """
    Calculates a route between two or more addresses using TomTom Geocoding 
    and Routing APIs.

    Args:
        address_list (list): Liste d'adresses (chaînes de caractères). Doit contenir 
                             au moins deux points.
                             Exemple : ["adresse 1", "adresse 2", ...]

    Returns:
        dict: Dictionnaire contenant le résumé de l'itinéraire (distance, temps), 
              ou un message d'erreur.
    """
    if len(address_list) < 2:
        return {"status": "error", "message": "La liste d'adresses doit contenir au moins 2 points pour calculer un itinéraire."}

    coordinates_list = []
    
    for i, address in enumerate(address_list):
        lat, lon = Coordinates_API(address)
        
        if lat is None or lon is None:
            return {"status": "error", "message": f"Échec du géocodage pour l'adresse #{i+1}: '{address}'. Impossible de calculer l'itinéraire."}
        
        coordinates_list.append((lat, lon))

    key = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"

    coords_string = ":".join([f"{lat},{lon}" for lat, lon in coordinates_list])

    BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute/"
    url = f"{BASE_URL}{coords_string}/json?key={key}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and 'routes' in data and len(data['routes']) > 0:
            route_summary = data['routes'][0]['summary']
            
            distance_meters = route_summary['lengthInMeters']
            travel_time_seconds = route_summary['travelTimeInSeconds']
            
            return {
                "status": "success",
                "distance_meters": distance_meters,
                "travel_time_seconds": travel_time_seconds,
                "departure_time": route_summary.get('departureTime'),
                "arrival_time": route_summary.get('arrivalTime'),
            }
        else:
            return {"status": "error", "message": "Aucun itinéraire trouvé ou réponse inattendue du service de routage."}

    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Erreur API lors du routage: {e}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "Erreur de décodage JSON de la réponse API de routage."}

# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------

def main():
    # Example 1: Weather check for known coordinates (Le Mans, France approx)
    print("\n--- OpenWeather Routing Results ---")

    start_time_OW = time.time()

    known_lat = 48.0713667
    known_lon = -0.7778768
    temp = Temperature_API(known_lat, known_lon)
    
    if temp is not None:
        print(f"Température for ({known_lat:.6f}, {known_lon:.6f}): {temp:.2f} °C")
    else:
        print(f"Could not retrieve temperature for known coordinates.")
        
    print("--- %s seconds ---" % (time.time() - start_time_OW))
    
    # Example 2: Routing using a list of addresses 
    start_time_TT = time.time()

    address_list = [
        "31 Rue Bernard Le Pecq, 53000 Laval, France",
        "30 Rue Saint-Guillaume, 75007 Paris, France", 
        "31 Rue de la Villette, 75019 Paris, France"  
    ]
    
    route_result = Routing_API(address_list)
    
    print("\n--- TomTom Routing Results ---")
    if route_result['status'] == 'success':
        distance_km = route_result['distance_meters'] / 1000
        travel_time_min = route_result['travel_time_seconds'] / 60
        
        print(f"Distance : {distance_km:.2f} km")
        print(f"Time: {travel_time_min:.2f} minutes")
    else:
        print(f"Statut: Error")
        print(f"Message: {route_result['message']}")

    print("--- %s seconds ---" % (time.time() - start_time_TT))

if __name__ == "__main__":
    main()