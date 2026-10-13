import os
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
from utils.ocr import extract_text_from_file
from utils.llm import call_ollama_stream, get_available_models, call_ollama

BASE_DIR = Path(__file__).parent
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE"))
SUMMARIZE_TIMEOUT = int(os.getenv("SUMMARIZE_TIMEOUT"))

def extract_urls_from_text(text):
    raw = re.findall(r'https?://[^\s<>"]+', text)
    cleaned = []
    for url in raw:
        url = url.rstrip('.,;!?()')
        cleaned.append(url)
    return cleaned

def fetch_url_content(url, timeout=10, max_chars=8000):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator='\n', strip=True)
        lines = (line.strip() for line in text.splitlines() if line.strip())
        content = '\n'.join(lines)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... [conteúdo truncado]"
        return content
    except Exception as e:
        return f"[Erro ao acessar URL: {str(e)}]"

@st.cache_data(show_spinner="Carregando arquivos...")
def load_files_from_path(path_str):
    path = Path(path_str)
    if not path.exists():
        return "", [], f"Caminho não encontrado: {path_str}"
    supported_extensions = [".pdf", ".docx", ".pptx", ".txt", ".png", ".jpg", ".jpeg"]
    files_to_process = []
    if path.is_file():
        if path.suffix.lower() in supported_extensions:
            files_to_process = [path]
        else:
            return "", [], f"Formato não suportado: {path.suffix}"
    elif path.is_dir():
        for ext in supported_extensions:
            files_to_process.extend(list(path.glob(f"*{ext}")))
            files_to_process.extend(list(path.glob(f"*{ext.upper()}")))
        files_to_process = list(set(files_to_process))
    else:
        return "", [], f"Caminho inválido: {path_str}"
    if not files_to_process:
        return "", [], f"Nenhum arquivo suportado encontrado em {path_str}"
    all_text = ""
    loaded_files = []
    progress_bar = st.progress(0, text="Extraindo textos...")
    for i, file_path in enumerate(files_to_process):
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            text = extract_text_from_file(file_bytes, file_path.name, model=None)
            if text:
                all_text += f"\n\n--- {file_path.name} ---\n{text}\n"
                loaded_files.append(file_path.name)
        except Exception as e:
            st.warning(f"Erro ao ler {file_path.name}: {e}")
        progress_bar.progress((i + 1) / len(files_to_process))
    progress_bar.empty()
    if loaded_files:
        msg = f"Carregados {len(loaded_files)} arquivo(s)"
        if path.is_file():
            msg = f"Carregado: {path.name}"
        return all_text, loaded_files, msg
    else:
        return "", [], "Nenhum texto foi extraído dos arquivos."

def process_and_save_uploaded_file(uploaded_file, target_folder):
    try:
        file_bytes = uploaded_file.read()
        file_path = target_folder / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        with st.spinner(f"Extraindo texto de {uploaded_file.name}..."):
            text = extract_text_from_file(file_bytes, uploaded_file.name, model=None)
        return text if text else ""
    except Exception as e:
        st.error(f"Erro ao processar {uploaded_file.name}: {e}")
        return ""

def summarize_chunk(chunk, model):
    if not chunk or len(chunk) < 100:
        return chunk
    prompt = f"Resuma o seguinte texto de forma concisa, mantendo todas as informações importantes e os pontos principais:\n\n{chunk}"
    try:
        summary = call_ollama(prompt, model)
        if summary and len(summary) < len(chunk):
            return summary
        return chunk
    except Exception:
        return chunk

def split_into_chunks(text, chunk_size):
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks

def filter_context_by_keywords(context, keywords):
    if not context or not keywords:
        return context
    parts = context.split("\n\n--- ")
    filtered_parts = []
    for part in parts:
        if not part.strip():
            continue
        header = part.split(" ---", 1)[0] if " ---" in part else ""
        if any(k.lower() in header.lower() for k in keywords):
            filtered_parts.append(part)
    if filtered_parts:
        return "\n\n--- ".join(filtered_parts)
    return context

def reduce_context(context, model, target_length, keywords=None):
    if not context:
        return context
    if len(context) <= target_length:
        return context
    if keywords:
        filtered = filter_context_by_keywords(context, keywords)
        if filtered and len(filtered) < len(context):
            context = filtered
            if len(context) <= target_length:
                return context
    current_text = context
    max_iterations = 3
    iteration = 0
    while len(current_text) > target_length and iteration < max_iterations:
        iteration += 1
        chunks = split_into_chunks(current_text, CHUNK_SIZE)
        if not chunks:
            break
        summaries = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        for idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            progress_text.text(f"Resumindo parte {idx+1} de {len(chunks)}...")
            summarized = summarize_chunk(chunk, model)
            if summarized:
                summaries.append(summarized)
            progress_bar.progress((idx + 1) / len(chunks))
        progress_bar.empty()
        progress_text.empty()
        if not summaries:
            break
        current_text = "\n\n".join(summaries)
        if len(current_text) <= target_length:
            break
    if len(current_text) > target_length:
        current_text = current_text[:target_length]
    return current_text

