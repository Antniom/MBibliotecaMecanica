# Plano Mestre — Super-Biblioteca de Engenharia Mecânica

> Documento de especificação para um agente AI (ex: Claude Code) construir, de ponta a ponta, um sistema de digitalização, OCR, validação por IA, organização e pesquisa de todo o material da licenciatura.
> Última verificação das condições de mercado (preços, free tiers, terms of service): **30 de junho de 2026**.

---

## 0. Princípios orientadores

1. **Não reinventar a roda.** Usar bibliotecas/serviços existentes em cada etapa (conversão, OCR, validação, busca, geração de site). Só escrever código próprio para orquestração, taxonomia e cola entre sistemas.
2. **Tudo deve ser retomável.** Cada documento/página tem um estado persistido em base de dados local. Se uma API atingir rate limit a meio, o pipeline para sem erro fatal e recomeça exatamente onde ficou, noutro dia, sem reprocessar o que já está feito.
3. **Custo real = 0 €.** Toda a cadeia usa apenas ferramentas gratuitas: conversão e OCR locais (open-source, sem limite de páginas), com o Gemini Flash (free tier) só para a validação final e geração do Markdown/XML.
4. **Execução local-first.** O processamento pesado (conversão, OCR, validação) deve correr no teu computador (script Python, retomável), não num serverless com timeout de 10–60s. A nuvem serve só para hospedar o resultado final (site estático).
5. **O utilizador só vê os ficheiros originais.** Markdown, XML e tudo o que é gerado pelo pipeline existe para alimentar a pesquisa e o assistente de IA — nunca aparece como conteúdo principal da página, só por download explícito (ver secção 6).

---

## 1. Stack tecnológico recomendado

| Camada | Ferramenta | Porquê | Custo |
|---|---|---|---|
| Conversão de ficheiros digitais → Markdown | **MarkItDown** (Microsoft, MIT license, `pip install markitdown`) | Converte PDF nativo, DOCX, PPTX, XLSX, HTML, CSV, etc. diretamente para Markdown estruturado (mantém títulos, tabelas, listas) — substitui extração crua de texto | Grátis, local |
| OCR de páginas digitalizadas/manuscritas | **plugin `markitdown-ocr`**, configurado para usar um **Ollama local** (endpoint compatível com OpenAI, `http://localhost:11434/v1`) com um modelo de visão atual (ex.: `qwen2.5-vl` ou equivalente mais recente) | O plugin já deteta páginas sem camada de texto, renderiza-as a 300dpi e manda-as para o modelo de visão, devolvendo Markdown — sem teres de escrever essa lógica à mão. Por correr contra o Ollama local em vez da OpenAI, fica a custo zero | Grátis, local |
| OCR especialista (escalonamento p/ manuscrita muito densa) | **PaddleOCR** ou **Surya OCR** | Quando a página continua com confiança baixa após o passo anterior, reprocessa-se com um motor de OCR dedicado (mais forte em reconhecimento de caracteres do que um VLM generalista) | Grátis, local |
| Rasterização de página / metadados de PDF | **PyMuPDF (`fitz`)** | Usado para contagem de páginas, hash, e gerar a imagem de cada página (para o passo de validação visual seguinte) | Grátis, local |
| Conversão de formatos não cobertos pelo MarkItDown (ex. .doc antigo) | **LibreOffice headless** (`soffice --headless --convert-to pdf`) | Só como pré-conversão pontual para formatos legados; também útil para gerar um PDF de pré-visualização de um .pptx/.docx no site | Grátis, local |
| Validação/correção final por visão | **Gemini 3.5 Flash** via SDK `google-genai` (free tier) | Recebe a imagem da página + Markdown produzido pelas camadas anteriores, corrige erros, devolve confiança, extrai tópicos e estrutura em XML semântico | Grátis (free tier) |
| Orquestração e estado | **Python + SQLite** | Ficheiro único, sem servidor, perfeito para retomar entre sessões | Grátis |
| Classificação automática (disciplina/tipo) | Regras de nome de ficheiro + fallback Gemini Flash | Primeiro tenta regex no nome/pasta; só chama IA quando ambíguo | Grátis |
| Geração do site | **Astro** (content collections em Markdown) | Estático, rápido, ideal para hosting grátis | Grátis |
| Pesquisa full-text | **Pagefind** | Indexa o HTML gerado no build, pesquisa 100% client-side, zero backend | Grátis |
| Ajuda conversacional no browser | **Chrome Prompt API / Summarizer API** (Gemini Nano on-device) | Privado, instantâneo, sem custo — só funciona em Chrome desktop | Grátis |
| Hosting do site | **Cloudflare Pages** (alternativa: Vercel Hobby) | Build ilimitado, sem limite agressivo de função/cron como o Vercel Hobby | Grátis |
| Armazenamento dos ficheiros originais | **GitHub Releases** (sem limite total documentado, 2 GiB/ficheiro, bandwidth ilimitado) | O próprio GitHub recomenda oficialmente Releases para distribuir binários grandes fora do repositório Git normal. Sem custo, sem segunda conta a gerir, e já integrado com o GitHub Actions que vais usar para o cron do pipeline | Grátis, sem limite total conhecido |
| Agendamento (opcional, "set and forget") | **GitHub Actions** (cron) ou simplesmente correr localmente | Actions tem 2000 min/mês grátis em repos privados — chega para retomar o pipeline todas as noites | Grátis |

