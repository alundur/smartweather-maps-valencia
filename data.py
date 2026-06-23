import json
import pandas as pd
from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326")

def load_fuentes(path="fuentes_agua.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        rows = []
        for fte in data["features"]:
            x = fte["geometry"]["x"]
            y = fte["geometry"]["y"]
            
            lat, lon = transformer.transform(x, y)
            
            rows.append({
                "lat": lat,
                "lon": lon,
                "calle": fte["attributes"].get("calle", "Desconocida")
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"Error cargando fuentes: {e}")
        return pd.DataFrame(columns=["lat", "lon", "calle"])