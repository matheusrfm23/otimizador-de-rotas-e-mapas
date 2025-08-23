# src/optimizer.py
# Responsável pela lógica de otimização de rotas offline com Google OR-Tools.
# VERSÃO 3.0.2: Refatorado para usar a função haversine_distance do módulo utils.

import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# Importa a função de cálculo de distância do nosso módulo de utilitários
from src.utils import haversine_distance

def ortools_optimizer(df: pd.DataFrame, start_node: int = 0, end_node: int = 0) -> pd.DataFrame:
    """
    Otimiza a rota usando o Google OR-Tools para resolver o Problema do 
    Caixeiro Viajante (TSP).

    Args:
        df (pd.DataFrame): DataFrame com os pontos a serem otimizados.
        start_node (int): O índice do ponto de partida no DataFrame.
        end_node (int): O índice do ponto de chegada no DataFrame.

    Returns:
        pd.DataFrame: Um novo DataFrame com os pontos na ordem otimizada.
                      Retorna o DataFrame original se a otimização falhar.
    """
    if len(df) <= 2:
        # Não há pontos intermediários para otimizar, retorna a ordem original.
        return df

    coords = df[['Latitude', 'Longitude']].values.tolist()
    num_locations = len(coords)
    num_vehicles = 1

    # Cria o gerenciador de índices e o modelo de roteamento.
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, [start_node], [end_node])
    routing = pywrapcp.RoutingModel(manager)

    # Cria e registra o "callback" de distância.
    # Esta função interna será chamada pelo OR-Tools para saber a distância entre dois pontos.
    def distance_callback(from_index, to_index):
        """Retorna a distância entre dois nós usando a função haversine."""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        lat1, lon1 = coords[from_node]
        lat2, lon2 = coords[to_node]
        # AQUI ESTÁ A MUDANÇA: Usando a função importada de utils.py
        return haversine_distance(lat1, lon1, lat2, lon2)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define o custo da viagem como sendo a nossa distância.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Define os parâmetros da busca para encontrar a melhor solução.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(5)

    # Executa a otimização.
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        # Extrai a ordem otimizada dos índices do resultado.
        route_indices = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route_indices.append(node_index)
            index = solution.Value(routing.NextVar(index))
        
        # Adiciona o último nó (ponto final) que o loop não inclui.
        route_indices.append(manager.IndexToNode(index))
        
        # Reordena o DataFrame original com base na lista de índices otimizada.
        optimized_df = df.iloc[route_indices].reset_index(drop=True)
        return optimized_df
    else:
        # Se não encontrar solução, retorna o DataFrame original.
        return df