**Sobre o armazenamento via GitHub Releases:** cria-se um release por ano letivo (`1-ano`, `2-ano`, `3-ano`) — ou até por semestre, se algum ano ultrapassar centenas de ficheiros — e cada ficheiro original é anexado como "asset" a esse release. O link de download fica num formato fixo e previsível (`https://github.com/<user>/<repo>/releases/download/<tag>/<ficheiro>`), fácil de guardar em `documents.storage_provider`/`storage_url` e de usar diretamente nos botões "Transferir original" do site. Duas coisas a decidir logo no início:
- **Repositório público vs. privado:** assets de um release num repo privado só descarregam com autenticação (token), o que complica o link direto no site público. Se não houver problema em os ficheiros ficarem publicamente acessíveis a quem tiver o link (não indexado nem listado, mas não protegido por login), um repositório público é o caminho mais simples. Se preferires manter tudo privado, o site tem de fazer proxy dos downloads através de uma função que injeta o token — mais complexidade, mas mantém tudo fechado.
- **Direitos de autor de enunciados/materiais do professor:** alguns dos PDFs (testes, fichas) podem ter sido produzidos pelos docentes — vale a pena confirmares que estás confortável com esse material ficar acessível por link direto antes de tornares o repositório público.

**Sobre o MarkItDown:** é o tool que mencionaste — é mantido pela equipa AutoGen da Microsoft, MIT license, 139 mil+ estrelas no GitHub, ativamente atualizado. Sozinho, **não tem OCR para PDFs digitalizados** (só extrai a camada de texto já existente; páginas-imagem voltam vazias) — daí a necessidade do plugin `markitdown-ocr` por cima, que resolve exatamente esse buraco quando ligado a um modelo de visão (local, no nosso caso). Há ainda um `markitdown-mcp` (servidor MCP) que podes instalar no teu agente de coding para testar conversões diretamente durante o desenvolvimento.

**Porque esta cascata e não um único OCR pago:** o MarkItDown+Ollama trata da maioria das páginas (texto impresso, a maioria dos PDFs) sem qualquer chamada externa. PaddleOCR/Surya entram só para os casos mais difíceis. O Gemini Flash (grátis) entra por último, só para validar/arbitrar — preservando o orçamento gratuito para o que realmente precisa dele.

---

## 2. Taxonomia / estrutura de pastas

Baseada no plano de estudos oficial da Licenciatura em Engenharia Mecânica do Politécnico de Leiria (ESTG, 6 semestres). Os códigos entre parêntesis são os códigos oficiais da UC, úteis para cruzar com a pauta/Moodle.

