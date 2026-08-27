# DECISOES.md

> Registro final do desafio técnico de Estágio em Engenharia de Inteligência Artificial — Itaú Unibanco.
> Consolida as decisões, trade-offs, limitações e o estado efetivamente entregue no projeto.

---

# 1. Princípios adotados

A solução foi construída a partir de alguns princípios que orientaram as decisões técnicas dos dois níveis.

## 1.1 Cálculo determinístico e interpretação por LLM são responsabilidades diferentes

Soma, mediana, contagem, conversão monetária, thresholds, flags e rankings são calculados em Python/Pandas.

A LLM recebe fatos já calculados e atua apenas na interpretação e redação do parecer.

Em termos práticos:

**Pandas/Python**
- limpeza;
- normalização;
- agregações;
- mediana;
- soma;
- contagem;
- thresholds;
- regras;
- flags;
- ranking;
- métricas agregadas.

**LLM**
- interpretação;
- tipologia;
- red flags em linguagem natural;
- justificativa;
- recomendação de análise humana;
- escolha de tools no agente.

A LLM nunca foi usada como substituta de uma operação matemática que pudesse ser calculada de forma reproduzível.

---

## 1.2 Dado ausente não deve ser inventado

Quando uma informação não existe, ela é preservada como ausente ou o caso é marcado como não avaliável para aquela etapa.

Não foram inventados ou imputados:

- datas;
- valores;
- custos;
- resultados de API;
- riscos;
- pareceres;
- regulamentações;
- intenções do cliente.

Quando uma métrica não estava disponível, ela foi explicitamente registrada como indisponível.

---

## 1.3 O dado bruto deve permanecer rastreável

As bases brutas são preservadas.

As transformações são feitas em bases tratadas separadas, permitindo comparar:

`dado original → transformação → resultado`.

Valores e moedas originais são mantidos, com criação de colunas derivadas quando necessário.

---

## 1.4 Falha externa não deve gerar resposta fictícia

Quando a LLM retorna erro, o sistema:

1. registra a falha;
2. preserva os resultados já obtidos;
3. não inventa parecer;
4. não inventa tokens;
5. não atribui risco;
6. permite retomada posterior quando aplicável.

---

## 1.5 Validação estrutural não equivale a validação factual

Pydantic foi usado para garantir estrutura, tipos e enums.

Entretanto, uma resposta estruturalmente válida ainda pode conter uma afirmação que não apareceu nas evidências.

Essa diferença tornou-se central no Nível 2 e motivou uma camada adicional de aderência factual.

---

# 2. Nível 1 — dados e limpeza

## 2.1 Inspeção inicial

A base do Nível 1 possuía 20 operações.

Durante a inspeção foram identificados:

- uma duplicata exata da operação `OP-0007`;
- uma operação com data ausente;
- operações em BRL e USD.

A inspeção foi feita antes das regras para evitar que problemas de qualidade alterassem resultados posteriores.

---

## 2.2 Decisão: remover apenas duplicatas exatas

A duplicata foi removida mantendo uma única ocorrência.

Resultado:

- 20 operações brutas;
- 19 operações tratadas.

### Alternativa não escolhida

Remover todo ID repetido sem comparar o restante da linha.

### Motivo

Um mesmo ID com conteúdo diferente representaria uma inconsistência distinta de uma duplicata exata e deveria ser investigado, não removido automaticamente.

A relevância da limpeza ficou clara porque uma duplicata pode alterar agregações e produzir sinalizações artificiais.

---

## 2.3 Decisão: preservar a operação sem data

A operação sem data não foi excluída.

Ela permanece utilizável em análises que não dependem da dimensão temporal, como:

- volume total;
- quantidade de operações;
- mediana do cliente;
- Regra 2 de valor atípico.

Ela é excluída apenas da Regra 1, que depende do agrupamento por `cliente_id + data`.

### Trade-off

Preencher uma data permitiria incluir a operação em análises temporais, mas criaria uma informação inexistente.

A decisão foi preservar a incerteza.

