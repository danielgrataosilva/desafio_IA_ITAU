"""Agente inicial do Nivel 2 com function calling manual e auditavel."""

import json
import os
import re
import time
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

try:
    from . import tools as tools_nivel_2
    from .pipeline import executar_pipeline
except ImportError:  # Execucao direta a partir da pasta nivel_2.
    import tools as tools_nivel_2
    from pipeline import executar_pipeline

MAX_CHAMADAS_TOOLS = 3
MAX_TENTATIVAS_API = 2
ESPERA_RETRY_SEGUNDOS = 1
CODIGOS_TRANSITORIOS = {429, 503}


class ParecerAgente(BaseModel):
    cliente_id: str
    nivel_risco: Literal['baixo', 'm\u00e9dio', 'alto']
    tipologia_suspeita: str
    red_flags: list[str]
    justificativa: str
    tools_utilizadas: list[str]
    recomendacao_analista: str | None = None


def _carregar_configuracao():
    raiz = Path(__file__).resolve().parents[1]
    load_dotenv(raiz / '.env')
    return os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')


def _declaracoes_tools():
    declaracoes = [
        types.FunctionDeclaration(
            name='historico_cliente',
            description=(
                'Retorna um resumo agregado do cliente: quantidade de opera\u00e7\u00f5es, volume, '
                'mediana, sinaliza\u00e7\u00f5es e intervalo de datas dispon\u00edveis.'
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'cliente_id': types.Schema(
                        type=types.Type.STRING,
                        description='Identificador do cliente a analisar.',
                    )
                },
                required=['cliente_id'],
            ),
        ),
        types.FunctionDeclaration(
            name='operacoes_do_dia',
            description=(
                'Retorna opera\u00e7\u00f5es de um cliente em uma data conhecida, com valores, canais, '
                'contrapartes e flags determin\u00edsticas. Use somente quando possuir uma data concreta.'
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'cliente_id': types.Schema(type=types.Type.STRING),
                    'data': types.Schema(
                        type=types.Type.STRING,
                        description='Data no formato AAAA-MM-DD.',
                    ),
                },
                required=['cliente_id', 'data'],
            ),
        ),
        types.FunctionDeclaration(
            name='perfil_canal',
            description=(
                'Retorna distribui\u00e7\u00e3o de canais, percentuais e volumes de um cliente.'
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'cliente_id': types.Schema(type=types.Type.STRING)
                },
                required=['cliente_id'],
            ),
        ),
    ]
    return types.Tool(function_declarations=declaracoes)


def _contexto_inicial(cliente_id):
    contexto = executar_pipeline()
    ranking = contexto['ranking_clientes']
    linha = ranking.loc[ranking['cliente_id'].eq(cliente_id)]
    if linha.empty:
        return None

    dados = linha.iloc[0]
    tipos_sinalizacao = []
    if int(dados['sinais_regra_1']) > 0:
        tipos_sinalizacao.append('fracionamento')
    if int(dados['sinais_regra_2']) > 0:
        tipos_sinalizacao.append('valor_atipico')
    return {
        'cliente_id': cliente_id,
        'tipos_sinalizacao_detectados': tipos_sinalizacao,
        'quantidade_sinais_regra_1': int(dados['sinais_regra_1']),
        'quantidade_sinais_regra_2': int(dados['sinais_regra_2']),
    }


def _prompt_inicial(contexto):
    return f"""Voc\u00ea atua como apoio \u00e0 triagem humana de preven\u00e7\u00e3o \u00e0 lavagem de dinheiro.

Recebeu apenas este contexto determin\u00edstico m\u00ednimo:
{json.dumps(contexto, ensure_ascii=False, indent=2)}

Decida autonomamente se precisa de uma ou mais tools para compreender o caso. N\u00e3o calcule, recalcule ou altere valores, medianas, limites ou flags. N\u00e3o invente fatos, datas, legisla\u00e7\u00e3o, regulamenta\u00e7\u00e3o, inten\u00e7\u00e3o ou motiva\u00e7\u00e3o do cliente. Use `operacoes_do_dia` somente quando tiver uma data concreta fornecida por fatos ou por uma tool. Ferramentas devem ser escolhidas por necessidade, n\u00e3o chamadas automaticamente.

Ao terminar as consultas necess\u00e1rias, aguarde a solicita\u00e7\u00e3o de parecer final estruturado. O parecer deve usar linguagem de possibilidade, apoiar a triagem humana e n\u00e3o concluir definitivamente lavagem de dinheiro.
"""


