# src/utils.py
# Módulo de utilitários com funções compartilhadas pelo projeto.
# VERSÃO 3.0.1: Criação do módulo e centralização da função _haversine_distance.

import math

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Calcula a distância em metros entre dois pontos geográficos usando a
    fórmula de Haversine.

    A função retorna um número inteiro, pois é o formato esperado por algumas
    bibliotecas de otimização como o OR-Tools.

    Args:
        lat1 (float): Latitude do ponto 1.
        lon1 (float): Longitude do ponto 1.
        lat2 (float): Latitude do ponto 2.
        lon2 (float): Longitude do ponto 2.

    Returns:
        int: A distância calculada em metros, arredondada para o inteiro mais próximo.
    """
    R = 6371000  # Raio da Terra em metros
    
    # Converte coordenadas de graus para radianos
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Diferença entre as latitudes e longitudes
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    # Aplicação da fórmula de Haversine
    a = math.sin(delta_lat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return int(distance)


import streamlit as st
from typing import Dict

def get_api_keys() -> Dict[str, str]:
    """
    Busca todas as chaves de API necessárias dos segredos do Streamlit
    e as retorna em um dicionário.
    """
    keys = {
        "GEMINI_API_KEY": st.secrets.get("GEMINI_API_KEY", ""),
        "ORS_API_KEY": st.secrets.get("ORS_API_KEY", ""),
        "AI_PASSWORD": st.secrets.get("AI_PASSWORD", "")
    }
    return keys


import pandas as pd
from typing import List

def find_close_points(df: pd.DataFrame, threshold_meters: int = 100) -> List[Dict]:
    """
    Encontra pares de pontos em um DataFrame que estão mais próximos do que
    um determinado limiar de distância.

    Args:
        df (pd.DataFrame): O DataFrame contendo os pontos com colunas 'Latitude' e 'Longitude'.
        threshold_meters (int): A distância máxima em metros para considerar os pontos próximos.

    Returns:
        List[Dict]: Uma lista de dicionários, onde cada dicionário representa um par de
                    pontos próximos e contém seus índices e nomes.
    """
    close_pairs = []
    df_copy = df.reset_index() # Garante que temos um índice numérico de 0 a N-1

    for i in range(len(df_copy)):
        for j in range(i + 1, len(df_copy)):
            point1 = df_copy.iloc[i]
            point2 = df_copy.iloc[j]

            distance = haversine_distance(
                point1['Latitude'], point1['Longitude'],
                point2['Latitude'], point2['Longitude']
            )

            if distance < threshold_meters:
                close_pairs.append({
                    "point1_index": point1['index'],
                    "point1_name": point1.get('Nome', f"Ponto {point1['index']}"),
                    "point2_index": point2['index'],
                    "point2_name": point2.get('Nome', f"Ponto {point2['index']}"),
                    "distance": distance
                })
    return close_pairs
