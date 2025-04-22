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

doc_url = 'https://www.inteli.edu.br/wp-content/uploads/2024/08/RELATORIO-ANUAL-2024-22082024-FINAL-DIGITAL.pdf'

filepath = pathlib.Path('file.pdf')
filepath.write_bytes(httpx.get(doc_url).content)

prompt = "Qual foi o caixa líquido gerado pela empresa no ano de 2023?"

response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=[
        types.Part.from_bytes(
            data=filepath.read_bytes(),
            mime_type='application/pdf'
        ),
        prompt])

print(response.text)