def _prompt_final(contexto, tools_utilizadas, limite_atingido):
    observacao_limite = (
        'O limite de chamadas de tools foi atingido; use somente o contexto já disponível. '
        if limite_atingido
        else ''
    )
    return f"""Produza agora o parecer final estruturado para o cliente {contexto['cliente_id']}.

{observacao_limite}As únicas evidências permitidas são o contexto inicial e as respostas das tools já presentes nesta conversa. Cada fato específico citado precisa estar diretamente nessas evidências: valores, datas, canais, identificadores de operação, contrapartes, quantidades e flags. Não complete lacunas por inferência, memória ou conhecimento externo.

Se uma data foi consultada sem os detalhes de outras datas, não cite valores, canais, contrapartes ou operações dessas outras datas. Se um detalhe relevante não foi consultado, declare que ele não foi consultado ou que não há evidência suficiente, em vez de estimá-lo. Não recalcule valores, não invente informações e não atribua intenção, motivação, legislação ou regulamentação. Linguagem interpretativa deve ser condicional, por exemplo 'pode ser compatível com' ou 'merece análise'. Declare que se trata de apoio à triagem humana, não de conclusão definitiva.

As tools efetivamente usadas foram: {json.dumps(tools_utilizadas, ensure_ascii=False)}.
Retorne exatamente os campos do schema solicitado, incluindo essa mesma lista em `tools_utilizadas`.
"""


PADRAO_DATA_ISO = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
PADRAO_VALOR_MONETARIO = re.compile(r'R\$\s*([0-9][0-9.\s]*(?:,[0-9]{1,2})?)')


def _normalizar_valor_monetario(texto):
    """Normaliza formatos brasileiros e decimais para uma comparação simples."""
    texto = str(texto).replace(' ', '')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return round(float(texto), 2)
    except ValueError:
        return None


def _coletar_evidencias_especificas(valor, datas, valores):
    """Coleta datas ISO e valores numéricos presentes nas evidências consultadas."""
    if isinstance(valor, dict):
        for item in valor.values():
            _coletar_evidencias_especificas(item, datas, valores)
    elif isinstance(valor, list):
        for item in valor:
            _coletar_evidencias_especificas(item, datas, valores)
    elif isinstance(valor, str):
        datas.update(PADRAO_DATA_ISO.findall(valor))
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
        valores.add(round(float(valor), 2))


def _validar_rastreabilidade_basica(contexto, tools_chamadas, parecer):
    """Sinaliza datas e valores monetários citados sem evidência consultada.

    A checagem é deliberadamente limitada: ela não valida semântica, canais ou
    contrapartes. Sem alerta automático não equivale a comprovação factual; a
    revisão humana continua necessária.
    """
    datas_evidencia, valores_evidencia = set(), set()
    _coletar_evidencias_especificas(contexto, datas_evidencia, valores_evidencia)
    for chamada in tools_chamadas:
        if chamada.get('executada'):
            _coletar_evidencias_especificas(
                chamada.get('resultado'), datas_evidencia, valores_evidencia
            )

    texto_parecer = json.dumps(parecer, ensure_ascii=False)
    datas_sem_evidencia = sorted(set(PADRAO_DATA_ISO.findall(texto_parecer)) - datas_evidencia)
    valores_citados = {
        valor
        for item in PADRAO_VALOR_MONETARIO.finditer(texto_parecer)
        if (valor := _normalizar_valor_monetario(item.group(1))) is not None
    }
    valores_sem_evidencia = sorted(valores_citados - valores_evidencia)
    alertas = []
    if datas_sem_evidencia:
        alertas.append(f'Datas sem evidência consultada: {datas_sem_evidencia}.')
    if valores_sem_evidencia:
        alertas.append(
            f'Valores monetários sem evidência consultada: '
            f'{[f"R$ {valor:,.2f}" for valor in valores_sem_evidencia]}.'
        )
    return {
        'status': 'com_alertas' if alertas else 'sem_alertas_automaticos',
        'alertas': alertas,
        'limitacao': (
            'A checagem cobre apenas datas ISO e valores monetários; revisão humana '
            'permanece necessária para canais, contrapartes e demais alegações.'
        ),
    }


def _validar_argumentos(nome, argumentos, cliente_id):
    esquemas = {
        'historico_cliente': {'cliente_id'},
        'operacoes_do_dia': {'cliente_id', 'data'},
        'perfil_canal': {'cliente_id'},
    }
    if nome not in esquemas:
        return False, 'Tool n\u00e3o registrada.', None
    if not isinstance(argumentos, dict):
        return False, 'Argumentos devem ser um objeto.', None
    if set(argumentos) != esquemas[nome]:
        return False, f'Argumentos inv\u00e1lidos para {nome}.', None
    if not isinstance(argumentos.get('cliente_id'), str) or argumentos['cliente_id'] != cliente_id:
        return False, 'cliente_id deve corresponder ao caso em an\u00e1lise.', None
    if nome == 'operacoes_do_dia' and not isinstance(argumentos.get('data'), str):
        return False, 'data deve ser uma string no formato AAAA-MM-DD.', None
    return True, None, argumentos


