import streamlit as st
import pandas as pd
import joblib
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from APIs import WeatherService, NavigationService, ChargingService
import numpy as np

# --- CONFIG ---
TOMTOM_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
EV_MODELS = {"Tesla Model 3 LR": 75.0, "Tesla Model 3 Std": 60.0, "Megane E-Tech": 60.0, "Peugeot e-208": 50.0}

st.set_page_config(page_title="EV Smart Routing", layout="wide", page_icon="🔋")

if 'calcul_fait' not in st.session_state:
    st.session_state.calcul_fait = False
    st.session_state.res = {}

@st.cache_resource
def init_services():
    nav = NavigationService(TOMTOM_KEY)
    weather = WeatherService()
    charger = ChargingService(['Datasets/Recharge_Data_1.csv', 'Datasets/Recharge_Data_2.csv', 'Datasets/Super_Recharge_Data.csv'], nav)
    model = joblib.load('Test_V2/final_ev_model.pkl')
    return nav, weather, charger, model

nav, weather, charger, model = init_services()

def get_real_charging_power(max_power, current_soc):
    """Simule la courbe de charge réelle (la puissance chute après 60-70%)"""
    if current_soc < 60:
        return max_power * 0.85 # Efficience moyenne
    elif current_soc < 80:
        return max_power * 0.50 # La puissance chute
    else:
        return max_power * 0.20 # Charge lente de fin

def predict_energy_safe(model, context):
    features = ["Speed_kmh", "Distance_Travelled_km", "Battery_State_%", "Humidity_%", "Battery_Temperature_C"]
    pred = float(model.predict(pd.DataFrame([context])[features])[0])
    if pred > 150 and context['Distance_Travelled_km'] < 100: pred /= 1000
    c100 = (pred / context['Distance_Travelled_km']) * 100 if context['Distance_Travelled_km'] > 0 else 0
    if c100 > 35 or c100 < 8: pred = (18 / 100) * context['Distance_Travelled_km']
    return max(0.0, pred)

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚡ Configuration")
    dep_city = st.text_input("Départ", "Rennes, France")
    arr_city = st.text_input("Arrivée", "Laval, France")
    ev_choice = st.selectbox("Véhicule", options=list(EV_MODELS.keys()), index=2)
    capa = EV_MODELS[ev_choice]
    soc_init = st.slider("Batterie départ (%)", 0, 100, 30)
    soc_target = st.slider("Batterie arrivée visée (%)", 0, 100, 20)
    btn_calcul = st.button("🚀 Calculer", use_container_width=True)
    btn_connect = st.button("🔌 Connecter à la voiture", use_container_width=True)

