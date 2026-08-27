"""Testes locais da observabilidade por chamada, sem acesso à API Gemini."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nivel_2 import agente


class ErroApiFalso(Exception):
    def __init__(self, codigo, mensagem='erro sintético'):
        super().__init__(mensagem)
        self.code = codigo


class ModelosFalsos:
    def __init__(self, respostas):
        self.respostas = iter(respostas)

    def generate_content(self, **_kwargs):
        proxima = next(self.respostas)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima


class ClienteFalso:
    def __init__(self, respostas):
        self.models = ModelosFalsos(respostas)


def resposta_falsa(
    entrada=100,
    saida=20,
    pensamentos=None,
    total=120,
):
    uso = SimpleNamespace(
        prompt_token_count=entrada,
        candidates_token_count=saida,
        thoughts_token_count=pensamentos,
        total_token_count=total,
    )
    return SimpleNamespace(usage_metadata=uso)


def metricas_vazias():
    return {'chamadas_api': [], 'proxima_sequencia_api': 0}


class TesteObservabilidadeChamadaApi(unittest.TestCase):
    def _chamar(self, cliente, metricas, etapa='decisao_tool'):
        return agente._chamar_com_retry(
            cliente,
            'gemini-teste',
            [],
            None,
            etapa,
            metricas,
        )

    def test_sucesso_registra_latencia_e_tokens_da_chamada(self):
        metricas = metricas_vazias()
        with patch.object(agente.time, 'perf_counter', side_effect=[10.0, 11.25]):
            resposta, tentativas, erro = self._chamar(
                ClienteFalso([resposta_falsa(100, 20, 7, 127)]), metricas
            )

        self.assertIsNotNone(resposta)
        self.assertIsNone(erro)
        self.assertEqual(tentativas, [{'tentativa': 1, 'status': 'sucesso'}])
        chamada = metricas['chamadas_api'][0]
        self.assertEqual(chamada['sequencia'], 1)
        self.assertEqual(chamada['etapa'], 'decisao_tool')
        self.assertEqual(chamada['status'], 'sucesso')
        self.assertEqual(chamada['latencia_segundos'], 1.25)
        self.assertEqual(chamada['tokens_entrada'], 100)
        self.assertEqual(chamada['tokens_saida'], 20)
        self.assertEqual(chamada['tokens_pensamento'], 7)
        self.assertEqual(chamada['tokens_totais'], 127)
        self.assertIsNone(chamada['custo_monetario'])
        self.assertIsNone(chamada['erro'])

    def test_retry_preserva_falha_503_e_sucesso_na_mesma_sequencia(self):
        metricas = metricas_vazias()
        cliente = ClienteFalso([ErroApiFalso(503), resposta_falsa()])
        with (
            patch.object(agente.errors, 'ServerError', ErroApiFalso),
            patch.object(agente.time, 'sleep'),
            patch.object(agente.time, 'perf_counter', side_effect=[1.0, 1.4, 2.0, 3.1]),
        ):
            resposta, tentativas, erro = self._chamar(cliente, metricas, 'parecer_final')

        self.assertIsNotNone(resposta)
        self.assertIsNone(erro)
        self.assertEqual([item['status'] for item in tentativas], ['erro_api', 'retry_agendado', 'sucesso'])
        self.assertEqual(len(metricas['chamadas_api']), 2)
        primeira, segunda = metricas['chamadas_api']
        self.assertEqual((primeira['sequencia'], primeira['tentativa']), (1, 1))
        self.assertEqual((segunda['sequencia'], segunda['tentativa']), (1, 2))
        self.assertEqual(primeira['codigo_http'], 503)
        self.assertEqual(primeira['latencia_segundos'], 0.4)
        self.assertEqual(segunda['status'], 'sucesso')
        self.assertEqual(segunda['latencia_segundos'], 1.1)

    def test_erro_503_persistente_registra_erro_e_latencia(self):
        metricas = metricas_vazias()
        cliente = ClienteFalso([ErroApiFalso(503), ErroApiFalso(503)])
        with (
            patch.object(agente.errors, 'ServerError', ErroApiFalso),
            patch.object(agente.time, 'sleep'),
            patch.object(agente.time, 'perf_counter', side_effect=[1.0, 1.3, 2.0, 2.9]),
        ):
            resposta, _tentativas, erro = self._chamar(cliente, metricas)

        self.assertIsNone(resposta)
        self.assertEqual(erro, 'erro sintético')
        self.assertEqual(len(metricas['chamadas_api']), 2)
        self.assertTrue(all(item['codigo_http'] == 503 for item in metricas['chamadas_api']))
        self.assertTrue(all(item['latencia_segundos'] > 0 for item in metricas['chamadas_api']))

    def test_erro_429_registra_erro_e_latencia_em_cada_tentativa(self):
        metricas = metricas_vazias()
        cliente = ClienteFalso([ErroApiFalso(429), ErroApiFalso(429)])
        with (
            patch.object(agente.errors, 'ServerError', ErroApiFalso),
            patch.object(agente.time, 'sleep'),
            patch.object(agente.time, 'perf_counter', side_effect=[4.0, 4.6, 5.0, 5.8]),
        ):
            resposta, tentativas, erro = self._chamar(cliente, metricas)

        self.assertIsNone(resposta)
        self.assertEqual(erro, 'erro sintético')
        self.assertEqual([item['status'] for item in tentativas], ['erro_api', 'retry_agendado', 'erro_api'])
        self.assertEqual(len(metricas['chamadas_api']), 2)
        self.assertTrue(all(item['codigo_http'] == 429 for item in metricas['chamadas_api']))
        self.assertEqual([item['latencia_segundos'] for item in metricas['chamadas_api']], [0.6, 0.8])

    def _evidencias_percentual_uso(self):
        return [
            {
                'nome': 'perfil_canal',
                'executada': True,
                'resultado': {
                    'canais': [
                        {'canal': 'pix', 'percentual_uso': 36.36363636363637},
                    ]
                },
            }
        ]

    def _parecer_textual(self, texto):
        return {
            'cliente_id': 'CLI-TESTE',
            'nivel_risco': 'médio',
            'tipologia_suspeita': 'teste',
            'red_flags': [texto],
            'justificativa': texto,
            'tools_utilizadas': ['perfil_canal'],
            'recomendacao_analista': None,
        }

    def test_percentual_uso_das_operacoes_e_permitido(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'cliente_id': 'CLI-TESTE'},
            self._evidencias_percentual_uso(),
            self._parecer_textual('PIX concentra 36,36% das operações.'),
        )
        self.assertEqual(resultado['alertas'], [])

    def test_percentual_uso_do_numero_de_operacoes_e_permitido(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'cliente_id': 'CLI-TESTE'},
            self._evidencias_percentual_uso(),
            self._parecer_textual('PIX concentra 36,36% do número de operações.'),
        )
        self.assertEqual(resultado['alertas'], [])

    def test_percentual_uso_apresentado_como_volume_gera_alerta(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'cliente_id': 'CLI-TESTE'},
            self._evidencias_percentual_uso(),
            self._parecer_textual('PIX representa 36,36% do volume.'),
        )
        self.assertIn('Percentual de uso apresentado como percentual de volume: [36.36].', resultado['alertas'])

    def test_percentual_uso_das_operacoes_e_do_volume_gera_alerta(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'cliente_id': 'CLI-TESTE'},
            self._evidencias_percentual_uso(),
            self._parecer_textual('PIX representa 36,36% das operações e do volume.'),
        )
        self.assertIn('Percentual de uso apresentado como percentual de volume: [36.36].', resultado['alertas'])

    def test_datas_e_valores_monetarios_continuam_validados(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'data': '2026-03-01', 'valor': 100.0},
            [],
            self._parecer_textual('O evento de 2026-03-02 teve valor de R$ 200,00.'),
        )
        self.assertTrue(any('Datas sem evidência' in alerta for alerta in resultado['alertas']))
        self.assertTrue(any('Valores monetários sem evidência' in alerta for alerta in resultado['alertas']))

    def test_resposta_sem_percentual_permanece_sem_alerta(self):
        resultado = agente._validar_rastreabilidade_basica(
            {'cliente_id': 'CLI-TESTE'},
            self._evidencias_percentual_uso(),
            self._parecer_textual('O uso do canal merece análise.'),
        )
        self.assertEqual(resultado['alertas'], [])

    def test_metricas_indisponiveis_sao_none_e_nao_zero(self):
        metricas = metricas_vazias()
        with patch.object(agente.time, 'perf_counter', side_effect=[8.0, 8.2]):
            self._chamar(ClienteFalso([SimpleNamespace(usage_metadata=None)]), metricas)

        chamada = metricas['chamadas_api'][0]
        for campo in (
            'tokens_entrada',
            'tokens_saida',
            'tokens_pensamento',
            'tokens_totais',
            'custo_monetario',
        ):
            self.assertIsNone(chamada[campo])


if __name__ == '__main__':
    unittest.main()