def _executar_tool(nome, argumentos, cliente_id):
    valido, erro, argumentos_validados = _validar_argumentos(nome, argumentos, cliente_id)
    if not valido:
        return {'erro': erro}, False
    funcoes = {
        'historico_cliente': tools_nivel_2.historico_cliente,
        'operacoes_do_dia': tools_nivel_2.operacoes_do_dia,
        'perfil_canal': tools_nivel_2.perfil_canal,
    }
    return funcoes[nome](**argumentos_validados), True


def _chamar_com_retry(cliente_gemini, modelo, conteudos, configuracao):
    tentativas = []
    for tentativa in range(1, MAX_TENTATIVAS_API + 1):
        try:
            resposta = cliente_gemini.models.generate_content(
                model=modelo,
                contents=conteudos,
                config=configuracao,
            )
            tentativas.append({'tentativa': tentativa, 'status': 'sucesso'})
            return resposta, tentativas, None
        except httpx.TimeoutException as erro:
            tentativas.append({'tentativa': tentativa, 'status': 'timeout', 'erro': str(erro)})
            return None, tentativas, str(erro)
        except (errors.ServerError, errors.ClientError) as erro:
            codigo = getattr(erro, 'code', None)
            tentativas.append(
                {'tentativa': tentativa, 'status': 'erro_api', 'codigo': codigo, 'erro': str(erro)}
            )
            if codigo not in CODIGOS_TRANSITORIOS or tentativa == MAX_TENTATIVAS_API:
                return None, tentativas, str(erro)
            tentativas.append(
                {
                    'tentativa': tentativa + 1,
                    'status': 'retry_agendado',
                    'espera_segundos': ESPERA_RETRY_SEGUNDOS,
                }
            )
            time.sleep(ESPERA_RETRY_SEGUNDOS)


def _acumular_uso(metricas, resposta):
    uso = getattr(resposta, 'usage_metadata', None)
    if uso is None:
        return
    for campo, atributo in (
        ('tokens_entrada', 'prompt_token_count'),
        ('tokens_saida', 'candidates_token_count'),
        ('tokens_totais', 'total_token_count'),
    ):
        valor = getattr(uso, atributo, None)
        if valor is not None:
            metricas[campo] += int(valor)
    pensamentos = getattr(uso, 'thoughts_token_count', None)
    if pensamentos is not None:
        metricas['tokens_pensamento'] += int(pensamentos)
        metricas['pensamentos_disponiveis'] = True


