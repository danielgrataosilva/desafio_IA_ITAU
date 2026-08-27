"""Execucao sequencial, retomavel e auditavel do lote do Nivel 2."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from .agente import analisar_cliente
    from .pipeline import executar_pipeline
except ImportError:  # Execucao direta a partir da pasta nivel_2.
    from agente import analisar_cliente
    from pipeline import executar_pipeline

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
CAMINHO_PADRAO_SAIDA = RAIZ_PROJETO / 'outputs' / 'lote_nivel_2.json'
LIMITE_503_CONSECUTIVOS = 2
NIVEIS_RISCO_VALIDOS = {'baixo', 'm\u00e9dio', 'alto'}


def obter_clientes_top_10():
    """Obtem programaticamente os dez primeiros clientes do ranking deterministico."""
    ranking = executar_pipeline()['ranking_clientes'].head(10).copy()
    ranking.insert(0, 'posicao', range(1, len(ranking) + 1))
    colunas = [
        'posicao',
        'cliente_id',
        'sinais_regra_1',
        'sinais_regra_2',
        'total_sinalizacoes',
        'volume_total_brl',
    ]
    return [
        {
            'posicao': int(linha['posicao']),
            'cliente_id': linha['cliente_id'],
            'sinais_regra_1': int(linha['sinais_regra_1']),
            'sinais_regra_2': int(linha['sinais_regra_2']),
            'total_sinalizacoes': int(linha['total_sinalizacoes']),
            'volume_total_brl': float(linha['volume_total_brl']),
        }
        for _, linha in ranking[colunas].iterrows()
    ]


def carregar_resultados(caminho_saida=CAMINHO_PADRAO_SAIDA):
    """Carrega o arquivo de resultados; ausencia de arquivo representa lote ainda nao iniciado."""
    caminho = Path(caminho_saida)
    if not caminho.exists():
        return []
    conteudo = json.loads(caminho.read_text(encoding='utf-8'))
    if not isinstance(conteudo, dict) or not isinstance(conteudo.get('resultados'), list):
        raise ValueError('Arquivo de resultados invalido: esperado objeto com lista resultados.')
    return conteudo['resultados']


def salvar_resultados(resultados, caminho_saida=CAMINHO_PADRAO_SAIDA):
    """Salva cada estado de forma atomica para preservar resultados ja concluidos."""
    caminho = Path(caminho_saida)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    documento = {
        'versao': 1,
        'atualizado_em_utc': datetime.now(timezone.utc).isoformat(),
        'resultados': resultados,
    }
    temporario = caminho.with_suffix(caminho.suffix + '.tmp')
    temporario.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    temporario.replace(caminho)


def resultado_sucesso_valido(registro):
    return (
        registro.get('status') == 'sucesso'
        and registro.get('nivel_risco') in NIVEIS_RISCO_VALIDOS
        and bool(registro.get('cliente_id'))
    )


def _contem_codigo(erro, codigo):
    return str(codigo) in (erro or '')


def _montar_registro(cliente_ranking, analise):
    parecer = analise.get('parecer') or {}
    metricas = analise.get('metricas') or {}
    status_agente = analise.get('status_final')
    sucesso = status_agente == 'sucesso' and parecer.get('nivel_risco') in NIVEIS_RISCO_VALIDOS
    return {
        **cliente_ranking,
        'status': 'sucesso' if sucesso else 'erro',
        'nivel_risco': parecer.get('nivel_risco'),
        'tipologia_suspeita': parecer.get('tipologia_suspeita'),
        'red_flags': parecer.get('red_flags', []),
        'justificativa': parecer.get('justificativa'),
        'recomendacao_analista': parecer.get('recomendacao_analista'),
        'tools_utilizadas': parecer.get('tools_utilizadas', []),
        'quantidade_chamadas_tools': analise.get('quantidade_chamadas_tools', 0),
        'tokens_entrada': metricas.get('tokens_entrada'),
        'tokens_saida': metricas.get('tokens_saida'),
        'tokens_pensamento': metricas.get('tokens_pensamento'),
        'tokens_totais': metricas.get('tokens_totais'),
        'latencia_segundos': metricas.get('latencia_total_segundos'),
        'retries': analise.get('quantidade_retries', 0),
        'erro_final': analise.get('erro_api'),
    }


def _substituir_registro(resultados, registro):
    for indice, existente in enumerate(resultados):
        if existente.get('cliente_id') == registro['cliente_id']:
            resultados[indice] = registro
            return
    resultados.append(registro)


def executar_lote(caminho_saida=CAMINHO_PADRAO_SAIDA, analisador=analisar_cliente, clientes_ranking=None):
    """Processa clientes em ordem, salva cada resultado e permite retomada segura."""
    clientes = clientes_ranking if clientes_ranking is not None else obter_clientes_top_10()
    resultados = carregar_resultados(caminho_saida)
    resumo_execucao = {
        'clientes_planejados': len(clientes),
        'clientes_processados_agora': [],
        'clientes_pulados_por_sucesso': [],
        'interrompido': False,
        'motivo_interrupcao': None,
    }
    falhas_503_consecutivas = 0

    for cliente in clientes:
        existente = next(
            (item for item in resultados if item.get('cliente_id') == cliente['cliente_id']),
            None,
        )
        if existente and resultado_sucesso_valido(existente):
            resumo_execucao['clientes_pulados_por_sucesso'].append(cliente['cliente_id'])
            falhas_503_consecutivas = 0
            continue

        try:
            analise = analisador(cliente['cliente_id'])
        except Exception as erro:  # Falha local tambem precisa ser persistida.
            analise = {
                'status_final': 'erro_local',
                'parecer': None,
                'quantidade_chamadas_tools': 0,
                'metricas': {},
                'quantidade_retries': 0,
                'erro_api': f'Erro local controlado: {erro}',
            }

        registro = _montar_registro(cliente, analise)
        _substituir_registro(resultados, registro)
        salvar_resultados(resultados, caminho_saida)
        resumo_execucao['clientes_processados_agora'].append(cliente['cliente_id'])

        erro_final = registro['erro_final']
        if _contem_codigo(erro_final, 429):
            resumo_execucao['interrompido'] = True
            resumo_execucao['motivo_interrupcao'] = 'quota_429'
            break
        if _contem_codigo(erro_final, 503):
            falhas_503_consecutivas += 1
            if falhas_503_consecutivas >= LIMITE_503_CONSECUTIVOS:
                resumo_execucao['interrompido'] = True
                resumo_execucao['motivo_interrupcao'] = 'indisponibilidade_503_generalizada'
                break
        else:
            falhas_503_consecutivas = 0

    resumo_execucao['metricas_agregadas'] = calcular_metricas(resultados)
    return resumo_execucao


def calcular_metricas(resultados):
    """Calcula metricas somente a partir dos registros persistidos e disponiveis."""
    if not resultados:
        return {
            'clientes_com_sucesso': 0,
            'clientes_com_erro': 0,
            'tokens_totais_consumidos': 0,
            'tokens_medios_por_sucesso': None,
            'latencia_total_segundos': 0.0,
            'latencia_media_segundos': None,
            'retries_totais': 0,
            'distribuicao_nivel_risco': {},
            'custo_monetario': None,
            'limitacao_custo': 'O SDK/modelo nao disponibiliza custo monetario diretamente.',
        }

    tabela = pd.DataFrame(resultados)
    sucesso = tabela.loc[tabela['status'].eq('sucesso')]
    tokens = pd.to_numeric(tabela['tokens_totais'], errors='coerce')
    latencias = pd.to_numeric(tabela['latencia_segundos'], errors='coerce')
    retries = pd.to_numeric(tabela['retries'], errors='coerce').fillna(0)
    tokens_sucesso = pd.to_numeric(sucesso['tokens_totais'], errors='coerce')

    return {
        'clientes_com_sucesso': int(tabela['status'].eq('sucesso').sum()),
        'clientes_com_erro': int(tabela['status'].eq('erro').sum()),
        'tokens_totais_consumidos': int(tokens.fillna(0).sum()),
        'tokens_medios_por_sucesso': (
            float(tokens_sucesso.mean()) if tokens_sucesso.notna().any() else None
        ),
        'latencia_total_segundos': float(latencias.fillna(0).sum()),
        'latencia_media_segundos': float(latencias.mean()) if latencias.notna().any() else None,
        'retries_totais': int(retries.sum()),
        'distribuicao_nivel_risco': {
            str(nivel): int(quantidade)
            for nivel, quantidade in sucesso['nivel_risco'].value_counts().items()
        },
        'custo_monetario': None,
        'limitacao_custo': 'O SDK/modelo nao disponibiliza custo monetario diretamente.',
    }