if btn_calcul:
    with st.spinner("Calcul intelligent de l'énergie..."):
        c1, c2 = nav.get_coords(dep_city), nav.get_coords(arr_city)
        if c1 and c2:
            route_base = nav.calculate_route(c1, c2)
            meteo = weather.get_local_weather(c1[0], c1[1])
            pts_km, pts_soc = [0], [soc_init]
            
            conso_directe = predict_energy_safe(model, {'Speed_kmh': route_base['vitesse_moy'], 'Distance_Travelled_km': route_base['summary']['lengthInMeters']/1000, 'Battery_State_%': soc_init, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
            needs_stop = (soc_init - (conso_directe / capa * 100)) < soc_target
            
            t_charge, borne = 0, None
            
            def add_curved_segment(start_soc, dist_leg, v_moy, current_km_total, final_target_soc=None):
                conso_ia_globale = predict_energy_safe(model, {'Speed_kmh': v_moy, 'Distance_Travelled_km': dist_leg, 'Battery_State_%': start_soc, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                soc_diff_total = (conso_ia_globale / capa * 100)
                temp_soc = start_soc
                for k in range(1, 11):
                    v_profil = 1.2 if 3 <= k <= 8 else 0.8
                    conso_step = soc_diff_total * (v_profil / 10.0)
                    temp_soc -= conso_step
                    if k == 10 and final_target_soc is not None:
                        temp_soc = final_target_soc
                    pts_km.append(current_km_total + (dist_leg / 10) * k)
                    pts_soc.append(max(0, temp_soc))
                return temp_soc

            if needs_stop:
                mid_pt = route_base['geometry'][len(route_base['geometry'])//2]
                borne = charger.find_best(mid_pt[0], mid_pt[1])
                if borne:
                    leg1 = nav.calculate_route(c1, (borne['lat'], borne['lon']))
                    leg2 = nav.calculate_route((borne['lat'], borne['lon']), c2)
                    d1, d2 = leg1['summary']['lengthInMeters']/1000, leg2['summary']['lengthInMeters']/1000
                    
                    soc_at_borne = add_curved_segment(soc_init, d1, leg1['vitesse_moy'], 0)
                    
                    e_leg2 = predict_energy_safe(model, {'Speed_kmh': leg2['vitesse_moy'], 'Distance_Travelled_km': d2, 'Battery_State_%': 50, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                    soc_conso_l2 = (e_leg2 / capa * 100)
                    soc_depart_borne = min(90.0, soc_conso_l2 + soc_target)
                    
                    # CALCUL DU TEMPS DE CHARGE RÉELISTE
                    avg_pwr = get_real_charging_power(borne['puissance'], (soc_at_borne + soc_depart_borne)/2)
                    kwh_needed = ((soc_depart_borne - soc_at_borne) * capa / 100)
                    t_charge = (kwh_needed / avg_pwr) * 60 * 1.15 # 15% de pertes thermiques/comm
                    
                    pts_km.append(d1); pts_soc.append(soc_depart_borne)
                    add_curved_segment(soc_depart_borne, d2, leg2['vitesse_moy'], d1, final_target_soc=soc_target)
                    
                    geom, dist_res, t_res = leg1['geometry']+leg2['geometry'], d1+d2, (leg1['summary']['travelTimeInSeconds']+leg2['summary']['travelTimeInSeconds'])//60
                else: needs_stop = False

            if not needs_stop:
                add_curved_segment(soc_init, route_base['summary']['lengthInMeters']/1000, route_base['vitesse_moy'], 0, final_target_soc=soc_init-(conso_directe/capa*100))
                geom, dist_res, t_res = route_base['geometry'], route_base['summary']['lengthInMeters']/1000, route_base['summary']['travelTimeInSeconds'] // 60

            st.session_state.res = {
                'c1': c1, 'c2': c2, 'geom': geom, 'dist': dist_res, 'temps': t_res,
                'soc_final': pts_soc[-1], 'needs_stop': needs_stop, 'borne': borne,
                'pts_km': pts_km, 'pts_soc': pts_soc, 't_charge': max(0, t_charge)
            }
            st.session_state.calcul_fait = True

if btn_connect :
    st.markdown(f"[🔌 Connecter à la voiture](https://connect.smartcar.com/oauth/authorize?response_type=code&client_id=474fb84e-7dad-49d9-af3d-b82727c213db&mode=simulated)")

# --- AFFICHAGE DES RÉSULTATS (PERSISTANTS) ---
if st.session_state.calcul_fait:
    res = st.session_state.res
    st.divider()
    
    # 1. INDICATEURS DYNAMIQUES
    if res['needs_stop']:
        m1, m2, m3, m4 = st.columns(4)
    else:
        m1, m2, m3 = st.columns(3)

    m1.metric("📏 Distance Totale", f"{res['dist']:.1f} km")
    m2.metric("⏱️ Temps de route", f"{res['temps']//60}h {res['temps']%60}min")
    
    if res['needs_stop']:
        m3.metric("🔌 Temps de charge", f"{res['t_charge']:.0f} min")
        m4.metric("🏁 Batterie Arrivée", f"{res['soc_final']:.1f}%")
        nom_borne = res['borne']['nom'].strip()
        st.success(f"📍 **Plan de recharge :** Arrêt à la borne **{nom_borne}** pendant **{res['t_charge']:.0f} minutes** pour repartir sereinement.")
    else:
        m3.metric("🏁 Batterie Arrivée", f"{res['soc_final']:.1f}%")
        st.info("✅ Aucun arrêt recharge n'est nécessaire pour ce trajet.")

    # 2. CARTE INTERACTIVE
    st.subheader("🗺️ Itinéraire réel")
    m = folium.Map(location=[(res['c1'][0]+res['c2'][0])/2, (res['c1'][1]+res['c2'][1])/2], zoom_start=9)
    folium.PolyLine(res['geom'], color="#0045ff", weight=5).add_to(m)
    
    folium.Marker(res['c1'], tooltip="Départ", icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(res['c2'], tooltip="Arrivée", icon=folium.Icon(color='red', icon='flag')).add_to(m)
    
    if res['needs_stop'] and res['borne']:
        folium.Marker(
            [res['borne']['lat'], res['borne']['lon']], 
            popup=f"<b>{res['borne']['nom'].strip()}</b><br>Charge : {res['t_charge']:.0f} min", 
            icon=folium.Icon(color='orange', icon='bolt', prefix='fa')
        ).add_to(m)
        
    st_folium(m, width="100%", height=500, key="map")

    # 3. GRAPHIQUE
    st.subheader("📉 Profil de batterie")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=res['pts_km'], y=res['pts_soc'], mode='lines+markers', line=dict(color='#00d1b2', width=4), name="Niveau SOC"))
    fig.add_hrect(y0=0, y1=20, fillcolor="red", opacity=0.15, annotation_text="ZONE CRITIQUE")
    fig.update_layout(xaxis_title="Distance parcourue (KM)", yaxis_title="Batterie (%)", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 Prêt pour le départ ? Configurez votre trajet.")