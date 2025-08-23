# src/data_handler.py
# Responsável por carregar, analisar, limpar e processar os dados de entrada.
# VERSÃO 3.0.6: Grande refatoração. Funções quebradas em módulos menores e mais lógicos.

import pandas as pd
import tempfile
import os
import re
import requests
import io
from lxml import etree
import gpxpy
from typing import Dict, Any, Optional, Tuple, List

# Importa a função de cálculo de distância do nosso módulo de utilitários
from src.utils import haversine_distance

# --- SEÇÃO 1: PARSERS DE ARQUIVO E EXTRAÇÃO DE DADOS BRUTOS ---

def _parse_gpx_file(file_path: str) -> pd.DataFrame:
    """Analisa um arquivo GPX para extrair os waypoints (pontos)."""
    points = []
    try:
        with open(file_path, 'r', encoding='utf-8') as gpx_file:
            gpx = gpxpy.parse(gpx_file)
        for waypoint in gpx.waypoints:
            points.append({
                "Nome": waypoint.name or "Waypoint GPX", 
                "Latitude": waypoint.latitude, 
                "Longitude": waypoint.longitude
            })
        return pd.DataFrame(points)
    except Exception as e:
        print(f"ERRO ao analisar o arquivo GPX: {e}")
        return pd.DataFrame()

def _parse_kml_tree(tree: etree._ElementTree) -> pd.DataFrame:
    """Extrai pontos de uma estrutura de árvore KML (usado por KML de arquivo e de URL)."""
    points = []
    # Namespace é um "dicionário" para o KML entender os elementos como 'Placemark'.
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    for placemark in tree.xpath('.//kml:Placemark', namespaces=ns):
        name = placemark.findtext('kml:name', default="Ponto KML", namespaces=ns).strip()
        coords_text = placemark.findtext('.//kml:coordinates', default="", namespaces=ns).strip()
        if coords_text:
            # As coordenadas no KML vêm como "lon,lat,alt"
            coords = coords_text.split(',')
            if len(coords) >= 2:
                points.append({
                    "Nome": name, 
                    "Latitude": float(coords[1]), 
                    "Longitude": float(coords[0])
                })
    return pd.DataFrame(points)

def _parse_kml_file(file_path: str) -> pd.DataFrame:
    """Analisa um arquivo KML a partir de um caminho de arquivo."""
    try:
        tree = etree.parse(file_path)
        return _parse_kml_tree(tree)
    except Exception as e:
        print(f"ERRO ao analisar o arquivo KML: {e}")
        return pd.DataFrame()

def _parse_csv_or_excel(file_path: str) -> pd.DataFrame:
    """Lê um arquivo CSV ou XLSX e o retorna como um DataFrame."""
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path, on_bad_lines='skip', sep=None, engine='python')
        else: # .xlsx
            return pd.read_excel(file_path)
    except Exception as e:
        print(f"ERRO ao ler o arquivo de planilha: {e}")
        return pd.DataFrame()

# --- SEÇÃO 2: LÓGICA DE LIMPEZA E VALIDAÇÃO ---

def _auto_detect_and_standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Tenta detetar e padronizar as colunas de Latitude, Longitude, Nome e Link."""
    rename_map = {}
    keywords = {
        'Latitude': ['latitude', 'lat'],
        'Longitude': ['longitude', 'lon', 'lng'],
        'Nome': ['nome', 'name', 'título', 'ref', 'ponto', 'local', 'referencia'],
        'Link': ['link', 'url', 'gmaps', 'maps']
    }
    df_cols_lower = {c.lower(): c for c in df.columns}
    
    for standard_name, kws in keywords.items():
        if standard_name not in df.columns:
            for kw in kws:
                if kw in df_cols_lower:
                    original_col_name = df_cols_lower[kw]
                    rename_map[original_col_name] = standard_name
                    break # Para de procurar sinônimos para este nome padrão
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    return df

def _validate_coordinates(latitude: float, longitude: float) -> bool:
    """Verifica se uma coordenada está dentro dos limites geográficos válidos."""
    return -90 <= latitude <= 90 and -180 <= longitude <= 180

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpa e valida as colunas de coordenadas de um DataFrame.
    Remove linhas com coordenadas inválidas ou ausentes.
    """
    if 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        return pd.DataFrame() # Retorna vazio se as colunas essenciais não existirem

    # Converte os valores para numérico, tratando erros.
    df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
    df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

    # Remove linhas onde a conversão falhou (resultando em NaT/NaN)
    df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
    
    # Aplica a validação de limites geográficos
    valid_coords = df.apply(
        lambda row: _validate_coordinates(row['Latitude'], row['Longitude']), 
        axis=1
    )
    return df[valid_coords].reset_index(drop=True)

# --- SEÇÃO 3: ORQUESTRADOR PRINCIPAL ---

def process_uploaded_file(uploaded_file: Any) -> Dict[str, Any]:
    """
    Orquestra o carregamento de um arquivo, tratando múltiplos formatos.
    Esta é a função principal que será chamada pelo app.py.
    """
    try:
        suffix = os.path.splitext(uploaded_file.name)[1].lower()
        
        # Salva o arquivo temporariamente no disco para que as bibliotecas possam lê-lo
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            file_path = tmp_file.name

        # Delega o processamento para a função correta com base na extensão
        if suffix == '.gpx':
            df_raw = _parse_gpx_file(file_path)
        elif suffix == '.kml':
            df_raw = _parse_kml_file(file_path)
        elif suffix in ['.csv', '.xlsx']:
            df_raw = _parse_csv_or_excel(file_path)
        else:
            os.remove(file_path)
            return {'status': 'error', 'message': f'Formato de arquivo "{suffix}" não suportado.'}
        
        os.remove(file_path) # Apaga o arquivo temporário

        if df_raw.empty:
            return {'status': 'error', 'message': 'Nenhum dado encontrado no arquivo.'}

        # Padroniza as colunas e limpa os dados
        df_std = _auto_detect_and_standardize_columns(df_raw.copy())
        
        # Verifica se as colunas de coordenadas existem após a padronização
        if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
            # Se não existirem, o app.py deverá pedir o mapeamento manual
            return {'status': 'manual_mapping_required', 'data': df_raw}

        df_cleaned = clean_data(df_std)
        
        if df_cleaned.empty:
            return {'status': 'error', 'message': 'Dados encontrados, mas nenhum ponto válido após a limpeza.'}
        
        return {'status': 'success', 'data': df_cleaned}

    except Exception as e:
        # Garante que o arquivo temporário seja removido em caso de erro
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return {'status': 'error', 'message': f'Ocorreu um erro inesperado: {e}'}

# ... (As funções de processamento de links e texto serão adicionadas depois) ...