```
biblioteca/
├── 1-ano/
│   ├── 1-semestre/
│   │   ├── analise-matematica/        (9123201)
│   │   ├── algebra-linear/            (9123202)
│   │   ├── fisica/                    (9123203)
│   │   ├── programacao/               (9123204 — SciLab)
│   │   ├── ingles/                    (9123205)
│   │   └── quimica-e-materiais/       (9123206)
│   └── 2-semestre/
│       ├── matematica-aplicada/       (9123207)
│       ├── estatistica/               (9123208)
│       ├── desenho-tecnico/           (9123209)
│       ├── tecnologia-dos-materiais/  (9123210)
│       ├── tecnologia-mecanica-i/     (9123211)
│       └── mecanica-aplicada/         (9123212)
├── 2-ano/
│   ├── 1-semestre/
│   │   ├── resistencia-dos-materiais/             (9123213)
│   │   ├── tecnologia-mecanica-ii/                (9123214)
│   │   ├── termodinamica/                         (9123215)
│   │   ├── mecanica-dos-fluidos/                  (9123216)
│   │   ├── processos-transformacao-plasticos/     (9123217)
│   │   └── modelacao-assistida-por-computador/    (9123218)
│   └── 2-semestre/
│       ├── orgaos-de-maquinas-i/                  (9123219)
│       ├── processamento-mecanica-compositos/     (9123220)
│       ├── engenharia-assistida-por-computador/   (9123221)
│       ├── fabrico-assistido-por-computador/      (9123222)
│       ├── opcao-i/                               (escolher: desenho-de-moldes-e-plasticos [9123237] OU desenho-de-construcao-mecanica [9123238])
│       └── eletrotecnia-e-eletronica-industrial/  (9123224)
└── 3-ano/
    ├── 1-semestre/
    │   ├── orgaos-de-maquinas-ii/                 (9123225)
    │   ├── processos-avancados-de-fabrico/        (9123226)
    │   ├── opcao-ii/                              (escolher: projeto-de-moldes [9123239] OU projeto-mecanico [9123240])
    │   ├── concecao-e-desenvolvimento-de-produto/ (9123228)
    │   ├── opcao-iii/                             (escolher: simulacao-computacional-moldes-plasticos [9123241] OU simulacao-computacional-projeto-mecanico [9123242])
    │   └── automacao-industrial/                  (9123230)
    └── 2-semestre/
        ├── qualidade-e-gestao-de-recursos/        (9123231)
        ├── gestao-da-producao-e-manutencao/       (9123232)
        ├── opcao-iv/                              (escolher: projeto-industrial [9123243] OU estagio [9123244])
        ├── seminario/                             (9123234)
        ├── opcao-v/                               (escolher: redes-de-fluidos [9123245] OU moldes-materiais-ceramicos [9123246] OU controlo-de-gestao [9123247])
        └── inovacao-e-empreendedorismo/           (9123236)
```

> **Nota sobre as Opções:** o plano oficial tem 5 unidades de opção (I a V), cada uma com 2–3 alternativas possíveis. Usa apenas a pasta da opção que **tu** frequentaste de facto (ex.: `2-ano/2-semestre/opcao-i/` deve chamar-se diretamente `desenho-de-construcao-mecanica/` se foi essa a tua escolha — não crias as alternativas que não fizeste).
> **Inglês** foi incluído porque consta do plano oficial; ajusta/remove se não tiveres material relevante para arquivar dessa UC.

Dentro de **cada disciplina**, subpastas fixas por tipo:

```
resistencia-dos-materiais/
├── 00-indice.md              ← gerado automaticamente, uso interno (ver secções 6 e 7)
├── teoria/                   ← slides, sebentas, PDFs teóricos
├── fichas-exercicios/        ← fichas de exercícios (com/sem resolução)
├── resumos/
├── resolucoes/                ← resoluções de exercícios/testes manuscritas
├── testes-exames/
│   ├── teste-1/
│   ├── teste-2/
│   └── exame/
└── trabalhos-projetos/       ← ficheiros não-PDF (CAD, MATLAB/Simulink, SciLab, Excel, código…)
```

Cada ficheiro original processado fica acompanhado, num local **interno** (não navegável diretamente pelo utilizador — ver secção 6), por:
- `nome-original.md` (Markdown estruturado com tags XML — ver secção 5)
- `nome-original.meta.json` (metadados: disciplina, tipo, ano letivo, confiança do OCR, hash, etc.)

O ficheiro original (`nome-original.pdf` ou outro formato) é o único elemento que aparece na navegação visível do site.

---

## 3. Pipeline de processamento (visão geral)

