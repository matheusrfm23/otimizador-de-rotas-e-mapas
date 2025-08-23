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

