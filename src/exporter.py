# src/exporter.py
# Responsável por criar visualizações e exportar dados para diversos formatos.
# VERSÃO 3.0.5: Código limpo, adicionados comentários detalhados e docstrings.

import pandas as pd
import folium
import json
from lxml import etree
import gpxpy
from gpxpy.gpx import GPX, GPXWaypoint, GPXRoute, GPXRoutePoint
from typing import Optional, Dict, List

# --- SEÇÃO 1: CRIAÇÃO DE MAPA INTERATIVO ---

def create_interactive_map(df: pd.DataFrame, route_geojson: Optional[Dict] = None) -> Optional[str]:
    """
    Cria um mapa interativo com os pontos e a rota otimizada usando Folium.

    Args:
        df (pd.DataFrame): DataFrame com os pontos da rota na ordem correta.
        route_geojson (Optional[Dict]): GeoJSON da rota online (se disponível).
                                        Se não for fornecido, uma linha reta será desenhada.

    Returns:
        Optional[str]: O HTML do mapa Folium como uma string, ou None se o DataFrame estiver vazio.
    """
    if df is None or df.empty:
        return None

    # Centraliza o mapa no primeiro ponto da rota.
    start_point = df.iloc[0]
    map_center = [start_point['Latitude'], start_point['Longitude']]
    
    m = folium.Map(location=map_center, zoom_start=13, tiles="CartoDB positron")

    # Adiciona um marcador para cada ponto no DataFrame.
    for index, row in df.iterrows():
        point_name = row.get('Nome', f'Ponto {index + 1}')
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=f"<b>{point_name}</b><br>Lat: {row['Latitude']:.5f}<br>Lon: {row['Longitude']:.5f}",
            tooltip=f"{index + 1}: {point_name}"
        ).add_to(m)

    # Desenha a linha da rota no mapa.
    if route_geojson:
        # Se tivermos o GeoJSON da rota online, desenha o trajeto real.
        folium.GeoJson(
            data=route_geojson,
            name='Rota Otimizada',
            style_function=lambda x: {'color': '#007BFF', 'weight': 5, 'opacity': 0.8}
        ).add_to(m)
    else:
        # Caso contrário, desenha uma linha reta pontilhada (rota offline).
        locations = df[['Latitude', 'Longitude']].values.tolist()
        folium.PolyLine(
            locations=locations,    
            color="#FF6347",    
            weight=3,    
            opacity=0.8,    
            dash_array='5, 10'
        ).add_to(m)
    
    # Ajusta o zoom para que toda a rota caiba na tela.
    m.fit_bounds(m.get_bounds())
    return m._repr_html_()

# --- SEÇÃO 2: FUNÇÕES DE EXPORTAÇÃO DE ARQUIVO ---

def export_to_csv(df: pd.DataFrame) -> str:
    """Converte o DataFrame para uma string no formato CSV."""
    return df.to_csv(index=False, encoding='utf-8-sig')

def export_to_geojson(df: pd.DataFrame) -> str:
    """Converte os pontos e a rota para uma string no formato GeoJSON."""
    features = []
    # Cria uma "Feature" do tipo Ponto para cada linha do DataFrame.
    for index, row in df.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row['Longitude'], row['Latitude']]},
            "properties": {
                "name": row.get('Nome', f"Ponto {index + 1}"),
                "order": index + 1
            }
        })
    # Cria uma "Feature" do tipo LineString para representar a rota.
    line_coordinates = df[['Longitude', 'Latitude']].values.tolist()
    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": line_coordinates},
        "properties": {"name": "Rota Otimizada"}
    })
    geojson_output = {"type": "FeatureCollection", "features": features}
    return json.dumps(geojson_output, indent=2)