```
[Inventário]
     │  hash SHA-256 de cada ficheiro → deteta duplicados, regista em SQLite
     ▼
[Classificação automática]
     │  regex no caminho/nome do ficheiro → disciplina + tipo
     │  ambíguo → 1 chamada Gemini Flash com o nome do ficheiro e 1ª página
     ▼
[Conversão nativa — MarkItDown]
     │  PDFs com camada de texto, DOCX, PPTX, XLSX → Markdown estruturado direto
     │  formatos não cobertos (CAD, Simulink, .m, código-fonte) → sem conversão,
     │  ficam só indexados por nome/metadados
     │  estado → "convertido" ou "precisa_ocr"
     ▼
[OCR — MarkItDown + plugin markitdown-ocr (Ollama local)]
     │  só corre nas páginas sem camada de texto (scans/manuscritos)
     │  deteção automática, renderização a 300dpi, envio ao modelo de visão local
     │  sem rate limit externo — só limitado por CPU/GPU
     │  confiança baixa → escalona
     ▼
[Escalonamento — PaddleOCR / Surya]
     │  só as páginas problemáticas (normalmente <10–20% do total)
     │  passam por aqui; mais lento, mas continua a custo 0
     ▼
[Validação por visão — Gemini 3.5 Flash, free tier]
     │  recebe: imagem da página + Markdown produzido pelas camadas anteriores
     │  prompt: "confirma/corrige a transcrição, atenção a fórmulas, unidades,
     │           texto manuscrito sobreposto e tabelas; devolve confidence 0-1"
     │  confidence baixa (<0.6) → marca para revisão manual (lista no painel)
     │  estado → "validado"
     ▼
[Geração do Markdown estruturado + XML semântico]
     │  uma chamada final ao Gemini Flash junta todas as páginas validadas do
     │  documento e gera o .md interno com a estrutura da secção 5
     │  estado → "exportado"
     ▼
[Indexação — Astro + Pagefind build]
     │  o .md interno alimenta o índice de busca e o contexto do assistente de
     │  IA, mas NÃO é renderizado como conteúdo visível (ver secção 6)
     ▼
[Deploy — Cloudflare Pages; ficheiros originais via GitHub Releases]
```

---

## 4. Esquema de estado (SQLite) — a chave da resiliência a rate limits

```sql
CREATE TABLE documents (
  id            TEXT PRIMARY KEY,      -- hash SHA-256 do ficheiro original
  path_original TEXT NOT NULL,
  disciplina    TEXT,
  tipo          TEXT,                  -- teoria | ficha | resumo | resolucao | teste | trabalho
  ano           INTEGER,
  semestre      INTEGER,
  storage_release_tag TEXT,            -- tag do release (ex.: '1-ano', '2-ano', '3-ano')
  storage_url   TEXT,                  -- URL direto do asset no GitHub Release
  status        TEXT DEFAULT 'pending',
  -- pending → classificado → convertido/precisa_ocr → ocr_done →
  -- validacao_em_curso → validado → exportado → indexado
  created_at    TIMESTAMP,
  updated_at    TIMESTAMP
);

CREATE TABLE pages (
  doc_id        TEXT REFERENCES documents(id),
  page_num      INTEGER,
  needs_ocr     BOOLEAN,
  ocr_text      TEXT,
  ocr_provider  TEXT,                  -- 'markitdown-native' | 'markitdown-ocr-ollama' | 'paddleocr' | 'surya' | 'gemini'
  ocr_status    TEXT DEFAULT 'pending',
  validated_text TEXT,
  confidence    REAL,
  validation_status TEXT DEFAULT 'pending',
  attempts      INTEGER DEFAULT 0,
  last_error    TEXT,
  last_attempt_at TIMESTAMP,
  PRIMARY KEY (doc_id, page_num)
);

CREATE TABLE api_usage_log (
  provider      TEXT,                  -- 'gemini_flash' (única API externa do pipeline)
  date          DATE,
  requests_today INTEGER DEFAULT 0,
  tokens_today  INTEGER DEFAULT 0
);
```

