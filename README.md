# Desafio Técnico — Estágio em Engenharia de Inteligência Artificial

Solução desenvolvida para o desafio técnico de Estágio em Engenharia de Inteligência Artificial do Itaú Unibanco.

O cenário é fictício e simula uma etapa de triagem em prevenção à lavagem de dinheiro (PLD): regras determinísticas identificam sinais nas operações e uma LLM interpreta os fatos para apoiar a priorização de casos que podem exigir análise humana.

> As regras e critérios deste repositório pertencem ao desafio técnico. Eles não representam política real de PLD, regulamentação ou metodologia interna do Itaú.

---

## Objetivo

A solução combina duas camadas com responsabilidades separadas:

**Python/Pandas**
- limpeza e validação dos dados;
- conversão monetária;
- agregações;
- medianas;
- aplicação das regras determinísticas;
- flags;
- ranking;
- métricas.

**LLM**
- interpretação dos fatos já calculados;
- classificação estruturada de risco;
- tipologia;
- red flags;
- justificativa;
- escolha contextual de ferramentas no Nível 2.

A LLM não é usada para calcular somas, medianas ou thresholds.

---

# Estrutura do repositório

```text
.
├── README.md
├── ENTREGA.yaml
├── requirements.txt
├── .env.example
├── dados/
│   ├── dados_nivel_1.json
│   └── dados_nivel_2.json
├── nivel_1/
│   └── nivel_1.ipynb
├── nivel_2/
│   ├── nivel_2.ipynb
│   ├── pipeline.py
│   ├── tools.py
│   ├── agente.py
│   ├── lote.py
│   ├── confronto.py
│   └── testes relacionados
├── outputs/
└── docs/
    ├── DECISOES.md
    └── USO_DE_IA.md
```

Arquivos adicionais foram mantidos quando ajudam na modularização e nos testes, sem substituir os arquivos obrigatórios do enunciado.

---

# Configuração

## 1. Python

Use uma versão recente do Python compatível com as dependências do projeto.

Se `requirements.txt` estiver presente:

```bash
pip install -r requirements.txt
```

---

## 2. Variáveis de ambiente

O repositório utiliza `.env` local para credenciais.

Use `.env.example` como referência para os nomes das variáveis necessárias.

Nunca coloque valores de API key em:

- código;
- notebook;
- README;
- outputs;
- `.env.example`.

O arquivo `.env` deve permanecer fora do Git.

---

# Nível 1

O Nível 1 concentra:

- inspeção e limpeza da base menor;
- normalização BRL/USD usando a taxa fixa fornecida no JSON;
- Regra 1 — fracionamento;
- Regra 2 — valor atípico;
- validação das regras;
- integração com LLM;
- saída estruturada com Pydantic;
- tratamento de resposta inválida;
- registro de tokens e latência;
- comparação entre dois prompts.

## Principais decisões

- apenas duplicatas exatas são removidas;
- registros sem data são preservados;
- um registro sem data fica fora somente de regras que exigem dimensão temporal;
- `valor` e `moeda` originais são preservados;
- `valor_brl` é derivado usando exclusivamente a taxa do JSON;
- cálculos ficam em Pandas/Python;
- interpretação fica na LLM.

O notebook do Nível 1 deve ser entregue com as células e saídas executadas, conforme exigido pelo enunciado.

---

# Nível 2

O Nível 2 reaproveita a lógica determinística em uma base maior e adiciona ferramentas e comportamento agentic.

## Pipeline

`nivel_2/pipeline.py` centraliza:

- carregamento;
- limpeza;
- conversão;
- regras;
- sinalizações;
- ranking.

Na base atual:

- 322 operações brutas;
- 317 após remoção de 5 duplicatas exatas;
- 4 eventos de fracionamento;
- 21 operações atípicas;
- 17 clientes com pelo menos uma sinalização.

A unidade adotada para o ranking é:

- 1 evento `cliente_id + data` da Regra 1 = 1 sinalização;
- 1 operação da Regra 2 = 1 sinalização.

Empates no número de sinalizações são desempatados por volume total.

---

## Tools

Foram implementadas:

- `historico_cliente(cliente_id)`;
- `operacoes_do_dia(cliente_id, data)`;
- `perfil_canal(cliente_id)`.

As tools têm responsabilidades separadas e devolvem contexto determinístico.

O agente recebe um contexto inicial compacto e escolhe quais tools consultar, em vez de executar todas automaticamente.

---

## Agente

`nivel_2/agente.py` utiliza function calling com execução local das tools.

O fluxo inclui:

1. modelo recebe o caso;
2. modelo escolhe uma tool;
3. código valida nome e argumentos;
4. tool é executada localmente;
5. resposta retorna ao modelo;
6. o modelo pode solicitar novo contexto;
7. parecer estruturado é validado.

Foi estabelecido limite de três chamadas de tools por análise.

Pydantic valida a estrutura da resposta. Como isso não garante factualidade, também foi criada uma verificação simples de aderência das datas e valores monetários às evidências consultadas.