Um `flag_fracionamento = False` em uma operação sem data significa apenas que ela não foi sinalizada pela regra temporal; não significa que tenha sido integralmente avaliada e comprovada como não fracionada.

---

# 3. Nível 1 — normalização monetária

A taxa `taxa_cambio_usd_brl` fornecida no próprio JSON foi usada de forma fixa.

Não foi consultada cotação externa.

Os campos originais:

- `valor`;
- `moeda`;

foram preservados.

Foi criada:

- `valor_brl`.

Exemplo validado:

- `OP-0013`;
- USD 12.000;
- taxa do arquivo: 5,4;
- `valor_brl`: R$ 64.800.

---

## 3.1 Decisão: validar moedas suportadas

BRL e USD foram aceitas.

Uma moeda desconhecida não deve ser tratada silenciosamente como BRL.

### Motivo

O domínio da moeda afeta diretamente o cálculo de conversão. Nesse caso, uma validação rígida protege o resultado.

---

# 4. Nível 1 — regras determinísticas

## 4.1 Regra 1 — Fracionamento

A regra foi implementada exatamente conforme o enunciado:

- mesmo cliente;
- mesma data;
- pelo menos 3 operações;
- soma em BRL maior que R$ 50.000;
- nenhuma operação individual atinge R$ 20.000.

Logo, o maior valor individual deve ser menor que R$ 20.000.

### Caso positivo validado

`CLI-A-1` em `2026-03-09`:

- 3 operações;
- soma de R$ 54.200;
- maior operação de R$ 18.800;
- sinalização positiva.

### Caso negativo validado

`CLI-A-2` em `2026-03-14`:

- total superior a R$ 50.000;
- apenas duas operações;
- valores individuais superiores ao limite;
- não deve ser sinalizado.

---

## 4.2 Regra 2 — Valor atípico

Critério:

- cliente com pelo menos 4 operações;
- operação com `valor_brl > 5 × mediana do cliente`.

Caso validado:

`OP-0013`, cliente `CLI-A-4`:

- 4 operações;
- mediana: R$ 5.450;
- limite: R$ 27.250;
- operação: R$ 64.800;
- sinalização positiva.

---

## 4.3 Decisão: não delegar cálculos à LLM

As regras, thresholds e validações permanecem em Pandas/Python.

A LLM recebe os resultados prontos.

Essa separação foi mantida em todo o desafio.

---

# 5. Nível 1 — prompts e LLM

## 5.1 Prompt 1

O primeiro prompt foi mais simples.

Em uma execução válida registrada durante o desenvolvimento:

- risco: `alto`;
- tokens de entrada: 257;
- tokens de saída: 250;
- tokens totais: 967;
- latência: 3,315 s;
- tokens de pensamento não haviam sido registrados naquela chamada.

### Problemas observados

A resposta mencionou possível:

> “burla a limites regulatórios de reporte”

Nenhuma regulamentação desse tipo havia sido fornecida.

Além disso, afirmou que R$ 18.800 representava “a maior parte” de R$ 57.500, o que é incompatível com os próprios números.

Esses dois pontos mostraram que uma resposta fluente não deve ser aceita automaticamente como correta.

---

## 5.2 Prompt 2

O Prompt 2 foi mais restritivo.

Foram adicionadas instruções para:

- não inventar legislação;
- não inferir intenção ou motivação;
- não transformar hipótese em fato;
- usar apenas fatos fornecidos;
- usar linguagem de possibilidade;
- delimitar o parecer como apoio à triagem humana.

Em uma execução válida:

- risco: `médio`;
- tokens de entrada: 347;
- tokens de saída: 224;
- tokens de pensamento: 617;
- tokens totais: 1.188;
- latência: 10,373 s.

---

## 5.3 Trade-off entre os prompts

O Prompt 2 foi mais controlado e aderente às evidências, mas teve:

- mais tokens de entrada;
- maior latência;
- maior quantidade total de tokens.

A conclusão não é que “mais instruções são sempre melhores”.

