# USO_DE_IA.md

> Registro transparente do uso de ferramentas de IA durante o desafio.  
> O objetivo deste documento é mostrar onde a IA ajudou, como suas respostas foram revisadas e quais erros ou caminhos inadequados foram identificados durante o desenvolvimento.

---

# 1. Ferramentas utilizadas

## ChatGPT

Foi utilizado como apoio para:

- interpretar o enunciado;
- transformar requisitos em etapas menores;
- explicar conceitos que ainda eram novos para mim;
- discutir decisões metodológicas antes da implementação;
- revisar resultados;
- criar checklists de validação;
- elaborar prompts para o ambiente de desenvolvimento;
- auditar o Nível 1 e o Nível 2 contra o enunciado;
- discutir trade-offs;
- organizar a documentação;
- preparar explicações que eu consiga defender em entrevista técnica.

Entre os conceitos estudados durante o desafio estiveram:

- DataFrame;
- `groupby`;
- tratamento de nulos;
- duplicatas;
- mediana;
- Pydantic;
- tokens;
- latência;
- tools;
- function calling;
- agente;
- execução em lote;
- persistência;
- retomada;
- confronto regra × modelo.

O uso do ChatGPT não substituiu a validação nos dados, código e outputs.

---

## Codex / Work

Foi utilizado como copiloto de implementação para:

- criar e editar arquivos do projeto;
- implementar células de notebook;
- criar `pipeline.py`;
- criar e revisar `tools.py`;
- criar `agente.py`;
- implementar function calling;
- implementar `lote.py`;
- implementar persistência incremental e retomada;
- criar `confronto.py`;
- criar testes;
- executar auditorias técnicas;
- verificar segurança;
- revisar o estado do Git.

As implementações produzidas com IA foram revisadas.

Em vários momentos essa revisão identificou decisões excessivas, falhas de contexto ou lacunas de observabilidade.

---

## Gemini

Foi a LLM integrada ao sistema.

Foi utilizada para:

- gerar parecer estruturado no Nível 1;
- comparar duas versões de prompt;
- interpretar fatos já calculados;
- escolher tools no Nível 2;
- gerar parecer de triagem no fluxo agentic.

A LLM não foi usada para calcular:

- soma;
- mediana;
- conversão;
- thresholds;
- flags;
- ranking.

Essas tarefas permaneceram em Python/Pandas.

---

# 2. Forma de trabalho com IA

O uso de IA seguiu, na prática, este ciclo:

1. entender o requisito;
2. discutir uma solução;
3. implementar;
4. executar;
5. validar;
6. revisar criticamente;
7. corrigir;
8. documentar.

A saída da IA nunca foi tratada automaticamente como verdade.

Quando faltava evidência, a regra adotada foi declarar a limitação em vez de preencher a lacuna.

---

# 3. Casos em que a IA levou a um caminho inadequado ou precisou ser corrigida

## 3.1 Inferência regulatória sem evidência

No Nível 1, o primeiro parecer do Gemini mencionou possível:

> “burla a limites regulatórios de reporte”

O contexto fornecido não continha regulamentação real.

O threshold fazia parte da regra sintética do desafio.

### Correção

O segundo prompt passou a proibir explicitamente:

- legislação não fornecida;
- regulamentação inventada;
- intenção do cliente;
- motivação não sustentada;
- hipótese apresentada como fato.

---

## 3.2 Relação numérica incorreta

No mesmo primeiro parecer, a LLM afirmou que R$ 18.800 representava “a maior parte” de R$ 57.500.

Isso não é compatível com os números fornecidos.

### Aprendizado

Mesmo quando os números são copiados corretamente, a relação descrita entre eles pode estar errada.

Por isso os cálculos continuam determinísticos e as respostas precisam de revisão.

---

## 3.3 Validação rígida de tipos criada com apoio de IA

Uma versão de `pipeline.py` introduziu uma lista rígida `TIPOS_ESPERADOS`.

Se aparecesse um tipo novo, o pipeline lançaria erro.

A revisão percebeu que as regras não dependiam do campo `tipo`.

### Correção

- moeda continua com validação rígida;
- `tipo` passou a ser apenas inspecionado.

A alteração não modificou os resultados determinísticos.

---

## 3.4 Agente escolheu uma data pouco útil

No primeiro teste agentic, `historico_cliente()` informava apenas primeira e última data.

O modelo decidiu usar `operacoes_do_dia()`, mas não tinha informação suficiente para escolher necessariamente uma data ligada à sinalização.

### Correção

A tool passou a devolver somente as datas associadas a:

- operações atípicas;
- eventos de fracionamento.

Ela não passou a entregar os detalhes completos das operações.

