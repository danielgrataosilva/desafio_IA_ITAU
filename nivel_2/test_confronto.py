"""Testes locais do confronto; não utilizam API ou Gemini."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from nivel_2.confronto import (
    calcular_metricas_confronto,
    construir_tabela_confronto,
    executar_confronto,
)


class TesteConfronto(unittest.TestCase):
    def setUp(self):
        self.ranking = pd.DataFrame(
            [
                {"cliente_id": "CLI-1", "sinais_regra_1": 0, "sinais_regra_2": 1, "total_sinalizacoes": 1, "volume_total_brl": 10.0},
                {"cliente_id": "CLI-2", "sinais_regra_1": 0, "sinais_regra_2": 2, "total_sinalizacoes": 2, "volume_total_brl": 20.0},
                {"cliente_id": "CLI-3", "sinais_regra_1": 1, "sinais_regra_2": 0, "total_sinalizacoes": 1, "volume_total_brl": 30.0},
            ]
        )
        self.registros = [
            {
                "cliente_id": "CLI-1",
                "status": "sucesso",
                "status_validacao_factual": "sem_alertas_automaticos",
                "nivel_risco": "médio",
                "tools_utilizadas": ["historico_cliente"],
            },
            {
                "cliente_id": "CLI-2",
                "status": "erro",
                "status_validacao_factual": "com_alertas",
                "nivel_risco": "alto",
                "alertas_factualidade": ["valor sem evidência"],
            },
            {
                "cliente_id": "CLI-3",
                "status": "erro",
                "status_validacao_factual": None,
                "nivel_risco": None,
                "erro_final": "429 RESOURCE_EXHAUSTED",
            },
        ]

    def test_alerta_factual_e_erro_tecnico_ficam_fora_do_denominador(self):
        tabela = construir_tabela_confronto(self.ranking, self.registros)
        metricas = calcular_metricas_confronto(tabela)
        self.assertEqual(metricas["casos_comparaveis"], 1)
        self.assertEqual(metricas["concordancias"], 1)
        self.assertEqual(metricas["taxa_concordancia"], 1.0)
        self.assertEqual(tabela.loc[1, "status_llm"], "indisponivel_para_confronto")
        self.assertEqual(tabela.loc[2, "motivo_nao_comparavel"], "Erro técnico 429/quota; parecer final indisponível.")

    def test_sem_parecer_nao_vira_risco_baixo(self):
        tabela = construir_tabela_confronto(self.ranking, [])
        self.assertTrue((~tabela["comparavel"]).all())
        self.assertTrue(tabela["risco_llm"].isna().all())
        self.assertTrue((tabela["status_llm"] == "indisponivel_para_confronto").all())

    def test_sem_comparaveis_nao_divide_por_zero(self):
        tabela = construir_tabela_confronto(self.ranking, [])
        metricas = calcular_metricas_confronto(tabela)
        self.assertEqual(metricas["casos_comparaveis"], 0)
        self.assertIsNone(metricas["taxa_concordancia"])

    def test_reexecucao_le_novo_json_sem_alterar_codigo(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho_lote = Path(diretorio) / "lote.json"
            caminho_saida = Path(diretorio) / "confronto.json"
            caminho_lote.write_text(json.dumps({"resultados": []}), encoding="utf-8")
            resultado = executar_confronto(caminho_lote, caminho_saida)
            self.assertTrue(caminho_saida.exists())
            self.assertEqual(len(resultado["registros"]), 10)
            self.assertEqual(resultado["metricas_parciais"]["casos_comparaveis"], 0)
            self.assertNotIn("NaN", caminho_saida.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
