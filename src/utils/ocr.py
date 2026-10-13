import requests
import os
import streamlit as st
from PyPDF2 import PdfReader
from io import BytesIO
import base64
import fitz
import pytesseract
from PIL import Image
import cv2
import numpy as np
from pptx import Presentation
from docx import Document as DocxDocument

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "")
OCR_URL = "https://api.ocr.space/parse/image"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com")

def deskew(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5:
        return image
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

def preprocess_image(pil_img):
    img = np.array(pil_img.convert('RGB'))
    img = deskew(img)
    img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return Image.fromarray(thresh)

def postprocess_text(text):
    replacements = {
        '|': 'l', '1': 'l', '0': 'O', '5': 'S',
        'é': 'e', 'ã': 'a', 'ç': 'c', 'á': 'a',
        'í': 'i', 'ó': 'o', 'ú': 'u', 'â': 'a',
        'ê': 'e', 'ô': 'o', '"': '', '`': "'",
        '…': '...', '—': '-', '–': '-'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line:
            if line.endswith('-'):
                line = line[:-1]
            if len(line) > 1:
                clean_lines.append(line)
    return '\n'.join(clean_lines)

def extract_text_from_file(file_bytes, filename, model=None):
    ext = filename.split('.')[-1].lower()
    if ext == 'pdf':
        return extract_text_from_pdf(file_bytes, model)
    elif ext in ['png', 'jpg', 'jpeg']:
        return extract_text_from_image(file_bytes)
    elif ext == 'pptx':
        return extract_text_from_pptx(file_bytes)
    elif ext == 'docx':
        return extract_text_from_docx(file_bytes)
    elif ext == 'txt':
        return file_bytes.decode('utf-8', errors='ignore')
    else:
        st.warning(f"Formato {ext} não suportado para extração.")
        return ""

def extract_text_from_pdf(pdf_bytes, model=None):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"
        doc.close()
        if text.strip():
            return postprocess_text(text)
    except Exception as e:
        st.info(f"PyMuPDF falhou: {str(e)}")

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        if text.strip():
            return postprocess_text(text)
    except Exception as e:
        st.info(f"PyPDF2 falhou: {str(e)}")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = ""
        for page_num, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img = Image.open(BytesIO(img_bytes))
            processed = preprocess_image(img)
            config = '--psm 6 --oem 3 -l por+eng'
            page_text = pytesseract.image_to_string(processed, config=config)
            if page_text.strip():
                all_text += f"\n--- Página {page_num} ---\n{page_text}\n"
        doc.close()
        if all_text.strip():
            return postprocess_text(all_text)
    except Exception as e:
        st.info(f"Tesseract falhou: {str(e)}")

    ocr_text = extract_text_with_ocr(pdf_bytes)
    if ocr_text.strip():
        return postprocess_text(ocr_text)

    if model and is_vision_model(model):
        st.info("Tentando extrair texto com visão do Ollama...")
        return postprocess_text(extract_text_with_vision(pdf_bytes, model))
    else:
        st.warning("Não foi possível extrair texto. Considere usar um modelo com suporte a visão (ex: gemma4:31b).")
        return ""

def extract_text_from_image(file_bytes):
    try:
        img = Image.open(BytesIO(file_bytes))
        processed = preprocess_image(img)
        config = '--psm 6 --oem 3 -l por+eng'
        text = pytesseract.image_to_string(processed, config=config)
        return postprocess_text(text)
    except Exception as e:
        st.error(f"Erro no OCR de imagem: {str(e)}")
        return ""

def extract_text_from_pptx(file_bytes):
    try:
        prs = Presentation(BytesIO(file_bytes))
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
                if hasattr(shape, "notes_slide") and shape.notes_slide:
                    notes = shape.notes_slide.notes_text_frame.text
                    if notes:
                        text += notes + "\n"
        return postprocess_text(text)
    except Exception as e:
        st.error(f"Erro ao extrair texto do PowerPoint: {str(e)}")
        return ""

def extract_text_from_docx(file_bytes):
    try:
        doc = DocxDocument(BytesIO(file_bytes))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return postprocess_text(text)
    except Exception as e:
        st.error(f"Erro ao extrair texto do DOCX: {str(e)}")
        return ""

def extract_text_with_ocr(pdf_bytes):
    if not OCR_SPACE_API_KEY:
        st.error("Chave OCR Space não configurada.")
        return ""
    if len(pdf_bytes) > 1.5 * 1024 * 1024:
        st.warning("Arquivo > 1.5 MB. OCR Space (plano gratuito) não suporta. Usando fallback...")
        return ""
    files = {'file': ('document.pdf', pdf_bytes, 'application/pdf')}
    data = {
        'apikey': OCR_SPACE_API_KEY,
        'language': 'por',
        'isOverlayRequired': False,
        'filetype': 'PDF'
    }
    try:
        response = requests.post(OCR_URL, files=files, data=data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if result.get('OCRExitCode') == 1:
                return result['ParsedResults'][0]['ParsedText']
            else:
                st.error(f"Erro no OCR: {result.get('ErrorMessage', 'Desconhecido')}")
                return ""
        else:
            st.error(f"Falha na requisição OCR: {response.status_code}")
            st.error(f"Detalhes: {response.text}")
            return ""
    except Exception as e:
        st.error(f"Exceção no OCR: {str(e)}")
        return ""

def is_vision_model(model):
    vision_models = os.getenv("OLLAMA_VISION_MODELS", "gemma4:31b").split(',')
    vision_models = [m.strip() for m in vision_models if m.strip()]
    return model in vision_models

def extract_text_with_vision(pdf_bytes, model):
    if not OLLAMA_API_KEY:
        st.error("Chave Ollama não configurada.")
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = ""
        max_pages = 10
        for i, page in enumerate(doc):
            if i >= max_pages:
                st.info(f"Limite de {max_pages} páginas para visão. As demais não foram processadas.")
                break
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            prompt = "Extraia todo o texto desta imagem. Responda apenas com o texto extraído, sem comentários adicionais."
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [img_base64],
                "stream": False,
                "options": {"num_predict": 4000}
            }
            headers = {
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json"
            }
            url = f"{OLLAMA_HOST}/api/generate"
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            if response.status_code == 200:
                data = response.json()
                page_text = data.get('response', '')
                all_text += f"\n--- Página {i+1} ---\n{page_text}\n"
            else:
                st.error(f"Erro na chamada Ollama (página {i+1}): {response.status_code} - {response.text}")
        doc.close()
        return all_text.strip()
    except Exception as e:
        st.error(f"Erro ao extrair com visão: {str(e)}")
        return ""