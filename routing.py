import os
import osmnx as ox
import networkx as nx
import math
import requests
import time
import csv
from datetime import datetime, timedelta
from shapely.geometry import Point, LineString
import pandas as pd
import streamlit as st
import logging
from data import load_fuentes
from modelo_ml import entrenar_clusters_vias_urbanas

GRAFO_PATH = "valencia.graphml"
LOG_PREDICCIONES = "predicciones_log.csv"

logging.basicConfig(level=logging.INFO)

@st.cache_resource
def cargar_grafo_valencia():
    if not os.path.exists(GRAFO_PATH):
        with st.spinner("🌐 Downloading Valencia street network from OpenStreetMap for the first time..."):
            G_osm = ox.graph_from_place("Valencia, Spain", network_type="walk")
            ox.save_graphml(G_osm, filepath=GRAFO_PATH)
    return ox.load_graphml(GRAFO_PATH)

G = cargar_grafo_valencia()
fuentes = load_fuentes()

#hybrid meteorological engine. It gets live data from AEMET API and uses Open-Meteo as a backup if AEMET fails
@st.cache_data(ttl=600)
def get_clima_todas_estaciones(lat_ref=39.4806, lon_ref=-0.3664, nombre_ref="Valencia"):
    api_key = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbmFsdW5hZHUwNUBnbWFpbC5jb20iLCJqdGkiOiI5ZTIxMTQ1YS1iOWM0LTQyODYtODhlYS0wMjIxNjhmZjgxNGQiLCJpc3MiOiJBRU1FVCIsImlhdCI6MTc4MTk1MjkyOCwidXNlcklkIjoiOWUyMTE0NWEtYjljNC00Mjg2LTg4ZWEtMDIyMTY4ZmY4MTRkIiwicm9sZSI6IiJ9.9aJ3nGXk_7C-MN9jMTAMfg79pG_0yWmIyK5cFVu5dkY"
    headers = {'cache-control': "no-cache", 'api_key': api_key}
    clima_map = {}
    
    try:
        url_viveros = "https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/8416Y"
        r1 = requests.get(url_viveros, headers=headers, timeout=3).json()
        if r1.get("estado") == 200:
            datos_url = r1.get("datos")
            observaciones = requests.get(datos_url, timeout=3).json()
            if isinstance(observaciones, list) and len(observaciones) > 0:
                obs_actual = next((obs for obs in reversed(observaciones) if "ta" in obs and obs.get("ta") is not None), None)
                if obs_actual:
                    clima_map["8416Y"] = {
                        "lat": 39.4806, "lon": -0.3664,
                        "nombre": "VALENCIA (VIVEROS) - AEMET ONLINE",
                        "temp_act": float(obs_actual.get("ta")),
                        "viento": round(float(obs_actual.get("vv", 3.3)) * 3.6, 1) if "vv" in obs_actual else 12.0,
                        "humedad": float(obs_actual.get("hr", 65.0)) if "hr" in obs_actual else 65.0,
                        "lluvia": float(obs_actual.get("prec", 0.0)) if "prec" in obs_actual else 0.0,
                        "fallback": False
                    }
                    return clima_map
    except Exception:
        pass

    try:
        url_open_meteo = f"https://api.open-meteo.com/v1/forecast?latitude={lat_ref}&longitude={lon_ref}&current=temperature_2m,relative_humidity_2m,rain,wind_speed_10m"
        response = requests.get(url_open_meteo, timeout=4).json()
        if "current" in response:
            current = response["current"]
            clima_map["8416Y"] = {
                "lat": lat_ref, "lon": lon_ref,
                "nombre": f"{nombre_ref} - TIEMPO REAL",
                "temp_act": float(current.get("temperature_2m", 24.5)),
                "viento": float(current.get("wind_speed_10m", 12.0)),
                "humedad": float(current.get("relative_humidity_2m", 65.0)),
                "lluvia": float(current.get("rain", 0.0)),
                "fallback": False
            }
            return clima_map
    except Exception as e:
        logging.error(f"Error en pasarela meteorológica de respaldo: {e}")
        
    return {"8416Y": {"lat": 39.4806, "lon": -0.3664, "nombre": "VALENCIA (VIVEROS) - LOCAL CACHE", "temp_act": 24.5, "viento": 12.0, "humedad": 65.0, "lluvia": 0.0, "fallback": True}}

def obtener_estacion_mas_cercana(lat_calle, lon_calle):
    clima_todas = get_clima_todas_estaciones()
    return list(clima_todas.keys())[0]

def get_clima_real_valencia(lat=39.4806, lon=-0.3664, nombre="Valencia"):
    climas = get_clima_todas_estaciones(lat_ref=lat, lon_ref=lon, nombre_ref=nombre)
    return climas.get("8416Y", list(climas.values())[0])

def get_trafico_real():
    """Simulates a real-time traffic check based on rush hour schedules in Valencia."""
    hora_actual = datetime.now().hour
    if hora_actual in [8, 9, 14, 19, 20]:
        return True
    return False

