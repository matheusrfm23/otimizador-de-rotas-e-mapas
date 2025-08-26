# src/gemini_services.py
# Módulo para todas as interações com a API do Google Gemini.
# VERSÃO 3.1.0: Refatoradas funções de IA para processamento em lote.

import google.generativeai as genai
import pandas as pd
import streamlit as st
import json
import time
import math

# Importa a função de cálculo de distância do nosso módulo de utilitários
from src.utils import haversine_distance
# Importa as configurações centralizadas
from src.config import GEMINI_MODEL_NAME

# --- CONFIGURAÇÃO E FUNÇÕES AUXILIARES ---

# Define um tamanho de lote para as chamadas de API
BATCH_SIZE = 10

def configure_gemini(api_key: str) -> bool:
    """
    Configura a API do Gemini com a chave fornecida.
    """
    try:
        if not api_key:
            print("ERRO: A chave da API do Gemini não foi fornecida.")
            return False
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"ERRO: Falha ao configurar a API do Gemini: {e}")
        return False

@st.cache_resource
def get_gemini_model():
    """Cria e cacheia o modelo generativo do Gemini."""
    return genai.GenerativeModel(GEMINI_MODEL_NAME)

def _call_gemini_api(prompt: str, api_key: str, retries: int = 3, delay: int = 5) -> str:
    """
    Função centralizada e robusta para chamar a API do Gemini.
    Implementa retentativas em caso de falha.
    """
    if not configure_gemini(api_key):
        raise ConnectionError("Falha ao configurar a API do Gemini. Verifique a chave.")

    model = get_gemini_model()
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            # Limpeza aprimorada para extrair o JSON de dentro do texto de resposta
            json_text = response.text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()
            return json_text
        except Exception as e:
            print(f"ERRO na API do Gemini (tentativa {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise

# --- FUNÇÕES DE IA PARA A APLICAÇÃO ---

def enrich_data_with_gemini(df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """
    Usa a IA do Gemini para adicionar informações de endereço e categoria aos pontos em lotes.
    """
    df_copy = df.copy()
    if 'Endereço' not in df_copy.columns:
        df_copy['Endereço'] = ""
    if 'Categoria' not in df_copy.columns:
        df_copy['Categoria'] = ""

    total_rows = len(df_copy)
    progress_bar = st.progress(0, text="A IA está a enriquecer os seus dados (em lotes)...")

    for i in range(0, total_rows, BATCH_SIZE):
        batch = df_copy.iloc[i:i+BATCH_SIZE]

        # Cria uma lista de dicionários para o prompt
        points_to_process = []
        for index, row in batch.iterrows():
            points_to_process.append({
                "id": index,
                "nome": row['Nome'],
                "latitude": row['Latitude'],
                "longitude": row['Longitude']
            })

        try:
            prompt = f"""
            Analise a lista de locais JSON a seguir. Para cada local, forneça o endereço
            completo mais provável e uma categoria (Ex: Serviço Público, Comércio,
            Ponto Turístico, Residencial, Outro).

            Locais:
            {json.dumps(points_to_process, indent=2)}

            Responda APENAS com um array JSON, onde cada objeto contém o "id" original,
            e as chaves "endereco" e "categoria" que você encontrou.
            Exemplo de resposta:
            [
              {{
                "id": 0,
                "endereco": "Praça Sete de Setembro, s/n - Centro, Belo Horizonte - MG, 30130-010, Brasil",
                "categoria": "Ponto Turístico"
              }},
              {{
                "id": 1,
                "endereco": "Av. Afonso Pena, 1500 - Centro, Belo Horizonte - MG, 30130-005, Brasil",
                "categoria": "Serviço Público"
              }}
            ]
            """
            json_text = _call_gemini_api(prompt, api_key)
            results = json.loads(json_text)
            
            for result in results:
                idx = result.get("id")
                if idx is not None and idx in df_copy.index:
                    df_copy.at[idx, 'Endereço'] = result.get("endereco", "Não encontrado")
                    df_copy.at[idx, 'Categoria'] = result.get("categoria", "Não definida")
            
        except Exception as e:
            print(f"ERRO ao enriquecer o lote a partir do índice {i}: {e}")
            # Em caso de erro no lote, marca todos os itens do lote como erro
            for index in batch.index:
                df_copy.at[index, 'Endereço'] = "Erro na busca em lote"
                df_copy.at[index, 'Categoria'] = "Erro na busca em lote"
        
        processed_count = min(i + BATCH_SIZE, total_rows)
        progress_bar.progress(processed_count / total_rows, text=f"Processando: {processed_count}/{total_rows} pontos")

    progress_bar.empty()
    st.success("Dados enriquecidos com sucesso!")
    return df_copy

def standardize_names_with_gemini(df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """
    Usa a IA do Gemini para padronizar os nomes dos locais em lotes.
    """
    df_copy = df.copy()
    total_rows = len(df_copy)
    progress_bar = st.progress(0, text="A IA está a padronizar os nomes (em lotes)...")

    for i in range(0, total_rows, BATCH_SIZE):
        batch = df_copy.iloc[i:i+BATCH_SIZE]

        names_to_process = []
        for index, row in batch.iterrows():
            names_to_process.append({"id": index, "nome_original": row['Nome']})

        try:
            prompt = f"""
            Analise a lista de nomes de locais a seguir. Para cada um, padronize o nome para
            um formato completo e oficial, corrigindo erros de digitação e expandindo
            abreviações (como Av. para Avenida, R. para Rua).

            Nomes:
            {json.dumps(names_to_process, indent=2)}

            Responda APENAS com um array JSON, onde cada objeto contém o "id" original
            e a chave "nome_padronizado".
            Exemplo de resposta:
            [
              {{
                "id": 0,
                "nome_padronizado": "Praça Sete de Setembro"
              }},
              {{
                "id": 1,
                "nome_padronizado": "Avenida Afonso Pena"
              }}
            ]
            """
            json_text = _call_gemini_api(prompt, api_key)
            results = json.loads(json_text)

            for result in results:
                idx = result.get("id")
                standardized_name = result.get("nome_padronizado")
                if idx is not None and standardized_name and idx in df_copy.index:
                    df_copy.at[idx, 'Nome'] = standardized_name
                
        except Exception as e:
            print(f"ERRO ao padronizar o lote a partir do índice {i}: {e}")

        processed_count = min(i + BATCH_SIZE, total_rows)
        progress_bar.progress(processed_count / total_rows, text=f"Padronizando: {processed_count}/{total_rows} nomes")

    progress_bar.empty()
    st.success("Nomes padronizados com sucesso!")
    return df_copy
