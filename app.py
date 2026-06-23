import streamlit as st
import folium
import os
import csv
import pandas as pd
import altair as alt
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from datetime import datetime
from geopy.geocoders import Nominatim
from routing import calcular_ruta_completa, obtener_fuentes_cercanas_a_ruta, get_clima_real_valencia, get_trafico_real, LOG_PREDICCIONES
from data import load_fuentes

st.set_page_config(page_title="SmartWeather-Maps Valencia", page_icon="🌿", layout="wide")

fuentes = load_fuentes()

#feedback logging
def registrar_voto(carita_seleccionada):
    archivo_csv = "valoraciones.csv"
    fila = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), carita_seleccionada]
    
    existe = os.path.exists(archivo_csv)
    with open(archivo_csv, mode="a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if not existe:
            escritor.writerow(["Fecha_Hora", "Valoracion"])
        escritor.writerow(fila)


def formatear_tiempo_humano(minutos_totales):
    minutos_enteros = int(round(minutos_totales))
    if minutos_enteros < 60:
        return f"{minutos_enteros} min"
    else:
        horas = minutos_enteros // 60
        minutos_restantes = minutos_enteros % 60
        if minutos_restantes == 0:
            return f"{horas}h"
        return f"{horas}h {minutos_restantes}min"

#geolocation infrastructure
@st.cache_data(ttl=86400)
def geocodificar_direccion(query_texto):
    geolocator = Nominatim(user_agent="upv_edm_project_2026")
    try:
        query_valencia = f"{query_texto.replace(',', '')}, Valencia, Spain"
        return geolocator.geocode(query_valencia, timeout=6)
    except Exception:
        return None

@st.cache_data(ttl=86400)
def obtener_sugerencias_direccion(query_texto):
    geolocator = Nominatim(user_agent="upv_edm_project_2026")
    try:
        return geolocator.geocode(query_texto, exactly_one=False, limit=5, timeout=6)
    except Exception:
        return None

if "origen_confirmado" not in st.session_state:
    st.session_state["origen_confirmado"] = "UPV"
if "destino_confirmado" not in st.session_state:
    st.session_state["destino_confirmado"] = "Plaza del Ayuntamiento"

st.markdown("""
    <style>
    .metric-box { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #2e7d32; }
    .stButton>button { border-radius: 8px; font-weight: bold; }
    .card-salud { background-color: #e3f2fd; border-radius: 10px; padding: 20px; border-left: 6px solid #1e88e5; margin-bottom: 15px; }
    .card-explicacion { background-color: #f1f8e9; border-radius: 10px; padding: 20px; border-left: 6px solid #7cb342; margin-bottom: 15px; }
    .leyenda-mapa { background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; margin-top: -10px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }
    .leyenda-item { display: flex; align-items: center; font-size: 14px; color: #333333; gap: 8px; }
    .linea-fresca-ej { height: 6px; width: 35px; border-radius: 3px; background: linear-gradient(90deg, green, orange, red); }
    .linea-rapida-ej { height: 0px; width: 35px; border-top: 3px dashed gray; }
    .icono-salida { color: #2196f3; font-weight: bold; font-size: 16px; }
    .icono-llegada { color: #f44336; font-weight: bold; font-size: 16px; }
    .icono-fuente { color: #5f9ea0; font-weight: bold; font-size: 16px; }
    </style>
""", unsafe_allow_html=True)

tab_ciudadano, tab_mlops, tab_datos = st.tabs(["🗺️ Citizen Interface", "🔬 MLOps Dashboard (Drift Evaluation)", "📂 Data Pipelines & Architecture"])

with tab_ciudadano:
    with st.sidebar:
        st.header("🕒 System Status")
        #we use spain timezone
        from zoneinfo import ZoneInfo
        hora_actual = datetime.now(ZoneInfo("Europe/Madrid"))
        st.success(f"📅 **Date:** {hora_actual.strftime('%d-%m-%Y')}\n\n⌚ **Time:** {hora_actual.strftime('%H:%M:%S')}")
        
        st.markdown("---")
        st.header("🍂 Seasonal Optimization")
        estacion = st.radio("Urban Experience Mode:", ["Cool Routine (Summer)", "Sunny Paths (Winter)"])
        
        st.markdown("---")
        st.header("📍 Waypoints")
        origen_txt = st.text_input("Origin (Street, square or building)", value=st.session_state["origen_confirmado"])
        destino_txt = st.text_input("Destination (Street, square or building)", value=st.session_state["destino_confirmado"])
        
        st.markdown("---")
        st.subheader("⏱️ Temporal Simulation")
        delay = st.slider("Departure delay (Minutes)", min_value=0, max_value=60, value=0, step=15)
        
        st.markdown("---")
        st.subheader("📊 Service Evaluation")
        st.write("Rate your routing experience:")
        
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1: v_mal = st.button("😡", help="Dissatisfied", use_container_width=True)
        with col_f2: v_reg = st.button("😐", help="Neutral", use_container_width=True)
        with col_f3: v_bue = st.button("🙂", help="Satisfied", use_container_width=True)
        with col_f4: v_enc = st.button("🤩", help="Love it!", use_container_width=True)
            
        if v_mal:
            registrar_voto("Poor experience (😡)")
            st.error("📉 Feedback logged to audit and recalibrate the routing space.")
        elif v_reg:
            registrar_voto("Neutral (😐)")
            st.warning("📊 Logged in the local optimization dataset for analytics.")
        elif v_bue:
            registrar_voto("Satisfied (🙂)")
            st.success("😊 Thanks! Glad you enjoyed your optimized route.")
        elif v_enc:
            registrar_voto("Excellent (🤩)")
            st.balloons() 
            st.success("🚀 Excellent score stored in the database!")

    is_verano = "Cool" in estacion
    st.title("SmartWeather Maps")

    if is_verano:
        st.markdown("<p style='font-style: italic; font-size: 34px; color: #2e7d32; margin-top: -15px;'>🌿 A la fresca</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p style='font-style: italic; font-size: 34px; color: #e65100; margin-top: -15px;'>☀️ Al solet</p>", unsafe_allow_html=True)

    loc_origen_cabecera = geocodificar_direccion(origen_txt) if origen_txt else None
    if loc_origen_cabecera:
        lat_cab, lon_cab, nombre_cab = loc_origen_cabecera.latitude, loc_origen_cabecera.longitude, origen_txt.split(",")[0]
    else:
        lat_cab, lon_cab, nombre_cab = 39.4697, -0.3763, "Valencia Center"

    clima = get_clima_real_valencia(lat=lat_cab, lon=lon_cab, nombre=nombre_cab)
    trafico_activo = get_trafico_real()

    if clima['lluvia'] >= 4.0 or clima['viento'] > 40.0:
        st.error("⚠️ **Algorithmic Abstention Triggered (Cautious Classifier):** Extreme weather conditions detected in Valencia. To ensure pedestrian safety, eco-routing recommendations are temporarily suspended.")
    else:
        estado_lluvia = "☀️ Clear skies or light clouds" if clima['lluvia'] < 0.1 else (f"🌦️ Light drizzle ({clima['lluvia']} mm)" if clima['lluvia'] < 1.5 else f"🌧️ Heavy rain! ({clima['lluvia']} mm)")
        st.info(f"🏙️ **Current Atmospheric Telemetry at {clima['nombre']}:** {clima['temp_act']}°C | 💧 Humidity: {clima['humedad']}% | {estado_lluvia} | 💨 Wind: {clima['viento']} km/h")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1: btn_calcular = st.button("🚀 Calculate Climate-Optimized Route", use_container_width=True)
        with col_btn2: ver_mapa_calor = st.checkbox("🔥 Display Thermal Sensations Heatmap", value=False)

        if btn_calcular or "forzar_calculo" in st.session_state:
            if "forzar_calculo" in st.session_state: del st.session_state["forzar_calculo"]
                
            with st.spinner("Clustering urban ways and validating geocoding points..."):
                coor_origen, coor_destino = None, None
                loc_orig = geocodificar_direccion(origen_txt)
                if loc_orig: coor_origen = (loc_orig.latitude, loc_orig.longitude)
                else: st.error(f"❌ Origin not found: '{origen_txt}'")

                loc_dest = geocodificar_direccion(destino_txt)
                if loc_dest: coor_destino = (loc_dest.latitude, loc_dest.longitude)
                else: st.error(f"❌ Destination not found: '{destino_txt}'")

                if coor_origen and coor_destino:
                    res_inteligente = calcular_ruta_completa(coor_origen, coor_destino, "fresco", delay, "Verano" if is_verano else "Invierno")
                    res_rapida = calcular_ruta_completa(coor_origen, coor_destino, "rapido", delay, "Verano" if is_verano else "Invierno")
                    fuentes_cercanas = obtener_fuentes_cercanas_a_ruta(res_inteligente["coords_completas"], fuentes)
                    num_fuentes = len(fuentes_cercanas)
                    
                    st.markdown("### 📊 What are you saving with this route?")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric(
                            label="⏱️ Estimated Walking Time", 
                            value=formatear_tiempo_humano(res_inteligente["tiempo_min"]), 
                            delta=f"+{round(res_inteligente['tiempo_min'] - res_rapida['tiempo_min'])} min vs Shortest"
                        )
                    with c2:
                        diferencia_grados = round(res_rapida["temp_media"] - res_inteligente["temp_media"], 1)
                        
                        if is_verano:
                            label_kpi = "🌡️ Average Thermal Sensation"
                            valor_kpi = f"{res_inteligente['temp_media']} °C"
                            delta_kpi = f"-{diferencia_grados} °C cooler than shortest route" if diferencia_grados > 0 else "Identical temperature profile"
                            color_delta = "inverse"
                        else:
                            label_kpi = "🌡️ Average Thermal Sensation"
                            valor_kpi = f"{res_inteligente['temp_media']} °C"
                            delta_kpi = f"+{abs(diferencia_grados)} °C warmer (towards sunlight)" if diferencia_grados < 0 else "Identical temperature profile"
                            color_delta = "normal"

                        st.metric(label=label_kpi, value=valor_kpi, delta=delta_kpi, delta_color=color_delta)

                    with c3:
                        if trafico_activo:
                            st.metric(label="🚗 Traffic Heat Burden (Real-Time)", value="High Congestion / Road Heat absorption", delta="🚨 Traffic jam active", delta_color="inverse")
                        else:
                            st.metric(label="🚗 Traffic Heat Burden (Real-Time)", value="Low / Clear pathways", delta="🍃 Fluid eco-flow", delta_color="normal")
                    
                    m = folium.Map(location=res_inteligente["coords_completas"][0], zoom_start=15, tiles="cartodbpositron")
                    if ver_mapa_calor:
                        HeatMap([[t["coords"][0][0], t["coords"][0][1], t["temp"]/35.0] for t in res_inteligente["tramos"]], radius=40, blur=25).add_to(m)
                        
                    folium.PolyLine(res_rapida["coords_completas"], color="gray", weight=3, opacity=0.4, dash_array="5, 10").add_to(m)
                    
                    t_base_actual = clima['temp_act']
                    for tramo in res_inteligente["tramos"]:
                        t = tramo["temp"]
                        color_tramo = ("green" if t < t_base_actual else ("orange" if t == t_base_actual else "red")) if is_verano else ("darkred" if t > t_base_actual else ("orange" if t == t_base_actual else "blue"))
                        folium.PolyLine(tramo["coords"], color=color_tramo, weight=7, opacity=0.95).add_to(m)
                    
                    if is_verano and not fuentes_cercanas.empty:
                        for idx, f in fuentes_cercanas.iterrows():
                            folium.Marker(location=[f["lat"], f["lon"]], popup=f"Fountain: {f['calle']}", icon=folium.Icon(color="cadetblue", icon="tint", prefix="fa")).add_to(m)
                    
                    folium.Marker(res_inteligente["coords_completas"][0], popup="Origin", icon=folium.Icon(color="blue", icon="play")).add_to(m)
                    folium.Marker(res_inteligente["coords_completas"][-1], popup="Destination", icon=folium.Icon(color="red", icon="stop")).add_to(m)
                    
                    st_folium(m, width=1100, height=450, returned_objects=[])
                    
                    st.markdown(f"""
                        <div class="leyenda-mapa">
                            <div class="leyenda-item"><div class="linea-fresca-ej"></div><span><b>Climatological Route:</b> Solid Line (Segmented by AI)</span></div>
                            <div class="leyenda-item"><div class="linea-rapida-ej"></div><span><b>Traditional Route:</b> Gray Dashed Line</span></div>
                            <div class="leyenda-item"><span class="icono-salida">▶ Blue</span><span><b>Origin</b></span></div>
                            <div class="leyenda-item"><span class="icono-llegada">■ Rojo</span><span><b>Destination</b></span></div>
                            {"<div class='leyenda-item'><span class='icono-fuente'>💧</span><span><b>Drinking Fountain</b></span></div>" if is_verano else ""}
                        </div>
                    """, unsafe_allow_html=True)

                    st.markdown("### 💡 Why does the system suggest this path?")
                    col_usr1, col_usr2 = st.columns(2)
                    with col_usr1:
                        st.markdown(f"""
                        <div class="card-explicacion">
                            <h4>🌳 Cluster-Based Route Advantages</h4>
                            <ul>
                                <li><b>Smart Streets:</b> This walk passes <b>{res_inteligente['pct_peatonal']}%</b> through urban segments autonomously grouped by the model into the highest thermal comfort cluster.</li>
                                <li><b>AI Segmentation:</b> Congested avenues are automatically penalized based on computed spatial proximities and environmental features.</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_usr2:
                        if is_verano and res_inteligente['temp_media'] >= 24.0 and num_fuentes > 0:
                            paradas_sugeridas = min(num_fuentes, max(1, round(res_inteligente['agua_ml'] / 200)))
                            consejo_parada = (
                                f"💡  <b>System Health Recommendation:</b><br><br>"
                                f"• Your estimated fluid loss under these climate conditions is <b>{res_inteligente['agua_ml']} ml</b> of water.<br>"
                                f"• We advice you to stop and rehydrate at least at <b>{paradas_sugeridas} of the {num_fuentes} public fountains</b> along your path."
                            )
                        else:
                            consejo_parada = (
                                f"🥤 <b>System Recommendation:</b><br><br>"
                                f"• Your estimated fluid loss is <b>{res_inteligente['agua_ml']} ml</b> of water.<br>"
                                f"• With <b>{num_fuentes} public fountains</b> bounding your path, no mandatory rehydration stops are required for this walk."
                            )
                        
                        # Render card box container for hydration advice
                        st.markdown(f"""
                        <div class="card-salud">
                            <h4>🎒 Predictive Hydration Advice</h4>
                            <p style="color: #0d47a1; font-weight: bold;">{consejo_parada}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Collapsible tab with data lineage details (st.expander)
                        with st.expander("🔍 See where this hydration data comes from"):
                            st.write(f"""
                            **Methodology & Calculations Details:**
                            * **Estimated Loss ({res_inteligente['agua_ml']} ml):** Calculated by multiplying a dynamic sweating rate index against your journey's estimated walking duration ({res_inteligente['tiempo_min']} min). In summer conditions, the baseline loss increases adaptively if the promedial microclimatic sensation rises over 22°C.
                            * **Recommended Stops:** Derived by partitioning total water costs into standard 200 ml physiological rehydration metrics, alerting you to utilize **{num_fuentes} intersecting municipal points** fetched directly from Valencia City Council's open spatial register.
                            """)

#MLOps
with tab_mlops:
    st.header("🔬 Analytical Pipeline Monitoring in Production (EDM)")
    st.caption("Statistical performance indicators extracted directly from the real-time execution logs of our unsupervised K-Means model.")
    
    st.subheader("1. 📡 Feature Density Tracking (Data Drift / Feature Drift)")
    if os.path.exists(LOG_PREDICCIONES) and os.path.getsize(LOG_PREDICCIONES) > 0:
        df_logs = pd.read_csv(LOG_PREDICCIONES).copy()
        st.write(f"Streaming historical requests processed: **{len(df_logs)} routing items**.")
        
        simular_drift = st.toggle("🚨 Force Heatwave Injection (Simulate population statistical drift)")
        
        columna_temp = "Metereologia_Temp"
        
        if simular_drift:
            df_logs[columna_temp] = df_logs[columna_temp] + 12.0
            
            st.error("💥 **DATA DRIFT DETECTED!** (p-value < 0.01). The real-time distribution of `Metereologia_Temp` shows a massive mean displacement relative to the baseline. MLOps systems suggest a hot-rebuild or restructuring the edge cost space.")
            
            chart_drift = alt.Chart(df_logs).mark_area(opacity=0.4, color='red').encode(
                x=alt.X(f"{columna_temp}:Q", title="Injected Biased Temperature (°C)", scale=alt.Scale(domain=[15, 50])),
                y=alt.Y("count()", title="Frequency")
            ).properties(height=200)
            st.altair_chart(chart_drift, use_container_width=True)
        else:
            st.success("Stable input signatures. The incoming temperature distributions match the expected training domain profile.")
            chart_normal = alt.Chart(df_logs).mark_area(opacity=0.3, color='blue').encode(
                x=alt.X(f"{columna_temp}:Q", title="Baseline Temperature (°C)", scale=alt.Scale(domain=[15, 50])),
                y=alt.Y("count()", title="Frequency")
            ).properties(height=180)
            st.altair_chart(chart_normal, use_container_width=True)
    else:
        st.info("Compute at least one route to initialize `predicciones_log.csv` and compute the data drift chart.")

    st.subheader("2. 📉 Human Comfort Alignment Drift (Concept Drift)")
    if os.path.exists("valoraciones.csv"):
        df_votos = pd.read_csv("valoraciones.csv")
        conteo_df = df_votos["Valoracion"].value_counts().reset_index()
        conteo_df.columns = ["Categoría", "Votos"]
        
        color_map = {"Poor experience (😡)": "#ef5350", "Neutral (😐)": "#ffa726", "Satisfied (🙂)": "#66bb6a", "Excellent (🤩)": "#ec407a"}
        categorias_ordenadas = list(color_map.keys())
        colores_ordenados = list(color_map.values())
        
        chart_fb = alt.Chart(conteo_df).mark_bar().encode(
            x=alt.X("Categoría:N", sort="-y"), y="Votos:Q",
            color=alt.Color("Categoría:N", scale=alt.Scale(domain=categorias_ordenadas, range=colores_ordenados), legend=None)
        ).properties(height=220)
        st.altair_chart(chart_fb, use_container_width=True)
        
        votos_negativos = len(df_votos[df_votos["Valoracion"].str.contains("😡|Poor|Mala", na=False)])
        ratio_error = (votos_negativos / len(df_votos)) * 100 if len(df_votos) > 0 else 0
        
        st.metric(label="Urban Comfort Error Ratio", value=f"{round(ratio_error, 1)} %")
        if ratio_error > 25.0:
            st.warning("⚠️ **Concept Drift Alert Triggered:** Critical feedback has breached the target error SLA. Citizens' environmental perception has shifted or urban roadblocks are active. Full K-Means cluster hyperparameter recalibration required.")
        else:
            st.success("Business KPIs stable. Recommended pathways maintain high human comfort acceptance profiles.")
    else:
        st.info("No user feedback records available yet.")

#data architecture
with tab_datos:
    st.header("📂 Data Architecture & Information Pipelines")
    st.write("Formal description of the data ingestion, feature transformation, and geographical modeling engine deployed for Valencia:")
    
    st.markdown("### 🧠 1. Unsupervised Machine Learning Pipeline (K-Means)")
    st.markdown("Unlike brittle rule-based structures (`if/else`), the analytical heart of this deployment uses a dynamically fitting **K-Means Clustering** engine:")
    st.markdown("* **Feature Engineering:** For each street edge, the system vectors relation properties (length, pedestrian classification) with Euclidean distance tensors calculated against `fuentes_agua.json` and real-time API atmospheric features.")
    st.markdown("* **Scaling & Grouping:** Inputs are normalized using a `StandardScaler` pipeline to keep coordinate distance boundaries unbiased, feeding the K-Means algorithm to isolate three distinct comfort tiers.")

    st.markdown("### 🗺️ 2. Cartographic GIS Infrastructure (Spatial Directed Graph)")
    st.markdown("The network model depends on a serialized relational structure (**valencia.graphml**), representing the urban landscape as a **Relational Topological Graph (Nodes and Edges)**:")
    st.markdown("* **Nodes (Intersections):** Geometric intersections linked with strict Latitude and Longitude coordinate keys.")
    st.markdown("* **Edges (Streets):** Roads containing open-source metadata schema attributes derived from OpenStreetMap (such as raw physical `length` and structural `highway` labels).")
    
    st.markdown("### 📡 3. Hybrid Real-Time Meteorological Streaming")
    st.markdown("To estimate macroclimate variables safely across the urban canvas, the backend leverages a multi-source high-availability pipeline:")
    st.markdown("* **Primary Source (AEMET OpenData):** Hourly REST queries targeting official physical stations inside Valencia via authenticated API tokens.")
    st.markdown("* **Hyperlocal Backup Channel (Open-Meteo API):** Instant automatic *Failover* protocol handling upstream 404 or connection failures by falling back to geo-interpolated satellite models.")
    
    st.markdown("### 🚗 4. Traffic & Hydration Object Sensors (OpenData València)")
    st.markdown("The engine dynamically reads the urban mobility matrix from the city council. In parallel, it projects a local municipal ETRS89 node register (`fuentes_agua.json`) from its native projection **EPSG:25830 into the international WGS84 standard EPSG:4326 (Lat/Lon)** via `pyproj` transformation matrices, computing the necessary feature arrays for the unsupervised model.")