Em teste posterior, o agente escolheu uma data realmente sinalizada.

---

## 3.5 Pydantic aprovou estrutura, mas não factualidade

Um parecer passou normalmente pelo schema Pydantic, mas citou detalhes de operações que não haviam sido retornados pelas tools consultadas.

### Aprendizado

Pydantic valida estrutura, não verdade factual.

### Correção

O prompt final passou a exigir que detalhes específicos aparecessem apenas se estivessem:

- no contexto inicial;
- ou nas tools realmente consultadas.

Também foi criada uma checagem simples pós-resposta para:

- datas;
- valores monetários.

---

## 3.6 `CLI-023` — alerta factual em execução de lote

Durante o lote do Nível 2, a validação detectou valores monetários sem evidência consultada:

- R$ 65.417,16;
- R$ 148.535,01.

A resposta não foi considerada sucesso pleno.

Isso foi importante para evitar que uma resposta estruturalmente válida entrasse como resultado confiável.

---

## 3.7 Falha de observabilidade detectada

No caso `CLI-013`, o agente chegou a executar tools antes de a chamada final falhar por quota.

Os nomes das tools não haviam sido persistidos quando não existia parecer final.

### Correção

O lote passou a preservar `tools_chamadas` mesmo quando a análise termina com erro.

As informações ausentes do registro antigo não foram reconstruídas por suposição.

---

# 4. Diagnóstico de falhas da API

## 4.1 `gemini-3.7-flash`

O modelo apresentou erros 503.

Para verificar se o problema estava relacionado ao agente, foi realizado um teste mínimo sem:

- agente;
- tools;
- function calling;
- Pydantic;
- structured output.

A instrução era somente responder `OK`.

Resultado observado:

- HTTP 503;
- mensagem do provedor: `This model is currently experiencing high demand.`;
- latência: 7,403 s.

### Conclusão

O teste fornece forte evidência de indisponibilidade momentânea daquele modelo/provedor no momento observado.

Ele não prova que o agente esteja livre de outros problemas.

---

## 4.2 Primeiro teste do `gemini-3.6-flash`

Um modelo alternativo foi testado.

A primeira tentativa falhou localmente com:

`RuntimeError: Cannot send a request, as the client has been closed.`

Como isso ocorreu antes de uma resposta do provedor, o erro foi tratado como problema local.

Após correção, uma tentativa ficou inconclusiva porque a resposta final não foi capturada.

Nenhuma conclusão sobre sucesso, 503 ou 429 foi inventada.

---

## 4.3 Teste mínimo válido do 3.6

Uma nova chamada controlada retornou:

- texto: `OK`;
- sem erro HTTP;
- latência: 94,557 s.

Esse resultado demonstrou apenas que o modelo respondeu naquela execução.

A latência elevada impede usar esse teste isolado para afirmar superioridade de desempenho ou estabilidade.

---

## 4.4 Teste completo do agente no 3.6

O agente foi então testado com `CLI-014`.

Após as melhorias de contexto e factualidade, uma execução registrou:

- status: sucesso;
- risco: médio;
- 3 tools;
- 0 retries;
- 3.170 tokens de entrada;
- 826 tokens de saída;
- 1.889 tokens de pensamento;
- 5.885 tokens totais;
- latência: 86,749 s;
- sem alertas factuais automáticos.

---

## 4.5 Lote interrompido por quota

O lote com `gemini-3.6-flash` foi executado de forma incremental.

Depois de quatro registros, ocorreu erro 429 de quota.

O sistema:

1. salvou o estado;
2. interrompeu o lote;
3. manteve os demais casos pendentes;
4. não criou pareceres fictícios.

O desafio orienta o uso de camada gratuita e informa que não é esperado nem desejado gastar dinheiro; por isso não foi contratado plano pago para contornar a quota.

---

# 5. Como os erros foram diferenciados

Durante o desenvolvimento, erros diferentes foram tratados de forma diferente.

## Erro local

Exemplo:

`client has been closed`

Indica problema na execução/uso do SDK.

Não deve ser chamado de falha do provedor.

---

## 503

Indica indisponibilidade do serviço/modelo.

Foi tratado com retry limitado e, no lote, interrupção após falhas consecutivas.

---

## 429

Indica limite/quota.

O lote é salvo e interrompido.

---

## Alerta factual

A API respondeu e a estrutura pode até estar válida, mas existem detalhes que não possuem evidência consultada.

Esses casos não são tratados como sucesso pleno.

---

# 6. Separação de modelos e resultados

Os resultados produzidos com modelos diferentes foram mantidos separados.

O objetivo foi evitar misturar análises produzidas em condições diferentes sem rastreabilidade.

