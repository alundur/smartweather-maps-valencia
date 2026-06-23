import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib

MODELO_PATH = "kmeans_microclima.joblib"
SCALER_PATH = "scaler_microclima.joblib"

def entrenar_clusters_vias_urbanas(G, fuentes_df, clima_actual):
    """
    Entrena un modelo No Supervisado (K-Means) en tiempo real utilizando 
    las características estructurales del grafo y las condiciones dinámicas de la API.
    """
    datos_vias = []
    
    #metheorological variables
    temp_api = clima_actual["temp_act"]
    humedad_api = clima_actual["humedad"]
    viento_api = clima_actual["viento"]
    lluvia_api = clima_actual["lluvia"]
    

    for u, v, k, data in G.edges(keys=True, data=True):
        longitud = float(data.get("length", 1.0))
        
        highway = data.get("highway", "")
        if isinstance(highway, list): highway = highway[0]
        es_peatonal = 1 if str(highway) in ["pedestrian", "living_street", "footway", "steps", "path"] else 0
        
        #water fountain
        node_u = G.nodes[u]
        lat_u, lon_u = node_u["y"], node_u["x"]
        
        if not fuentes_df.empty:
            distancias = np.sqrt((fuentes_df["lat"] - lat_u)**2 + (fuentes_df["lon"] - lon_u)**2)
            distancia_fuente_min = float(distancias.min())
        else:
            distancia_fuente_min = 1.0
            
        datos_vias.append({
            "u": u, "v": v, "k": k,
            "Feature_Longitud": longitud,
            "Feature_EsPeatonal": es_peatonal,
            "Feature_DistanciaFuente": distancia_fuente_min,
            "Feature_TempBase": temp_api,
            "Feature_Humedad": humedad_api,
            "Feature_Viento": viento_api,
            "Feature_Lluvia": lluvia_api
        })
        
    df_features = pd.DataFrame(datos_vias)
    

    columnas_ml = [
        "Feature_Longitud", "Feature_EsPeatonal", "Feature_DistanciaFuente", 
        "Feature_TempBase", "Feature_Humedad", "Feature_Viento", "Feature_Lluvia"
    ]
    

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_features[columnas_ml])
    
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    kmeans.fit(X_scaled)
    
    joblib.dump(kmeans, MODELO_PATH)
    joblib.dump(scaler, SCALER_PATH)
    
    df_features["Cluster_Asignado"] = kmeans.labels_
    
    resumen_clusters = df_features.groupby("Cluster_Asignado").agg({
        "Feature_EsPeatonal": "mean",
        "Feature_DistanciaFuente": "mean"
    })
    
    cluster_ordenado = resumen_clusters.sort_values(
        by=["Feature_EsPeatonal", "Feature_DistanciaFuente"], 
        ascending=[False, True]
    ).index.tolist()
    
    mapeo_costes = {
        cluster_ordenado[0]: 0.8,   #optimal (fresh) cluster
        cluster_ordenado[1]: 1.2,   #neutral
        cluster_ordenado[2]: 2.2    #bad (hot) cluster
    }
    
    df_features["Factor_Coste_ML"] = df_features["Cluster_Asignado"].map(mapeo_costes)
    
    return df_features