st.set_page_config(page_title="Chatbot - Contexto PDF", layout="wide")
st.title("🤖 Assistente de Qualidade de Página (TELUS)")
st.markdown("Faça perguntas sobre as diretrizes de qualidade com base nos arquivos da pasta.")

with st.sidebar:
    st.header("⚙️ Configurações")
    models = get_available_models()
    selected_model = st.selectbox("Modelo Ollama", models, index=0)
    default_path = str(BASE_DIR.parent / "data" / "livros")
    file_or_folder = st.text_input("Caminho do arquivo ou pasta", value=default_path)
    if st.button("🔄 Recarregar arquivos"):
        st.cache_data.clear()
        if "loaded_path" in st.session_state:
            del st.session_state["loaded_path"]
        st.rerun()
    st.divider()
    st.subheader("📊 Estatísticas do Contexto")
    current_path = str(Path(file_or_folder).resolve())
    if "loaded_path" not in st.session_state or st.session_state.loaded_path != current_path:
        with st.spinner("Carregando arquivos..."):
            text, files, msg = load_files_from_path(file_or_folder)
            st.session_state.context_text = text
            st.session_state.loaded_files = files
            st.session_state.loaded_path = current_path
            st.session_state.messages = []
            if text:
                st.success(msg)
            else:
                st.warning(msg)
    if "context_text" in st.session_state and st.session_state.context_text:
        char_count = len(st.session_state.context_text)
        word_count = len(st.session_state.context_text.split())
        st.metric("Caracteres", f"{char_count:,}")
        st.metric("Palavras", f"{word_count:,}")
        st.metric("Arquivos carregados", len(st.session_state.get("loaded_files", [])))
        if st.session_state.get("loaded_files"):
            st.caption("Arquivos:")
            for f in st.session_state.loaded_files:
                st.write(f"- {f}")
    else:
        st.info("Nenhum contexto carregado.")
    if st.button("🧹 Limpar contexto (reset)"):
        st.session_state.context_text = ""
        st.session_state.loaded_files = []
        st.session_state.messages = []
        st.rerun()

uploaded_files = st.file_uploader(
    "📎 Envie mais arquivos (PDF, imagem, DOCX, PPTX, TXT) para adicionar ao contexto",
    accept_multiple_files=True,
    type=["pdf", "png", "jpg", "jpeg", "docx", "pptx", "txt"]
)
if uploaded_files:
    target_folder = Path(file_or_folder)
    if not target_folder.exists():
        target_folder = Path.cwd()
    new_texts = []
    new_files = []
    for file in uploaded_files:
        if file.name not in st.session_state.get("loaded_files", []):
            text = process_and_save_uploaded_file(file, target_folder)
            if text:
                new_texts.append(f"\n\n--- {file.name} (upload) ---\n{text}")
                new_files.append(file.name)
    if new_texts:
        st.session_state.context_text += "\n".join(new_texts)
        st.session_state.loaded_files.extend(new_files)
        st.success(f"{len(new_texts)} arquivo(s) adicionados ao contexto e salvos em {target_folder}!")
        st.rerun()

with st.expander("📄 Visualizar contexto completo (clique para expandir)"):
    st.text_area("Contexto carregado", st.session_state.context_text, height=300, disabled=True)

st.divider()
st.subheader("💬 Faça sua pergunta")

