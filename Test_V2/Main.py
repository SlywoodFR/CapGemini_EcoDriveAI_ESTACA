import pandas as pd
import joblib
import logging
import warnings
from APIs import WeatherService, NavigationService, LicensePlateService, ChargingService

# --- CONFIG ---
TOMTOM_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
MAPBOX_TOKEN = "pk.eyJ1Ijoic2x5d29vZGZyIiwiYSI6ImNtaWc0dWo3ODAzMjUzZnF4anlyM2UydjgifQ.GZvrtjfqUJo4jmPh-oTp_w"
PLATE_TOKEN = "TokenDemo2025A"

warnings.filterwarnings("ignore")

def predict_energy(model, context):
    features = ["Speed_kmh", "Distance_Travelled_km", "Battery_State_%", "Humidity_%", "Battery_Temperature_C"]
    df = pd.DataFrame([context])[features]
    return max(0.0, float(model.predict(df)[0]))

def main():
    print("\n" + "="*60 + "\n⚡ EV SMART ROUTER - NAVIGATION OPTIMISÉE\n" + "="*60)

    # 1. INITIALISATION
    try:
        model = joblib.load('Test_V2/final_ev_model.pkl')
        nav = NavigationService(TOMTOM_KEY, MAPBOX_TOKEN)
        weather = WeatherService()
        charger = ChargingService([
            'Datasets/Recharge_Data_1.csv', 
            'Datasets/Recharge_Data_2.csv', 
            'Datasets/Super_Recharge_Data.csv'
        ], nav)
    except Exception as e:
        print(f"❌ Erreur Initialisation : {e}")
        return

    # Paramètres utilisateur
    depart, arrivee = "Paris, France", "Marseille, France"
    soc_actuel = 100.0    # Simulation batterie faible
    soc_min_visé = 20.0  # Ton seuil de sécurité
    capa_batt = 60.0

    print(f"\n📍 Analyse du trajet : {depart} -> {arrivee}")

    # 2. TEST DU TRAJET DIRECT
    route = nav.calculate_route(depart, arrivee)
    if not route:
        print("❌ Erreur : Impossible de joindre les serveurs TomTom.")
        return
    
    dist_totale = route['summary']['lengthInMeters'] / 1000
    vitesse = (route['summary']['lengthInMeters'] / route['summary']['travelTimeInSeconds']) * 3.6
    meteo = weather.get_local_weather(route['geometry'][0][0], route['geometry'][0][1])

    # Prédiction IA
    ctx_dir = {
        'Speed_kmh': vitesse, 
        'Distance_Travelled_km': dist_totale, 
        'Battery_State_%': soc_actuel, 
        'Humidity_%': meteo['humidity'], 
        'Battery_Temperature_C': 25
    }
    conso_dir = predict_energy(model, ctx_dir)
    soc_fin_dir = soc_actuel - (conso_dir / capa_batt * 100)

    print(f"📊 Diagnostic direct : Arrivée estimée à {soc_fin_dir:.1f}%")

    # 3. GESTION DE L'ARRÊT (Priorité : Sécurité & Efficience)
    if soc_fin_dir < soc_min_visé:
        print(f"⚠️ Alerte : SOC trop bas. Recherche d'une borne optimale...")
        
        # On cherche une borne au milieu géographique
        mid_idx = len(route['geometry']) // 2
        mid_pt = route['geometry'][mid_idx]
        borne = charger.find_best_station(mid_pt[0], mid_pt[1])
        
        if borne:
            print(f"✅ Borne trouvée : {borne['nom']} ({borne['puissance']} kW)")
            
            # Recalcul réel par segments
            leg1 = nav.calculate_route(depart, (borne['lat'], borne['lon']))
            leg2 = nav.calculate_route((borne['lat'], borne['lon']), arrivee)
            
            if leg1 and leg2:
                # Énergie Leg 1
                dist1 = leg1['summary']['lengthInMeters'] / 1000
                conso1 = predict_energy(model, {'Speed_kmh': vitesse, 'Distance_Travelled_km': dist1, 'Battery_State_%': soc_actuel, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                soc_borne = soc_actuel - (conso1 / capa_batt * 100)
                
                # Énergie Leg 2
                dist2 = leg2['summary']['lengthInMeters'] / 1000
                conso2 = predict_energy(model, {'Speed_kmh': vitesse, 'Distance_Travelled_km': dist2, 'Battery_State_%': 50, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                besoin_fin = (conso2 / capa_batt * 100)
                
                # Règle optimisée : repartir juste assez pour arriver à 20% (max 80%)
                soc_repartir = min(80.0, besoin_fin + soc_min_visé)
                
                # Temps de charge (Min)
                kwh_ajoute = ((soc_repartir - soc_borne) * capa_batt) / 100
                t_charge = (kwh_ajoute / borne['puissance']) * 60 * 1.1

                # Affichage complet
                print("\n" + "-"*50)
                print(f"🏁 RÉSUMÉ DU TRAJET OPTIMISÉ :")
                print(f"   ⏱️  Temps total (Route+Charge) : {(leg1['summary']['travelTimeInSeconds']+leg2['summary']['travelTimeInSeconds'])//60 + int(t_charge)} min")
                print(f"   🔌 Temps de charge : {t_charge:.0f} min")
                print(f"   🔋 SOC Sortie Borne : {soc_repartir:.0f}%")
                print(f"   🔋 SOC Arrivée : {soc_min_visé}%")
                print("-" * 50)
                
                # Génération de la carte avec détour
                nav.generate_map(leg1['geometry']+leg2['geometry'], [leg1['waypoints'][0], (borne['lat'], borne['lon']), leg2['waypoints'][1]], "trajet_optimise.png")
    else:
        print("\n✅ Trajet direct sécurisé. Pas d'arrêt nécessaire.")
        nav.generate_map(route['geometry'], route['waypoints'], "trajet_optimise.png")

if __name__ == "__main__":
    main()