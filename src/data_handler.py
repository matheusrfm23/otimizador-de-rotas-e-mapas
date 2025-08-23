# src/data_handler.py
# Responsável por carregar, analisar, limpar e processar os dados de entrada.
# VERSÃO 3.0.12: Corrigida a lógica de leitura de arquivos de upload locais.

import pandas as pd
import tempfile
import os
import re
import requests
import io
from lxml import etree
import gpxpy
from typing import Dict, Any, Optional, Tuple

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
    """Extrai pontos de uma estrutura de árvore KML."""
    points = []
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    for placemark in tree.xpath('.//kml:Placemark', namespaces=ns):
        name = placemark.findtext('kml:name', default="Ponto KML", namespaces=ns).strip()
        coords_text = placemark.findtext('.//kml:coordinates', default="", namespaces=ns).strip()
        if coords_text:
            coords = coords_text.split(',')
            if len(coords) >= 2:
                points.append({
                    "Nome": name, 
                    "Latitude": float(coords[1]), 
                    "Longitude": float(coords[0])
                })
    return pd.DataFrame(points)

def _parse_csv_or_excel(file_content: bytes, is_excel: bool) -> pd.DataFrame:
    """Lê o conteúdo de um arquivo CSV ou XLSX e o retorna como um DataFrame."""
    try:
        if is_excel:
            return pd.read_excel(io.BytesIO(file_content))
        else:
            try:
                text_content = file_content.decode('utf-8')
            except UnicodeDecodeError:
                text_content = file_content.decode('latin-1')
            return pd.read_csv(io.StringIO(text_content), on_bad_lines='skip', sep=None, engine='python')
    except Exception as e:
        print(f"ERRO ao ler o conteúdo da planilha: {e}")
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
                    break
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    return df

