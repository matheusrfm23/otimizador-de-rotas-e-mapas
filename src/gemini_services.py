# src/gemini_services.py
# Módulo para todas as interações com a API do Google Gemini.
# VERSÃO 3.0.4: Refatorado para usar utils.haversine_distance e código limpo.

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

    Returns:
        bool: True se a configuração for bem-sucedida, False caso contrário.
    """
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
        if not api_key:
            # Não usamos st.error aqui para não poluir a interface.
            # O erro será tratado por quem chama a função.
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
            # Extrai o texto JSON da resposta, removendo marcadores de código.
            json_text = response.text.strip().replace("```json", "").replace("```", "")
            return json_text
        except Exception as e:
            print(f"ERRO na API do Gemini (tentativa {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay) # Espera antes de tentar novamente
            else:
                raise # Lança o erro após a última tentativa

# --- FUNÇÕES DE IA PARA A APLICAÇÃO ---

def enrich_data_with_gemini(df: pd.DataFrame) -> pd.DataFrame:
    """
    Usa a IA do Gemini para adicionar informações de endereço e categoria aos pontos.
    """
    if 'Endereço' not in df.columns:
        df['Endereço'] = ""
    if 'Categoria' not in df.columns:
        df['Categoria'] = ""

    for index, row in df.iterrows():
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
            
            df.at[index, 'Endereço'] = data.get("endereco", "Não encontrado")
            df.at[index, 'Categoria'] = data.get("categoria", "Não definida")
            
        except Exception as e:
            print(f"ERRO ao enriquecer a linha {index}: {e}")
            df.at[index, 'Endereço'] = "Erro na busca"
            df.at[index, 'Categoria'] = "Erro na busca"
    
    st.success("Dados enriquecidos com sucesso!")
    return df

def standardize_names_with_gemini(df: pd.DataFrame) -> pd.DataFrame:
    """
    Usa a IA do Gemini para padronizar os nomes dos locais.
    """
    for index, row in df.iterrows():
        try:
            prompt = f"""
            Analise o seguinte nome de local: "{row['Nome']}".
            Padronize este nome para um formato completo e oficial. Corrija erros 
            de digitação e expanda abreviações (como Av. para Avenida, R. para Rua).
            Responda APENAS com um objeto JSON contendo a chave "nome_padronizado".
            Exemplo para "Pça Sete": {{"nome_padronizado": "Praça Sete de Setembro"}}
            """
            json_text = _call_gemini_api(prompt)
            data = json.loads(json_text)
            
            standardized_name = data.get("nome_padronizado")
            if standardized_name:
                df.at[index, 'Nome'] = standardized_name
                
        except Exception as e:
            print(f"ERRO ao padronizar o nome na linha {index}: {e}")

    st.success("Nomes padronizados com sucesso!")
    return df

# ... (As outras funções de IA como find_duplicates, refine_locations e repair_dataframe
# serão adicionadas nos próximos passos para mantermos o foco) ...