Essa verificação é parcial e não substitui revisão humana.

---

## Execução em lote

`nivel_2/lote.py` foi projetado para:

- obter programaticamente o Top 10;
- processar os clientes sequencialmente;
- salvar o estado incrementalmente;
- permitir retomada;
- não repetir sucessos plenos;
- registrar falhas;
- interromper de forma controlada em problemas de disponibilidade ou quota.

### Estado atual

A infraestrutura do lote está implementada, mas a execução disponível está parcial.

No lote atual com `gemini-3.6-flash`:

- `CLI-014`: sucesso pleno;
- `CLI-028`: sucesso pleno;
- `CLI-023`: resposta retida por alerta factual;
- `CLI-013`: erro técnico 429;
- 6 clientes permanecem pendentes.

A execução foi interrompida por limite de quota da camada gratuita.

Nenhum parecer foi inventado para preencher os casos ausentes.

---

## Confronto entre regras e LLM

`nivel_2/confronto.py` compara o risco atribuído pela LLM com um critério determinístico criado exclusivamente para o desafio:

- 0 sinais → baixo;
- 1 sinal → médio;
- 2 ou mais sinais → alto.

Esse critério é sintético e não representa risco real de PLD.

Somente casos com sucesso pleno e sem alerta factual entram no denominador.

No estado atual:

- 2 casos comparáveis;
- 0 concordâncias;
- 2 divergências;
- taxa parcial de concordância: 0%.

Os dois casos comparáveis são:

- `CLI-014`: regras alto × LLM médio;
- `CLI-028`: regras alto × LLM médio.

A taxa é parcial e não representa os 10 clientes do ranking.

Para as divergências atuais, não há evidência suficiente para determinar automaticamente qual avaliação é mais adequada.

---

# Modelos e disponibilidade da API

Durante o desenvolvimento foram observados problemas externos de disponibilidade e quota.

## `gemini-3.7-flash`

Apresentou erro 503 inclusive em teste mínimo sem agente ou tools.

## `gemini-3.6-flash`

Respondeu a teste mínimo e a execuções agentic, mas o lote posteriormente atingiu erro 429 de quota.

Resultados de modelos diferentes foram mantidos separados para preservar rastreabilidade.

Não foi contratado plano pago para contornar as limitações.

---

# Outputs

Os resultados de execução são salvos em `outputs/`.

O output do lote atual identifica explicitamente o modelo utilizado.

O confronto também é salvo nessa pasta.

Resultados incompletos ou indisponíveis são tratados como tal; ausência de parecer não é convertida em risco baixo.

---

# Observabilidade

Quando disponíveis, são registrados:

- modelo;
- tokens;
- latência;
- retries;
- erro;
- status;
- tools consultadas;
- status de factualidade.

## Limitação atual

A latência está registrada principalmente por análise completa do cliente.

O enunciado solicita custo e latência de cada chamada individual da API; portanto, o detalhamento por chamada ainda é uma melhoria necessária.

O custo monetário não foi disponibilizado diretamente pelo SDK utilizado e não foi estimado.

---

# Segurança

A chave da API fica somente em `.env`.

Durante o desenvolvimento foram verificados:

- `.env` ignorado pelo Git;
- ausência de chave nos arquivos versionados;
- ausência de chave nos outputs;
- ausência de segredo no histórico consultado.

`.env.example` deve conter somente os nomes das variáveis.

---

# Documentação

Detalhes sobre decisões, trade-offs e limitações:

`docs/DECISOES.md`

Registro do uso de ferramentas de IA e dos casos em que suas saídas precisaram ser corrigidas:

`docs/USO_DE_IA.md`

---

# Estado da entrega

## Nível 1

Implementação realizada, incluindo:

- limpeza;
- regras;
- validação;
- LLM estruturada;
- comparação entre prompts.

Antes da entrega final, o notebook deve ser conferido para garantir que a versão final esteja executada e commitada com suas saídas.

## Nível 2

**Implementação**
- regras em escala: completa;
- tools: completas;
- agente: completo;
- infraestrutura do lote: completa;
- confronto: implementado.

**Execução**
- lote: parcial;
- confronto: parcial por depender dos casos válidos do lote.

## Nível 3

Não implementado.

A prioridade foi entregar os Níveis 1 e 2 de forma sólida e documentar com transparência o que ficou incompleto.

---

# Limitações principais

- lote do Top 10 ainda não concluído;
- confronto baseado atualmente em apenas dois casos comparáveis;
- validação factual automática é parcial;
- observabilidade de latência ainda precisa ser detalhada por chamada;
- custo monetário não foi retornado pelo SDK;
- dependência de API externa introduziu indisponibilidade e quota.

Os planos de evolução estão documentados em `docs/DECISOES.md`.

---

# Conclusão

O principal desenho da solução é a separação entre:

**regra sinaliza → LLM contextualiza → humano decide**

As regras determinísticas mantêm os cálculos reproduzíveis. A LLM acrescenta interpretação, mas suas respostas são tratadas como apoio à triagem e permanecem sujeitas a validação e revisão humana.