def nearest(lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


#core routing function. It calculates the best route by modifying street weights using our K-Means clusters
def calcular_ruta_completa(origen, destino, modo="fresco", minutos_delay=0, estacion="Verano"):
    t_inicio = time.time()
    orig = nearest(*origen)
    dest = nearest(*destino)
    
    clima_actual = get_clima_real_valencia(*origen)
    
    df_confort_ml = entrenar_clusters_vias_urbanas(G, fuentes, clima_actual)
    
    dict_costes_ml = df_confort_ml.set_index(["u", "v", "k"])["Factor_Coste_ML"].to_dict()
    dict_clusters_ml = df_confort_ml.set_index(["u", "v", "k"])["Cluster_Asignado"].to_dict()
    
    for u, v, k, data in G.edges(keys=True, data=True):
        base_length = float(data.get("length", 1.0))
        
        if modo == "rapido": 
            data["weight"] = base_length
        else:
            factor_ml = dict_costes_ml.get((str(u), str(v), k), dict_costes_ml.get((int(u) if str(u).isdigit() else u, int(v) if str(v).isdigit() else v, k), 1.2))
            
            if clima_actual["lluvia"] >= 1.5:
                highway = data.get("highway", "")
                if isinstance(highway, list): highway = highway[0]
                if str(highway) in ["footway", "pedestrian"]:
                    factor_ml *= 0.75
                    
            data["weight"] = max(0.1, base_length * factor_ml)
            
    route = nx.shortest_path(G, orig, dest, weight="weight")
    
    tramos_coords = []
    distancia_total = 0.0
    calles_peatonales = 0
    todas_las_temps = [] 
    
    for i in range(len(route) - 1):
        u, v = route[i], route[i+1]
        data = G.get_edge_data(u, v)[0]
        c1 = (G.nodes[u]["y"], G.nodes[u]["x"])
        c2 = (G.nodes[v]["y"], G.nodes[v]["x"])
        
        distancia_total += float(data.get("length", 0))
        
        cluster_id = dict_clusters_ml.get((str(u), str(v), 0), dict_clusters_ml.get((int(u) if str(u).isdigit() else u, int(v) if str(v).isdigit() else v, 0), 1))
        
        temp_orientativa = clima_actual["temp_act"] + (1.8 if cluster_id == 2 else -1.4 if cluster_id == 0 else 0.0)
        todas_las_temps.append(temp_orientativa)
        
        tramos_coords.append({"coords": [c1, c2], "temp": round(temp_orientativa, 1)})
        
        highway = data.get("highway", "")
        if isinstance(highway, list): highway = highway[0]
        if str(highway) in ["pedestrian", "living_street", "footway"]:
            calles_peatonales += float(data.get("length", 0))
            
    tiempo_minutos = round((distancia_total / 1.25) / 60, 1)
    pct_peatonal = round((calles_peatonales / distancia_total) * 100, 1) if distancia_total > 0 else 0
    agua_ml = round((300 if estacion == "Verano" else 150) * (tiempo_minutos / 60))
    
    temp_media_ruta = sum(todas_las_temps) / len(todas_las_temps) if todas_las_temps else clima_actual["temp_act"]
    
    #automated logging system for performance and MLOps tracking
    t_total_ms = round((time.time() - t_inicio) * 1000, 2)
    existe_log = os.path.exists(LOG_PREDICCIONES)
    with open(LOG_PREDICCIONES, mode="a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if not existe_log or os.path.getsize(LOG_PREDICCIONES) == 0:
            escritor.writerow(["Fecha_Hora", "Metereologia_Temp", "Metereologia_Lluvia", "Distancia_Ruta_m", "Tiempo_Inferencia_ms"])
        escritor.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), clima_actual["temp_act"], clima_actual["lluvia"], distancia_total, t_total_ms])

    return {
        "tramos": tramos_coords,
        "coords_completas": [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route],
        "distancia_m": round(distancia_total),
        "tiempo_min": tiempo_minutos,
        "temp_media": round(temp_media_ruta, 1),
        "pct_peatonal": pct_peatonal,
        "agua_ml": agua_ml
    }


#geofilter function to find public water fountains near the selected route
def obtener_fuentes_cercanas_a_ruta(ruta_coords, fuentes_df, distancia_umbral=0.0015):
    if fuentes_df.empty or not ruta_coords: 
        return pd.DataFrame()
        
    lats, lons = [c[0] for c in ruta_coords], [c[1] for c in ruta_coords]
    fuentes_caja = fuentes_df[
        (fuentes_df["lat"].between(min(lats) - distancia_umbral, max(lats)+distancia_umbral)) & 
        (fuentes_df["lon"].between(min(lons) - distancia_umbral, max(lons)+distancia_umbral))
    ].copy()
    
    if fuentes_caja.empty: 
        return pd.DataFrame()
        
    ruta_linea = LineString([(lon, lat) for lat, lon in ruta_coords])
    mascara_cercania = []
    
    for idx, row in fuentes_caja.iterrows():
        punto_fuente = Point(row["lon"], row["lat"])
        mascara_cercania.append(ruta_linea.distance(punto_fuente) <= distancia_umbral)
        
    return fuentes_caja[mascara_cercania]