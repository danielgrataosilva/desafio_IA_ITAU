"""Confronto auditável entre sinais determinísticos e pareceres LLM do Nível 2.

Este módulo não chama a API. Ele compara somente o ranking do pipeline com os
registros já persistidos pelo lote.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from .pipeline import executar_pipeline
except ImportError:  # Execução direta a partir da pasta nivel_2.
    from pipeline import executar_pipeline

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
CAMINHO_PADRAO_LOTE = RAIZ_PROJETO / "outputs" / "lote_nivel_2_gemini_3_6_flash.json"
CAMINHO_PADRAO_SAIDA = RAIZ_PROJETO / "outputs" / "confronto_nivel_2.json"

CRITERIO_SINTETICO = {
    "mapeamento": {
        "0": "baixo",
        "1": "médio",
        "2_ou_mais": "alto",
    },
    "finalidade": "Critério sintético criado exclusivamente para permitir o confronto solicitado no desafio.",
    "nao_representa": [
        "regra real de PLD",
        "regulação",
        "metodologia do Itaú",
    ],
    "ressalvas": [
        "Quantidade de sinalizações não equivale necessariamente ao risco real.",
        "Divergência entre regra e agente não significa automaticamente que o agente errou.",
        "As regras determinísticas são simplificadas e podem gerar falsos positivos.",
    ],
}
NIVEIS_RISCO_VALIDOS = {"baixo", "médio", "alto"}


def risco_esperado_regras(total_sinalizacoes):
    """Aplica exclusivamente o mapeamento sintético documentado neste módulo."""
    total = int(total_sinalizacoes)
    if total == 0:
        return "baixo"
    if total == 1:
        return "médio"
    return "alto"


def carregar_registros_lote(caminho_lote=CAMINHO_PADRAO_LOTE):
    """Lê registros persistidos; ausência do arquivo equivale a lote ainda não iniciado."""
    caminho = Path(caminho_lote)
    if not caminho.exists():
        return []
    documento = json.loads(caminho.read_text(encoding="utf-8"))
    registros = documento.get("resultados") if isinstance(documento, dict) else None
    if not isinstance(registros, list):
        raise ValueError("Arquivo de lote inválido: esperado objeto com lista resultados.")
    return registros


def _motivo_nao_comparavel(registro):
    if registro is None:
        return "Sem registro persistido no lote; LLM indisponível para confronto."
    if registro.get("status_validacao_factual") == "com_alertas":
        return "Resposta com alerta factual; não pode ser tratada como parecer válido."
    erro = registro.get("erro_final") or ""
    if "429" in erro:
        return "Erro técnico 429/quota; parecer final indisponível."
    if "503" in erro:
        return "Erro técnico 503; parecer final indisponível."
    if registro.get("status") != "sucesso":
        return "Status do lote não é sucesso; parecer final indisponível para confronto."
    if registro.get("status_validacao_factual") != "sem_alertas_automaticos":
        return "Validação factual ausente ou não aprovada."
    if registro.get("nivel_risco") not in NIVEIS_RISCO_VALIDOS:
        return "Nível de risco da LLM ausente ou inválido."
    return None


def construir_tabela_confronto(ranking_clientes, registros_lote):
    """Monta os dez casos do ranking, inclusive os indisponíveis para confronto."""
    ranking = ranking_clientes.head(10).copy().reset_index(drop=True)
    ranking.insert(0, "posicao", range(1, len(ranking) + 1))
    por_cliente = {registro.get("cliente_id"): registro for registro in registros_lote}
    linhas = []

    for _, linha in ranking.iterrows():
        cliente_id = linha["cliente_id"]
        registro = por_cliente.get(cliente_id)
        motivo = _motivo_nao_comparavel(registro)
        comparavel = motivo is None
        risco_llm = registro.get("nivel_risco") if registro else None
        linhas.append(
            {
                "posicao": int(linha["posicao"]),
                "cliente_id": cliente_id,
                "sinais_regra_1": int(linha["sinais_regra_1"]),
                "sinais_regra_2": int(linha["sinais_regra_2"]),
                "total_sinalizacoes": int(linha["total_sinalizacoes"]),
                "risco_esperado_regras": risco_esperado_regras(linha["total_sinalizacoes"]),
                "status_lote": registro.get("status") if registro else None,
                "status_llm": "sucesso" if comparavel else "indisponivel_para_confronto",
                "status_validacao_factual": (
                    registro.get("status_validacao_factual") if registro else None
                ),
                "risco_llm": risco_llm if comparavel else None,
                "comparavel": comparavel,
                "concordancia": (
                    bool(risco_esperado_regras(linha["total_sinalizacoes"]) == risco_llm)
                    if comparavel
                    else None
                ),
                "motivo_nao_comparavel": motivo,
                "tools_utilizadas": registro.get("tools_utilizadas", []) if registro else [],
                "modelo_utilizado": registro.get("modelo_utilizado") if registro else None,
            }
        )
    return pd.DataFrame(linhas)


def calcular_metricas_confronto(tabela):
    """Calcula métricas exclusivamente sobre casos comparáveis."""
    comparaveis = tabela.loc[tabela["comparavel"]].copy()
    quantidade = len(comparaveis)
    concordancias = int(comparaveis["concordancia"].sum()) if quantidade else 0
    divergencias = quantidade - concordancias
    tabela_divergencias = comparaveis.loc[comparaveis["concordancia"].eq(False)].copy()
    distribuicao = {}
    if not tabela_divergencias.empty:
        rotulos = (
            "regras "
            + tabela_divergencias["risco_esperado_regras"]
            + " × LLM "
            + tabela_divergencias["risco_llm"]
        )
        distribuicao = {str(chave): int(valor) for chave, valor in rotulos.value_counts().items()}
    return {
        "casos_comparaveis": quantidade,
        "concordancias": concordancias,
        "divergencias": divergencias,
        "taxa_concordancia": concordancias / quantidade if quantidade else None,
        "distribuicao_divergencias": distribuicao,
        "aviso": "A taxa de concordância atual é parcial e não representa os 10 clientes do ranking.",
    }


def analisar_divergencias(tabela):
    """Descreve divergências sem declarar automaticamente qual avaliação é correta."""
    analises = []
    divergencias = tabela.loc[
        tabela["comparavel"].eq(True) & tabela["concordancia"].eq(False)
    ]
    for _, linha in divergencias.iterrows():
        analises.append(
            {
                "cliente_id": linha["cliente_id"],
                "fatos_deterministicos": {
                    "sinais_regra_1": int(linha["sinais_regra_1"]),
                    "sinais_regra_2": int(linha["sinais_regra_2"]),
                    "total_sinalizacoes": int(linha["total_sinalizacoes"]),
                },
                "risco_esperado_criterio_sintetico": linha["risco_esperado_regras"],
                "risco_retornado_agente": linha["risco_llm"],
                "tools_realmente_consultadas": linha["tools_utilizadas"],
                "interpretacao_possivel": (
                    "O critério sintético converte a quantidade de sinalizações em risco, "
                    "enquanto o agente retornou outro nível após consultar as tools registradas. "
                    "Isso é uma interpretação do contraste entre os dois métodos, não um fato adicional."
                ),
                "conclusao": (
                    "Não há evidência suficiente para determinar qual avaliação é mais adequada neste caso."
                ),
            }
        )
    return analises


def _converter_registros(tabela):
    """Converte tipos do Pandas e valores ausentes para JSON estrito."""
    registros = tabela.to_dict(orient="records")
    for registro in registros:
        for chave, valor in list(registro.items()):
            if isinstance(valor, (list, dict, str, bool)) or valor is None:
                continue
            if pd.isna(valor):
                registro[chave] = None
            elif hasattr(valor, "item"):
                registro[chave] = valor.item()
    return registros


def salvar_confronto(documento, caminho_saida=CAMINHO_PADRAO_SAIDA):
    """Persiste o confronto de forma atômica e auditável."""
    caminho = Path(caminho_saida)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)


def executar_confronto(caminho_lote=CAMINHO_PADRAO_LOTE, caminho_saida=CAMINHO_PADRAO_SAIDA):
    """Gera confronto usando somente pipeline local e resultados LLM já persistidos."""
    ranking = executar_pipeline()["ranking_clientes"]
    registros_lote = carregar_registros_lote(caminho_lote)
    tabela = construir_tabela_confronto(ranking, registros_lote)
    metricas = calcular_metricas_confronto(tabela)
    documento = {
        "versao": 1,
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "criterio_sintetico": CRITERIO_SINTETICO,
        "registros": _converter_registros(tabela),
        "metricas_parciais": metricas,
        "divergencias": analisar_divergencias(tabela),
        "limitacoes": [
            "O confronto usa um critério sintético e não mede risco real de PLD.",
            "Somente casos com sucesso e sem alertas factuais entram no denominador.",
            "Resultados ausentes, alertas factuais e erros técnicos não equivalem a risco baixo.",
            "O JSON do lote persiste nomes de tools, mas não as respostas brutas delas; detalhes não são reconstruídos.",
            "A taxa de concordância atual é parcial e não representa os 10 clientes do ranking.",
        ],
    }
    salvar_confronto(documento, caminho_saida)
    return documento


if __name__ == "__main__":
    resultado = executar_confronto()
    print(json.dumps(resultado["metricas_parciais"], ensure_ascii=False, indent=2))
