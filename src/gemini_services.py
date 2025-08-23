# src/gemini_services.py
# Módulo para todas as interações com a API do Google Gemini.
# VERSÃO 3.0.5: Adicionada a função enrich_data_with_gemini.

import google.generativeai as genai
import pandas as pd
import streamlit as st
import json
import time

# Importa a função de cálculo de distância do nosso módulo de utilitários
from src.utils import haversine_distance

# --- CONFIGURAÇÃO E FUNÇÕES AUXILIARES ---

def configure_gemini() -> bool:
    """
    Configura a API do Gemini com a chave dos secrets do Streamlit.
    """
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
        if not api_key:
            print("ERRO: Chave da API do Gemini não encontrada nos secrets.")
            return False
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"ERRO: Falha ao configurar a API do Gemini: {e}")
        return False

def _call_gemini_api(prompt: str, retries: int = 3, delay: int = 5) -> str:
    """
    Função centralizada e robusta para chamar a API do Gemini.
    Implementa retentativas em caso de falha.
    """
    if not configure_gemini():
        raise ConnectionError("Falha ao configurar a API do Gemini. Verifique a chave.")

    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            json_text = response.text.strip().replace("```json", "").replace("```", "")
            return json_text
        except Exception as e:
            print(f"ERRO na API do Gemini (tentativa {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise

# --- FUNÇÕES DE IA PARA A APLICAÇÃO ---

def enrich_data_with_gemini(df: pd.DataFrame) -> pd.DataFrame:
    """
    Usa a IA do Gemini para adicionar informações de endereço e categoria aos pontos.
    """
    df_copy = df.copy()
    if 'Endereço' not in df_copy.columns:
        df_copy['Endereço'] = ""
    if 'Categoria' not in df_copy.columns:
        df_copy['Categoria'] = ""

    progress_bar = st.progress(0, text="A IA está a enriquecer os seus dados...")
    total_rows = len(df_copy)

    for index, row in df_copy.iterrows():
        try:
            prompt = f"""
            Analise o seguinte local:
            - Nome: "{row['Nome']}"
            - Latitude: {row['Latitude']}
            - Longitude: {row['Longitude']}
            Com base nesses dados, forneça o endereço completo mais provável e uma 
            categoria para este local (Ex: Serviço Público, Comércio, Ponto Turístico, 
            Residencial, Outro).
            Responda APENAS com um objeto JSON contendo as chaves "endereco" e "categoria".
            Exemplo: {{"endereco": "Praça Sete de Setembro, s/n - Centro, Belo Horizonte - MG, 30130-010, Brasil", "categoria": "Ponto Turístico"}}
            """
            json_text = _call_gemini_api(prompt)
            data = json.loads(json_text)
            
            df_copy.at[index, 'Endereço'] = data.get("endereco", "Não encontrado")
            df_copy.at[index, 'Categoria'] = data.get("categoria", "Não definida")
            
        except Exception as e:
            print(f"ERRO ao enriquecer a linha {index}: {e}")
            df_copy.at[index, 'Endereço'] = "Erro na busca"
            df_copy.at[index, 'Categoria'] = "Erro na busca"
        
        progress_bar.progress((index + 1) / total_rows, text=f"Processando: {row['Nome']}")

    progress_bar.empty()
    st.success("Dados enriquecidos com sucesso!")
    return df_copy
