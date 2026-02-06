import streamlit as st
import pandas as pd
import joblib
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from APIs import WeatherService, NavigationService, ChargingService
import numpy as np

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

with st.sidebar:
    st.title("⚡ Configuration")
    dep_city = st.text_input("Départ")
    arr_city = st.text_input("Arrivée")
    ev_choice = st.selectbox("Véhicule", options=list(EV_MODELS.keys()), index=2)
    soc_init = st.slider("Batterie départ (%)", 0, 100, 100)
    soc_min_safe = st.slider("Batterie arrivé (%)", 0, 100, 0)
    btn_calcul = st.button("🚀 Calculer", use_container_width=True)

if btn_calcul:
    with st.spinner("Calcul du meilleur itinéraire..."):
        c1 = nav.get_coords(dep_city)
        c2 = nav.get_coords(arr_city)
        if c1 and c2:
            route_initiale = nav.calculate_route(c1, c2)
            dist_init = route_initiale['summary']['lengthInMeters'] / 1000
            meteo = weather.get_local_weather(c1[0], c1[1])
            
            # Prediction IA
            vitesse = dist_init / (route_initiale['summary']['travelTimeInSeconds'] / 3600)
            conso = model.predict(pd.DataFrame([[vitesse, dist_init, soc_init, meteo['humidity'], 25]], columns=["Speed_kmh", "Distance_Travelled_km", "Battery_State_%", "Humidity_%", "Battery_Temperature_C"]))[0]
            soc_final_theo = soc_init - (conso / EV_MODELS[ev_choice] * 100)

            needs_stop = soc_final_theo < soc_min_safe
            final_geom = route_initiale['geometry']
            borne = None
            temps_total = route_initiale['summary']['travelTimeInSeconds']

            if needs_stop:
                mid_pt = route_initiale['geometry'][len(route_initiale['geometry'])//2]
                borne = charger.find_best(mid_pt[0], mid_pt[1])
                if borne:
                    # RECALCUL DU CHEMIN VIA LA BORNE
                    leg1 = nav.calculate_route(c1, (borne['lat'], borne['lon']))
                    leg2 = nav.calculate_route((borne['lat'], borne['lon']), c2)
                    if leg1 and leg2:
                        final_geom = leg1['geometry'] + leg2['geometry']
                        temps_total = leg1['summary']['travelTimeInSeconds'] + leg2['summary']['travelTimeInSeconds']
                        dist_init = (leg1['summary']['lengthInMeters'] + leg2['summary']['lengthInMeters']) / 1000

            st.session_state.res = {
                'c1': c1, 'c2': c2, 'geom': final_geom, 'dist': dist_init, 'temps': temps_total // 60,
                'conso': conso, 'soc_final': soc_final_theo, 'needs_stop': needs_stop, 'borne': borne,
                'soc_min': soc_min_safe, 'soc_init': soc_init
            }
            st.session_state.calcul_fait = True

if st.session_state.calcul_fait:
    res = st.session_state.res
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Distance", f"{res['dist']:.1f} km")
    m2.metric("Temps", f"{res['temps']//60} h {res['temps']%60:.0f} min")
    m3.metric("Batterie Arrivée", f"{res['soc_min'] if res['needs_stop'] else res['soc_final']:.1f} %")
    m4.metric("Arrêt", "Vitré (ou proche)" if res['needs_stop'] else "Aucun")

    st.subheader("🗺️ Itinéraire")
    m = folium.Map(location=[(res['c1'][0]+res['c2'][0])/2, (res['c1'][1]+res['c2'][1])/2], zoom_start=9)
    folium.PolyLine(res['geom'], color="#0045ff", weight=5).add_to(m)
    folium.Marker(res['c1'], icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(res['c2'], icon=folium.Icon(color='red', icon='flag')).add_to(m)
    if res['needs_stop'] and res['borne']:
        folium.Marker([res['borne']['lat'], res['borne']['lon']], popup=f"{res['borne']['nom']}", icon=folium.Icon(color='orange', icon='bolt', prefix='fa')).add_to(m)
    st_folium(m, width="100%", height=500, key="map")

    # Graphique avec zone rouge
    fig = go.Figure()
    y_graph = [res['soc_init'], res['soc_init']-15, 60, res['soc_min']] if res['needs_stop'] else [res['soc_init'], res['soc_final']]
    fig.add_trace(go.Scatter(y=y_graph, mode='lines+markers', line=dict(color='#00d1b2', width=4)))
    fig.add_hrect(y0=0, y1=20, fillcolor="red", opacity=0.2, annotation_text="DANGER")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("👋 Bienvenue ! Configurez votre trajet et cliquez sur 'Calculer'.")