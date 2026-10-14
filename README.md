# Compiladores - Questões e Resoluções

Repositório para organização e extração de questões da disciplina de Compiladores.

## Estrutura do Projeto

```
compiladores-questoes/
├── src/                         # Código
│   ├── app.py                   # Aplicação principal Streamlit
│   ├── extract_document.py      # PDF fonte -> data/source.json + data/figs/
│   ├── build_document.py        # data/source.json -> PDF corrigido
│   ├── .env                     # Variáveis de ambiente (não versionar)
│   └── utils/                   # Utilitários do app
│       ├── ocr.py               # Extração de texto via OCR
│       ├── llm.py               # Integração com Ollama LLM
│       └── file_utils.py        # Utilitários de arquivo
├── data/
│   ├── _fonte_pre_correcao.pdf  # PDF antes da correção (fonte da extração)
│   ├── source.json              # Documento estruturado (20 seções, 99 questões)
│   ├── figs/                    # 86 figuras extraídas do PDF
│   └── Compiladores_Questoes_e_Resolucoes_reorganizado.pdf  # PDF gerado
├── pyproject.toml               # Dependências do projeto
└── requirements.txt
```

## Funcionalidades

- **Extração de texto de PDFs**: Suporte a PyMuPDF, PyPDF2, Tesseract OCR e OCR.space API
- **Processamento de imagens**: Pré-processamento com OpenCV (deskew, denoising, CLAHE)
- **Chatbot com contexto**: Interface Streamlit para fazer perguntas sobre o conteúdo extraído
- **Integração Ollama**: Suporte a modelos locais e remotos (gemma3:4b, gemma4:31b, gemma3:12b)
- **Resumo automático**: Redução de contexto longo para caber no limite do modelo

## Instalação

```bash
# Com uv (recomendado)
uv sync

# Ou com pip
pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` em `src/` com:

```env
OLLAMA_API_KEY=sua_chave_aqui
OLLAMA_HOST=https://ollama.com
OCR_SPACE_API_KEY=sua_chave_ocr_aqui
OLLAMA_AVAILABLE_MODELS=gemma3:4b, gemma4:31b, gemma3:12b
OLLAMA_MAX_TOKENS=100000
MAX_CONTEXT_CHARS=100000
CHUNK_SIZE=40000
SUMMARIZE_TIMEOUT=180
```

## Uso

```bash
cd src
streamlit run app.py
```

## Documento corrigido

O PDF `data/Compiladores_Questoes_e_Resolucoes_reorganizado.pdf` (123 páginas) é
gerado a partir de `data/source.json`. Ele foi corrigido em relação à versão
anterior (`data/_fonte_pre_correcao.pdf`) para resolver três problemas:

1. **Provás do meio × provas finais misturadas.** As provas complementares
   (au02, au05, wi08, au09, au11) vinham jogadas todas depois das finais. Agora
   o documento tem capa, sumário com página de cada questão e páginas-divisória:

   | Parte | Conteúdo |
   |---|---|
   | I — Provas do meio (midterms) | I.1, I.2, I.3 (provas do Prof. André) · M1–M4 (CSE401 midterms) · O1 (au02) e O2 (au05) |
   | II — Provas finais | F1–F3 (CSE401/CSEP501 finais) · O3 (wi08), O4 (au09) e O5 (au11) |
   | III — Exercícios dos slides | Exercício 1 a 5 |

2. **Questões repetidas.** Onze questões apareciam duas vezes no material
   (o mesmo enunciado e resolução em provas diferentes). A primeira ocorrência
   é mantida integralmente; as demais viram uma nota curta com a referência e a
   página exata da original — nada de copiar a mesma questão duas vezes.

3. **Texto quebrado no meio da frase.** As linhas quebradas no meio das frases
   foram reunidas, listas e rótulos (`Passo 1`, `(a)`, `(b)`, `Grafo:`) ganharam
   as quebras que faltavam e negrito herdado da fonte (`**texto**`) virou
   negrito de verdade. Blocos de código, tabelas e figuras ficaram como no
   original (as tabelas foram reconstruídas como grade).

Critério de classificação das provas sem rótulo oficial: conteúdo predominante.
au02 e au05 são de meio de período; wi08, au09 e au11 são finais. A 2ª prova do
Prof. André ficou no grupo do meio (é a 2ª prova do professor), com aviso no
topo de que o conteúdo é de fim de curso.

## Regenerando o PDF

```bash
# 1) PDF -> JSON estruturado + figuras
python3 src/extract_document.py

# 2) JSON -> PDF corrigido (itera até a paginação estabilizar)
python3 src/build_document.py
```

As duas etapas são independentes: dá para mexer só no renderizador
(`src/build_document.py`) e regenerar sem reextrair. Para mudar o conteúdo,
edite `data/source.json` (ou os mapas `SEC_TITLES`, `DUPES` e `PARTS` no topo de
`src/build_document.py`) e rode o passo 2.

## Dependências Principais

- `streamlit` - Interface web
- `pymupdf` / `pypdf2` - Leitura de PDF
- `pytesseract` - OCR local
- `opencv-python-headless` - Processamento de imagem
- `pillow` - Manipulação de imagens
- `requests` / `beautifulsoup4` - Web scraping
- `python-docx` / `python-pptx` - Documentos Office
- `reportlab` - Geração de PDF

## Licença

Projeto acadêmico para fins educacionais.