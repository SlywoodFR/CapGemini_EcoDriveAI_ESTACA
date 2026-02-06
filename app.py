import streamlit as st
import pandas as pd
import joblib
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from APIs import WeatherService, NavigationService, ChargingService, VehicleService
import numpy as np
import smartcar
from streamlit_searchbox import st_searchbox

# --- CONFIGURATION ---
TOMTOM_KEY = st.secrets["TOMTOM_KEY"]
SC_CLIENT_ID = st.secrets["SC_CLIENT_ID"]
SC_CLIENT_SECRET = st.secrets["SC_CLIENT_SECRET"]
SC_REDIRECT_URI = st.secrets["SC_REDIRECT_URI"]

st.set_page_config(page_title="EcoDriveAI - Planificateur", layout="wide", page_icon="⚡")

# --- BANDEAU DE TITRE ---
st.title("⚡ EcoDriveAI")
st.markdown("### Optimisation de trajets longue distance par Intelligence Artificielle")
st.caption("Gestion dynamique de la recharge, respect du SOC de sécurité et précision à l'arrivée.")

# Initialisation
if 'calcul_fait' not in st.session_state: st.session_state.calcul_fait = False

@st.cache_resource
def init_services():
    nav = NavigationService(TOMTOM_KEY)
    weather = WeatherService()
    charger = ChargingService(['Datasets/Recharge_Data_1.csv', 'Datasets/Recharge_Data_2.csv', 'Datasets/Super_Recharge_Data.csv'], nav)
    vehicle_db = VehicleService('Datasets/ev_database.csv')
    model = joblib.load('Test_V2/final_ev_model.pkl')
    return nav, weather, charger, vehicle_db, model

nav, weather, charger, vehicle_db, model = init_services()

# --- MESSAGE DE LANCEMENT ---
if not st.session_state.get('calcul_fait'):
    st.info("👋 **Bienvenue !** Configurez votre trajet dans la barre latérale à gauche, puis cliquez sur **Calculer l'itinéraire** pour générer votre plan de route personnalisé.")

# --- PRÉDICTION IA ---
def predict_full_trip(model, route_summary, start_soc, humidity):
    dist_km = route_summary['summary']['lengthInMeters'] / 1000
    context = {'Speed_kmh': route_summary['vitesse_moy'], 'Distance_Travelled_km': dist_km, 'Battery_State_%': start_soc, 'Humidity_%': humidity, 'Battery_Temperature_C': 25}
    features = ["Speed_kmh", "Distance_Travelled_km", "Battery_State_%", "Humidity_%", "Battery_Temperature_C"]
    pred = float(model.predict(pd.DataFrame([context])[features])[0])
    if (pred / dist_km * 100) < 16.5: pred = (16.5 / 100) * dist_km
    return pred

def get_real_charging_power(station_pwr, car_max_pwr, soc):
    limit = min(float(station_pwr), float(car_max_pwr))
    return limit * 0.85 if soc < 60 else limit * 0.50 if soc < 80 else limit * 0.20

# --- SIDEBAR ---
with st.sidebar:
    st.title("🔧 Configuration du Trajet")
    
    st.subheader("📍 Itinéraire")
    dep_city = st_searchbox(
        nav.get_suggestions, 
        key="dep_search", 
        placeholder="Lieu de départ..."
    )
    
    arr_city = st_searchbox(
        nav.get_suggestions, 
        key="arr_search", 
        placeholder="Lieu d'arrivée..."
    )
    
    st.divider()
    
    v_list = vehicle_db.get_vehicle_list()
    ev_choice = st.selectbox("Modèle", v_list if v_list else ["Tesla Model 3"])
    details = vehicle_db.get_details(ev_choice)
    capa, car_max_charge = (float(details['battery_capacity_kWh']), float(details['fast_charging_power_kw_dc'])) if details else (60.0, 150.0)
    
    soc_init = st.slider("Batterie départ (%)", 0, 100, 100)
    soc_safety = st.slider("🛡️ SOC sécurité (%)", 0, 25, 5)
    soc_target = st.slider("🏁 SOC arrivée (%)", soc_safety, 100, soc_safety)
    btn_calcul = st.button("🚀 Calculer", width='stretch')

