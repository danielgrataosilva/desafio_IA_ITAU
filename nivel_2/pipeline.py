"""Pipeline determinístico compartilhado do Nível 2."""

import json
from pathlib import Path

import pandas as pd

MINIMO_OPERACOES_FRACIONAMENTO = 3
LIMITE_SOMA_FRACIONAMENTO = 50_000
LIMITE_VALOR_INDIVIDUAL = 20_000
MINIMO_OPERACOES_VALOR_ATIPICO = 4
MULTIPLICADOR_VALOR_ATIPICO = 5
MOEDAS_ESPERADAS = {'BRL', 'USD'}

def caminho_padrao_dados():
    return Path(__file__).resolve().parents[1] / 'dados' / 'dados_nivel_2.json'


def executar_pipeline(caminho_dados=None):
    """Carrega, trata e aplica as duas regras determinísticas do Nível 2."""
    caminho = Path(caminho_dados) if caminho_dados else caminho_padrao_dados()
    with caminho.open(encoding='utf-8') as arquivo:
        dados_brutos = json.load(arquivo)

    taxa_cambio_usd_brl = dados_brutos['taxa_cambio_usd_brl']
    df_operacoes_bruto = pd.DataFrame(dados_brutos['operacoes'])
    df_operacoes_tratado = df_operacoes_bruto.drop_duplicates().copy()
    df_operacoes_tratado['data'] = pd.to_datetime(df_operacoes_tratado['data'])

    moedas_encontradas = set(df_operacoes_tratado['moeda'].unique())
    moedas_inesperadas = moedas_encontradas - MOEDAS_ESPERADAS
    if moedas_inesperadas:
        raise ValueError(
            f'Moedas n\u00e3o suportadas: {sorted(moedas_inesperadas)}. Esperadas: BRL e USD.'
        )

    tipos_encontrados = sorted(df_operacoes_tratado['tipo'].dropna().unique())

    df_operacoes_tratado['valor_brl'] = df_operacoes_tratado['valor'].astype(float)
    mascara_usd = df_operacoes_tratado['moeda'].eq('USD')
    df_operacoes_tratado.loc[mascara_usd, 'valor_brl'] = (
        df_operacoes_tratado.loc[mascara_usd, 'valor'].astype(float) * taxa_cambio_usd_brl
    )

    df_operacoes_com_data = df_operacoes_tratado.loc[
        df_operacoes_tratado['data'].notna()
    ].copy()
    resumo_fracionamento = (
        df_operacoes_com_data.groupby(['cliente_id', 'data'], as_index=False)
        .agg(
            quantidade_operacoes=('id', 'size'),
            soma_valor_brl=('valor_brl', 'sum'),
            maior_valor_individual_brl=('valor_brl', 'max'),
        )
    )
    resumo_fracionamento['flag_fracionamento'] = (
        (resumo_fracionamento['quantidade_operacoes'] >= MINIMO_OPERACOES_FRACIONAMENTO)
        & (resumo_fracionamento['soma_valor_brl'] > LIMITE_SOMA_FRACIONAMENTO)
        & (resumo_fracionamento['maior_valor_individual_brl'] < LIMITE_VALOR_INDIVIDUAL)
    )
    eventos_fracionamento = resumo_fracionamento.loc[
        resumo_fracionamento['flag_fracionamento']
    ].copy()

    df_operacoes_tratado = df_operacoes_tratado.merge(
        resumo_fracionamento[['cliente_id', 'data', 'flag_fracionamento']],
        on=['cliente_id', 'data'],
        how='left',
        validate='many_to_one',
    )
    df_operacoes_tratado['flag_fracionamento'] = (
        df_operacoes_tratado['flag_fracionamento'].fillna(False).astype(bool)
    )

    perfil_valor_por_cliente = (
        df_operacoes_tratado.groupby('cliente_id', as_index=False)
        .agg(
            quantidade_operacoes_cliente=('id', 'size'),
            mediana_valor_brl=('valor_brl', 'median'),
        )
    )
    df_operacoes_tratado = df_operacoes_tratado.merge(
        perfil_valor_por_cliente,
        on='cliente_id',
        how='left',
        validate='many_to_one',
    )
    df_operacoes_tratado['limite_valor_atipico_brl'] = (
        MULTIPLICADOR_VALOR_ATIPICO * df_operacoes_tratado['mediana_valor_brl']
    )
    df_operacoes_tratado['flag_valor_atipico'] = (
        (df_operacoes_tratado['quantidade_operacoes_cliente'] >= MINIMO_OPERACOES_VALOR_ATIPICO)
        & (df_operacoes_tratado['valor_brl'] > df_operacoes_tratado['limite_valor_atipico_brl'])
    )

    sinais_regra_1_por_cliente = (
        eventos_fracionamento.groupby('cliente_id')
        .size()
        .rename('sinais_regra_1')
    )
    sinais_regra_2_por_cliente = (
        df_operacoes_tratado.loc[df_operacoes_tratado['flag_valor_atipico']]
        .groupby('cliente_id')
        .size()
        .rename('sinais_regra_2')
    )
    ranking_clientes = (
        df_operacoes_tratado.groupby('cliente_id', as_index=False)
        .agg(volume_total_brl=('valor_brl', 'sum'))
        .merge(sinais_regra_1_por_cliente, on='cliente_id', how='left')
        .merge(sinais_regra_2_por_cliente, on='cliente_id', how='left')
    )
    ranking_clientes[['sinais_regra_1', 'sinais_regra_2']] = (
        ranking_clientes[['sinais_regra_1', 'sinais_regra_2']].fillna(0).astype(int)
    )
    ranking_clientes['total_sinalizacoes'] = (
        ranking_clientes['sinais_regra_1'] + ranking_clientes['sinais_regra_2']
    )
    ranking_clientes = ranking_clientes.sort_values(
        ['total_sinalizacoes', 'volume_total_brl'],
        ascending=[False, False],
    ).reset_index(drop=True)

    _validar_resultados(
        df_operacoes_bruto,
        df_operacoes_tratado,
        moedas_inesperadas,
        ranking_clientes,
    )

    return {
        'taxa_cambio_usd_brl': taxa_cambio_usd_brl,
        'tipos_encontrados': tipos_encontrados,
        'df_operacoes_bruto': df_operacoes_bruto,
        'df_operacoes_tratado': df_operacoes_tratado,
        'resumo_fracionamento': resumo_fracionamento,
        'eventos_fracionamento': eventos_fracionamento,
        'perfil_valor_por_cliente': perfil_valor_por_cliente,
        'ranking_clientes': ranking_clientes,
    }


def _validar_resultados(df_bruto, df_tratado, moedas_inesperadas, ranking_clientes):
    assert len(df_bruto) == 322
    assert df_bruto['data'].isna().sum() == 7
    assert len(df_tratado) == 317
    assert df_tratado['cliente_id'].nunique() == 30
    assert df_tratado['data'].isna().sum() == 6
    assert not moedas_inesperadas
    assert (
        ranking_clientes['total_sinalizacoes']
        == ranking_clientes['sinais_regra_1'] + ranking_clientes['sinais_regra_2']
    ).all()