A decisão correta é buscar o menor nível de complexidade de prompt que ainda preserve:

- qualidade;
- factualidade;
- clareza;
- controle;
- segurança.

---

# 6. Pydantic

Pydantic foi usado para exigir uma estrutura previsível.

Campos principais:

- `nivel_risco`;
- `tipologia_suspeita`;
- `red_flags`;
- `justificativa`.

O risco foi limitado aos valores permitidos.

Uma resposta sintética propositalmente malformada foi testada com:

- risco inválido;
- campo obrigatório ausente.

A validação rejeitou corretamente a resposta.

---

## 6.1 Limitação

Pydantic valida:

- estrutura;
- tipos;
- campos;
- enums.

Ele não valida:

- se um número realmente apareceu nas evidências;
- se uma data foi consultada;
- se uma relação causal é verdadeira;
- se uma inferência tem fundamento.

Essa limitação motivou melhorias no Nível 2.

---

# 7. Nível 2 — escala e reutilização

A base maior possui:

- 322 operações brutas;
- 30 clientes.

Após remover 5 duplicatas exatas:

- 317 operações tratadas.

Datas ausentes:

- 7 na base bruta;
- 6 após deduplicação.

A redução ocorre porque uma das linhas duplicadas também tinha data ausente.

As mesmas decisões do Nível 1 foram reaproveitadas:

- preservar base bruta;
- remover apenas duplicatas exatas;
- preservar operações sem data;
- usar taxa fixa do JSON;
- preservar `valor` e `moeda`;
- criar `valor_brl`;
- manter as duas regras.

---

## 7.1 Modularização em `pipeline.py`

A lógica foi centralizada em `pipeline.py`.

### Motivo

Notebook, tools e agente precisam trabalhar com o mesmo tratamento.

Copiar a lógica para vários arquivos aumentaria o risco de versões diferentes das mesmas regras.

A modularização reduziu duplicação e criou uma única fonte de verdade para o processamento determinístico.

---

# 8. Campo `tipo`: inspeção sem bloqueio

Na base do Nível 2 apareceu `saque`.

Uma implementação inicial produzida com apoio de IA criou `TIPOS_ESPERADOS` e interrompia o pipeline se um novo tipo aparecesse.

Essa decisão foi revisada.

## Decisão final

- `moeda`: validação rígida, porque afeta o cálculo;
- `tipo`: inspeção e exposição, sem bloquear automaticamente o pipeline.

### Motivo

As regras atuais não dependem de `tipo`.

Um tipo novo e válido não deveria impedir toda a análise.

Após o ajuste, permaneceram:

- 317 operações tratadas;
- 4 eventos de fracionamento;
- 21 operações atípicas;
- mesmo Top 10.

---

# 9. Unidade de sinalização do ranking

O enunciado pede os 10 clientes mais sinalizados, mas não define explicitamente como contar um evento de fracionamento com várias operações.

## Decisão

- 1 evento `cliente_id + data` que satisfaz a Regra 1 = 1 sinalização;
- 1 operação que satisfaz a Regra 2 = 1 sinalização.

Logo:

`total_sinalizacoes = eventos_fracionamento + operacoes_atipicas`

### Motivo

Contar cada operação marcada dentro do mesmo evento de fracionamento inflaria artificialmente o peso de um único evento.

O desempate do Top 10 usa volume total em BRL, conforme solicitado no enunciado.

---

# 10. Tools

Foram criadas três tools:

- `historico_cliente(cliente_id)`;
- `operacoes_do_dia(cliente_id, data)`;
- `perfil_canal(cliente_id)`.

## 10.1 `historico_cliente`

Retorna visão agregada:

- quantidade de operações;
- volume;
- mediana;
- sinais;
- datas disponíveis;
- datas associadas às sinalizações.

## 10.2 `operacoes_do_dia`

Retorna detalhes de uma data específica:

- id;
- data;
- valor;
- moeda;
- valor BRL;
- canal;
- tipo;
- contraparte;
- flags.