**Regras do job runner (script `run_pipeline.py`):**
- A conversão e o OCR locais (MarkItDown, MarkItDown+Ollama, PaddleOCR, Surya) não têm rate limit externo — só são limitados pelo teu CPU/GPU, por isso podem correr em lote contínuo sem necessidade de backoff.
- Antes de cada chamada ao Gemini Flash (a única API externa), verifica `api_usage_log` contra os limites do dia (na ordem de 10–15 pedidos/minuto e ~1500/dia no free tier — confirma sempre o valor atual em ai.google.dev) e pausa/encerra graciosamente se estiver perto do limite.
- Em erro `429` do Gemini: backoff exponencial com jitter (1s, 2s, 4s, 8s…, máx. 5 tentativas), depois marca `attempts += 1` e passa ao próximo item — **nunca trava o pipeline inteiro**.
- Cada execução do script processa um lote (ex.: 200 páginas) e termina sozinha. Corre-se novamente amanhã (manual ou via cron) e continua exatamente de onde ficou, porque o estado está todo na base de dados.
- Idempotência: qualquer página já com `validation_status = 'validado'` nunca é reprocessada, mesmo que o script seja interrompido a meio.

---

## 5. Estrutura do Markdown interno (com marcação XML semântica)

> Este ficheiro **nunca é mostrado diretamente** na navegação principal do site (ver secção 6) — existe só para alimentar a pesquisa, o assistente de IA, e o download opcional "Versão IA".

Exemplo de saída para `resolucao-teste1-2023.pdf`:

```markdown
---
title: "Resolução Teste 1 — 2023"
disciplina: "Resistência dos Materiais"
ano: 2
semestre: 1
tipo: "resolucao"
avaliacao: "teste-1"
fonte_original: "resolucao-teste1-2023.pdf"
ocr_provider: "markitdown-ocr-ollama+paddleocr"
validado_por: "gemini-3.5-flash"
confianca_media: 0.91
data_processamento: "2026-06-30"
---

<document>
  <section topic="flexao-de-vigas" page="1">

## Exercício 1 — Flexão de viga simplesmente apoiada

<handwritten confidence="0.88">
Dados: L = 2 m, q = 5 kN/m, E = 210 GPa...
</handwritten>

<equation type="latex">
M_{max} = \frac{q L^2}{8}
</equation>

  </section>

  <section topic="torcao-de-eixos" page="2">
  ...
  </section>
</document>
```

Tags recomendadas: `<section topic="" page="">`, `<equation type="latex|image">`, `<table>`, `<figure caption="">`, `<handwritten confidence="">`, `<low-confidence>` (marca trechos para revisão manual). O `topic` de cada secção é o que alimenta a organização "por matéria do Teste 1/2" (secção 7).

---

## 6. Interface do utilizador — o que é mostrado

**Princípio central:** o utilizador navega e vê apenas **ficheiros originais**. Tudo o que o pipeline gera (Markdown, XML, texto OCR) é invisível por defeito — só serve a pesquisa e o assistente de IA, e só fica acessível por um download explícito.

**Navegação (pastas):**
Ano → Semestre → Disciplina → Tipo → lista de ficheiros. Cada ficheiro aparece como um "cartão" simples: nome original, ícone do tipo de ficheiro, talvez data/tamanho. Nada de Markdown visível nesta vista.

**Ao clicar num ficheiro** (ex.: um PDF), abre uma vista de detalhe com:
- Pré-visualização do original quando possível (ex.: visualizador de PDF embutido via `pdf.js`) — opcional, mas natural numa biblioteca.
- Botão **"Transferir original"** → download direto do ficheiro tal como está (`.pdf`, `.docx`, `.dwg`, etc.).
- Botão **"Versão IA"** (visualmente distinto, ex. ícone de estrela/faísca) com um **tooltip** ao passar o rato, algo como:
  > *"Transcrição em texto, gerada por OCR e verificada por IA. Se quiseres usar este documento noutra ferramenta de IA (ChatGPT, Claude, etc.), esta versão consome muito menos tokens do que enviar o PDF original — é só texto, sem o peso das imagens/scans. Pode conter erros e não substitui o original."*
  Ao clicar, faz download do `.md` correspondente. Não abre dentro do site como página normal.

