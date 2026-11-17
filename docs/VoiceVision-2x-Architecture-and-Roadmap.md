# VoiceVision 2.x
## Visão estratégica, auditoria arquitetural, landscape tecnológico e roadmap de evolução

**Tipo de documento:** Proposta técnica e instruções de trabalho para OpenCode  
**Projeto:** [rodolfomatos/voicevision](https://github.com/rodolfomatos/voicevision)  
**Estado:** Proposta para análise e evolução incremental  
**Versão:** 1.0  
**Data:** 16 de novembro de 2026

---

# 1. Instruções para o OpenCode

Este documento define uma visão-alvo e um plano de trabalho para a evolução do VoiceVision. Deve ser tratado como uma especificação de investigação, arquitetura e implementação incremental, não como autorização para reescrever imediatamente o projeto.

## 1.1. Regra fundamental

**Antes de alterar código, inspeciona integralmente o estado atual do repositório.** Não assumas que as funcionalidades, interfaces, dependências ou estruturas descritas neste documento já existem. Não removas nem substituas funcionalidades sem identificar o seu comportamento atual, dependentes e testes.

O documento contém:
- uma visão estratégica;
- uma arquitetura-alvo proposta;
- tecnologias e projetos externos a avaliar;
- hipóteses que carecem de confirmação por inspeção do código;
- um roadmap por milestones;
- critérios de aceitação;
- regras de segurança, compatibilidade e qualidade.

Distingue sempre:
1. **Facto observado:** confirmado no código, documentação ou execução.
2. **Hipótese:** possibilidade a verificar.
3. **Recomendação:** decisão arquitetural proposta.
4. **Decisão aprovada:** decisão explicitamente confirmada pelo responsável do projeto.

Não apresentes como auditoria concluída aquilo que ainda não foi inspecionado.

## 1.2. Modo de trabalho obrigatório

Trabalha em etapas pequenas e verificáveis:

1. Inspecionar o repositório e produzir um relatório `docs/audit/AS_IS.md`.
2. Mapear arquitetura, dependências, interfaces e fluxos reais.
3. Comparar o estado atual com a arquitetura-alvo deste documento.
4. Apresentar gaps, riscos e alternativas, com referências a ficheiros e linhas.
5. Propor um plano de alterações priorizado.
6. Só implementar depois de o plano estar suficientemente fundamentado.
7. Preservar compatibilidade e funcionalidades existentes sempre que possível.
8. Executar testes após cada alteração e documentar resultados.

Não executar uma refatorização global, não introduzir frameworks de agentes por moda e não acrescentar dependências pesadas sem demonstrar benefício.

## 1.3. Entregáveis esperados

Criar ou atualizar, conforme a estrutura existente do projeto:

```text
docs/
├── architecture/
│   ├── VISION.md
│   ├── TARGET_ARCHITECTURE.md
│   ├── PROVIDER_CONTRACTS.md
│   ├── EVENT_MODEL.md
│   ├── SECURITY_MODEL.md
│   └── ADR/
├── audit/
│   ├── AS_IS.md
│   ├── DEPENDENCY_MAP.md
│   ├── GAP_ANALYSIS.md
│   ├── TECHNOLOGY_LANDSCAPE.md
│   └── RISK_REGISTER.md
├── roadmap/
│   ├── ROADMAP_2X.md
│   └── ACCEPTANCE_CRITERIA.md
└── benchmarks/
    └── BASELINE.md
```

Não criar documentos duplicados se já existirem equivalentes. Integrar e atualizar a documentação existente.

---

# 2. Resumo executivo

O VoiceVision deve evoluir para uma **biblioteca e motor de inteligência multimodal local, extensível e independente de modelos**, capaz de receber sinais do mundo real — áudio, vídeo, imagem, texto e sensores —, transformá-los em contexto, conhecimento e ações, e disponibilizar essas capacidades a outras aplicações através de interfaces estáveis.

A ambição não é criar mais um assistente pessoal monolítico, nem competir diretamente com frameworks de orquestração em tempo real, plataformas RAG ou gateways de modelos. A ambição é fornecer uma infraestrutura modular que possa ser incorporada por aplicações e sistemas diferentes.

A proposta assenta em cinco princípios:

1. **Local-first:** a operação local e offline deve continuar a ser um princípio central.
2. **Composable:** os módulos devem ser reutilizáveis e substituíveis.
3. **Model-agnostic:** não depender de um fornecedor, modelo ou runtime específico.
4. **Event-driven:** os subsistemas comunicam através de eventos e contratos claros, sem acoplamento desnecessário.
5. **Secure-by-design:** ferramentas e ações têm permissões explícitas, validação e auditoria.

A evolução deve ser incremental. Primeiro é necessário conhecer rigorosamente o código atual; depois estabilizar contratos, gestão de sessão e execução; só então expandir memória, conhecimento e capacidades multimodais.

---

# 3. Visão e posicionamento do VoiceVision

## 3.1. Visão

**VoiceVision — Local Multimodal Intelligence Engine**

Um motor local de inteligência multimodal que:

- ouve e interpreta áudio;
- observa e interpreta imagens e vídeo;
- compreende linguagem natural;
- mantém contexto e memória entre sessões;
- consulta conhecimento local ou externo, quando autorizado;
- descobre e executa ferramentas e competências;
- comunica através de voz, texto e outras interfaces;
- funciona sem cloud como configuração possível e preferencial;
- pode ser integrado em aplicações de terceiros.

Princípio de comunicação:

> Perceive. Understand. Remember. Act.

## 3.2. O que o VoiceVision é

- Uma biblioteca Python e um runtime modular.
- Um conjunto de capacidades de perceção, cognição e execução.
- Uma camada de abstração sobre modelos e ferramentas.
- Uma infraestrutura que pode ser usada por aplicações externas.
- Um projeto que deve permitir configurações mínimas e avançadas.

## 3.3. O que o VoiceVision não deve tentar ser

- Uma aplicação monolítica que controla toda a experiência do utilizador.
- Um clone de Pipecat, LiveKit, AutoFlow ou de outro framework.
- Um sistema dependente de um único LLM.
- Uma plataforma RAG obrigatória para todos os utilizadores.
- Um executor arbitrário de código controlado pelo LLM.
- Um conjunto de dependências obrigatórias para funcionalidades opcionais.

## 3.4. Utilizadores e cenários

A arquitetura deve servir, pelo menos, estes cenários:

1. **Biblioteca integrada:** uma aplicação Python usa STT, TTS ou visão sem iniciar um assistente completo.
2. **Assistente local:** execução contínua com wake word, conversação e memória.
3. **Agente multimodal:** recebe áudio e imagens, consulta contexto e usa ferramentas.
4. **Backend de aplicações:** disponibiliza capacidades via HTTP, WebSocket ou MCP.
5. **Automação local:** integra dispositivos e serviços, com permissões controladas.
6. **Ambiente offline:** funciona sem acesso à Internet, usando modelos e dependências locais.
7. **Ambiente híbrido:** permite providers remotos opcionais, explicitamente configurados.

---

# 4. Princípios arquiteturais

## 4.1. Local-first, não local-only

A configuração base deve favorecer execução local. Providers remotos podem existir, mas:
- devem ser opcionais;
- devem estar claramente identificados;
- não podem ser ativados silenciosamente;
- devem respeitar a política de privacidade configurada;
- devem permitir ao utilizador perceber que dados saem da máquina.

## 4.2. Modular monolith como ponto de partida

Adotar inicialmente um **modular monolith**:
- módulos separados por responsabilidade;
- interfaces explícitas;
- dependências direcionais;
- possibilidade de executar certos providers como processos ou serviços externos;
- sem distribuir tudo por microserviços prematuramente.

A separação lógica deve preceder a separação física.

## 4.3. Providers intercambiáveis

O core não deve importar implementações concretas de Whisper, Piper, Ollama, llama.cpp, Mem0 ou qualquer outro produto.

O core depende de contratos. Os providers implementam esses contratos.

## 4.4. Separar perceção, decisão e execução

- **Perceção:** transforma sinais em representações estruturadas.
- **Decisão:** interpreta contexto e determina o próximo passo.
- **Execução:** executa ações autorizadas.

Uma transcrição, deteção visual ou resposta de LLM não é uma autorização para executar uma operação sensível.

## 4.5. Streaming e cancelamento como capacidades de primeira classe

O sistema deve tratar desde o início:
- dados parciais;
- streams;
- backpressure;
- cancelamento;
- timeouts;
- interrupções;
- encerramento gracioso;
- concorrência e sincronização.

Não desenhar as interfaces como se todos os providers fossem operações síncronas de request/response.

## 4.6. Configuração explícita e dependências opcionais

Uma instalação base deve ser leve. Funcionalidades como GraphRAG, diarização avançada, vídeo contínuo ou gateways externos devem ser extras opcionais.

---

# 5. Auditoria do estado atual — M0

A primeira tarefa do OpenCode é determinar o que existe realmente no repositório.

## 5.1. Inventário

Inspecionar:

- estrutura de diretórios;
- módulos Python;
- entry points;
- configuração e variáveis de ambiente;
- dependências obrigatórias e opcionais;
- scripts de instalação;
- Dockerfiles e serviços;
- testes;
- CI/CD;
- documentação;
- exemplos;
- licenças;
- integrações externas;
- gestão de modelos e artefactos.

Produzir um mapa dos módulos e das dependências entre eles.

## 5.2. Fluxos a rastrear

Documentar o fluxo real de cada capacidade existente:

### Áudio
- captura;
- buffers e frames;
- VAD;
- wake word;
- STT;
- transcrição parcial/final;
- gestão de silêncio;
- endpointing;
- TTS;
- reprodução;
- interrupção e cancelamento.

### Conversação
- criação de sessão;
- histórico;
- contexto;
- seleção do modelo;
- streaming de resposta;
- tool/function calling;
- erros;
- fim de turno;
- concorrência entre pedidos.

### Visão
- captura de imagem/vídeo;
- seleção de frames;
- pré-processamento;
- OCR/deteção/interpretação;
- associação da observação à sessão;
- limites de frequência e retenção.

### Integrações
- HTTP;
- WebSocket;
- SDK Python;
- CLI;
- MCP;
- integrações com aplicações e serviços externos.

### Memória e conhecimento
- persistência;
- formato dos dados;
- indexação;
- recuperação;
- atualização;
- eliminação;
- separação entre histórico e memória.

### Execução
- ferramentas;
- skills;
- descoberta;
- validação de argumentos;
- permissões;
- timeouts;
- isolamento;
- auditoria.

## 5.3. Qualidade e maturidade

Para cada módulo, avaliar:

| Dimensão | Perguntas |
|---|---|
| Responsabilidade | Tem uma função clara? |
| Acoplamento | Depende de implementações concretas? |
| Coesão | Contém responsabilidades não relacionadas? |
| Testabilidade | Pode ser testado isoladamente? |
| Concorrência | Gere cancelamento e recursos corretamente? |
| Robustez | Tem timeouts e tratamento de falhas? |
| Observabilidade | Expõe métricas e erros úteis? |
| Segurança | Valida entradas e limita ações? |
| Documentação | Contratos e limitações estão descritos? |
| Compatibilidade | Existem consumidores que dependem da API atual? |

## 5.4. Formato obrigatório das conclusões

Cada conclusão deve conter:
- estado: confirmado / hipótese / não verificado;
- evidência: ficheiro, classe, função e linhas;
- impacto;
- risco;
- recomendação;
- testes necessários.

Não declarar um gap sem verificar se a funcionalidade já existe.

---

# 6. Landscape tecnológico e projetos de referência

Os projetos seguintes são referências para comparação. Não são dependências automaticamente aprovadas. Antes de adotar código ou bibliotecas, verificar atividade, licença, compatibilidade, maturidade, dependências transitivas, segurança e custo operacional.

## 6.1. pHantasma

Repositório: https://github.com/linuxkafe/phantasma

Projeto de assistente local de voz. A documentação pública consultada descreve componentes como:
- openWakeWord;
- WebRTC VAD;
- Whisper;
- Ollama;
- Piper;
- SoX;
- Flask;
- SQLite;
- SearXNG;
- Skills carregadas dinamicamente.

### Ideias a estudar
- modelo de Skills;
- descoberta/carregamento de capacidades;
- ciclo de conversação simples;
- integração de componentes locais;
- feedback sonoro e estados de interação.

### Não copiar automaticamente
- arquitetura monolítica;
- dependências diretas de ferramentas concretas;
- modelo de memória sem avaliação;
- estrutura interna sem verificar a adequação ao VoiceVision.

### Orientação
Não fazer fork nem incorporar o projeto como dependência. Estudar padrões e componentes isolados. Verificar a licença MIT e a licença de todas as dependências antes de reutilizar código.

## 6.2. PingCAP AutoFlow

Repositório: https://github.com/pingcap/autoflow

Projeto orientado para GraphRAG e conhecimento conversacional, com tecnologias como TiDB, LlamaIndex e DSPy.

### Ideias a estudar
- ingestão de documentos e páginas;
- extração de entidades e relações;
- recuperação híbrida;
- combinação de pesquisa vetorial e estrutura de grafo;
- contextualização de respostas.

### Limitações para o VoiceVision
- complexidade de infraestrutura;
- dependência de serviços de armazenamento e indexação;
- possível desproporção para um assistente local simples;
- não resolve o problema central de gestão de áudio em tempo real.

### Orientação
Não incorporar AutoFlow no core. Definir uma abstração `KnowledgeProvider`. GraphRAG deve ser uma implementação opcional, possivelmente um serviço externo.

## 6.3. Awesome DeepSeek Integration

Repositório: https://github.com/deepseek-ai/awesome-deepseek-integration

Usar como catálogo de descoberta, não como roadmap nem como garantia de compatibilidade. A seleção deve privilegiar projetos que funcionem independentemente da API DeepSeek.

Projetos/categorias a investigar:
- LiteLLM;
- Mem0;
- smolagents;
- RAGFlow;
- KAG;
- ferramentas de avaliação e observabilidade;
- integrações MCP.

## 6.4. Pipecat

Repositório: https://github.com/pipecat-ai/pipecat

Framework Python para pipelines de voz e multimodais em tempo real.

### Estudar
- pipeline de frames;
- streaming;
- separação de transporte e processamento;
- gestão de tarefas;
- interrupções;
- turn management;
- providers de STT, LLM e TTS;
- sincronização de eventos.

### Orientação
É a principal referência para comparar a arquitetura de tempo real. Não adotar integralmente sem benchmark. Determinar se o VoiceVision já resolve os mesmos problemas com menor complexidade.

## 6.5. LiveKit Agents

Repositório: https://github.com/livekit/agents

Framework para agentes de voz/vídeo e sessões em tempo real, especialmente relevante para WebRTC e cenários distribuídos.

### Estudar
- gestão de sessões;
- transporte WebRTC;
- turn-taking;
- barge-in;
- interrupções;
- escalabilidade;
- integração de vídeo e áudio.

### Orientação
Manter como integração ou backend opcional se o VoiceVision evoluir para múltiplos clientes, comunicação distribuída ou experiências WebRTC. Não tornar obrigatório para utilização local.

## 6.6. Outros projetos

| Projeto | URL | Área | Orientação |
|---|---|---|---|
| Silero VAD | https://github.com/snakers4/silero-vad | VAD | Benchmark |
| openWakeWord | https://github.com/dscripka/openWakeWord | Wake word | Provider candidato |
| Mem0 | https://github.com/mem0ai/mem0 | Memória | Benchmark |
| LiteLLM | https://github.com/BerriAI/litellm | Model routing | Adapter opcional |
| Langfuse | https://github.com/langfuse/langfuse | Observabilidade LLM | Avaliar |
| promptfoo | https://github.com/promptfoo/promptfoo | Testes e red teaming | Avaliar |
| smolagents | https://github.com/huggingface/smolagents | Agentes | Comparar com runtime próprio |
| pyannote.audio | https://github.com/pyannote/pyannote-audio | Diarização | Provider opcional |
| RAGFlow | https://github.com/infiniflow/ragflow | RAG documental | Serviço externo opcional |
| LightRAG | https://github.com/HKUDS/LightRAG | GraphRAG | Benchmark |
| Bolna | https://github.com/bolna-ai/bolna | Voice agents | Estudar turn management |
| Home Assistant | https://github.com/home-assistant/core | Automação | Integração opcional |

A lista é uma shortlist inicial. O OpenCode deve verificar o estado atual dos projetos, documentação, releases e licenças antes de recomendar adoção.

---

# 7. Arquitetura-alvo proposta

## 7.1. Visão lógica

```text
┌────────────────────────────────────────────────────────────┐
│                    INTERACTION INTERFACES                   │
│       Python SDK | REST | WebSocket | MCP | CLI             │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│              SESSION & CONVERSATION ENGINE                  │
│ Session Manager | Turn Manager | State Machine              │
│ Cancellation | Barge-in | Context Assembly                  │
└───────────────┬───────────────────────┬─────────────────────┘
                │                       │
┌───────────────▼──────────┐  ┌─────────▼────────────────────┐
│     PERCEPTION LAYER     │  │       COGNITIVE LAYER        │
│                          │  │                              │
│ Audio:                   │  │ LLM Router                   │
│ - Capture                │  │ Context Manager              │
│ - VAD                    │  │ Reasoning                    │
│ - Wake word              │  │ Memory                       │
│ - STT                    │  │ Knowledge / RAG              │
│ - Speaker ID             │  │                              │
│                          │  │                              │
│ Vision:                  │  └──────────────┬───────────────┘
│ - Camera                 │                 │
│ - Image                  │  ┌──────────────▼───────────────┐
│ - Video                  │  │       EXECUTION LAYER       │
│ - OCR                    │  │ Tools | Skills | MCP         │
│ - Detection              │  │ Workflows | Permissions      │
└───────────────┬──────────┘  └──────────────┬───────────────┘
                │                            │
                └──────────────┬─────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│                       OUTPUT LAYER                          │
│             TTS | Audio | Text | Events | Notifications     │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                   SHARED INFRASTRUCTURE                     │
│ Event Bus | Provider Registry | Configuration               │
│ Permissions | Logging | Metrics | Tracing | Evaluation      │
└────────────────────────────────────────────────────────────┘
```

O diagrama representa separação lógica, não obriga a processos ou serviços independentes.

## 7.2. Organização de módulos indicativa

A estrutura real deve respeitar a organização atual se esta já for coerente. A seguinte árvore é uma orientação, não uma instrução para mover tudo imediatamente:

```text
voicevision/
├── core/
│   ├── events/
│   ├── sessions/
│   ├── conversation/
│   ├── state/
│   ├── config/
│   └── errors/
├── perception/
│   ├── audio/
│   ├── vision/
│   └── sensors/
├── intelligence/
│   ├── llm/
│   ├── routing/
│   ├── context/
│   ├── memory/
│   └── knowledge/
├── execution/
│   ├── tools/
│   ├── skills/
│   ├── permissions/
│   └── workflows/
├── providers/
│   ├── stt/
│   ├── tts/
│   ├── vad/
│   ├── wakeword/
│   ├── llm/
│   ├── vision/
│   ├── memory/
│   └── knowledge/
├── interfaces/
│   ├── python/
│   ├── http/
│   ├── websocket/
│   ├── mcp/
│   └── cli/
├── observability/
│   ├── logging/
│   ├── metrics/
│   └── tracing/
└── evaluation/
```

## 7.3. Responsabilidades

### Core
- ciclo de vida da aplicação;
- gestão de sessões;
- eventos internos;
- estados de conversação;
- configuração;
- erros tipados;
- cancelamento e timeouts.

### Perception
- transformar dados de áudio, vídeo, imagem e sensores em resultados estruturados;
- não decidir autonomamente ações externas;
- suportar streaming e dados parciais.

### Intelligence
- selecionar modelos;
- compor contexto;
- interpretar pedidos;
- decidir quando consultar memória ou conhecimento;
- produzir pedidos de ferramentas estruturados.

### Execution
- descobrir ferramentas;
- validar argumentos;
- verificar permissões;
- executar;
- aplicar timeouts e limites;
- registar resultados.

### Providers
- encapsular tecnologias concretas;
- expor contratos comuns;
- gerir recursos e dependências próprias;
- declarar capacidades e limitações.

### Interfaces
- expor funcionalidades a aplicações;
- manter compatibilidade;
- não duplicar lógica de negócio.

### Observability/Evaluation
- medir latência por etapa;
- rastrear interações;
- permitir testes reproduzíveis;
- avaliar qualidade e regressões.

---

# 8. Gestão de sessão e conversação

Esta é uma das áreas prioritárias da evolução.

## 8.1. Máquina de estados

Definir uma máquina de estados explícita. Um modelo inicial possível:

```text
IDLE
  └── wake word / input ──> LISTENING

LISTENING
  ├── speech detected ──> CAPTURING
  └── cancel ──> IDLE

CAPTURING
  ├── endpoint detected ──> TRANSCRIBING
  └── cancel ──> IDLE

TRANSCRIBING
  ├── final transcript ──> THINKING
  └── error ──> ERROR

THINKING
  ├── tool request ──> EXECUTING
  ├── response ready ──> SPEAKING
  └── cancel ──> CANCELLED

EXECUTING
  ├── tool result ──> THINKING
  ├── error ──> ERROR
  └── cancel ──> CANCELLED

SPEAKING
  ├── playback complete ──> IDLE / LISTENING
  ├── user interruption ──> INTERRUPTED
  └── cancel ──> CANCELLED
```

O desenho final deve contemplar estados transitórios, erros recuperáveis, sessões concorrentes e retomada. Não assumir que esta máquina de estados é suficiente sem análise dos fluxos reais.

## 8.2. Turn management

Distinguir:
- deteção de atividade vocal;
- deteção de fim de fala;
- endpointing;
- interpretação de pausa;
- conclusão de turno;
- interrupção do assistente.

Uma pausa não significa necessariamente que o utilizador terminou. A estratégia deve ser configurável e testada em condições reais.

## 8.3. Barge-in

Quando o utilizador começa a falar durante a resposta:
1. detetar a nova fala;
2. cancelar a geração ou reprodução em curso, conforme aplicável;
3. interromper imediatamente o áudio reproduzido;
4. invalidar chunks de saída antigos;
5. preservar o estado conversacional consistente;
6. iniciar o novo turno;
7. evitar que a resposta anterior seja retomada acidentalmente.

É necessário testar interrupções em cada fase: geração LLM, TTS, buffering e playback.

## 8.4. Streaming

Os providers devem suportar resultados parciais sempre que tecnicamente possível. Definir:
- ordenação de chunks;
- identificador de sessão e turno;
- timestamps;
- cancelamento;
- backpressure;
- tratamento de chunks atrasados;
- política para resultados parciais que são substituídos por resultados finais.

---

# 9. Contratos e Provider Architecture

As interfaces seguintes são exemplos conceptuais. O OpenCode deve adaptá-las às convenções, versões de Python e padrões existentes no repositório.

## 9.1. Requisitos comuns

Todos os providers devem:
- expor capacidades e metadados;
- validar configuração;
- declarar dependências;
- ter ciclo de vida claro;
- suportar timeouts;
- permitir cancelamento quando aplicável;
- produzir erros tipados;
- disponibilizar logs e métricas;
- ser testáveis com mocks/fakes;
- não exigir que o core conheça a tecnologia concreta.

## 9.2. Interfaces indicativas

```python
class STTProvider:
    async def transcribe(self, audio, *, options=None):
        ...

    async def stream(self, audio_stream, *, options=None):
        ...


class TTSProvider:
    async def synthesize(self, text, *, options=None):
        ...

    async def stream(self, text_stream, *, options=None):
        ...


class LLMProvider:
    async def generate(self, messages, *, tools=None, options=None):
        ...

    async def stream(self, messages, *, tools=None, options=None):
        ...


class VADProvider:
    async def process(self, audio_frame):
        ...


class WakeWordProvider:
    async def process(self, audio_frame):
        ...


class VisionProvider:
    async def analyze(self, image, *, context=None, options=None):
        ...


class MemoryProvider:
    async def remember(self, item, *, metadata=None):
        ...

    async def recall(self, query, *, limit=5, filters=None):
        ...

    async def forget(self, memory_id):
        ...


class KnowledgeProvider:
    async def search(self, query, *, limit=5, filters=None):
        ...


class SkillProvider:
    def discover(self):
        ...

    async def execute(self, skill_id, arguments, *, context):
        ...
```

Não é obrigatório que todos os métodos sejam `async` se a tecnologia ou interface justificar outra abordagem. Evitar criar abstrações artificiais.

## 9.3. Provider registry

O registry deve permitir:
- registar providers;
- descobrir capacidades;
- selecionar provider por configuração;
- validar compatibilidade;
- consultar estado;
- gerir inicialização e encerramento;
- impedir combinações incompatíveis.

Não confundir registry de providers com registry de Skills.

## 9.4. Model Router

O router deve suportar:
- seleção por capacidade;
- seleção por configuração;
- fallback explícito;
- limites de timeout;
- deteção de indisponibilidade;
- política de privacidade;
- custos, quando aplicável;
- métricas de latência e falhas.

A seleção automática não deve enviar dados para um provider remoto sem autorização/configuração explícita.

LiteLLM pode ser avaliado como adapter, não como dependência obrigatória do core.

---

# 10. Event model

Introduzir ou consolidar um sistema de eventos interno.

## 10.1. Eventos indicativos

```text
audio.started
audio.frame_received
audio.speech_detected
audio.speech_ended

wakeword.detected

transcription.partial
transcription.final

conversation.session_created
conversation.turn_started
conversation.turn_completed
conversation.interrupted
conversation.cancelled

llm.request_started
llm.token_received
llm.request_completed
llm.request_failed

skill.discovered
skill.requested
skill.started
skill.completed
skill.failed

tts.started
tts.audio_chunk
tts.completed
tts.cancelled

vision.frame_received
vision.analysis_started
vision.analysis_completed

memory.stored
memory.recalled
memory.deleted

knowledge.search_started
knowledge.search_completed
```

## 10.2. Envelope comum

Cada evento deve transportar, quando aplicável:
- `event_id`;
- `event_type`;
- `timestamp`;
- `session_id`;
- `turn_id`;
- `correlation_id`;
- `source`;
- `schema_version`;
- payload tipado.

Não transportar grandes buffers de áudio/vídeo no event bus. Usar streams, referências a buffers ou objetos de dados apropriados.

## 10.3. Requisitos

- ordenação definida onde necessária;
- tratamento de falhas dos handlers;
- isolamento entre listeners;
- backpressure;
- cancelamento;
- política de retenção;
- compatibilidade de schemas;
- tracing por `correlation_id`.

Começar com uma implementação in-process simples. Só introduzir broker externo se existir necessidade comprovada.

---

# 11. Skills, Tools e MCP

## 11.1. Objetivo

Criar um sistema extensível de competências que permita ao VoiceVision descobrir e executar operações autorizadas.

Uma Skill é uma capacidade semântica com contrato, permissões e ciclo de vida. Não deve ser simplesmente um ficheiro Python arbitrário executado pelo LLM.

## 11.2. Manifesto de Skill

Exemplo conceptual:

```yaml
id: vision.describe
name: Describe image
version: 1.0.0
description: Describe the content of an image.
input_schema:
  type: object
  properties:
    image_ref:
      type: string
  required:
    - image_ref
permissions:
  - vision.read
execution:
  timeout_seconds: 20
  mode: in_process
```

O formato definitivo pode ser JSON, YAML ou outro, desde que seja validável e versionado.

## 11.3. Capacidades possíveis

| Skill | Função |
|---|---|
| `vision.describe` | Descrever imagem |
| `vision.ocr` | Extrair texto de imagem |
| `voice.transcribe` | Transcrever áudio |
| `memory.recall` | Recuperar memória |
| `memory.learn` | Propor/guardar memória |
| `knowledge.search` | Pesquisar conhecimento |
| `home.control` | Controlar dispositivos autorizados |
| `web.search` | Pesquisa web, se ativada |
| `system.execute` | Operações locais explicitamente autorizadas |
| `calendar.manage` | Operações de calendário com permissões |

Estas são ideias de catálogo, não skills que devam ser todas implementadas no MVP.

## 11.4. Segurança

Obrigatório:
- schema validation;
- allowlist de skills;
- permissões por skill e por sessão;
- confirmação humana para operações sensíveis;
- timeout;
- limites de recursos;
- prevenção de path traversal;
- proteção contra command injection;
- isolamento de processos quando necessário;
- logs de auditoria;
- segredos fora dos manifests;
- não permitir execução arbitrária de código sugerido pelo LLM.

O resultado de uma ferramenta é dado não fiável. Não deve poder alterar políticas de segurança ou instruções do sistema.

## 11.5. MCP

MCP deve ser uma interface de interoperabilidade. Não deve ser o mecanismo interno obrigatório de execução.

O core pode executar uma Skill diretamente; o adapter MCP expõe capacidades compatíveis a clientes externos. Evitar duplicar autorização e validação entre o runtime interno e o servidor MCP.

---

# 12. Memória e Knowledge

## 12.1. Separar conceitos

Não misturar:
- histórico integral de conversação;
- contexto temporário de uma sessão;
- memória de longo prazo;
- preferências do utilizador;
- factos extraídos;
- conhecimento documental;
- cache.

Cada tipo tem regras de retenção, atualização, privacidade e recuperação diferentes.

## 12.2. Memória de longo prazo

Uma memória útil exige:
- extração seletiva;
- proveniência;
- confiança;
- timestamp;
- atualização e resolução de contradições;
- recuperação contextual;
- eliminação;
- exportação;
- controlo pelo utilizador.

Não guardar automaticamente tudo o que o utilizador diz. A memória deve ter políticas configuráveis.

## 12.3. Implementação inicial

Começar com uma solução local simples, por exemplo SQLite, se for adequada ao estado atual do projeto.

Definir `MemoryProvider` antes de avaliar implementações externas.

## 12.4. Mem0

Repositório: https://github.com/mem0ai/mem0

Avaliar:
- qualidade da extração;
- qualidade da recuperação;
- atualizações e contradições;
- custo de inferência;
- dependências;
- operação offline;
- controlo e eliminação de dados;
- latência.

Não adotar apenas por oferecer uma API conveniente.

## 12.5. Knowledge e RAG

Definir `KnowledgeProvider` para pesquisa contextual.

Possíveis implementações:
- pesquisa textual local;
- pesquisa vetorial;
- RAG documental;
- GraphRAG;
- serviço externo.

## 12.6. GraphRAG

GraphRAG deve ser opcional e justificado por casos de uso que beneficiem de relações explícitas entre entidades.

Avaliar LightRAG, AutoFlow e alternativas, comparando:
- qualidade da recuperação;
- custo de ingestão;
- custo de armazenamento;
- latência;
- complexidade operacional;
- operação local;
- explicabilidade e proveniência.

Não introduzir uma base de dados de grafos ou infraestrutura adicional sem benchmark e caso de uso concreto.

---

# 13. Visão e multimodalidade

## 13.1. Pipeline de visão independente

A visão deve poder ser utilizada sem ativar o pipeline de voz.

Capacidades possíveis:
- análise de imagem pontual;
- OCR;
- deteção de objetos;
- descrição de cenas;
- análise de frames;
- interpretação contextual;
- associação de observações à sessão.

## 13.2. Vídeo

Não enviar continuamente todos os frames para o LLM.

Definir:
- frequência de amostragem;
- deteção de alterações;
- seleção de frames;
- limites de resolução;
- limites de memória;
- política de retenção;
- processamento local;
- consentimento e indicadores de captura.

## 13.3. Contexto audiovisual

A sessão pode reunir:
- transcrição;
- timestamp;
- observações visuais;
- identidade de speaker, quando disponível;
- resultados de ferramentas;
- contexto relevante.

A associação temporal deve ser explícita. Não assumir que uma imagem corresponde ao conteúdo de uma frase sem evidência temporal/contextual.

## 13.4. Speaker identification

Diarização e identificação de pessoa são conceitos distintos. O sistema deve distinguir speakers dentro de um áudio sem inferir automaticamente a identidade civil de alguém.

Avaliar pyannote.audio como provider opcional, tendo em conta dependências, modelos, licenças e requisitos de hardware.

---

# 14. Observabilidade e avaliação

## 14.1. Métricas de latência

Medir separadamente:

- captura até VAD;
- wake word;
- VAD até endpoint;
- STT;
- preparação de contexto;
- LLM first-token latency;
- duração total de inferência;
- execução de ferramentas;
- TTS first-audio latency;
- duração de síntese;
- buffering e playback;
- latência total percebida.

Registar percentis p50, p95 e p99 quando houver volume de amostras suficiente.

## 14.2. Tracing

Uma interação deve ter um identificador de correlação que permita reconstruir o percurso entre:
- sessão;
- turno;
- transcrição;
- pedido LLM;
- tool call;
- TTS;
- resultado final.

## 14.3. Privacidade

Não guardar áudio, transcrições, imagens ou prompts por defeito em sistemas de observabilidade.

Permitir:
- redaction;
- amostragem;
- retenção configurável;
- opt-in para gravação de traces com conteúdo;
- separação de metadados e payloads sensíveis.

## 14.4. Ferramentas

Avaliar:
- Langfuse: https://github.com/langfuse/langfuse
- promptfoo: https://github.com/promptfoo/promptfoo

Estas ferramentas podem ser usadas no desenvolvimento e avaliação sem serem dependências runtime obrigatórias.

## 14.5. Testes

Criar:
- unit tests;
- contract tests para providers;
- integração com providers locais;
- testes de streaming;
- testes de concorrência;
- testes de cancelamento;
- testes de interrupção;
- testes offline;
- testes de regressão de qualidade;
- testes de segurança das Skills.

---

# 15. Segurança, privacidade e confiança

A segurança deve ser transversal à arquitetura.

## 15.1. Princípios

- Menor privilégio.
- Consentimento e transparência.
- Execução explicitamente autorizada.
- Segredos protegidos.
- Dados locais por defeito.
- Retenção mínima.
- Logs sem conteúdo sensível por defeito.
- Separação entre instruções, dados e resultados de ferramentas.

## 15.2. Ameaças a considerar

- prompt injection em documentos, páginas web ou resultados de ferramentas;
- execução de comandos não autorizados;
- exfiltração de dados por providers remotos;
- acesso indevido ao microfone/câmara;
- exposição de credenciais;
- skills maliciosas;
- dependências comprometidas;
- path traversal;
- command injection;
- denial of service por streams ou ferramentas;
- dados de sessão cruzados entre utilizadores.

## 15.3. Política de ações

Classificar as operações:

| Nível | Tipo | Política |
|---|---|---|
| 0 | Leitura não sensível | Pode executar conforme configuração |
| 1 | Leitura de dados privados | Permissão explícita |
| 2 | Alteração reversível | Autorização configurada |
| 3 | Ação externa ou sensível | Confirmação humana |
| 4 | Ação destrutiva ou privilegiada | Bloqueada por defeito ou confirmação reforçada |

A classificação concreta deve ser configurável e documentada.

---

# 16. Roadmap de implementação

A ordem abaixo é uma proposta. O plano final deve ser ajustado após a auditoria M0.

## M0 — Architecture Audit

**Objetivo:** conhecer o estado real e estabelecer baseline.

Tarefas:
- inventário do repositório;
- mapa de dependências;
- rastreio dos fluxos;
- análise de concorrência e processos;
- análise de API e compatibilidade;
- revisão de testes;
- revisão de licenças;
- benchmarks iniciais;
- gap analysis;
- registo de riscos.

Entregáveis:
- `AS_IS.md`;
- `DEPENDENCY_MAP.md`;
- `GAP_ANALYSIS.md`;
- `TECHNOLOGY_LANDSCAPE.md`;
- `RISK_REGISTER.md`;
- `BASELINE.md`.

**Critério de saída:** arquitetura atual documentada com evidência, gaps priorizados e plano aprovado.

## M1 — Core Abstraction

**Objetivo:** consolidar contratos e ciclo de vida sem alterar desnecessariamente os providers existentes.

Tarefas:
- interfaces de providers;
- configuração e registry;
- erros tipados;
- gestão de recursos;
- event bus in-process;
- Session Manager;
- Conversation State Machine;
- cancelamento e timeouts;
- testes de contratos.

**Critério de saída:** pelo menos dois providers de uma mesma categoria podem ser selecionados sem alterar o core, se existirem alternativas viáveis.

## M2 — Real-time Voice

**Objetivo:** melhorar a naturalidade e robustez da interação de voz.

Tarefas:
- benchmark VAD;
- benchmark wake word;
- streaming STT/TTS;
- endpointing;
- turn management;
- barge-in;
- cancelamento de geração e playback;
- gestão de buffers;
- testes em condições de ruído.

**Critério de saída:** interrupção consistente, sem reprodução de áudio obsoleto, e métricas de latência disponíveis.

## M3 — Skills & Intelligence

**Objetivo:** formalizar a execução de ferramentas.

Tarefas:
- Skill manifest;
- discovery;
- registry;
- JSON Schema;
- permissões;
- timeouts;
- execução isolada quando necessária;
- logs de auditoria;
- integração MCP;
- Model Router.

**Critério de saída:** uma Skill pode ser descoberta, validada, autorizada, executada e auditada sem acoplamento ao LLM utilizado.

## M4 — Memory & Knowledge

**Objetivo:** acrescentar memória persistente e recuperação contextual.

Tarefas:
- separar histórico, contexto e memória;
- definir modelo de dados;
- implementar persistência local;
- recall e atualização;
- eliminação/exportação;
- benchmark Mem0;
- KnowledgeProvider;
- RAG básico;
- benchmark GraphRAG.

**Critério de saída:** memória persiste entre sessões, tem proveniência e pode ser consultada e eliminada de forma controlada.

## M5 — Multimodal & Quality

**Objetivo:** consolidar visão, avaliação e qualidade operacional.

Tarefas:
- VisionProvider;
- OCR e descrição de imagem;
- seleção de frames;
- associação temporal;
- contexto audiovisual;
- observabilidade;
- benchmarks;
- testes de regressão;
- documentação de deployment.

**Critério de saída:** uma sessão pode integrar áudio e observações visuais com timestamps, tracing e limites de privacidade definidos.

---

# 17. Prioridades

| Prioridade | Trabalho | Justificação |
|---|---|---|
| P0 | Auditoria do código atual | Evitar refatorizações cegas |
| P0 | Contratos e providers | Reduzir acoplamento |
| P0 | Gestão de sessão/turno | Base da interação realtime |
| P0 | Cancelamento e barge-in | Naturalidade e correção |
| P0 | Segurança de Tools/Skills | Evitar execução indevida |
| P1 | Event model | Desacoplamento |
| P1 | Model routing | Flexibilidade |
| P1 | Memória persistente | Continuidade contextual |
| P1 | Observabilidade | Diagnóstico e otimização |
| P2 | GraphRAG | Conhecimento relacional |
| P2 | Vídeo contínuo | Multimodalidade avançada |
| P2 | Diarização avançada | Casos de uso específicos |
| P2 | Integrações distribuídas | Escala e múltiplos clientes |

---

# 18. Critérios de aceitação transversais

## 18.1. Arquitetura
- O core não depende de implementações concretas de providers.
- Interfaces documentadas e versionadas.
- Dependências opcionais não são carregadas no arranque base.
- Erros são tipados e propagados de forma consistente.

## 18.2. Offline
- Pipeline configurado para operação local funciona sem Internet.
- Ausência de chamadas remotas silenciosas.
- Modelos e dependências necessários estão identificados.
- Testes offline fazem parte do CI sempre que possível.

## 18.3. Realtime
- Streams suportam cancelamento.
- Não há bloqueio indevido da captura de áudio.
- Barge-in cancela geração/reprodução obsoleta.
- Eventos são associados à sessão e turno corretos.

## 18.4. Skills
- Argumentos validados por schema.
- Permissões verificadas antes da execução.
- Timeouts aplicados.
- Ações sensíveis exigem confirmação.
- Execuções ficam auditadas.

## 18.5. Memória
- Persistência entre sessões.
- Proveniência e timestamps.
- Atualização e eliminação.
- Recuperação avaliada com dataset de teste.
- Política de retenção documentada.

## 18.6. Qualidade
- Testes unitários e de integração.
- Contract tests de providers.
- Benchmarks reproduzíveis.
- CI sem regressões conhecidas.
- Documentação atualizada com cada alteração relevante.

---

# 19. Decisões arquiteturais propostas

Estas decisões são recomendações iniciais, sujeitas a validação após M0.

| Tema | Recomendação | Estado |
|---|---|---|
| Fork pHantasma | Não | Proposta |
| Incorporar AutoFlow | Não | Proposta |
| Skills inspiradas no pHantasma | Sim | Proposta |
| Pipecat | Benchmark e referência | Proposta |
| LiveKit | Adapter/opção futura | Proposta |
| LiteLLM | Adapter opcional | Proposta |
| Mem0 | Benchmark antes de adotar | Proposta |
| GraphRAG | Módulo opcional | Proposta |
| Event bus | In-process inicialmente | Proposta |
| Provider architecture | Sim | Proposta |
| Modular monolith | Sim | Proposta |
| Offline-first | Preservar | Princípio |
| MCP | Interface de interoperabilidade | Proposta |
| Microservices | Não introduzir sem necessidade | Princípio |

O OpenCode não deve converter estas propostas em alterações automáticas sem apresentar evidência e avaliar o impacto sobre o projeto atual.

---

# 20. Plano de benchmark

Antes de substituir qualquer componente, estabelecer comparação com o provider atual.

## 20.1. Áudio
- precisão VAD em silêncio e ruído;
- falsos positivos de wake word;
- falsos negativos;
- latência de deteção;
- latência STT;
- qualidade da transcrição;
- latência TTS;
- inteligibilidade;
- consumo CPU/RAM/GPU.

## 20.2. Conversação
- tempo até primeiro token;
- tempo até primeira resposta audível;
- latência total;
- tempo de interrupção;
- taxa de falhas;
- comportamento sob concorrência.

## 20.3. Memória e RAG
- precisão e recall;
- relevância contextual;
- latência;
- custo de armazenamento;
- comportamento perante contradições;
- qualidade da proveniência;
- capacidade de eliminação.

## 20.4. Providers
Comparar:
- compatibilidade com interfaces;
- maturidade;
- manutenção;
- licença;
- dependências;
- operação offline;
- hardware necessário;
- facilidade de instalação;
- comportamento em falha.

Todos os benchmarks devem registar:
- hardware;
- sistema operativo;
- versões;
- configuração;
- dataset;
- número de execuções;
- método de cálculo;
- resultados brutos.

---

# 21. Compatibilidade e estratégia de migração

A evolução deve evitar quebrar consumidores existentes.

1. Inventariar API pública e imports utilizados.
2. Identificar configurações e formatos persistidos.
3. Criar contratos novos em paralelo quando necessário.
4. Adaptar implementações antigas através de wrappers.
5. Depreciar interfaces apenas com documentação e período de transição.
6. Manter exemplos funcionais.
7. Criar testes de compatibilidade.
8. Não alterar defaults de privacidade ou execução sem decisão explícita.

A versão major só deve ser incrementada quando existirem alterações incompatíveis justificadas e documentadas.

---

# 22. Riscos principais

| Risco | Impacto | Mitigação |
|---|---|---|
| Overengineering | Alto | Modular monolith e milestones |
| Dependências pesadas | Alto | Extras opcionais |
| Regressão de áudio | Alto | Baseline e contract tests |
| Concorrência incorreta | Alto | State machine e testes |
| Execução insegura de Skills | Crítico | Permissões, validação e isolamento |
| Fuga de dados para cloud | Crítico | Política explícita de providers |
| Memória incorreta | Alto | Proveniência, confiança e controlo |
| Complexidade GraphRAG | Médio/alto | Módulo opcional |
| Duplicação com Pipecat | Médio | Benchmark antes de adotar |
| Incompatibilidade API | Alto | Migração gradual |
| Observabilidade com dados sensíveis | Alto | Redaction e retenção mínima |

---

# 23. Tarefas imediatas para OpenCode

Executar apenas a fase de auditoria, salvo instrução posterior em contrário.

## Tarefa 1 — Inspeção
- Ler README, documentação e configuração.
- Inspecionar todos os módulos relevantes.
- Identificar entry points e dependências.
- Executar testes existentes.
- Identificar funcionalidades implementadas e incompletas.

## Tarefa 2 — Mapa arquitetural
- Produzir diagrama da arquitetura atual.
- Mapear fluxos de áudio, conversação, visão, memória e ferramentas.
- Mapear chamadas entre módulos.
- Identificar acoplamentos e ciclos.

## Tarefa 3 — Auditoria técnica
- Avaliar concorrência, processos, buffers e cancelamento.
- Avaliar API, WebSocket, SDK e MCP.
- Avaliar segurança das ferramentas.
- Avaliar armazenamento e privacidade.
- Avaliar testes e CI.

## Tarefa 4 — Comparação
Comparar a arquitetura atual com:
- pHantasma;
- AutoFlow;
- Pipecat;
- LiveKit Agents;
- Silero VAD;
- openWakeWord;
- Mem0;
- LiteLLM;
- Langfuse;
- promptfoo;
- smolagents;
- pyannote.audio;
- LightRAG.

Não é necessário analisar todos com a mesma profundidade. Priorizar os que correspondem a gaps reais identificados no código.

## Tarefa 5 — Relatório
Produzir:
- estado atual;
- pontos fortes a preservar;
- problemas confirmados;
- gaps;
- oportunidades;
- alternativas;
- riscos;
- decisões recomendadas;
- roadmap revisto;
- tarefas de implementação com dependências e critérios de aceitação.

## Tarefa 6 — Parar e apresentar conclusões
No final da auditoria, **não começar automaticamente a refatorização**. Apresentar o relatório e a sequência recomendada de alterações para validação.

---

# 24. Resultado esperado

O resultado final não deve ser apenas um assistente de voz com mais integrações.

Deve ser uma infraestrutura modular que permita a qualquer aplicação:

1. receber sinais do mundo real;
2. interpretar esses sinais;
3. manter contexto;
4. consultar memória e conhecimento;
5. decidir que capacidade utilizar;
6. executar operações autorizadas;
7. devolver resultados por diferentes interfaces.

A vantagem competitiva do VoiceVision deve estar na composição coerente destas capacidades, na operação local, na independência de modelos e na facilidade de integração.

**Não construir tudo. Construir o núcleo certo, definir bons contratos e permitir que o ecossistema forneça o resto.**

---

# 25. Referências

## Repositórios centrais
- VoiceVision: https://github.com/rodolfomatos/voicevision
- pHantasma: https://github.com/linuxkafe/phantasma
- AutoFlow: https://github.com/pingcap/autoflow
- Awesome DeepSeek Integration: https://github.com/deepseek-ai/awesome-deepseek-integration

## Realtime e voz
- Pipecat: https://github.com/pipecat-ai/pipecat
- LiveKit Agents: https://github.com/livekit/agents
- Silero VAD: https://github.com/snakers4/silero-vad
- openWakeWord: https://github.com/dscripka/openWakeWord
- pyannote.audio: https://github.com/pyannote/pyannote-audio
- Bolna: https://github.com/bolna-ai/bolna

## Modelos, agentes e memória
- LiteLLM: https://github.com/BerriAI/litellm
- Mem0: https://github.com/mem0ai/mem0
- smolagents: https://github.com/huggingface/smolagents

## Conhecimento e RAG
- RAGFlow: https://github.com/infiniflow/ragflow
- LightRAG: https://github.com/HKUDS/LightRAG

## Observabilidade e avaliação
- Langfuse: https://github.com/langfuse/langfuse
- promptfoo: https://github.com/promptfoo/promptfoo

---

**Fim do documento.**
