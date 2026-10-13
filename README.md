# Compiladores - Questões e Resoluções

Repositório para organização e extração de questões da disciplina de Compiladores.

## Estrutura do Projeto

```
compiladores-questoes/
├── src/                    # Código fonte do extrator
│   ├── app.py             # Aplicação principal Streamlit
│   ├── .env               # Variáveis de ambiente (não versionar)
│   └── utils/             # Utilitários
│       ├── ocr.py         # Extração de texto via OCR
│       ├── llm.py         # Integração com Ollama LLM
│       └── file_utils.py  # Utilitários de arquivo
├── data/                  # Dados de entrada
│   └── Compiladores_Questoes_e_Resolucoes_reorganizado.pdf
├── assets/                # Imagens extraídas do PDF
├── pyproject.toml         # Dependências do projeto
└── uv.lock                # Lock file do uv
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

## Extração de Questões

O PDF `Compiladores_Questoes_e_Resolucoes_reorganizado.pdf` contém questões da disciplina de Compiladores organizadas com suas resoluções.

As imagens das páginas foram extraídas para a pasta `assets/` (p008_i0.png a p118_i0.png).

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