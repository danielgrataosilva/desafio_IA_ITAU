"""Testes sinteticos da infraestrutura de lote, sem chamadas ao Gemini."""

import tempfile
import unittest
from pathlib import Path

from nivel_2.lote import calcular_metricas, carregar_resultados, executar_lote


CLIENTES = [
    {
        'posicao': 1,
        'cliente_id': 'CLI-S-1',
        'sinais_regra_1': 1,
        'sinais_regra_2': 2,
        'total_sinalizacoes': 3,
        'volume_total_brl': 100.0,
    },
    {
        'posicao': 2,
        'cliente_id': 'CLI-S-2',
        'sinais_regra_1': 0,
        'sinais_regra_2': 1,
        'total_sinalizacoes': 1,
        'volume_total_brl': 50.0,
    },
    {
        'posicao': 3,
        'cliente_id': 'CLI-S-3',
        'sinais_regra_1': 0,
        'sinais_regra_2': 1,
        'total_sinalizacoes': 1,
        'volume_total_brl': 30.0,
    },
]


def sucesso(cliente_id):
    return {
        'status_final': 'sucesso',
        'parecer': {
            'cliente_id': cliente_id,
            'nivel_risco': 'm\u00e9dio',
            'tipologia_suspeita': 'Teste sint\u00e9tico',
            'red_flags': ['Sinal sint\u00e9tico'],
            'justificativa': 'Resultado produzido apenas para testar infraestrutura.',
            'recomendacao_analista': None,
            'tools_utilizadas': ['historico_cliente'],
        },
        'quantidade_chamadas_tools': 1,
        'metricas': {
            'tokens_entrada': 10,
            'tokens_saida': 5,
            'tokens_pensamento': None,
            'tokens_totais': 15,
            'latencia_total_segundos': 0.5,
        },
        'quantidade_retries': 0,
        'erro_api': None,
    }


def erro(cliente_id, codigo):
    return {
        'status_final': 'erro_api',
        'parecer': None,
        'quantidade_chamadas_tools': 0,
        'metricas': {
            'tokens_entrada': 2,
            'tokens_saida': None,
            'tokens_pensamento': None,
            'tokens_totais': 2,
            'latencia_total_segundos': 0.2,
        },
        'quantidade_retries': 1,
        'erro_api': f'{codigo} erro sint\u00e9tico para {cliente_id}',
    }


class TesteLoteSintetico(unittest.TestCase):
    def test_salvamento_incremental_e_retomada(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / 'resultados.json'
            chamadas = []

            def analisador(cliente_id):
                chamadas.append(cliente_id)
                return sucesso(cliente_id) if cliente_id == 'CLI-S-1' else erro(cliente_id, 503)

            primeira = executar_lote(caminho, analisador, CLIENTES[:2])
            self.assertEqual(chamadas, ['CLI-S-1', 'CLI-S-2'])
            self.assertEqual(len(carregar_resultados(caminho)), 2)
            self.assertFalse(primeira['interrompido'])

            chamadas.clear()

            def retomada(cliente_id):
                chamadas.append(cliente_id)
                return sucesso(cliente_id)

            segunda = executar_lote(caminho, retomada, CLIENTES[:2])
            self.assertEqual(segunda['clientes_pulados_por_sucesso'], ['CLI-S-1'])
            self.assertEqual(chamadas, ['CLI-S-2'])
            self.assertEqual(segunda['metricas_agregadas']['clientes_com_sucesso'], 2)

    def test_interrupcao_por_quota_429(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / 'resultados.json'
            chamadas = []

            def analisador(cliente_id):
                chamadas.append(cliente_id)
                if cliente_id == 'CLI-S-2':
                    return erro(cliente_id, 429)
                return sucesso(cliente_id)

            resumo = executar_lote(caminho, analisador, CLIENTES)
            self.assertTrue(resumo['interrompido'])
            self.assertEqual(resumo['motivo_interrupcao'], 'quota_429')
            self.assertEqual(chamadas, ['CLI-S-1', 'CLI-S-2'])
            self.assertEqual(len(carregar_resultados(caminho)), 2)

    def test_output_antigo_sem_chamadas_api_permanece_compativel(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / 'resultado_antigo.json'
            caminho.write_text(
                '{\n  "resultados": [{"cliente_id": "CLI-ANTIGO", "status": "sucesso", '
                '"nivel_risco": "médio", "tokens_totais": 15, "latencia_segundos": 0.5, '
                '"retries": 0}]\n}',
                encoding='utf-8',
            )
            resultados = carregar_resultados(caminho)

        self.assertNotIn('chamadas_api', resultados[0])
        metricas = calcular_metricas(resultados)
        self.assertEqual(metricas['clientes_com_sucesso'], 1)
        self.assertEqual(metricas['tokens_totais_consumidos'], 15)

    def test_metricas_parciais(self):
        resultados = [
            {**CLIENTES[0], **_registro_sucesso_para_metricas()},
            {**CLIENTES[1], **_registro_erro_para_metricas()},
        ]
        metricas = calcular_metricas(resultados)
        self.assertEqual(metricas['clientes_com_sucesso'], 1)
        self.assertEqual(metricas['clientes_com_erro'], 1)
        self.assertEqual(metricas['tokens_totais_consumidos'], 17)
        self.assertEqual(metricas['tokens_medios_por_sucesso'], 15.0)
        self.assertEqual(metricas['retries_totais'], 1)
        self.assertEqual(metricas['distribuicao_nivel_risco'], {'m\u00e9dio': 1})
        self.assertIsNone(metricas['custo_monetario'])


def _registro_sucesso_para_metricas():
    return {
        'status': 'sucesso',
        'nivel_risco': 'm\u00e9dio',
        'tokens_totais': 15,
        'latencia_segundos': 0.5,
        'retries': 0,
    }


def _registro_erro_para_metricas():
    return {
        'status': 'erro',
        'nivel_risco': None,
        'tokens_totais': 2,
        'latencia_segundos': 0.2,
        'retries': 1,
    }


if __name__ == '__main__':
    unittest.main()