def _validate_coordinates(latitude: float, longitude: float) -> bool:
    """Verifica se uma coordenada está dentro dos limites geográficos válidos."""
    try:
        return -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180
    except (ValueError, TypeError):
        return False

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa e valida as colunas de coordenadas de um DataFrame."""
    if 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        return pd.DataFrame()

    df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
    df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
    df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
    
    valid_coords = df.apply(
        lambda row: _validate_coordinates(row['Latitude'], row['Longitude']), 
        axis=1
    )
    return df[valid_coords].reset_index(drop=True)

# --- SEÇÃO 3: ORQUESTRADORES DE PROCESSAMENTO ---

def process_uploaded_file(uploaded_file: Any) -> Dict[str, Any]:
    """Orquestra o carregamento de um arquivo, tratando múltiplos formatos."""
    try:
        suffix = os.path.splitext(uploaded_file.name)[1].lower()
        file_content = uploaded_file.getvalue() # Use getvalue() para compatibilidade

        if suffix == '.gpx': 
            with tempfile.NamedTemporaryFile(delete=False, suffix=".gpx") as tmp_file:
                tmp_file.write(file_content)
                file_path = tmp_file.name
            df_raw = _parse_gpx_file(file_path)
            os.remove(file_path)
        elif suffix == '.kml':
            tree = etree.fromstring(file_content)
            df_raw = _parse_kml_tree(etree.ElementTree(tree))
        elif suffix in ['.csv', '.xlsx']: 
            df_raw = _parse_csv_or_excel(file_content, is_excel=(suffix == '.xlsx'))
        else:
            return {'status': 'error', 'message': f'Formato de arquivo "{suffix}" não suportado.'}
        
        if df_raw.empty:
            return {'status': 'error', 'message': 'Nenhum dado encontrado no arquivo.'}

        df_std = _auto_detect_and_standardize_columns(df_raw.copy())
        
        if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
            return {'status': 'manual_mapping_required', 'data': df_raw, 'message': 'Selecione as colunas de coordenadas.'}

        df_cleaned = clean_data(df_std)
        
        if df_cleaned.empty:
            return {'status': 'error', 'message': 'Dados encontrados, mas nenhum ponto válido após a limpeza.'}
        
        return {'status': 'success', 'data': df_cleaned, 'message': f'{len(df_cleaned)} pontos processados com sucesso!'}

    except Exception as e:
        return {'status': 'error', 'message': f'Ocorreu um erro inesperado: {e}'}

def process_mymaps_link(url: str) -> Dict[str, Any]:
    """Baixa e processa os pontos de um link do Google My Maps."""
    try:
        mid_match = re.search(r"mid=([a-zA-Z0-9_-]+)", url)
        if not mid_match:
            return {'status': 'error', 'message': 'URL do My Maps inválida. Verifique o link.'}
        
        mid = mid_match.group(1)
        kml_url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
        
        response = requests.get(kml_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()

        tree = etree.fromstring(response.content)
        df = _parse_kml_tree(etree.ElementTree(tree))

        if df.empty:
            return {'status': 'error', 'message': 'Nenhum ponto encontrado no mapa. Verifique se o mapa não está vazio e se está público.'}

        df_cleaned = clean_data(df)
        return {'status': 'success', 'data': df_cleaned, 'message': f'{len(df_cleaned)} pontos do My Maps processados!'}

    except Exception as e:
        return {'status': 'error', 'message': f'Falha ao processar o link do My Maps: {e}'}

def process_drive_link(url: str) -> Dict[str, Any]:
    """Baixa e processa um arquivo do Google Drive de forma robusta."""
    try:
        file_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
        if not file_id_match:
            return {'status': 'error', 'message': 'URL do Google Drive inválida.'}
        
        file_id = file_id_match.group(1)
        
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        
        if "/spreadsheets/" in url:
            download_url = f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv'
            response = session.get(download_url, stream=True, timeout=15)
            is_excel = False
        else:
            download_url = f'https://drive.google.com/uc?export=download&id={file_id}'
            response = session.get(download_url, stream=True, timeout=15)
            
            token = None
            for key, value in response.cookies.items():
                if key.startswith('download_warning'):
                    token = value
                    break
            
            if token:
                params = {'id': file_id, 'export': 'download', 'confirm': token}
                response = session.get('https://drive.google.com/uc', params=params, stream=True, timeout=15)
            
            content_type = response.headers.get('Content-Type', '')
            is_excel = "spreadsheet" in content_type or "excel" in content_type

        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            return {'status': 'error', 'message': 'Acesso negado. Verifique se o link do Google Drive está compartilhado como "Qualquer pessoa com o link".'}

        response.raise_for_status()
        
        file_content = response.content
        if not file_content:
             return {'status': 'error', 'message': 'O arquivo do Drive foi baixado, mas está vazio.'}

        df_raw = _parse_csv_or_excel(file_content, is_excel=is_excel)

        if df_raw.empty:
            return {'status': 'error', 'message': 'O arquivo do Drive está vazio ou em formato não reconhecido.'}
        
        df_std = _auto_detect_and_standardize_columns(df_raw.copy())
        if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
            if 'Link' in df_std.columns:
                df_std['coords_from_link'] = df_std['Link'].astype(str).apply(extract_coords_from_text)
                coords_df = pd.DataFrame(df_std['coords_from_link'].dropna().tolist(), index=df_std.dropna(subset=['coords_from_link']).index)
                df_std['Latitude'] = coords_df[0]
                df_std['Longitude'] = coords_df[1]

            if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
                return {'status': 'manual_mapping_required', 'data': df_raw, 'message': 'Selecione as colunas de coordenadas.'}
        
        df_cleaned = clean_data(df_std)
        return {'status': 'success', 'data': df_cleaned, 'message': f'{len(df_cleaned)} pontos do Drive processados!'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'message': f'Falha de conexão ao processar o link do Drive: {e}'}
    except Exception as e:
        return {'status': 'error', 'message': f'Ocorreu um erro inesperado ao processar o link do Drive: {e}'}


def process_raw_text(text_data: str) -> Dict[str, Any]:
    """Processa dados de uma string de texto (geralmente CSV)."""
    try:
        if not text_data.strip():
            return {'status': 'error', 'message': 'A caixa de texto está vazia.'}

        df_raw = _parse_csv_or_excel(text_data.encode('utf-8'), is_excel=False)
        
        if df_raw.empty:
            return {'status': 'error', 'message': 'O texto está em formato não reconhecido.'}

        df_std = _auto_detect_and_standardize_columns(df_raw.copy())
        
        if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
            for col in df_std.columns:
                coords_series = df_std[col].dropna().astype(str).apply(extract_coords_from_text)
                if coords_series.count() / len(df_std[col].dropna()) > 0.5:
                    coords_df = pd.DataFrame(coords_series.dropna().tolist(), index=coords_series.dropna().index, columns=['Latitude', 'Longitude'])
                    df_std = df_std.join(coords_df)
                    if 'Nome' not in df_std.columns:
                        try:
                            name_col = [c for c in df_std.columns if c not in ['Latitude', 'Longitude', col]][0]
                            df_std.rename(columns={name_col: 'Nome'}, inplace=True)
                        except IndexError:
                            df_std['Nome'] = "Ponto"
                    break
        
        if 'Latitude' not in df_std.columns or 'Longitude' not in df_std.columns:
            return {'status': 'manual_mapping_required', 'data': df_raw, 'message': 'Não foi possível detectar as coordenadas. Por favor, mapeie manualmente.'}

        df_cleaned = clean_data(df_std)
        return {'status': 'success', 'data': df_cleaned, 'message': f'{len(df_cleaned)} pontos do texto processados!'}

    except Exception as e:
        return {'status': 'error', 'message': f'Falha ao processar o texto colado: {e}'}

def extract_coords_from_text(text: str) -> Optional[Tuple[float, float]]:
    """
    Extrai um par de latitude e longitude de uma string, com alta flexibilidade.
    Aceita links do Google Maps e vários formatos de texto.
    """
    if not isinstance(text, str): return None
    
    text_cleaned = text.strip()
    
    if "maps.app.goo.gl" in text_cleaned:
        try:
            response = requests.head(text_cleaned, allow_redirects=True, timeout=5)
            text_cleaned = response.url
        except requests.RequestException:
            pass

    text_cleaned = re.sub(r"[°'\"()NnSsOoWwEe]", "", text_cleaned)
    numbers = re.findall(r"-?\d+\.\d+", text_cleaned)
    
    if len(numbers) >= 2:
        try:
            # Pega os dois primeiros números encontrados
            c1, c2 = float(numbers[0]), float(numbers[1])
            if _validate_coordinates(c1, c2): return c1, c2
            if _validate_coordinates(c2, c1): return c2, c1
        except (ValueError, IndexError):
            pass

    at_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", text_cleaned)
    if at_match:
        lat, lon = float(at_match.group(1)), float(at_match.group(2))
        if _validate_coordinates(lat, lon): return lat, lon

    dir_match = re.findall(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)|!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", text_cleaned)
    if dir_match:
        for m in dir_match:
            lat, lon = (m[2], m[3]) if m[2] else (m[1], m[0])
            lat, lon = float(lat), float(lon)
            if _validate_coordinates(lat, lon): return lat, lon

    q_match = re.search(r"\?q=(-?\d+\.\d+),(-?\d+\.\d+)", text_cleaned)
    if q_match:
        lat, lon = float(q_match.group(1)), float(q_match.group(2))
        if _validate_coordinates(lat, lon): return lat, lon

    return None
