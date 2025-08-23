# app.py
# Ponto de entrada principal da aplicação Otimizador de Rotas e Mapas 3.0.
# Este script utiliza o Streamlit para criar a interface gráfica do usuário.
# VERSÃO 3.1.17: Implementado o gerenciamento de sessão (adicionar e salvar).

import streamlit as st
import pandas as pd
import re
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- Importação dos nossos módulos da pasta src ---
from src.data_handler import (
    process_uploaded_file, process_mymaps_link, process_drive_link, 
    process_raw_text, extract_coords_from_text, clean_data
)
from src.optimizer import ortools_optimizer
from src.services import optimize_route_online, geocode_address, autocomplete_address
from src.exporter import (
    create_interactive_map, export_to_csv, export_to_geojson,
    export_to_kml, export_to_gpx, generate_google_maps_links,
    export_to_mymaps_csv
)
# (As funções do gemini_services serão importadas quando as usarmos)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    layout="wide",
    page_title="Otimizador de Rotas 3.0",
    page_icon="🗺️"
)

# --- ESTADO DA SESSÃO E FUNÇÕES AUXILIARES ---

def initialize_session_state():
    """Define os valores padrão para as variáveis da sessão se elas não existirem."""
    defaults = {
        "processed_data": None,
        "optimized_data": None,
        "raw_data_for_mapping": None,
        "manual_mapping_required": False,
        "route_geojson": None,
        "total_distance": None,
        "total_duration": None,
        "address_input": "",
        "clear_address_input_flag": False,
        "pending_sidebar_file": None # Para o ficheiro carregado na barra lateral
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def clear_session():
    """Limpa todos os dados da sessão para reiniciar o processo."""
    keys_to_clear = list(st.session_state.keys())
    for key in keys_to_clear:
        del st.session_state[key]
    st.rerun()

def handle_processed_result(result: dict):
    """
    Função central para lidar com o resultado do processamento de dados.
    Atualiza o estado da sessão com base no status do resultado.
    """
    if not result:
        st.error("O processamento retornou um erro inesperado.")
        return

    if result['status'] == 'success':
        st.session_state.processed_data = result['data']
        st.session_state.manual_mapping_required = False
        st.success(result.get('message', "Dados processados com sucesso!"))
        st.rerun()
    elif result['status'] == 'manual_mapping_required':
        st.session_state.raw_data_for_mapping = result['data']
        st.session_state.manual_mapping_required = True
        st.warning(result.get('message', "Mapeamento manual necessário."))
        st.rerun()
    else: # status == 'error'
        st.error(result.get('message', 'Ocorreu um erro desconhecido.'))
        st.session_state.processed_data = None


# --- FUNÇÕES DE LAYOUT (UI) ---

def draw_sidebar():
    """Desenha a barra lateral da aplicação."""
    with st.sidebar:
        st.header("Opções da Rota")
        if st.button("Reiniciar Sessão", use_container_width=True, type="primary"):
            clear_session()
        
        # A secção de gestão de sessão só aparece se houver uma rota ativa
        if st.session_state.processed_data is not None:
            st.markdown("---")
            st.subheader("Gerir Sessão")
            
            # Botão para salvar a sessão
            if not st.session_state.processed_data.empty:
                st.download_button(
                    label="Salvar Sessão de Trabalho",
                    data=st.session_state.processed_data.to_csv(index=False).encode('utf-8-sig'),
                    file_name="sessao_otimizador.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Uploader para adicionar um novo ficheiro
            sidebar_uploader = st.file_uploader(
                "Carregar novo ficheiro na sessão",
                type=["csv", "xlsx", "kml", "gpx"],
                key="sidebar_uploader"
            )
            if sidebar_uploader:
                # Guarda o ficheiro no estado da sessão para ser processado na tela principal
                st.session_state.pending_sidebar_file = sidebar_uploader
                st.rerun()

def draw_add_point_section():
    """Desenha a seção para adicionar um novo ponto à rota."""
    st.markdown("---")
    st.subheader("Adicionar Novo Ponto")

    try:
        ORS_API_KEY = st.secrets["ORS_API_KEY"]
    except FileNotFoundError:
        ORS_API_KEY = ""

    if st.session_state.clear_address_input_flag:
        st.session_state.address_input = ""
        st.session_state.clear_address_input_flag = False

    add_mode = st.radio(
        "Método de adição:",
        ("Por Endereço / Link", "Por Coordenadas"),
        horizontal=True,
        label_visibility="collapsed"
    )

    if add_mode == "Por Endereço / Link":
        text_input = st.text_input(
            "Digite um endereço, link do Google Maps ou Plus Code",
            placeholder="Ex: Av. Paulista, 1578 ou https://maps.app.goo.gl/...",
            key="address_input"
        )
        
        suggestions_container = st.container()

        if text_input and "http" not in text_input and not re.search(r"-?\d+\.\d+", text_input):
             if len(text_input) > 3 and ORS_API_KEY:
                suggestions = autocomplete_address(text_input, ORS_API_KEY)
                with suggestions_container:
                    for suggestion in suggestions[:3]:
                        if st.button(suggestion, key=f"sug_{suggestion}", use_container_width=True):
                            st.session_state.address_input = suggestion
                            st.rerun()

        if st.button("Adicionar Ponto", key="add_by_text", disabled=not text_input):
            with st.spinner("Analisando entrada..."):
                coords = extract_coords_from_text(text_input)
                point_name = text_input
                
                if not coords:
                    if not ORS_API_KEY:
                        st.error("A chave da API do OpenRouteService é necessária para buscar endereços.")
                        return
                    coords = geocode_address(text_input, ORS_API_KEY)
                
                if coords:
                    lat, lon = coords
                    new_row = pd.DataFrame([{'Nome': point_name, 'Latitude': lat, 'Longitude': lon}])
                    st.session_state.processed_data = pd.concat([st.session_state.processed_data, new_row], ignore_index=True)
                    st.session_state.clear_address_input_flag = True
                    st.success("Ponto adicionado com sucesso.")
                    st.rerun()
                else:
                    st.error("Não foi possível encontrar coordenadas para a entrada fornecida.")

    elif add_mode == "Por Coordenadas":
        st.markdown("**Opção 1: Campos Separados**")
        c1, c2, c3 = st.columns([2, 2, 1])
        lat_sep = c1.text_input("Latitude", placeholder="-23.5613")
        lon_sep = c2.text_input("Longitude", placeholder="-46.6565")
        name_sep = c3.text_input("Nome (Opcional)", key="name_sep")

        st.markdown("**Opção 2: Colar Coordenadas Juntas**")
        c4, c5 = st.columns([3, 1])
        coords_combined = c4.text_input("Coordenadas em texto", placeholder="-19.842761°, -43.351048°")
        name_combined = c5.text_input("Nome (Opcional)", key="name_combined")
        
        if st.button("Adicionar por Coordenadas", key="add_by_coords"):
            lat, lon, name = None, None, None
            
            if lat_sep and lon_sep:
                try:
                    lat = float(str(lat_sep).replace(',', '.'))
                    lon = float(str(lon_sep).replace(',', '.'))
                    name = name_sep
                except (ValueError, TypeError):
                    st.error("Valores de Latitude e Longitude separados são inválidos.")
                    return
            
            elif coords_combined:
                coords_result = extract_coords_from_text(coords_combined)
                if coords_result:
                    lat, lon = coords_result
                    name = name_combined
                else:
                    st.error("Formato de coordenadas no campo de texto é inválido.")
                    return
            
            else:
                st.warning("Por favor, preencha os campos de coordenadas.")
                return

            point_name = name or f"Ponto {lat:.4f}, {lon:.4f}"
            new_row = pd.DataFrame([{'Nome': point_name, 'Latitude': lat, 'Longitude': lon}])
            st.session_state.processed_data = pd.concat([st.session_state.processed_data, new_row], ignore_index=True)
            st.success(f"Ponto '{point_name}' adicionado.")
            st.rerun()


def draw_optimization_controls():
    """Desenha os botões e a lógica para executar a otimização."""
    st.markdown("---")
    st.subheader("Executar Otimização")

    try:
        ORS_API_KEY = st.secrets["ORS_API_KEY"]
    except FileNotFoundError:
        ORS_API_KEY = ""
        st.warning("Chave da API do OpenRouteService não encontrada. A otimização online está desabilitada.")

    custom_start_end = st.toggle("Definir partida e chegada personalizadas")
    
    start_node = 0
    end_node = 0
    if not st.session_state.processed_data.empty:
        end_node = len(st.session_state.processed_data) - 1

    if custom_start_end and len(st.session_state.processed_data) > 1:
        df_data = st.session_state.processed_data
        point_options = [f"{idx}: {row.get('Nome', f'Ponto {idx+1}')}" for idx, row in df_data.iterrows()]
        
        col1, col2 = st.columns(2)
        start_point_str = col1.selectbox("Ponto de Partida", options=point_options, index=0)
        end_point_str = col2.selectbox("Ponto de Chegada", options=point_options, index=len(point_options)-1)
        
        start_node = int(start_point_str.split(':')[0])
        end_node = int(end_point_str.split(':')[0])
    
    elif not custom_start_end:
        st.caption("A otimização usará o primeiro ponto da tabela como início e o último como fim.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Otimizar Rota (Offline)", use_container_width=True, help="Mais rápido, usa distância em linha reta."):
            if len(st.session_state.processed_data) > 1:
                with st.spinner("Otimizando rota com OR-Tools..."):
                    optimized_df = ortools_optimizer(st.session_state.processed_data.copy(), start_node=start_node, end_node=end_node)
                    st.session_state.optimized_data = optimized_df
                    st.session_state.route_geojson = None
                    st.session_state.total_distance = None
                    st.session_state.total_duration = None
                    st.success("Otimização Offline concluída!")
            else:
                st.warning("São necessários pelo menos 2 pontos para otimizar.")
    
    with col2:
        if st.button("Otimizar Rota (Online)", use_container_width=True, type="primary", help="Mais preciso, usa ruas reais.", disabled=(not ORS_API_KEY)):
            if len(st.session_state.processed_data) > 1:
                with st.spinner("Otimizando rota com a API OpenRouteService..."):
                    result = optimize_route_online(st.session_state.processed_data.copy(), ORS_API_KEY, start_node=start_node, end_node=end_node)
                    if result:
                        st.session_state.optimized_data = result["data"]
                        st.session_state.route_geojson = result["geojson"]
                        st.session_state.total_distance = result["distance"]
                        st.session_state.total_duration = result["duration"]
                        st.success("Otimização Online concluída!")
                    else:
                        st.error("A otimização online falhou. Verifique o console para detalhes.")
            else:
                st.warning("São necessários pelo menos 2 pontos para otimizar.")

def draw_results_section():
    """Desenha a seção de resultados se uma rota otimizada existir."""
    if st.session_state.optimized_data is not None:
        st.markdown("---")
        st.header("3. Resultados da Otimização")
        
        st.dataframe(st.session_state.optimized_data, hide_index=True, use_container_width=True)

        if st.session_state.total_distance is not None:
            col1, col2 = st.columns(2)
            col1.metric("Distância Total", f"{st.session_state.total_distance:.2f} km")
            col2.metric("Duração Estimada", f"{st.session_state.total_duration:.1f} min")

        with st.spinner("Gerando mapa..."):
            map_html = create_interactive_map(st.session_state.optimized_data, st.session_state.route_geojson)
            if map_html:
                st.components.v1.html(map_html, height=600)
        
        st.subheader("Exportar Resultados")
        c1, c2, c3, c4, c5 = st.columns(5)
        df_opt = st.session_state.optimized_data
        
        with c1:
            st.download_button("Exportar CSV", export_to_csv(df_opt), "rota_otimizada.csv", use_container_width=True)
        with c2:
            st.download_button("Exportar GeoJSON", export_to_geojson(df_opt), "rota_otimizada.geojson", use_container_width=True)
        with c3:
            st.download_button("Exportar KML", export_to_kml(df_opt), "rota_otimizada.kml", use_container_width=True)
        with c4:
            st.download_button("Exportar GPX", export_to_gpx(df_opt), "rota_otimizada.gpx", use_container_width=True)
        with c5:
            st.download_button("Para My Maps", export_to_mymaps_csv(df_opt), "rota_para_mymaps.csv", use_container_width=True)

def draw_manual_mapping_screen():
    """Desenha a tela para o usuário mapear as colunas manualmente."""
    st.header("⚠️ Mapeamento Manual Necessário")
    st.markdown("Não conseguimos detectar as colunas de coordenadas. Por favor, selecione as colunas corretas abaixo.")
    
    df_raw = st.session_state.raw_data_for_mapping
    st.dataframe(df_raw.head())
    
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    options = [None] + list(df_raw.columns)
    
    lat_col = col1.selectbox("Selecione a coluna de Latitude", options=options)
    lon_col = col2.selectbox("Selecione a coluna de Longitude", options=options)
    name_col = col3.selectbox("Selecione a coluna de Nome (Opcional)", options=options)

    if st.button("Aplicar Mapeamento e Continuar"):
        if lat_col and lon_col:
            rename_dict = {lat_col: 'Latitude', lon_col: 'Longitude'}
            if name_col:
                rename_dict[name_col] = 'Nome'
            
            df_mapped = df_raw.rename(columns=rename_dict)
            df_cleaned = clean_data(df_mapped)

            if not df_cleaned.empty:
                st.session_state.processed_data = df_cleaned
                st.session_state.manual_mapping_required = False
                st.session_state.raw_data_for_mapping = None
                st.success(f"Mapeamento aplicado! {len(df_cleaned)} pontos válidos encontrados.")
                st.rerun()
            else:
                st.error("Nenhum ponto válido encontrado com as colunas selecionadas.")
        else:
            st.error("Por favor, selecione as colunas de Latitude e Longitude.")

def draw_add_or_replace_dialog():
    """Desenha o diálogo para adicionar ou substituir a rota atual."""
    with st.expander("Ficheiro carregado. O que deseja fazer?", expanded=True):
        pending_file = st.session_state.pending_sidebar_file
        st.info(f"Você carregou o ficheiro **{pending_file.name}**, mas já existe uma rota com {len(st.session_state.processed_data)} pontos em andamento.")
        
        col1, col2 = st.columns(2)
        
        if col1.button("Substituir Rota Atual", use_container_width=True):
            with st.spinner("Processando novo ficheiro..."):
                result = process_uploaded_file(pending_file)
                st.session_state.pending_sidebar_file = None # Limpa o ficheiro pendente
                handle_processed_result(result) # A função já recarrega a página

        if col2.button("Adicionar à Rota Atual", use_container_width=True, type="primary"):
            with st.spinner("Processando e adicionando novos pontos..."):
                result = process_uploaded_file(pending_file)
                if result and result.get('status') == 'success':
                    new_data = result['data']
                    st.session_state.processed_data = pd.concat(
                        [st.session_state.processed_data, new_data], 
                        ignore_index=True
                    )
                    st.success(f"{len(new_data)} novos pontos adicionados com sucesso!")
                elif result:
                    st.error(result.get('message', 'Falha ao processar o novo ficheiro.'))
                
                st.session_state.pending_sidebar_file = None
                st.rerun()

def draw_main_content():
    """Desenha o conteúdo principal da página, que muda conforme o estado."""
    
    if st.session_state.pending_sidebar_file:
        draw_add_or_replace_dialog()

    elif st.session_state.manual_mapping_required:
        draw_manual_mapping_screen()

    elif st.session_state.processed_data is None:
        st.header("1. Comece Sua Rota")
        st.markdown("Use uma das opções abaixo para carregar os pontos da sua rota.")
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Planilha (CSV/XLSX)", "GPS (KML/GPX)", "Rota Manual", "Link do My Maps", "Link do Drive", "Colar Texto"
        ])
        
        with tab1:
            st.markdown("✅ **Melhor opção para smartphones.**")
            spreadsheet_file = st.file_uploader(
                "Selecione um arquivo CSV ou XLSX", type=["csv", "xlsx"],
                label_visibility="collapsed", key="spreadsheet_uploader"
            )
            if spreadsheet_file:
                with st.spinner("Analisando e processando sua planilha..."):
                    result = process_uploaded_file(spreadsheet_file)
                    handle_processed_result(result)

        with tab2:
            st.warning("Pode não apresentar a performance esperada em smartphones.")
            gps_file = st.file_uploader(
                "Selecione um arquivo KML ou GPX", type=["kml", "gpx"],
                label_visibility="collapsed", key="gps_uploader"
            )
            if gps_file:
                with st.spinner("Analisando e processando seu arquivo de GPS..."):
                    result = process_uploaded_file(gps_file)
                    handle_processed_result(result)
        
        with tab3:
            st.markdown("Adicione seus pontos um por um, manualmente.")
            if st.button("Começar Rota Manual", use_container_width=True):
                st.session_state.processed_data = pd.DataFrame(columns=['Nome', 'Latitude', 'Longitude'])
                st.rerun()

        with tab4:
            st.markdown("Cole um link compartilhável do seu mapa no Google My Maps.")
            mymaps_url = st.text_input("URL do Google My Maps", label_visibility="collapsed", key="mymaps_url")
            if st.button("Processar Link do My Maps", use_container_width=True, disabled=not mymaps_url):
                with st.spinner("Extraindo pontos do My Maps..."):
                    result = process_mymaps_link(mymaps_url)
                    handle_processed_result(result)
        
        with tab5:
            st.markdown("Cole um link compartilhável de um arquivo CSV ou XLSX do Google Drive.")
            drive_url = st.text_input("URL do Google Drive", label_visibility="collapsed", key="drive_url")
            if st.button("Processar Link do Drive", use_container_width=True, disabled=not drive_url):
                with st.spinner("Baixando e processando arquivo do Google Drive..."):
                    result = process_drive_link(drive_url)
                    handle_processed_result(result)

        with tab6:
            st.markdown("Copie os dados de uma planilha (formato CSV) e cole abaixo.")
            text_data = st.text_area("Cole os dados aqui", height=200, label_visibility="collapsed", key="text_data")
            if st.button("Processar Texto Colado", use_container_width=True, disabled=not text_data):
                with st.spinner("Processando texto..."):
                    result = process_raw_text(text_data)
                    handle_processed_result(result)

    else:
        st.header("2. Revise e Edite sua Rota")
        st.markdown("Arraste as linhas para reordenar, clique duas vezes para editar e use as caixas de seleção para apagar pontos.")
        
        df_for_grid = st.session_state.processed_data.copy()
        gb = GridOptionsBuilder.from_dataframe(df_for_grid)
        gb.configure_default_column(editable=True, groupable=True)
        gb.configure_grid_options(rowDragManaged=True)
        gb.configure_selection(selection_mode='multiple', use_checkbox=True, header_checkbox=True)
        
        if not df_for_grid.empty:
            gb.configure_column(df_for_grid.columns[0], rowDrag=True)
        
        grid_options = gb.build()

        ag_grid_response = AgGrid(
            df_for_grid,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            allow_unsafe_jscode=True,    
            height=400,
            fit_columns_on_grid_load=True,
            key='editable_grid'
        )
        
        st.session_state.processed_data = ag_grid_response['data']
        
        selected_rows = ag_grid_response['selected_rows']
        if st.button("Apagar Pontos Selecionados", disabled=not selected_rows):
            if selected_rows:
                indices_to_drop = [row['_selectedRowNodeInfo']['nodeRowIndex'] for row in selected_rows]
                df_to_keep = st.session_state.processed_data.drop(indices_to_drop).reset_index(drop=True)
                st.session_state.processed_data = df_to_keep
                st.success(f"{len(selected_rows)} ponto(s) apagado(s).")
                st.rerun()
        
        draw_add_point_section()
        draw_optimization_controls()
        draw_results_section()


# --- INÍCIO DA EXECUÇÃO DO APP ---

initialize_session_state()

st.title("Otimizador de Rotas e Mapas 3.0 🗺️✨")
draw_sidebar()
draw_main_content()