## 10.3 `perfil_canal`

Retorna comportamento por canal:

- quantidade;
- percentual;
- volume;
- canal mais utilizado;
- canal de maior volume.

---

## 10.4 Decisão: tools com responsabilidades diferentes

Uma tool não deve devolver tudo.

Se `historico_cliente()` entregasse todas as operações detalhadas, as outras tools perderiam função.

A separação foi mantida para permitir que a escolha da LLM tenha valor real.

---

## 10.5 Cache

As tools usam cache interno para reutilizar o pipeline tratado.

Isso evita:

`carregar → limpar → converter → aplicar regras`

a cada nova chamada.

O cache não substitui persistência de resultados da LLM.

---

# 11. Agente e function calling

## 11.1 Function calling manual

A execução automática das funções pelo SDK foi desabilitada.

Fluxo:

1. modelo recebe o caso;
2. modelo solicita uma tool;
3. código valida o nome;
4. código valida os argumentos;
5. função é executada localmente;
6. chamada é registrada;
7. resultado retorna ao modelo;
8. modelo decide se precisa de outra tool.

### Motivo

Esse fluxo oferece:

- controle;
- rastreabilidade;
- validação;
- observação das tools realmente escolhidas.

Também ajuda a demonstrar que o comportamento é agentic e não um script chamando todas as funções automaticamente.

---

## 11.2 Contexto mínimo inicial

O agente recebe inicialmente somente:

- cliente;
- tipos de sinalização detectados;
- quantidade de sinais da Regra 1;
- quantidade de sinais da Regra 2.

Ele decide quais dados adicionais consultar.

---

## 11.3 Limite de três tools

Foi estabelecido um máximo de três chamadas de tools por análise.

### Trade-off

Mais chamadas poderiam trazer contexto adicional, porém aumentariam:

- tokens;
- latência;
- risco de loops;
- dependência da API.

Três chamadas foram usadas como limite simples e explícito para o desafio.

---

# 12. Melhoria das tools após teste real

No primeiro teste do agente, `historico_cliente()` informava apenas primeira e última data.

O agente escolheu consultar uma data concreta, mas ela não estava necessariamente ligada a uma sinalização.

## Correção

Foram adicionadas:

- `datas_operacoes_atipicas`;
- `datas_eventos_fracionamento`.

A tool continua sem entregar os detalhes das operações.

Ela apenas fornece pistas de datas relevantes.

Depois do ajuste, em teste real com `CLI-014`, o agente escolheu uma data efetivamente associada a uma operação atípica.

---

# 13. Aderência factual

Um parecer real passou pelo Pydantic, mas citou valores individuais que não haviam sido retornados pelas tools consultadas.

Esse caso mostrou que:

> estrutura válida não significa conteúdo factual.

## 13.1 Correções

O prompt final passou a exigir:

- usar somente fatos do contexto inicial ou tools consultadas;
- não completar lacunas;
- declarar quando uma informação não foi consultada;
- não inventar legislação;
- não inventar intenção;
- não inventar motivação.

Foi adicionada uma checagem pós-resposta simples para:

- datas ISO;
- valores monetários.

Se aparecer um valor/data não suportado pelas evidências, a resposta recebe alerta de factualidade e não é tratada como sucesso pleno.

---

## 13.2 Limitação

Essa validação não prova factualidade completa.

Ela não cobre de forma robusta:

- canais;
- contrapartes;
- causalidade;
- semântica;
- relações entre fatos.

Revisão humana continua necessária.

---

# 14. Execução em lote

## 14.1 Persistência incremental

Cada cliente é salvo logo após sua análise.

### Motivo

Uma falha posterior não deve apagar os resultados anteriores.

---

## 14.2 Retomada

Antes de chamar a LLM, o lote verifica o resultado persistido.

- sucesso pleno → não repetir;
- erro → pode reprocessar;
- alerta factual → pode reprocessar;
- ausente → processar.

Isso reduz chamadas repetidas.

---

