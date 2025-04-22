import os
import pathlib
import tempfile
import httpx
import PyPDF2
from urllib.parse import urlparse
import streamlit as st
from io import BytesIO

class PDFService:
    def __init__(self):
        self.temp_dir = pathlib.Path(tempfile.mkdtemp())
        self.current_pdf_path = None
        self.pdf_name = None
        
    def download_pdf_from_url(self, url):
        """Download PDF from a URL and return the path."""
        try:
            # Extrair nome do arquivo da URL
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            if not filename or not filename.lower().endswith('.pdf'):
                filename = 'downloaded_document.pdf'
            
            # Criar caminho para salvar o arquivo
            file_path = self.temp_dir / filename
            
            # Fazer download do PDF
            response = httpx.get(url)
            if response.status_code != 200:
                raise Exception(f"Falha ao baixar o PDF: {response.status_code}")
            
            # Verificar se é realmente um PDF
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                raise Exception("O URL não parece conter um arquivo PDF válido")
            
            # Salvar o arquivo
            file_path.write_bytes(response.content)
            self.current_pdf_path = file_path
            self.pdf_name = filename
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Erro ao baixar o PDF: {str(e)}")
    
    def save_uploaded_pdf(self, uploaded_file):
        """Salva um arquivo PDF enviado pelo usuário e retorna o caminho."""
        try:
            filename = uploaded_file.name
            file_path = self.temp_dir / filename
            
            # Salvar o arquivo
            file_path.write_bytes(uploaded_file.getvalue())
            self.current_pdf_path = file_path
            self.pdf_name = filename
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Erro ao salvar o PDF enviado: {str(e)}")
    
    def get_pdf_page_images(self, page_numbers):
        """Renderiza páginas específicas do PDF como imagens para exibição no Streamlit."""
        import fitz  # PyMuPDF
        
        if not self.current_pdf_path or not page_numbers:
            return []
        
        try:
            # Abrir o documento PDF
            doc = fitz.open(self.current_pdf_path)
            images = []
            
            # Para cada número de página, renderizar uma imagem
            for page_num in page_numbers:
                # Ajustar para indexação baseada em zero do PyMuPDF
                if page_num < 1 or page_num > len(doc):
                    continue
                    
                page = doc[page_num - 1]  # PyMuPDF usa indexação baseada em zero
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Renderizar com escala 2x para melhor qualidade
                img_bytes = pix.tobytes("png")
                images.append((page_num, img_bytes))
            
            doc.close()
            return images
            
        except Exception as e:
            st.error(f"Erro ao renderizar páginas do PDF: {str(e)}")
            return []
    
    def get_pdf_bytes(self):
        """Retorna os bytes do PDF atual."""
        if self.current_pdf_path and self.current_pdf_path.exists():
            return self.current_pdf_path.read_bytes()
        return None
    
    def validate_pdf(self, file_or_path):
        """Valida se o arquivo é um PDF válido."""
        try:
            if isinstance(file_or_path, pathlib.Path):
                PyPDF2.PdfReader(open(file_or_path, 'rb'))
            else:
                PyPDF2.PdfReader(BytesIO(file_or_path.getvalue()))
            return True
        except Exception as e:
            st.error(f"O arquivo não é um PDF válido: {str(e)}")
            return False
    
    def get_current_pdf_path(self):
        """Retorna o caminho do PDF atual."""
        return self.current_pdf_path
    
    def get_current_pdf_name(self):
        """Retorna o nome do PDF atual."""
        return self.pdf_name 