# --- LOGIQUE DE CALCUL ---
if btn_calcul:
    st.session_state.calcul_fait = False 
    
    if not dep_city or not arr_city:
        st.error("❌ Veuillez sélectionner une adresse dans la liste des suggestions.")
    else:
        with st.status("🔍 Vérification des adresses...", expanded=True) as status:
            c_start = nav.get_coords(dep_city)
            if c_start:
                st.write(f"✅ Départ trouvé : {dep_city}")
            else:
                st.error(f"❌ Impossible de localiser : **{dep_city}**")
                st.stop()
                
            c_end = nav.get_coords(arr_city)
            if c_end:
                st.write(f"✅ Arrivée trouvée : {arr_city}")
            else:
                st.error(f"❌ Impossible de localiser : **{arr_city}**")
                st.stop()
            
            # --- NOUVELLE SÉCURITÉ : Distance cohérente (anti-continent) ---
            dist_directe = np.sqrt(((c_start[0]-c_end[0])*111)**2 + ((c_start[1]-c_end[1])*74)**2)
            if dist_directe > 1500:
                st.error(f"⚠️ **Distance incohérente : {dist_directe:.0f} km.**")
                st.write("Il semble que l'une des villes soit sur un autre continent (ex: Laval au Québec).")
                st.info("💡 **Conseil :** Précisez le pays dans votre saisie (ex: 'Laval, France').")
                st.stop()

            status.update(label="🚀 Adresses validées. Simulation en cours...", state="running")

            try:
                meteo = weather.get_local_weather(c_start[0], c_start[1])
                pts_km, pts_soc, final_bornes, t_charge, t_route = [0], [soc_init], [], 0, 0
                curr_pos, curr_soc, d_total, total_geom = c_start, float(soc_init), 0, []

                for _ in range(8):
                    full_trip = nav.calculate_route(curr_pos, c_end)
                    
                    # --- SÉCURITÉ : Aucun chemin trouvé entre les points ---
                    if not full_trip:
                        st.error("❌ Aucun itinéraire routier trouvé. Vérifiez que les deux points sont sur le même continent.")
                        st.stop()
                        
                    conso_needed = predict_full_trip(model, full_trip, curr_soc, meteo['humidity'])
                    arrival_soc = curr_soc - (conso_needed / capa * 100)

                    if arrival_soc >= soc_target:
                        pts_km.append(d_total + full_trip['dist_km']); pts_soc.append(arrival_soc)
                        total_geom += full_trip['geometry']; t_route += full_trip['summary']['travelTimeInSeconds']; d_total += full_trip['dist_km']
                        break
                    else:
                        autonomie_km = ((curr_soc - soc_safety) / (conso_needed / full_trip['dist_km'] / capa * 100))
                        idx = min(int((autonomie_km * 0.85 / full_trip['dist_km']) * len(full_trip['geometry'])), len(full_trip['geometry'])-1)
                        borne = charger.find_best(full_trip['geometry'][idx][0], full_trip['geometry'][idx][1])
                        if not borne: break
                        leg_to_borne = nav.calculate_route(curr_pos, (borne['lat'], borne['lon']))
                        conso_to_borne = predict_full_trip(model, leg_to_borne, curr_soc, meteo['humidity'])
                        soc_at_borne = curr_soc - (conso_to_borne / capa * 100)
                        trip_after = nav.calculate_route((borne['lat'], borne['lon']), c_end)
                        conso_after = predict_full_trip(model, trip_after, 50, meteo['humidity'])
                        soc_rech = (conso_after / capa * 100) + soc_target
                        soc_rech = min(95.0, max(soc_rech, soc_at_borne + 15))
                        dur_c = int((((soc_rech - soc_at_borne)*capa/100) / get_real_charging_power(borne['puissance'], car_max_charge, (soc_at_borne+soc_rech)/2)) * 60 * 1.15)
                        pts_km.append(d_total + leg_to_borne['dist_km']); pts_soc.append(soc_at_borne); pts_km.append(d_total + leg_to_borne['dist_km']); pts_soc.append(soc_rech)
                        total_geom += leg_to_borne['geometry']; t_route += leg_to_borne['summary']['travelTimeInSeconds']; t_charge += dur_c
                        d_total += leg_to_borne['dist_km']; curr_pos, curr_soc = (borne['lat'], borne['lon']), soc_rech
                        final_bornes.append({**borne, 'duree': dur_c})
                
                if total_geom:
                    st.session_state.res = {'geom': total_geom, 'dist': d_total, 'bornes': final_bornes, 'pts_km': pts_km, 'pts_soc': pts_soc, 't_charge': t_charge, 't_route': t_route, 'c1': c_start, 'c2': c_end}
                    st.session_state.calcul_fait = True
                    status.update(label="✅ Calcul terminé !", state="complete")
            except Exception as e:
                st.error(f"Erreur durant le calcul : {e}")

# --- AFFICHAGE ---
if st.session_state.get('calcul_fait'):
    res = st.session_state.res
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📏 Distance", f"{res['dist']:.1f} km")
    h, m = divmod((res['t_route'] // 60) + res['t_charge'], 60)
    c2.metric("⏱️ Temps total", f"{h}h {m}min")
    c3.metric("🔌 Dont charge", f"{res['t_charge']} min")
    c4.metric("🏁 SOC Final", f"{res['pts_soc'][-1]:.1f}%")

    m = folium.Map(location=[res['c1'][0], res['c1'][1]], zoom_start=6)
    folium.PolyLine(res['geom'], color="#0045ff", weight=5).add_to(m)
    folium.Marker(res['c1'], popup="Départ", icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(res['c2'], popup="Arrivée", icon=folium.Icon(color='red', icon='flag')).add_to(m)
    
    for b in res['bornes']: 
        folium.Marker([b['lat'], b['lon']], icon=folium.Icon(color='orange', icon='bolt', prefix='fa')).add_to(m)
    st_folium(m, width="100%", height=500, key="map")