## 14.3 Processamento sequencial

O lote processa um cliente por vez.

### Motivo

Evita aumentar desnecessariamente:

- risco de quota;
- concorrência;
- dificuldade de rastrear erros.

---

# 15. Tratamento de 503 e 429

## 15.1 503

Representa indisponibilidade do serviço/modelo.

Há retry limitado.

Duas falhas 503 consecutivas no lote levam à interrupção por possível indisponibilidade generalizada.

---

## 15.2 429

Representa limite/quota.

Ao ocorrer:

1. estado é salvo;
2. lote é interrompido;
3. casos restantes ficam pendentes.

A opção foi não insistir em chamadas que provavelmente falhariam novamente.

---

# 16. Diagnóstico de disponibilidade do Gemini

## 16.1 `gemini-3.7-flash`

O modelo apresentou múltiplos `503 UNAVAILABLE`.

Foi realizado um teste mínimo com apenas:

`Responda apenas OK`

sem:

- agente;
- tools;
- function calling;
- Pydantic;
- structured output.

Resultado:

- HTTP 503;
- `ServerError`;
- mensagem do provedor: `This model is currently experiencing high demand.`;
- latência: 7,403 s.

### Conclusão

Há forte evidência de indisponibilidade momentânea daquele modelo/provedor naquele teste.

Isso não prova que o agente esteja livre de outros problemas.

---

## 16.2 `gemini-3.6-flash`

Foi testado como alternativa sem alterar permanentemente o modelo padrão.

### Primeiro problema

Uma tentativa falhou localmente:

`RuntimeError: Cannot send a request, as the client has been closed.`

A falha ocorreu antes de uma resposta do provedor e foi tratada como erro local.

Após correção, uma tentativa ficou inconclusiva porque o executor não capturou a resposta.

Uma nova chamada mínima controlada retornou:

- resposta `OK`;
- sem erro HTTP;
- latência: 94,557 s.

A latência elevada impede interpretar isso como bom desempenho; apenas demonstra que o modelo respondeu naquela execução.

---

## 16.3 Teste completo do agente com 3.6

Após melhorias de contexto e factualidade, uma análise controlada do `CLI-014` retornou:

- status: sucesso;
- risco: médio;
- tools: `historico_cliente`, `perfil_canal`, `operacoes_do_dia`;
- 3 chamadas de tools;
- retries: 0;
- tokens de entrada: 3.170;
- tokens de saída: 826;
- tokens de pensamento: 1.889;
- tokens totais: 5.885;
- latência: 86,749 s;
- validação factual automática: sem alertas.

A resposta declarou explicitamente quando não possuía detalhes de outras datas.

---

# 17. Separação dos resultados por modelo

Resultados do 3.7 e do 3.6 não foram misturados como se pertencessem ao mesmo lote final.

### Motivo

Trocar o modelo no meio da avaliação introduz uma nova variável.

Para preservar rastreabilidade, o lote 3.6 foi salvo separadamente.

---

# 18. Estado parcial do lote 3.6

O lote foi interrompido por quota 429 após quatro clientes.

Estado:

- 2 sucessos plenos;
- 1 resposta com alerta factual;
- 1 erro técnico;
- 6 pendentes.

Casos:

- `CLI-014`: sucesso pleno;
- `CLI-028`: sucesso pleno;
- `CLI-023`: alerta factual;
- `CLI-013`: erro técnico por 429;
- demais seis: pendentes.

---

## 18.1 Alerta factual de `CLI-023`

Foram detectados valores monetários sem evidência consultada:

- R$ 65.417,16;
- R$ 148.535,01.

A resposta não foi tratada como sucesso pleno.

---

## 18.2 Métricas parciais

Nos quatro registros persistidos:

- tokens totais: 20.761;
- média de tokens por sucesso pleno: 6.220,5;
- latência total: 475,753 s;
- latência média: 118,938 s;
- retries totais: 5;
- riscos entre os sucessos plenos: 2 `médio`.

O custo monetário não foi fornecido pelo SDK e não foi estimado.