**Onde fica então o conteúdo Markdown, se não aparece na página?**
- Embutido no HTML da página de detalhe, mas **visualmente escondido** (ex. `<div hidden data-pagefind-body>` ou classe `sr-only`). O Pagefind continua a indexar este texto na íntegra para a pesquisa funcionar, mesmo sem aparecer visualmente — CSS/`hidden` não impede a indexação, só a exclusão explícita do Pagefind impediria.
- Servido como contexto ao componente de chat do Chrome built-in AI (Fase 7) quando o utilizador pede ajuda sobre aquele documento específico.
- Disponível por download manual, como descrito acima.

**Implementação em Astro:** cada documento continua a ter uma content collection (frontmatter + corpo Markdown), mas o componente de página renderiza só o "cartão do ficheiro" + botões; o corpo Markdown vai para um bloco oculto no DOM, não para o `<article>` visível.

---

## 7. Organização por "matéria do Teste 1 / Teste 2"

O agente **não sabe à partida** que tópicos saem em cada teste — isso tem de ser inferido dos teus próprios documentos antigos:

0. Semear cada `00-indice.md` interno com os tópicos **oficiais do programa** da UC (disponíveis na página do curso do IPLeiria, já refletidos nos nomes de pasta da secção 2) — isto dá uma lista inicial de tópicos mesmo antes de qualquer teste antigo ser processado.
1. Durante a validação (secção 3), pedir ao Gemini Flash para também extrair uma lista curta de `topics` por documento (já incluído no campo `topic` das secções acima).
2. Para ficheiros cujo nome/pasta indique claramente "Teste 1", "T1", "1º Teste", "Exame" etc., agregar os `topics` encontrados nesses documentos.
3. Gerar automaticamente, por disciplina, um índice interno com duas listas: "Tópicos recorrentes no Teste 1" e "Tópicos recorrentes no Teste 2/Exame", ligando aos ficheiros originais relevantes (que continuam a ser o que o utilizador vê e abre).
4. Isto é só uma sugestão automática — vale a pena reveres manualmente os índices gerados antes de confiar neles para estudar.

---

## 8. Avisos importantes antes de começar

- **MarkItDown sozinho não faz OCR de PDFs digitalizados** — só extrai a camada de texto já existente. O plugin `markitdown-ocr` resolve isto, mas precisa de um `llm_client` configurado (no nosso caso, apontado para o Ollama local, não para a OpenAI) — confirma que o endpoint `http://localhost:11434/v1` está ativo antes de correr o pipeline.
- **Gemini API:** vais usar o free tier do Gemini 3.5 Flash para a validação e geração final. Confirma sempre os limites atuais (RPM/RPD) em ai.google.dev/gemini-api/docs/rate-limits antes de correr lotes grandes — os números mudam com alguma frequência.
- **Licença do Surya OCR:** o código é GPL-3.0 e os pesos do modelo usam uma licença "livre para investigação/uso pessoal e startups com receita <2M$", paga acima disso — perfeitamente adequado a uso pessoal de estudante.
- **Hardware (sem GPU dedicada):** MarkItDown e PaddleOCR correm perfeitamente bem em CPU. O modelo de visão local via Ollama também corre em CPU, mas fica bastante mais lento (dependendo do modelo, pode ser vários segundos a mais de um minuto por página) — não é um problema, só significa que o pipeline vai demorar mais dias-calendário a esvaziar a fila, o que o desenho retomável do pipeline (secção 4) já assume como normal. Vale a pena escolher um modelo de visão mais pequeno (ex.: variantes 3B–7B em vez de versões maiores) para equilibrar velocidade e precisão em CPU.
- **Chrome built-in AI (Gemini Nano)** só funciona em Chrome desktop (Windows/macOS/Linux), só processa texto (sem imagens), e tem qualidade muito inferior a um modelo cloud — serve bem para um assistente de apoio rápido e privado dentro do site, **não** para gerar a transcrição inicial nem o Markdown/XML final (isso é feito previamente pelo pipeline, com o Gemini 3.5 Flash "grande").
- **Vercel Hobby** limita cron a 1x/dia e funções a 10–60s — por isso o processamento pesado corre localmente/no GitHub Actions, e o Vercel/Cloudflare Pages só serve o site estático já pronto.

---

## 9. Fases de implementação (ordem para o agente seguir)

