import os
import json
import io
import pathlib
from typing import List, Optional
import httpx
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PyPDF2 import PdfReader, PdfWriter

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configurar a chave da API do Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

# Define o esquema para a saída estruturada
class LegalResponse(BaseModel):
    resposta: str = Field(..., description="Resposta textual à pergunta")
    paginas_referencia: List[int] = Field(default_factory=list, description="Números das páginas de referência")

doc_url = 'https://www2.senado.leg.br/bdsf/bitstream/handle/id/598313/Lei_licitacoes_contratos_administrativos_2ed.pdf'

filepath = pathlib.Path('file_pdf_legal.pdf')
if not filepath.exists():
    filepath.write_bytes(httpx.get(doc_url).content)
    print(f"Arquivo PDF baixado: {filepath}")
else:
    print(f"Arquivo PDF já existe: {filepath}")

prompt = "Qual o prazo da vigência da ata de registro de preço?"

response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=[
        types.Part.from_bytes(
            data=filepath.read_bytes(),
            mime_type='application/pdf'
        ),
        prompt],
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=LegalResponse,
        temperature=0.2,
    )
)

# Extrair e mostrar a resposta estruturada
try:
    resultado = json.loads(response.text)
    print(f"Resposta: {resultado['resposta']}")
    print(f"Páginas de referência: {resultado['paginas_referencia']}")
    print("\nJSON completo:")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Erro ao processar resposta estruturada: {e}")
    print("Resposta original:")
    print(response.text)