import streamlit as st
import pandas as pd
import joblib
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from APIs import WeatherService, NavigationService, ChargingService
import numpy as np
import smartcar

# --- CONFIGURATION ---
TOMTOM_KEY = "Mn7jMVv7fCgBTRjLxMEQqiLqSTQzmlYC"
EV_MODELS = {"Tesla Model 3 LR": 75.0, "Tesla Model 3 Std": 60.0, "Megane E-Tech": 60.0, "Peugeot e-208": 50.0}

SC_CLIENT_ID = '474fb84e-7dad-49d9-af3d-b82727c213db'
SC_CLIENT_SECRET = '2c9940fb-3997-4b0e-b57b-6f3f521df2eb'
SC_REDIRECT_URI = 'http://localhost:8501'

st.set_page_config(page_title="EV Smart Routing", layout="wide", page_icon="⚡")

# --- INITIALISATION SMARTCAR ---
sc_client = smartcar.AuthClient(
    client_id=SC_CLIENT_ID,
    client_secret=SC_CLIENT_SECRET,
    redirect_uri=SC_REDIRECT_URI,
    test_mode=True
)

if 'sc_token' not in st.session_state: st.session_state.sc_token = None
if 'calcul_fait' not in st.session_state: st.session_state.calcul_fait = False

# Capture du code OAuth et gestion du rafraîchissement
query_params = st.query_params
if "code" in query_params and st.session_state.sc_token is None:
    try:
        res_auth = sc_client.exchange_code(query_params["code"])
        st.session_state.sc_token = res_auth.access_token
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Erreur d'authentification Smartcar : {e}")

@st.cache_resource
def init_services():
    nav = NavigationService(TOMTOM_KEY)
    weather = WeatherService()
    charger = ChargingService(['Datasets/Recharge_Data_1.csv', 'Datasets/Recharge_Data_2.csv', 'Datasets/Super_Recharge_Data.csv'], nav)
    model = joblib.load('Test_V2/final_ev_model.pkl')
    return nav, weather, charger, model

nav, weather, charger, model = init_services()

# --- FONCTIONS TECHNIQUES ---
def get_real_charging_power(max_pwr, soc):
    if soc < 60: return max_pwr * 0.85
    if soc < 80: return max_pwr * 0.50
    return max_pwr * 0.20

def predict_energy_safe(model, context):
    features = ["Speed_kmh", "Distance_Travelled_km", "Battery_State_%", "Humidity_%", "Battery_Temperature_C"]
    pred = float(model.predict(pd.DataFrame([context])[features])[0])
    if pred > 150 and context['Distance_Travelled_km'] < 100: pred /= 1000
    c100 = (pred / context['Distance_Travelled_km']) * 100 if context['Distance_Travelled_km'] > 0 else 0
    if c100 > 35 or c100 < 8: pred = (18 / 100) * context['Distance_Travelled_km']
    return max(0.0, pred)

# --- SIDEBAR DYNAMIQUE ---
with st.sidebar:
    st.title("🔋 Configuration")
    dep_city = st.text_input("Départ", "Rennes, France")
    arr_city = st.text_input("Arrivée", "Laval, France")
    
    st.divider()
    st.subheader("🚗 État du véhicule")
    
    soc_init = 30
    capa = 60.0
    show_manual_inputs = True

    if st.session_state.sc_token:
        try:
            v_res = smartcar.get_vehicles(st.session_state.sc_token)
            vehicle = smartcar.Vehicle(v_res.vehicles[0], st.session_state.sc_token)
            
            # Récupération signaux V3 (SOC + Capacité)
            signals = vehicle.get_signals(['ev.battery.level', 'ev.battery.capacity'])
            
            if signals.body['ev.battery.level'].value is not None:
                soc_init = int(signals.body['ev.battery.level'].value * 100)
                sc_info = vehicle.attributes()
                st.success(f"✅ **{sc_info.make} {sc_info.model}**")
                st.metric("Batterie détectée", f"{soc_init}%")
                
                # Si la capacité est dispo, on l'utilise
                if signals.body['ev.battery.capacity'].value:
                    capa = float(signals.body['ev.battery.capacity'].value)
                    st.metric("Capacité détectée", f"{capa} kWh")
                    show_manual_inputs = False
                else:
                    st.warning("⚠️ Capacité non détectée, veuillez choisir le modèle manuel.")
        except:
            st.warning("⚠️ Connexion limitée.")

    if show_manual_inputs:
        if st.session_state.sc_token is None:
            auth_url = sc_client.get_auth_url(['read_battery', 'read_vehicle_info'], {'mode': 'simulated'})
            st.link_button("🔗 Connecter mon véhicule", auth_url, width='stretch') # Syntax 2026
        
        ev_choice = st.selectbox("Modèle (Manuel)", options=list(EV_MODELS.keys()), index=2)
        capa = EV_MODELS[ev_choice]
        soc_init = st.slider("Batterie départ (%)", 0, 100, soc_init)

    if st.session_state.sc_token:
        if st.button("🔌 Déconnecter", width='stretch'):
            st.session_state.sc_token = None
            st.rerun()

    st.divider()
    soc_target = st.slider("Batterie arrivée visée (%)", 0, 100, 20)
    btn_calcul = st.button("🚀 Calculer l'itinéraire", width='stretch')

