# src/services.py
# Responsável por interagir com APIs externas, como o OpenRouteService (ORS).
# VERSÃO 3.0.4: Adicionada a função de autocomplete de endereço.

import requests
import pandas as pd
from typing import Optional, Tuple, Dict, Any, List

# URL base da API. Todas as chamadas para o ORS começarão com este endereço.
BASE_URL = "https://api.openrouteservice.org"

def optimize_route_online(df: pd.DataFrame, api_key: str, start_node: int = 0, end_node: int = 0) -> Optional[Dict[str, Any]]:
    """
    Otimiza uma rota usando a API do OpenRouteService.
    """
    try:
        coords = df[["Longitude", "Latitude"]].values.tolist()
        jobs = [
            {"id": idx, "location": [lon, lat]}
            for idx, (lon, lat) in enumerate(coords)
            if idx != start_node and idx != end_node
        ]
        vehicles = [{
            "id": 1, "profile": "driving-car",
            "start": coords[start_node], "end": coords[end_node]
        }]
        payload = {"jobs": jobs, "vehicles": vehicles}
        headers = {"Authorization": api_key, "Content-Type": "application/json"}

        opt_response = requests.post(f"{BASE_URL}/optimization", json=payload, headers=headers, timeout=30)
        opt_response.raise_for_status()
        opt_result = opt_response.json()

        steps = opt_result["routes"][0]["steps"]
        ordered_job_indices = [s["id"] for s in steps if s['type'] == 'job']
        final_route_indices = [start_node] + ordered_job_indices + [end_node]
        ordered_df = df.iloc[final_route_indices].reset_index(drop=True)

        dir_payload = {"coordinates": ordered_df[["Longitude", "Latitude"]].values.tolist()}
        dir_response = requests.post(f"{BASE_URL}/v2/directions/driving-car/geojson", json=dir_payload, headers=headers, timeout=30)
        dir_response.raise_for_status()
        
        dir_result = dir_response.json()
        summary = dir_result["features"][0]["properties"]["summary"]
        distance_km = summary["distance"] / 1000
        duration_min = summary["duration"] / 60

        return {
            "data": ordered_df, "geojson": dir_result,
            "distance": distance_km, "duration": duration_min
        }
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha de conexão com a API do ORS: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"ERRO: A resposta da API do ORS está em um formato inesperado: {e}")
        return None
    except Exception as e:
        print(f"ERRO: Ocorreu um erro inesperado em optimize_route_online: {e}")
        return None

def geocode_address(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    """
    Converte um endereço de texto em coordenadas geográficas (geocodificação).
    """
    try:
        params = {"text": address, "size": 1}
        headers = {"Authorization": api_key}
        response = requests.get(f"{BASE_URL}/geocode/search", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get("features"):
            coords = data["features"][0]["geometry"]["coordinates"]
            return coords[1], coords[0] 
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha de conexão na geocodificação: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"ERRO: A resposta da API de geocodificação está em um formato inesperado: {e}")
        return None

def autocomplete_address(text: str, api_key: str) -> List[str]:
    """
    Busca sugestões de endereço usando a API de autocomplete do OpenRouteService.
    """
    if not text or len(text) < 3:
        return []
    
    try:
        params = {
            "text": text,
            "focus.point.lon": -43.9333, # Foco em Belo Horizonte para resultados mais relevantes
            "focus.point.lat": -19.9167,
        }
        headers = {"Authorization": api_key}
        
        response = requests.get(f"{BASE_URL}/geocode/autocomplete", headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get("features"):
            return [feature["properties"]["label"] for feature in data["features"]]
        else:
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha de conexão no autocomplete: {e}")
        return []
    except (KeyError, IndexError) as e:
        print(f"ERRO: A resposta da API de autocomplete está em um formato inesperado: {e}")
        return []