for msg in st.session_state.get("messages", []):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_prompt = st.chat_input("Digite sua pergunta sobre as diretrizes...")
if user_prompt:
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)
    context = st.session_state.context_text
    if not context.strip():
        st.error("Nenhum contexto carregado. Certifique-se de que o caminho contém arquivos suportados ou faça upload.")
    else:
        urls = list(set(extract_urls_from_text(user_prompt)))
        if urls:
            with st.status("🔍 Acessando URLs para extrair conteúdo...", expanded=False) as status:
                for url in urls:
                    status.write(f"Processando: {url}")
                    content = fetch_url_content(url)
                    if content and not content.startswith("[Erro]"):
                        context += f"\n\n--- Conteúdo de {url} ---\n{content}\n"
                        status.write(f"✅ Conteúdo de {url} adicionado ao contexto.")
                    else:
                        status.write(f"⚠️ Não foi possível extrair conteúdo de {url}.")
                status.update(label="✅ URLs processadas", state="complete")
        history = st.session_state.messages[-5:] if len(st.session_state.messages) > 5 else st.session_state.messages
        history_text = ""
        for msg in history:
            if msg["role"] == "user":
                history_text += f"Usuário: {msg['content']}\n"
            else:
                history_text += f"Assistente: {msg['content']}\n"
        qa_keywords = ["page quality", "rating", "url", "avaliação", "pq", "qualidade da página", "lowest", "highest", "medium", "low", "ymyl", "e-e-a-t"]
        is_qa_request = any(kw in user_prompt.lower() for kw in qa_keywords) or any("http" in word for word in user_prompt.split())

        total_prompt_chars = len(history_text) + len(context) + len(user_prompt) + 500
        need_reduction = total_prompt_chars > MAX_CONTEXT_CHARS

        if is_qa_request:
            base_prompt = f"""
Você é um especialista em Page Quality (PQ) rating, seguindo as diretrizes do Google.
O usuário está preenchendo um formulário de avaliação final e pede a melhor classificação para URLs.
Considere o histórico da conversa (últimas mensagens) para manter coerência e, se solicitado, refine sua resposta anterior.
HISTÓRICO DA CONVERSA:
{history_text}
CONTEXTO ADICIONAL (diretrizes, PDFs, conteúdo de URLs):
{context}
PERGUNTA ATUAL:
{user_prompt}
Se a pergunta pedir para refinar ou corrigir uma resposta anterior, use o histórico para ajustar a classificação ou o comentário.
Forneça a resposta de forma clara, listando as URLs com classificação e comentário em inglês.
"""
        else:
            base_prompt = f"""
Responda à pergunta do usuário com base no contexto fornecido (diretrizes, arquivos e conteúdo de URLs mencionadas).
Seja útil, direto e forneça uma resposta detalhada.
HISTÓRICO DA CONVERSA:
{history_text}
CONTEXTO:
{context}
PERGUNTA:
{user_prompt}
"""
        if need_reduction:
            st.info("Contexto muito longo. Resumindo para caber no limite do modelo...")
            try:
                prompt_words = re.findall(r'["\']([^"\']+)["\']|livro\s+([^\s,.]+)', user_prompt.lower())
                keywords = []
                for match in prompt_words:
                    if match[0]:
                        keywords.append(match[0])
                    elif match[1]:
                        keywords.append(match[1])
                if not keywords:
                    keywords = [w for w in user_prompt.lower().split() if len(w) > 4]
                target_len = MAX_CONTEXT_CHARS - len(history_text) - len(user_prompt) - 500
                target_len = max(target_len, 500)
                reduced_context = reduce_context(context, selected_model, target_len, keywords=keywords[:3])
                if reduced_context and len(reduced_context) < len(context):
                    context = reduced_context
                else:
                    st.warning("Falha ao resumir o contexto. Usando versão truncada.")
                    context = context[:target_len]
            except Exception as e:
                st.error(f"Erro durante o resumo: {e}. Usando contexto truncado.")
                context = context[:MAX_CONTEXT_CHARS]
            if is_qa_request:
                evaluation_prompt = f"""
Você é um especialista em Page Quality (PQ) rating, seguindo as diretrizes do Google.
O usuário está preenchendo um formulário de avaliação final e pede a melhor classificação para URLs.
Considere o histórico da conversa (últimas mensagens) para manter coerência e, se solicitado, refine sua resposta anterior.
HISTÓRICO DA CONVERSA:
{history_text}
CONTEXTO ADICIONAL (diretrizes, PDFs, conteúdo de URLs):
{context}
PERGUNTA ATUAL:
{user_prompt}
Se a pergunta pedir para refinar ou corrigir uma resposta anterior, use o histórico para ajustar a classificação ou o comentário.
Forneça a resposta de forma clara, listando as URLs com classificação e comentário em inglês.
"""
            else:
                evaluation_prompt = f"""
Responda à pergunta do usuário com base no contexto fornecido (diretrizes, arquivos e conteúdo de URLs mencionadas).
Seja útil, direto e forneça uma resposta detalhada.
HISTÓRICO DA CONVERSA:
{history_text}
CONTEXTO:
{context}
PERGUNTA:
{user_prompt}
"""
        else:
            evaluation_prompt = base_prompt
        with st.chat_message("assistant"):
            with st.spinner("Gerando resposta..."):
                try:
                    response = call_ollama_stream(
                        prompt=evaluation_prompt,
                        model=selected_model,
                        context=""
                    )
                    if response:
                        st.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        st.error("Erro ao obter resposta da IA. Verifique sua chave e modelo.")
                except Exception as e:
                    st.error(f"Erro durante a geração da resposta: {str(e)}")

st.caption("Nota: O contexto inclui as diretrizes e o conteúdo extraído dos arquivos e URLs mencionadas. Para respostas mais precisas, mantenha o prompt relevante.")