---

## 18.3 Lacuna de observabilidade encontrada

Em uma falha, três tools haviam sido executadas, mas seus nomes não tinham sido persistidos quando o parecer final falhou.

A implementação foi alterada para preservar `tools_chamadas` mesmo sem parecer final.

Os nomes antigos não foram reconstruídos retroativamente por falta de evidência.

---

# 19. Confronto entre regra e modelo

O enunciado exige um critério de correspondência, mas permite que o candidato o defina.

## 19.1 Critério adotado

- 0 sinalizações → risco esperado `baixo`;
- 1 sinalização → risco esperado `médio`;
- 2 ou mais → risco esperado `alto`.

### Atenção

Esse critério:

- é sintético;
- existe para possibilitar o confronto;
- não representa política de PLD;
- não representa regulamentação;
- não representa metodologia real do Itaú;
- não afirma que quantidade de sinais equivale a risco verdadeiro.

---

## 19.2 Casos comparáveis

Somente entram:

- sucesso pleno;
- parecer válido;
- validação factual sem alertas;
- risco disponível.

Ficam fora:

- erros;
- alertas;
- pendentes;
- respostas ausentes.

Ausência de parecer nunca vira risco baixo.

---

## 19.3 Resultado parcial

Casos comparáveis:

- `CLI-014`: regras alto × LLM médio;
- `CLI-028`: regras alto × LLM médio.

Resultado:

- comparáveis: 2;
- concordâncias: 0;
- divergências: 2;
- taxa parcial: 0%.

Essa taxa não representa os 10 clientes.

Para ambos foi registrada a conclusão:

> Não há evidência suficiente para determinar qual avaliação é mais adequada neste caso.

A divergência não foi tratada automaticamente como erro do agente ou das regras.

---

# 20. Observabilidade

Foram registrados, quando disponíveis:

- modelo;
- status;
- tokens de entrada;
- tokens de saída;
- tokens de pensamento;
- tokens totais;
- latência;
- retries;
- erros;
- tools utilizadas;
- alerta factual.

## Estado atual e limitação

`metricas.chamadas_api` já está implementado para novas execuções. Cada tentativa realmente enviada ao provedor registra, quando disponibilizados pelo SDK, latência, tokens, retries e erros por chamada. As métricas agregadas por análise de cliente continuam preservadas.

Os quatro registros históricos do lote foram gerados antes dessa melhoria e, por isso, não contêm métricas detalhadas por chamada. Esses dados não foram reconstruídos, estimados ou atribuídos retroativamente.

O custo monetário não é fornecido diretamente pelo SDK utilizado e permanece indisponível, sem estimativa.

---

# 21. Segurança

A API key é mantida em `.env`.

Verificações realizadas durante o desenvolvimento indicaram:

- `.env` no `.gitignore`;
- `.env` não rastreado pelo Git;
- nenhuma ocorrência de `.env` no histórico consultado;
- nenhuma chave nos notebooks;
- nenhuma chave nos outputs;
- scripts temporários de diagnóstico removidos.

`.env.example` contém somente nomes de variáveis.

---

# 22. Continuidade de negócio

A indisponibilidade observada mostrou que uma solução com LLM externa não deve depender de um único serviço para continuar operando.

## 22.1 O que já existe

- retry limitado;
- parada controlada após falhas consecutivas;
- interrupção em 429;
- persistência incremental;
- retomada;
- separação determinístico × LLM;
- separação de outputs por modelo.

Mesmo com a LLM indisponível, continuam funcionando:

- limpeza;
- conversão;
- regras;
- ranking;
- tools determinísticas.

A etapa interpretativa fica pendente.

Nenhum parecer fictício é gerado.

---

# 23. Limitações atuais

