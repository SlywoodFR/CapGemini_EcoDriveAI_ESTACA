import streamlit as st
import pandas as pd
import joblib
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from APIs import WeatherService, NavigationService, ChargingService, VehicleService
import numpy as np
import smartcar

# --- CONFIGURATION ---
TOMTOM_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
SC_CLIENT_ID = '474fb84e-7dad-49d9-af3d-b82727c213db'
SC_CLIENT_SECRET = '2c9940fb-3997-4b0e-b57b-6f3f521df2eb'
SC_REDIRECT_URI = 'http://localhost:8501'

st.set_page_config(page_title="EcoDriveAI - Planificateur de Trajets pour Véhicules Électriques", layout="wide", page_icon="⚡")

# --- BANDEAU DE TITRE ---
st.title("⚡ EcoDriveAI - Planificateur de Trajets pour Véhicules Électriques")
st.markdown("### Optimisation de trajets longue distance par Intelligence Artificielle")
st.caption("Gestion dynamique de la recharge, respect du SOC de sécurité et précision à l'arrivée.")

# Initialisation
sc_client = smartcar.AuthClient(SC_CLIENT_ID, SC_CLIENT_SECRET, SC_REDIRECT_URI, test_mode=True)
if 'sc_token' not in st.session_state: st.session_state.sc_token = None
if 'calcul_fait' not in st.session_state: st.session_state.calcul_fait = False

# OAuth
qp = st.query_params
if "code" in qp and st.session_state.sc_token is None:
    res_auth = sc_client.exchange_code(qp["code"])
    st.session_state.sc_token = res_auth.access_token
    st.query_params.clear()
    st.rerun()

@st.cache_resource
def init_services():
    nav = NavigationService(TOMTOM_KEY)
    weather = WeatherService()
    charger = ChargingService(['Datasets/Recharge_Data_1.csv', 'Datasets/Recharge_Data_2.csv', 'Datasets/Super_Recharge_Data.csv'], nav)
    vehicle_db = VehicleService('Datasets/ev_database.csv')
    model = joblib.load('Test_V2/final_ev_model.pkl')
    return nav, weather, charger, vehicle_db, model

nav, weather, charger, vehicle_db, model = init_services()

# --- MESSAGE DE LANCEMENT (NOUVEAU) ---
if not st.session_state.get('calcul_fait'):
    st.info("👋 **Bienvenue !** Configurez votre trajet dans la barre latérale à gauche, puis cliquez sur **Calculer l'itinéraire** pour générer votre plan de route personnalisé.")

# --- PRÉDICTION IA SUR TRAJET COMPLET ---
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
    dep_city = st.text_input("Départ")
    arr_city = st.text_input("Arrivée")
    st.divider()
    soc_init, capa, car_max_charge, show_manual = 100, 60.0, 150.0, True
    if st.session_state.sc_token:
        try:
            v_res = smartcar.get_vehicles(st.session_state.sc_token)
            v = smartcar.Vehicle(v_res.vehicles[0], st.session_state.sc_token)
            signals = v.get_signals(['ev.battery.level', 'ev.battery.capacity'])
            if signals.body['ev.battery.level'].value:
                soc_init = int(signals.body['ev.battery.level'].value * 100)
                st.success(f"✅ Connecté : {v.attributes().make}")
                match = vehicle_db.find_by_brand(v.attributes().make)
                if match: capa, car_max_charge, show_manual = float(match['battery_capacity_kWh']), float(match['fast_charging_power_kw_dc']), False
        except: pass
    if show_manual:
        v_list = vehicle_db.get_vehicle_list()
        ev_choice = st.selectbox("Modèle", v_list if v_list else ["Tesla Model 3"])
        details = vehicle_db.get_details(ev_choice)
        if details: capa, car_max_charge = float(details['battery_capacity_kWh']), float(details['fast_charging_power_kw_dc'])
        soc_init = st.slider("Batterie départ (%)", 0, 100, soc_init)
    st.divider()
    soc_safety = st.slider("🛡️ SOC de sécurité (%)", 0, 25, 5)
    soc_target = st.slider("🏁 SOC Arrivée visé (%)", soc_safety, 100, soc_safety)
    btn_calcul = st.button("🚀 Calculer l'itinéraire", width='stretch')

# --- LOGIQUE DE CALCUL ---
if btn_calcul:
    try:
        with st.spinner("Calcul de l'itinéraire optimal..."):
            c_start, c_end = nav.get_coords(dep_city), nav.get_coords(arr_city)
            if c_start and c_end:
                meteo = weather.get_local_weather(c_start[0], c_start[1])
                pts_km, pts_soc, final_bornes, t_charge, t_route = [0], [soc_init], [], 0, 0
                curr_pos, curr_soc, d_total, total_geom = c_start, float(soc_init), 0, []
                for _ in range(8):
                    full_trip = nav.calculate_route(curr_pos, c_end)
                    if not full_trip: break
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
                        pts_km.append(d_total + leg_to_borne['dist_km']); pts_soc.append(soc_at_borne)
                        pts_km.append(d_total + leg_to_borne['dist_km']); pts_soc.append(soc_rech)
                        total_geom += leg_to_borne['geometry']; t_route += leg_to_borne['summary']['travelTimeInSeconds']; t_charge += dur_c
                        d_total += leg_to_borne['dist_km']; curr_pos, curr_soc = (borne['lat'], borne['lon']), soc_rech
                        final_bornes.append({**borne, 'duree': dur_c})
                if total_geom:
                    st.session_state.res = {'geom': total_geom, 'dist': d_total, 'bornes': final_bornes, 'pts_km': pts_km, 'pts_soc': pts_soc, 't_charge': t_charge, 't_route': t_route, 'c1': c_start, 'c2': c_end, 'safety': soc_safety}
                    st.session_state.calcul_fait = True
    except Exception as e: st.exception(e)

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

    if res['bornes']:
        txt = [f"**{b['nom']}** ({b['duree']} min)" for b in res['bornes']]
        st.success(f"🔋 **Stratégie validée par l'IA :** {', '.join(txt)}")

    m = folium.Map(location=[res['c1'][0], res['c1'][1]], zoom_start=6)
    folium.PolyLine(res['geom'], color="#0045ff", weight=5).add_to(m)
    for b in res['bornes']: folium.Marker([b['lat'], b['lon']], icon=folium.Icon(color='orange', icon='bolt', prefix='fa')).add_to(m)
    st_folium(m, width="100%", height=500, key="map")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=res['pts_km'], y=res['pts_soc'], mode='lines+markers', line=dict(color='#00d1b2', width=4)))
    fig.add_hrect(y0=0, y1=res['safety'], fillcolor="red", opacity=0.15, annotation_text=f"SÉCURITÉ ({res['safety']}%)")
    fig.update_layout(xaxis_title="KM", yaxis_title="%", template="plotly_dark")
    st.plotly_chart(fig, width='stretch')