def export_to_kml(df: pd.DataFrame) -> bytes:
    """Converte os pontos e a rota para um arquivo KML em formato de bytes."""
    kml_root = etree.Element("kml", nsmap={None: "http://www.opengis.net/kml/2.2"})
    document = etree.SubElement(kml_root, "Document")
    etree.SubElement(document, "name").text = "Rota Otimizada"
    
    # Adiciona um Placemark para cada ponto.
    for index, row in df.iterrows():
        placemark = etree.SubElement(document, "Placemark")
        etree.SubElement(placemark, "name").text = str(row.get('Nome', f"Ponto {index + 1}"))
        point = etree.SubElement(placemark, "Point")
        etree.SubElement(point, "coordinates").text = f"{row['Longitude']},{row['Latitude']},0"
        
    # Adiciona um Placemark para a linha da rota.
    placemark_route = etree.SubElement(document, "Placemark")
    etree.SubElement(placemark_route, "name").text = "Trajeto da Rota"
    line_string = etree.SubElement(placemark_route, "LineString")
    coords_text = " ".join([f"{row['Longitude']},{row['Latitude']},0" for _, row in df.iterrows()])
    etree.SubElement(line_string, "coordinates").text = coords_text
    
    return etree.tostring(kml_root, pretty_print=True, xml_declaration=True, encoding='utf-8')

def export_to_gpx(df: pd.DataFrame) -> str:
    """Converte os pontos (waypoints) e a rota para uma string no formato GPX."""
    gpx = GPX()
    
    # Adiciona cada ponto como um Waypoint.
    for index, row in df.iterrows():
        gpx.waypoints.append(GPXWaypoint(
            latitude=row['Latitude'],
            longitude=row['Longitude'],
            name=str(row.get('Nome', f"Ponto {index + 1}"))
        ))
        
    # Cria uma Rota que conecta todos os waypoints.
    gpx_route = GPXRoute(name="Rota Otimizada")
    gpx_route.points = [GPXRoutePoint(row['Latitude'], row['Longitude']) for _, row in df.iterrows()]
    gpx.routes.append(gpx_route)
    
    return gpx.to_xml(prettyprint=True)

def export_to_mymaps_csv(df: pd.DataFrame) -> str:
    """Formata o DataFrame para um CSV compatível com o Google My Maps."""
    df_mymaps = df.copy()
    
    # Adiciona a coluna de ordem da rota, que é útil no My Maps.
    df_mymaps.insert(0, 'Ordem', range(1, len(df_mymaps) + 1))
    
    # Seleciona e reordena as colunas de interesse para o My Maps.
    cols_to_keep = ['Ordem', 'Nome', 'Latitude', 'Longitude']
    # Adiciona colunas extras se elas existirem (enriquecidas pela IA).
    if 'Endereço' in df_mymaps.columns:
        cols_to_keep.append('Endereço')
    if 'Categoria' in df_mymaps.columns:
        cols_to_keep.append('Categoria')
        
    df_mymaps = df_mymaps[cols_to_keep]
    
    return df_mymaps.to_csv(index=False, encoding='utf-8-sig')

# --- SEÇÃO 3: GERAÇÃO DE LINKS EXTERNOS ---

def generate_google_maps_links(df: pd.DataFrame) -> List[str]:
    """
    Gera links de navegação do Google Maps a partir de uma rota.
    Divide a rota em partes se exceder o limite de 10 pontos do Google Maps.
    """
    if df is None or df.empty or len(df) < 2:
        return []

    links = []
    base_url = "https://www.google.com/maps/dir/"
    num_points = len(df)
    # O Google Maps aceita origem + 9 destinos, totalizando 10 pontos por link.
    chunk_size = 10 

    # Itera sobre o DataFrame em "pedaços" de 9 em 9.
    # O -1 no passo (step) garante a sobreposição, fazendo com que o fim de um
    # "pedaço" seja o começo do próximo, criando uma rota contínua.
    for i in range(0, num_points, chunk_size - 1):
        chunk = df.iloc[i : i + chunk_size]
        if len(chunk) < 2:
            continue # Pula o último ponto se ele ficar sozinho
            
        points_str = "/".join([f"{row['Latitude']},{row['Longitude']}" for _, row in chunk.iterrows()])
        links.append(base_url + points_str)

    return links