1. O lote não foi concluído para os 10 clientes devido à quota 429.
2. O confronto possui apenas dois casos comparáveis.
3. A validação factual automática cobre datas, valores e o caso específico de `percentual_uso` apresentado como volume, mas não semântica completa.
4. O custo monetário não foi disponibilizado.
5. Latência e tokens por chamada são registrados quando disponibilizados pelo SDK; a cobertura de observabilidade ainda depende das informações expostas pelo provedor.
6. Serviços externos introduzem indisponibilidade e quota.
7. O critério de confronto é sintético.
8. Os dados e regras do desafio não representam política real do Itaú.
9. A cobertura automatizada de testes ainda não inclui todos os componentes.
10. Resultados de modelos diferentes precisam permanecer identificados e separados.

---

# 24. Avaliação de provedor alternativo — Groq

## Decisão

O Gemini permaneceu como provedor principal do caminho executável final. O Groq foi avaliado como contingência diante de latência elevada em algumas execuções Gemini, erros `503`, retries e da interrupção parcial do lote por `429`.

A avaliação foi técnica e controlada; não constituiu migração de provedor nem produziu resultados incorporados ao lote final.

## Sequência de testes

1. **Chat mínimo** com `openai/gpt-oss-20b`: autenticação e modelo disponível, resposta `OK`, latência aproximada de 0,398 s, 76 tokens de entrada, 36 de saída e 112 no total. O SDK informou 26 `reasoning_tokens`, mas não forneceu custo por chamada.
2. **Tool calling sintético** com a tool temporária `consultar_saldo(cliente_id)`: o modelo escolheu a tool, recebeu o resultado local controlado para `CLI-TESTE` e devolveu resposta final correta. Foram duas chamadas, cerca de 0,823 s de latência agregada e 462 tokens, sem erro do provedor. Uma primeira tentativa falhou apenas na codificação local do terminal Windows (`cp1252` versus Unicode); o reteste com saída UTF-8 passou e essa ocorrência não foi tratada como falha do Groq.
3. **Agente com caso real `CLI-014`**: o modelo escolheu `historico_cliente` e `perfil_canal`. O fluxo técnico chegou ao parecer estruturado, mas houve uma extrapolação factual: `percentual_uso = 36,36%` foi apresentado também como percentual de volume financeiro, embora a evidência correspondesse apenas à quantidade de operações. Pydantic e o controle factual então existente não detectaram essa relação semântica; a inconsistência foi identificada em revisão humana.
4. **Reteste real**: após o reforço factual, a primeira chamada consultou `historico_cliente`. A chamada seguinte recebeu erro `400` porque o nome de tool retornado foi contaminado por marcador interno (`perfil_canal<|channel|>commentary`), não correspondendo a uma tool declarada. Não houve parecer final nesse reteste.

## Melhoria preservada

A experiência motivou melhorias independentes de provedor e mantidas no caminho Gemini:

- cálculos quantitativos permanecem responsabilidade de Pandas/Python;
- a LLM não deve criar percentuais, proporções, médias, somas ou relações quantitativas derivadas;
- `percentual_uso` é explicitamente definido como participação na quantidade de operações, não no volume financeiro;
- a validação factual alerta quando esse percentual é apresentado como percentual de volume;
- testes locais cobrem os casos permitidos e a extrapolação proibida;
- latência, tokens, retries e erros por chamada de API permanecem observáveis quando disponíveis.

## Trade-off e decisão final

O Groq apresentou latência inferior aos testes Gemini e passou os testes mínimo e sintético de tool calling. Ainda assim, a falha factual semântica e o erro `400` de validação de tool no reteste real indicaram risco de estabilidade e regressão dentro do prazo do desafio.

A decisão de engenharia foi **não promover Groq ao caminho principal**. Ela considera estabilidade, factualidade, risco de regressão, tempo restante e a necessidade de preservar uma entrega funcional e auditável. Isso não significa que o Groq “não funciona”; significa que ele foi avaliado como contingência, mas não atingiu estabilidade suficiente para substituir Gemini nesta entrega.

O código, a dependência, a chave de exemplo e os outputs diagnósticos específicos do Groq foram removidos antes da entrega final. O registro documental foi preservado para manter transparência e rastreabilidade.