# --- LOGIQUE DE CALCUL SÉCURISÉE ---
if btn_calcul:
    with st.spinner("Analyse du trajet en cours..."):
        c1, c2 = nav.get_coords(dep_city), nav.get_coords(arr_city)
        if c1 and c2:
            route_base = nav.calculate_route(c1, c2)
            
            # SÉCURITÉ : Vérification que la route a été trouvée (Fix NoneType error)
            if route_base is None:
                st.error("❌ Impossible de trouver un itinéraire entre ces deux points. Vérifiez l'orthographe.")
            else:
                meteo = weather.get_local_weather(c1[0], c1[1])
                pts_km, pts_soc = [0], [soc_init]
                
                # Calcul IA Global
                dist_totale = route_base['summary']['lengthInMeters']/1000
                conso_ia = predict_energy_safe(model, {'Speed_kmh': route_base['vitesse_moy'], 'Distance_Travelled_km': dist_totale, 'Battery_State_%': soc_init, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                
                needs_stop = (soc_init - (conso_ia/capa*100)) < soc_target
                t_charge, borne = 0, None
                
                def add_curved_segment(s_soc, d_leg, v_moy, k_total, f_target=None):
                    c_globale = predict_energy_safe(model, {'Speed_kmh': v_moy, 'Distance_Travelled_km': d_leg, 'Battery_State_%': s_soc, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                    s_diff = (c_globale / capa * 100)
                    curr = s_soc
                    for k in range(1, 11):
                        poids = (1.2 if 3<=k<=8 else 0.8) / 10.0
                        curr -= (s_diff * poids)
                        if k == 10 and f_target is not None: curr = f_target
                        pts_km.append(k_total + (d_leg/10)*k); pts_soc.append(max(0, curr))
                    return curr

                if needs_stop:
                    mid_idx = len(route_base['geometry'])//2
                    mid_pt = route_base['geometry'][mid_idx]
                    borne = charger.find_best(mid_pt[0], mid_pt[1])
                    if borne:
                        l1, l2 = nav.calculate_route(c1, (borne['lat'], borne['lon'])), nav.calculate_route((borne['lat'], borne['lon']), c2)
                        if l1 and l2:
                            d1, d2 = l1['summary']['lengthInMeters']/1000, l2['summary']['lengthInMeters']/1000
                            soc_borne = add_curved_segment(soc_init, d1, l1['vitesse_moy'], 0)
                            
                            e_l2 = predict_energy_safe(model, {'Speed_kmh': l2['vitesse_moy'], 'Distance_Travelled_km': d2, 'Battery_State_%': 50, 'Humidity_%': meteo['humidity'], 'Battery_Temperature_C': 25})
                            s_rech = min(90.0, (e_l2/capa*100) + soc_target)
                            
                            t_charge = (((s_rech - soc_borne)*capa/100) / get_real_charging_power(borne['puissance'], (soc_borne+s_rech)/2)) * 60 * 1.15
                            pts_km.append(d1); pts_soc.append(s_rech)
                            add_curved_segment(s_rech, d2, l2['vitesse_moy'], d1, f_target=soc_target)
                            res_g, res_d, res_t = l1['geometry']+l2['geometry'], d1+d2, (l1['summary']['travelTimeInSeconds']+l2['summary']['travelTimeInSeconds'])//60
                        else: needs_stop = False
                    else: needs_stop = False
                
                if not needs_stop:
                    add_curved_segment(soc_init, dist_totale, route_base['vitesse_moy'], 0, f_target=soc_init-(conso_ia/capa*100))
                    res_g, res_d, res_t = route_base['geometry'], dist_totale, route_base['summary']['travelTimeInSeconds'] // 60

                st.session_state.res = {'c1': c1, 'c2': c2, 'geom': res_g, 'dist': res_d, 'temps': res_t, 'soc_final': pts_soc[-1], 'needs_stop': needs_stop, 'borne': borne, 'pts_km': pts_km, 'pts_soc': pts_soc, 't_charge': max(0, t_charge)}
                st.session_state.calcul_fait = True
        else:
            st.error("📍 Coordonnées introuvables. Précisez la ville ou le pays.")

# --- AFFICHAGE ---
if st.session_state.calcul_fait:
    res = st.session_state.res
    st.divider()
    cols = st.columns(4 if res['needs_stop'] else 3)
    cols[0].metric("📏 Distance", f"{res['dist']:.1f} km")
    cols[1].metric("⏱️ Temps route", f"{res['temps']//60}h {res['temps']%60}min")
    if res['needs_stop']:
        cols[2].metric("🔌 Charge", f"{res['t_charge']:.0f} min")
        cols[3].metric("🏁 Batterie", f"{res['soc_final']:.1f}%")
        st.success(f"📍 **Plan de recharge :** Arrêt à la borne **{res['borne']['nom'].strip()}** ({res['t_charge']:.0f} min).")
    else:
        cols[2].metric("🏁 Batterie Arrivée", f"{res['soc_final']:.1f}%")
        st.info("✅ Trajet direct sans recharge nécessaire.")

    m = folium.Map(location=[(res['c1'][0]+res['c2'][0])/2, (res['c1'][1]+res['c2'][1])/2], zoom_start=9)
    folium.PolyLine(res['geom'], color="#0045ff", weight=5).add_to(m)
    folium.Marker(res['c1'], icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(res['c2'], icon=folium.Icon(color='red', icon='flag')).add_to(m)
    if res['needs_stop']: folium.Marker([res['borne']['lat'], res['borne']['lon']], popup=f"<b>{res['borne']['nom'].strip()}</b>", icon=folium.Icon(color='orange', icon='bolt', prefix='fa')).add_to(m)
    st_folium(m, width="100%", height=500, key="map")

    st.subheader("📉 Profil de batterie")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=res['pts_km'], y=res['pts_soc'], mode='lines+markers', line=dict(color='#00d1b2', width=4), name="SOC %"))
    fig.add_hrect(y0=0, y1=20, fillcolor="red", opacity=0.15, annotation_text="ZONE CRITIQUE")
    fig.update_layout(xaxis_title="Distance (KM)", yaxis_title="Niveau Batterie (%)", template="plotly_dark")
    st.plotly_chart(fig, width='stretch')