Testar um modelo diferente não foi interpretado automaticamente como migração definitiva.

---

# 7. IA como apoio, não substituição da revisão

Os principais exemplos acima reforçaram uma mesma conclusão:

- a IA acelerou implementação e análise;
- também introduziu decisões excessivas;
- produziu inferências não fundamentadas;
- gerou respostas estruturalmente válidas com detalhes não sustentados;
- precisou de revisão humana.

Por isso a solução preserva:

- regras determinísticas;
- validações explícitas;
- testes;
- Pydantic;
- checagem factual parcial;
- revisão humana.

---

# 8. O que não foi feito com IA

A IA não foi usada para fabricar resultados ausentes.

Não foram inventados:

- custos;
- tokens não retornados;
- riscos quando a API falhou;
- tools antigas não persistidas;
- pareceres para clientes pendentes;
- dados de clientes;
- resultados de confronto ausentes.

Quando a informação não existia, foi registrada como indisponível.

---

# 9. Uso de IA para aprendizagem

Além da implementação, o desafio foi usado como processo de aprendizagem.

Conceitos que inicialmente não faziam parte do meu domínio técnico foram estudados durante o desenvolvimento, especialmente:

- Pandas aplicado a análise;
- DataFrame;
- `groupby`;
- Pydantic;
- APIs de LLM;
- tokens e latência;
- function calling;
- tools;
- agentes;
- persistência de lote;
- retomada;
- observabilidade;
- confronto entre regra determinística e modelo.

Isso foi importante porque a entrevista técnica pode exigir explicação das decisões do próprio código.

---

# 10. Avaliação de contingência — Groq

## Finalidade

O Groq foi efetivamente testado durante o desenvolvimento como alternativa de contingência aos problemas observados no Gemini: latência elevada em algumas execuções, erros `503`, retries e interrupção parcial do lote por quota `429`.

O modelo avaliado foi `openai/gpt-oss-20b`. O objetivo não foi substituir automaticamente o provedor, mas verificar de forma controlada a viabilidade de chat, tool calling e integração com o agente.

## Testes realizados

- **Chat mínimo:** autenticação concluída, modelo disponível e resposta `OK`; latência aproximada de 0,398 s, 76 tokens de entrada, 36 de saída, 112 no total e 26 `reasoning_tokens`. O SDK não forneceu custo por chamada.
- **Tool calling sintético:** a tool temporária `consultar_saldo(cliente_id)` foi escolhida pelo modelo para `CLI-TESTE`, validada e executada localmente; o resultado retornou ao modelo e a resposta final foi correta. O fluxo usou duas chamadas, 462 tokens e cerca de 0,823 s de latência agregada. Uma falha inicial de codificação do terminal Windows foi local, não do provedor; o reteste UTF-8 passou.
- **Agente com `CLI-014`:** o modelo consultou `historico_cliente` e `perfil_canal`, mas apresentou `percentual_uso` como percentual de volume financeiro. A revisão humana rejeitou essa extrapolação, pois o campo se refere apenas à quantidade de operações.
- **Estabilização e último reteste com `CLI-014`:** `parallel_tool_calls=False` eliminou o erro anterior de validação do nome contaminado da tool. A exigência de `response_format={"type":"json_object"}` foi atendida com instrução explícita para resposta JSON. As quatro chamadas à API foram concluídas tecnicamente; o modelo escolheu e executou `historico_cliente` e `perfil_canal`. Porém, o JSON final não continha `nivel_risco`, `tipologia_suspeita`, `red_flags` nem `justificativa`, e o Pydantic o rejeitou corretamente. Não houve parecer válido, validação factual final ou lote Groq. Métricas: aproximadamente 4,321 s e 7.312 tokens, sem retries.

## Supervisão e decisão humana

Nenhuma saída do Groq foi usada para preencher dados fictícios, completar resultados ausentes ou substituir evidências determinísticas. Respostas inconsistentes foram rejeitadas, e as correções — inclusive a regra de que cálculos quantitativos pertencem ao código/Pandas — foram decisões humanas.

O experimento gerou melhorias genéricas preservadas no caminho Gemini: observabilidade por chamada, tratamento de retries/erros, reforço contra cálculos derivados pela LLM e validação específica para impedir que `percentual_uso` seja apresentado como percentual de volume.

Apesar da boa latência e do tool calling funcional em testes controlados, incompatibilidades específicas do provider/modelo no fluxo real — inclusive factualidade, validação de tool e schema final — levaram à decisão definitiva de não promover Groq no prazo do desafio. Isso não significa que o Groq seja inviável em geral; apenas não atingiu o critério de estabilidade definido para esta entrega. Gemini permanece como provedor executável principal.
