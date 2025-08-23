# app.py
# Ponto de entrada principal da aplicação Otimizador de Rotas e Mapas 3.0.
# Este script utiliza o Streamlit para criar a interface gráfica do usuário.
# VERSÃO 3.1.8: Implementada a lógica para todas as abas de entrada de dados.

import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- Importação dos nossos módulos da pasta src ---
# Adicionadas as novas funções de processamento do data_handler
from src.data_handler import (
    process_uploaded_file, process_mymaps_link, process_drive_link, 
    process_raw_text
)
from src.optimizer import ortools_optimizer
from src.services import optimize_route_online, geocode_address
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
    if not result: # Lida com o caso de um resultado None
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
        st.markdown("---")
        if st.session_state.processed_data is not None:
            st.subheader("Adicionar à Rota Atual")
            sidebar_uploader = st.file_uploader(
                "Carregar novo arquivo na sessão",
                type=["csv", "xlsx", "kml", "gpx"],
                key="sidebar_uploader"
            )
            if sidebar_uploader:
                st.success(f"Arquivo {sidebar_uploader.name} carregado!")

def draw_optimization_controls():
    """Desenha os botões e a lógica para executar a otimização."""
    st.markdown("---")
    st.subheader("Executar Otimização")

    try:
        ORS_API_KEY = st.secrets["ORS_API_KEY"]
    except FileNotFoundError:
        ORS_API_KEY = ""
        st.warning("Chave da API do OpenRouteService não encontrada. A otimização online está desabilitada.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Otimizar Rota (Offline)", use_container_width=True, help="Mais rápido, usa distância em linha reta."):
            if len(st.session_state.processed_data) > 1:
                with st.spinner("Otimizando rota com OR-Tools..."):
                    optimized_df = ortools_optimizer(st.session_state.processed_data.copy())
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
                    result = optimize_route_online(st.session_state.processed_data.copy(), ORS_API_KEY)
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


def draw_main_content():
    """Desenha o conteúdo principal da página, que muda conforme o estado."""
    
    if st.session_state.processed_data is None:
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
        
        draw_optimization_controls()
        draw_results_section()


# --- INÍCIO DA EXECUÇÃO DO APP ---

initialize_session_state()

st.title("Otimizador de Rotas e Mapas 3.0 🗺️✨")
draw_sidebar()
draw_main_content()