def analisar_cliente(cliente_id):
    """Executa uma analise agentica para um unico cliente, com no maximo tres tool calls."""
    inicio = time.perf_counter()
    contexto = _contexto_inicial(cliente_id)
    metricas = {
        'tokens_entrada': 0,
        'tokens_saida': 0,
        'tokens_pensamento': 0,
        'tokens_totais': 0,
        'pensamentos_disponiveis': False,
    }
    resultado = {
        'status_final': 'nao_executado',
        'modelo_utilizado': None,
        'contexto_inicial': contexto,
        'tools_chamadas': [],
        'quantidade_chamadas_tools': 0,
        'parecer': None,
        'validacao_factual': None,
        'metricas': None,
        'erro_api': None,
        'quantidade_retries': 0,
        'tentativas_api': [],
        'limite_tools_atingido': False,
    }
    if contexto is None:
        resultado['status_final'] = 'cliente_inexistente'
        resultado['erro_api'] = 'cliente_id inexistente na base tratada.'
        resultado['metricas'] = _finalizar_metricas(metricas, inicio)
        return resultado

    chave_api, modelo = _carregar_configuracao()
    resultado['modelo_utilizado'] = modelo
    if not chave_api or not modelo:
        resultado['status_final'] = 'configuracao_ausente'
        resultado['erro_api'] = 'GEMINI_API_KEY ou GEMINI_MODEL n\u00e3o configurados.'
        resultado['metricas'] = _finalizar_metricas(metricas, inicio)
        return resultado

    cliente_gemini = genai.Client(api_key=chave_api)
    tool = _declaracoes_tools()
    configuracao_tools = types.GenerateContentConfig(
        tools=[tool],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    conteudos = [
        types.Content(role='user', parts=[types.Part(text=_prompt_inicial(contexto))])
    ]

    while resultado['quantidade_chamadas_tools'] < MAX_CHAMADAS_TOOLS:
        resposta, tentativas, erro = _chamar_com_retry(
            cliente_gemini, modelo, conteudos, configuracao_tools
        )
        resultado['tentativas_api'].extend(tentativas)
        resultado['quantidade_retries'] += sum(
            tentativa['status'] == 'retry_agendado' for tentativa in tentativas
        )
        if resposta is None:
            resultado['status_final'] = 'erro_api'
            resultado['erro_api'] = erro
            resultado['metricas'] = _finalizar_metricas(metricas, inicio)
            return resultado
        _acumular_uso(metricas, resposta)

        chamadas = list(getattr(resposta, 'function_calls', None) or [])
        if not chamadas:
            conteudos.append(resposta.candidates[0].content)
            break

        conteudos.append(resposta.candidates[0].content)
        respostas_tools = []
        for chamada in chamadas:
            if resultado['quantidade_chamadas_tools'] >= MAX_CHAMADAS_TOOLS:
                resultado['limite_tools_atingido'] = True
                break
            nome = chamada.name
            argumentos = dict(chamada.args or {})
            retorno, executada = _executar_tool(nome, argumentos, cliente_id)
            resultado['tools_chamadas'].append(
                {'nome': nome, 'argumentos': argumentos, 'resultado': retorno, 'executada': executada}
            )
            resultado['quantidade_chamadas_tools'] += 1
            if executada:
                respostas_tools.append(
                    types.Part.from_function_response(name=nome, response={'result': retorno})
                )

        if respostas_tools:
            conteudos.append(types.Content(role='user', parts=respostas_tools))
        if resultado['quantidade_chamadas_tools'] >= MAX_CHAMADAS_TOOLS:
            resultado['limite_tools_atingido'] = True
            break

    nomes_tools = [
        chamada['nome'] for chamada in resultado['tools_chamadas'] if chamada['executada']
    ]
    conteudos.append(
        types.Content(
            role='user',
            parts=[
                types.Part(
                    text=_prompt_final(
                        contexto,
                        nomes_tools,
                        resultado['limite_tools_atingido'],
                    )
                )
            ],
        )
    )
    configuracao_final = types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=ParecerAgente,
    )
    resposta_final, tentativas_finais, erro_final = _chamar_com_retry(
        cliente_gemini, modelo, conteudos, configuracao_final
    )
    resultado['tentativas_api'].extend(tentativas_finais)
    resultado['quantidade_retries'] += sum(
        tentativa['status'] == 'retry_agendado' for tentativa in tentativas_finais
    )
    if resposta_final is None:
        resultado['status_final'] = 'erro_api'
        resultado['erro_api'] = erro_final
        resultado['metricas'] = _finalizar_metricas(metricas, inicio)
        return resultado

    _acumular_uso(metricas, resposta_final)
    try:
        # Pydantic valida estrutura, tipos e enum; não comprova que o texto é factual.
        parecer = ParecerAgente.model_validate_json(resposta_final.text)
        if parecer.cliente_id != cliente_id:
            raise ValueError('cliente_id do parecer difere do cliente analisado.')
        if parecer.tools_utilizadas != nomes_tools:
            parecer = parecer.model_copy(update={'tools_utilizadas': nomes_tools})
        resultado['parecer'] = parecer.model_dump()
        resultado['validacao_factual'] = _validar_rastreabilidade_basica(
            contexto,
            resultado['tools_chamadas'],
            resultado['parecer'],
        )
        if resultado['validacao_factual']['alertas']:
            resultado['status_final'] = 'resposta_com_alertas_factualidade'
            resultado['erro_api'] = 'Parecer estruturado com citações sem evidência consultada.'
        else:
            resultado['status_final'] = 'sucesso'
    except (ValidationError, ValueError) as erro:
        resultado['status_final'] = 'resposta_invalida'
        resultado['erro_api'] = str(erro)
    resultado['metricas'] = _finalizar_metricas(metricas, inicio)
    return resultado


def _finalizar_metricas(metricas, inicio):
    return {
        'tokens_entrada': metricas['tokens_entrada'] or None,
        'tokens_saida': metricas['tokens_saida'] or None,
        'tokens_pensamento': (
            metricas['tokens_pensamento'] if metricas['pensamentos_disponiveis'] else None
        ),
        'tokens_totais': metricas['tokens_totais'] or None,
        'latencia_total_segundos': round(time.perf_counter() - inicio, 3),
    }