**Fase 0 — Setup**
- Criar repositório, ambiente Python (`venv`), instalar `markitdown[all]`, `markitdown-ocr`, `paddleocr`, `surya-ocr`, `pymupdf`, `google-genai`, `sqlite3` (stdlib).
- Instalar o Ollama localmente, descarregar um modelo de visão atual (ex.: `ollama pull qwen2.5-vl` ou equivalente mais recente) e confirmar que o endpoint OpenAI-compatible (`http://localhost:11434/v1`) responde.
- Criar a base de dados SQLite com o esquema da secção 4.
- Criar `.env` só para a chave Gemini (`GEMINI_API_KEY`) — nunca commitar.

**Fase 1 — Inventário e classificação**
- Script que percorre as pastas de origem, calcula hash, deteta duplicados, tenta classificar disciplina/tipo por regex no caminho e regista tudo em `documents`.

**Fase 2 — Conversão nativa (MarkItDown)**
- Para cada documento, corre o MarkItDown. PDFs/DOCX/PPTX/XLSX com texto extraível ficam logo convertidos (`ocr_provider = 'markitdown-native'`). Páginas sem texto (scans/manuscrito) ficam marcadas `needs_ocr = true`.
- Formatos não suportados (CAD, .m, código) só ficam indexados por metadados, sem conversão.

**Fase 3 — OCR local (MarkItDown+Ollama → PaddleOCR/Surya)**
- Job runner que corre o plugin `markitdown-ocr` (apontado ao Ollama local) sobre as páginas `needs_ocr = true`; sem rate limit externo, só limitado por CPU/GPU.
- Páginas com confiança ainda baixa são reencaminhadas para PaddleOCR/Surya como segunda opinião.

**Fase 4 — Validação final (Gemini Flash)**
- Job runner que usa a imagem da página (gerada via PyMuPDF) + o texto já convertido, produz `validated_text` + `confidence` + `topics`.

**Fase 5 — Geração do documento interno final**
- Por documento (todas as páginas `validado`), uma chamada final que junta tudo no Markdown+XML estruturado da secção 5.

**Fase 6 — Site (Astro) + Pagefind + UI "só originais"**
- Content collections leem os `.md` internos (frontmatter + corpo) para gerar metadados e o índice de pesquisa.
- Componentes de página mostram **só** os cartões de ficheiro original + botões "Transferir original" / "Versão IA" (com tooltip) — o corpo Markdown vai para um bloco oculto no DOM só para o Pagefind indexar (ver secção 6).
- Build do Pagefind no `astro build`.

**Fase 7 — Chrome built-in AI no frontend**
- Componente de chat que usa `LanguageModel.create()` (Prompt API) com o Markdown interno do documento atual como contexto; deteta `LanguageModel.availability()` e mostra fallback se não disponível.
- O botão "Versão IA" descrito na secção 6 fica ao lado do botão de download do original, na mesma vista de detalhe.

**Fase 8 — Deploy**
- Ficheiros originais → anexados como assets a Releases do GitHub, um por ano letivo (via `gh release upload` ou a GitHub API); guardar `storage_release_tag` + `storage_url` em `documents` para cada ficheiro.
- Site → Cloudflare Pages (build automático a cada push).
- Opcional: GitHub Actions agendado (cron noturno) para correr as Fases 3–5 automaticamente até esgotar a fila, retomando sempre do estado SQLite — e pode reaproveitar o mesmo `GITHUB_TOKEN` do runner para também tratar dos uploads de assets.

---

## 10. Checklist rápido para começar já

- [ ] Instalar Python, `markitdown[all]`, `markitdown-ocr`, `paddleocr`/`surya-ocr`
- [ ] Instalar o Ollama e confirmar o endpoint OpenAI-compatible local com um modelo de visão
- [ ] Obter chave de API Gemini no Google AI Studio (`GEMINI_API_KEY`, free tier)
- [ ] Criar (ou reaproveitar) um repositório GitHub para os assets e decidir público vs. privado (ver nota na secção 1)
- [ ] Criar conta Cloudflare Pages para o site (hosting, não armazenamento de ficheiros)
- [ ] Confirmar qual a opção (I a V) que escolheste em cada UC de opção, para nomear as pastas corretamente (secção 2)
- [ ] Reunir os ficheiros numa pasta única de "entrada" antes de correr a Fase 1
- [ ] Correr Fases 0–2 primeiro (sem qualquer chamada externa) para ver quantas páginas realmente precisam de OCR
