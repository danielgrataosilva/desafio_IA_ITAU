"""Tools determinísticas para consulta da base tratada do Nível 2."""

from functools import lru_cache

import pandas as pd

try:
    from .pipeline import executar_pipeline
except ImportError:  # Execução direta a partir da pasta nivel_2.
    from pipeline import executar_pipeline


@lru_cache(maxsize=1)
def _contexto():
    return executar_pipeline()


def _numero(valor):
    return float(valor)


def _data_iso(valor):
    if pd.isna(valor):
        return None
    return pd.Timestamp(valor).date().isoformat()


def _cliente_inexistente(cliente_id):
    return {
        'encontrado': False,
        'cliente_id': cliente_id,
        'erro': 'cliente_id inexistente na base tratada.',
    }


def historico_cliente(cliente_id):
    """Retorna o histórico agregado e determinístico de um cliente."""
    contexto = _contexto()
    ranking = contexto['ranking_clientes']
    linha_ranking = ranking.loc[ranking['cliente_id'].eq(cliente_id)]
    if linha_ranking.empty:
        return _cliente_inexistente(cliente_id)

    operacoes = contexto['df_operacoes_tratado'].loc[
        contexto['df_operacoes_tratado']['cliente_id'].eq(cliente_id)
    ]
    linha = linha_ranking.iloc[0]
    datas_disponiveis = operacoes['data'].dropna()
    datas_operacoes_atipicas = sorted(
        {
            _data_iso(data)
            for data in operacoes.loc[operacoes['flag_valor_atipico'], 'data'].dropna()
        }
    )
    eventos_fracionamento = contexto['eventos_fracionamento'].loc[
        contexto['eventos_fracionamento']['cliente_id'].eq(cliente_id)
    ]
    datas_eventos_fracionamento = sorted(
        {_data_iso(data) for data in eventos_fracionamento['data'].dropna()}
    )

    return {
        'encontrado': True,
        'cliente_id': cliente_id,
        'quantidade_operacoes': int(len(operacoes)),
        'volume_total_brl': _numero(linha['volume_total_brl']),
        'mediana_valor_brl': _numero(operacoes['valor_brl'].median()),
        'eventos_fracionamento': int(linha['sinais_regra_1']),
        'operacoes_atipicas': int(linha['sinais_regra_2']),
        'total_sinalizacoes': int(linha['total_sinalizacoes']),
        'primeira_data_disponivel': _data_iso(datas_disponiveis.min()) if not datas_disponiveis.empty else None,
        'ultima_data_disponivel': _data_iso(datas_disponiveis.max()) if not datas_disponiveis.empty else None,
        'datas_operacoes_atipicas': datas_operacoes_atipicas,
        'datas_eventos_fracionamento': datas_eventos_fracionamento,
    }


def operacoes_do_dia(cliente_id, data):
    """Retorna operações e flags de um cliente em uma data, sem chamar serviços externos."""
    contexto = _contexto()
    operacoes = contexto['df_operacoes_tratado']
    if not operacoes['cliente_id'].eq(cliente_id).any():
        resposta = _cliente_inexistente(cliente_id)
        resposta.update({'data_consultada': str(data), 'quantidade_operacoes': 0, 'operacoes': []})
        return resposta

    try:
        data_consultada = pd.to_datetime(data, errors='raise')
        if pd.isna(data_consultada):
            raise ValueError('data ausente')
        data_consultada = pd.Timestamp(data_consultada).normalize()
    except (TypeError, ValueError, OverflowError):
        return {
            'encontrado': False,
            'cliente_id': cliente_id,
            'data_consultada': str(data),
            'erro': 'data inválida; informe uma data reconhecida pelo Pandas.',
            'quantidade_operacoes': 0,
            'operacoes': [],
        }

    resultado = operacoes.loc[
        operacoes['cliente_id'].eq(cliente_id) & operacoes['data'].eq(data_consultada),
        [
            'id', 'data', 'valor', 'moeda', 'valor_brl', 'canal', 'tipo', 'contraparte',
            'flag_fracionamento', 'flag_valor_atipico',
        ],
    ].sort_values('id')

    registros = [
        {
            'id': linha['id'],
            'data': _data_iso(linha['data']),
            'valor': _numero(linha['valor']),
            'moeda': linha['moeda'],
            'valor_brl': _numero(linha['valor_brl']),
            'canal': linha['canal'],
            'tipo': linha['tipo'],
            'contraparte': linha['contraparte'],
            'flag_fracionamento': bool(linha['flag_fracionamento']),
            'flag_valor_atipico': bool(linha['flag_valor_atipico']),
        }
        for _, linha in resultado.iterrows()
    ]
    return {
        'encontrado': True,
        'cliente_id': cliente_id,
        'data_consultada': _data_iso(data_consultada),
        'quantidade_operacoes': len(registros),
        'operacoes': registros,
        'mensagem': None if registros else 'Nenhuma opera\u00e7\u00e3o encontrada para o cliente na data informada.',
    }


def perfil_canal(cliente_id):
    """Retorna distribuição de canais e volumes de um cliente em estruturas JSON-serializáveis."""
    contexto = _contexto()
    operacoes = contexto['df_operacoes_tratado'].loc[
        contexto['df_operacoes_tratado']['cliente_id'].eq(cliente_id)
    ]
    if operacoes.empty:
        return _cliente_inexistente(cliente_id)

    perfil = (
        operacoes.groupby('canal', as_index=False)
        .agg(
            quantidade_operacoes=('id', 'size'),
            volume_total_brl=('valor_brl', 'sum'),
        )
    )
    perfil['percentual_uso'] = (
        perfil['quantidade_operacoes'] / len(operacoes) * 100
    )
    perfil = perfil.sort_values('canal').reset_index(drop=True)
    canal_mais_utilizado = perfil.sort_values(
        ['quantidade_operacoes', 'canal'], ascending=[False, True]
    ).iloc[0]['canal']
    canal_maior_volume = perfil.sort_values(
        ['volume_total_brl', 'canal'], ascending=[False, True]
    ).iloc[0]['canal']

    return {
        'encontrado': True,
        'cliente_id': cliente_id,
        'quantidade_total_operacoes': int(len(operacoes)),
        'canais': [
            {
                'canal': linha['canal'],
                'quantidade_operacoes': int(linha['quantidade_operacoes']),
                'percentual_uso': _numero(linha['percentual_uso']),
                'volume_total_brl': _numero(linha['volume_total_brl']),
            }
            for _, linha in perfil.iterrows()
        ],
        'canal_mais_utilizado': canal_mais_utilizado,
        'canal_maior_volume': canal_maior_volume,
    }
