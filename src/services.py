# src/services.py
# Responsável por interagir com APIs externas, como o OpenRouteService (ORS).
# VERSÃO 3.0.3: Código limpo, adicionados comentários detalhados e docstrings.

import requests
import pandas as pd
from typing import Optional, Tuple, Dict, Any

# URL base da API. Todas as chamadas para o ORS começarão com este endereço.
BASE_URL = "https://api.openrouteservice.org"

def optimize_route_online(df: pd.DataFrame, api_key: str, start_node: int = 0, end_node: int = 0) -> Optional[Dict[str, Any]]:
    """
    Otimiza uma rota usando a API do OpenRouteService.

    Esta função realiza duas chamadas de API:
    1. /optimization: Para encontrar a ordem ótima dos pontos intermediários.
    2. /directions: Para obter a geometria da rota real (ruas) com base na 
       ordem otimizada.

    Args:
        df (pd.DataFrame): DataFrame com os pontos da rota.
        api_key (str): Chave da API para o OpenRouteService.
        start_node (int): Índice do ponto de partida.
        end_node (int): Índice do ponto de chegada.

    Returns:
        Um dicionário contendo o DataFrame ordenado, o GeoJSON da rota,
        a distância e a duração, ou None em caso de falha.
    """
    try:
        coords = df[["Longitude", "Latitude"]].values.tolist()

        # --- 1. Chamada para /optimization ---
        # Prepara a lista de "jobs" (pontos a serem visitados)
        jobs = [
            {"id": idx, "location": [lon, lat]}
            for idx, (lon, lat) in enumerate(coords)
            if idx != start_node and idx != end_node
        ]

        # Prepara o "vehicle" (veículo) com os pontos de início e fim
        vehicles = [{
            "id": 1,
            "profile": "driving-car",
            "start": coords[start_node],
            "end": coords[end_node]
        }]

        payload = {"jobs": jobs, "vehicles": vehicles}
        headers = {"Authorization": api_key, "Content-Type": "application/json"}

        opt_response = requests.post(f"{BASE_URL}/optimization", json=payload, headers=headers, timeout=30)
        opt_response.raise_for_status() # Lança um erro se a resposta for mal-sucedida (ex: 401, 500)
        
        opt_result = opt_response.json()

        # Extrai a ordem dos pontos da resposta da API
        steps = opt_result["routes"][0]["steps"]
        ordered_job_indices = [s["id"] for s in steps if s['type'] == 'job']
        
        # Reconstrói a lista final de índices, incluindo início e fim
        final_route_indices = [start_node] + ordered_job_indices + [end_node]

        ordered_df = df.iloc[final_route_indices].reset_index(drop=True)

        # --- 2. Chamada para /directions ---
        dir_payload = {"coordinates": ordered_df[["Longitude", "Latitude"]].values.tolist()}
        dir_response = requests.post(f"{BASE_URL}/v2/directions/driving-car/geojson", json=dir_payload, headers=headers, timeout=30)
        dir_response.raise_for_status()
        
        dir_result = dir_response.json()
        summary = dir_result["features"][0]["properties"]["summary"]
        distance_km = summary["distance"] / 1000
        duration_min = summary["duration"] / 60

        return {
            "data": ordered_df,
            "geojson": dir_result,
            "distance": distance_km,
            "duration": duration_min
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
    Converte um endereço de texto em coordenadas geográficas (geocodificação)
    usando a API do OpenRouteService.

    Args:
        address (str): O endereço a ser geocodificado.
        api_key (str): Chave da API para o OpenRouteService.

    Returns:
        Uma tupla com (Latitude, Longitude), ou None se não encontrado.
    """
    try:
        params = {"text": address, "size": 1}
        headers = {"Authorization": api_key}
        
        response = requests.get(f"{BASE_URL}/geocode/search", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get("features"):
            coords = data["features"][0]["geometry"]["coordinates"]
            # A API retorna [longitude, latitude], então invertemos para o nosso padrão
            return coords[1], coords[0] 
        else:
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha de conexão na geocodificação: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"ERRO: A resposta da API de geocodificação está em um formato inesperado: {e}")
        return None

