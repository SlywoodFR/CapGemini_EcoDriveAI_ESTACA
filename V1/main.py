import math
import pandas as pd
import joblib
import logging
import warnings
from APIs import WeatherService, NavigationService, LicensePlateService

# --- CONFIGURATION ---
TOMTOM_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
MAPBOX_TOKEN = "pk.eyJ1Ijoic2x5d29vZGZyIiwiYSI6ImNtaWc0dWo3ODAzMjUzZnF4anlyM2UydjgifQ.GZvrtjfqUJo4jmPh-oTp_w"
PLATE_TOKEN = "TokenDemo2025A"

# --- CALIBRATION ---
# Le dataset d'entraînement concerne des véhicules lourds (~170 kWh/100km).
# Une voiture normale consomme ~15-20 kWh/100km.
# On applique un facteur de 0.12 pour adapter l'IA à une voiture de tourisme.
CALIBRATION_FACTOR = 0.12 

logging.basicConfig(level=logging.INFO, format="%(message)s")
warnings.filterwarnings("ignore")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def cut_segments(geometry, elevations, step_km=5.0):
    segments = []
    curr = {'dist': 0, 'gain': 0, 'lat': geometry[0][0], 'lon': geometry[0][1]}
    for i in range(len(geometry)-1):
        dist = haversine(geometry[i][0], geometry[i][1], geometry[i+1][0], geometry[i+1][1])
        curr['dist'] += dist
        if elevations[i+1] > elevations[i]: curr['gain'] += (elevations[i+1] - elevations[i])
        if curr['dist'] >= step_km*1000 or i == len(geometry)-2:
            slope = (curr['gain'] / curr['dist']) * 100 if curr['dist'] > 0 else 0
            segments.append({'km': curr['dist']/1000, 'slope': slope, 'lat': geometry[i+1][0], 'lon': geometry[i+1][1]})
            curr = {'dist': 0, 'gain': 0, 'lat': geometry[i+1][0], 'lon': geometry[i+1][1]}
    return segments

def predict_segment(model, features, context):
    df = pd.DataFrame([context])
    
    # Formules Physiques (Identiques à l'entraînement)
    speed = context.get('Speed_kmh', 0)
    accel = context.get('Acceleration_ms2', 0)
    wind = context.get('Wind_Speed_ms', 0)
    weight = context.get('Vehicle_Weight_kg', 0)
    slope = context.get('Slope_%', 0)
    temp = context.get('Temperature_C', 20)

    df['Power_Drag'] = (speed + wind*3.6) ** 3
    df['Power_Inertia'] = weight * accel * speed
    df['Power_Gravity'] = weight * slope * speed
    df['Power_HVAC'] = abs(temp - 21)
    
    for col in features:
        if col not in df.columns: df[col] = 0.0
            
    for cat in ['Driving_Mode', 'Road_Type', 'Traffic_Condition', 'Weather_Condition']:
        val = context.get(cat)
        if f"{cat}_{val}" in features: df[f"{cat}_{val}"] = 1.0

    raw_pred = max(0.0, float(model.predict(df[features].astype(float))[0]))
    
    # Application de la calibration
    return raw_pred * CALIBRATION_FACTOR

def main():
    print("\n🔋 === EV SMART ROUTING (OPTIMISÉ) === 🔋")
    print(f"   🎯 Modèle IA chargé (Calibration: {CALIBRATION_FACTOR})")
    
    try:
        brain = joblib.load('ev_brain_v1.pkl')
        model, features = brain['model'], brain['features']
    except:
        print("❌ Modèle introuvable.")
        return

    nav = NavigationService(TOMTOM_KEY, MAPBOX_TOKEN)
    weather = WeatherService()
    plate = LicensePlateService(PLATE_TOKEN)

    depart, arrivee = "Rennes, France", "Laval, France"
    immat = "HF-996-CC"
    
    print(f"\n1️⃣  Véhicule : {immat}")
    try: car = plate.get_details(immat)
    except: car = {'weight': 1700.0, 'model': 'Mode Déconnecté'}
    total_weight = car['weight'] + 100
    print(f"   -> Modèle: {car['model']} | Poids total: {total_weight}kg")
    
    print(f"2️⃣  Itinéraire : {depart} -> {arrivee}")
    route = nav.calculate_route(depart, arrivee)
    if not route: return
    
    full_geom = route['geometry']
    print(f"   -> Distance: {route['summary']['lengthInMeters']/1000:.1f} km")
    
    elevations = weather.get_elevations(full_geom[::20])
    segments = cut_segments(full_geom[::20], elevations)
    
    total_kwh = 0
    current_battery = 80.0
    
    print(f"\n{'KM':<6} | {'PENTE':<6} | {'TEMP':<6} | {'CONSO':<10}")
    print("-" * 40)
    
    for seg in segments:
        meteo = weather.get_local_weather(seg['lat'], seg['lon'])
        
        context = {
            'Speed_kmh': 110,           
            'Acceleration_ms2': 0.02,
            'Wind_Speed_ms': meteo['wind_ms'],
            'Vehicle_Weight_kg': total_weight,
            'Slope_%': seg['slope'],
            'Distance_Travelled_km': seg['km'],
            'Tire_Pressure_psi': 40,
            'Battery_Temperature_C': 30, 
            'Temperature_C': meteo['temp'],
            'Humidity_%': 50,
            'Battery_State_%': current_battery,
            'Driving_Mode': 'Normal',
            'Road_Type': 'Highway',
            'Traffic_Condition': 'Low',
            'Weather_Condition': 'Sunny'
        }
        
        kwh = predict_segment(model, features, context)
        total_kwh += kwh
        current_battery -= (kwh * 1.5)

        print(f"{seg['km']:.1f}   | {seg['slope']:.1f}%   | {meteo['temp']:.0f}°C   | {kwh:.2f}")

    print("-" * 40)
    print(f"⚡ TOTAL PRÉDIT : {total_kwh:.2f} kWh")
    print(f"🔋 Batterie restante estimée : {max(0, current_battery):.1f}%")
    
    nav.generate_map(full_geom, route['waypoints'], "trajet_final.png")
    print("\n✅ Terminé ! Ouvrez 'trajet_final.png' pour voir la carte.")

if __name__ == "__main__":
    main()