import os
import json
import io
import pathlib
import time
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

# Modelo a ser usado (é necessário usar a versão explícita com sufixo)
model = 'gemini-2.0-flash-001'

# Criar um cache com TTL de 1 hora (3600 segundos)
print("Criando cache para o documento legal...")
cache = client.caches.create(
    model=model,
    config=types.CreateCachedContentConfig(
        display_name='lei_licitacoes_cache',  # nome para identificar o cache
        system_instruction=(
            'Você é um especialista em legislação brasileira. '
            'Sua função é analisar documentos legais e responder '
            'perguntas com base no conteúdo, citando as páginas de referência.'
        ),
        contents=[
            types.Part.from_bytes(
                data=filepath.read_bytes(),
                mime_type='application/pdf'
            )
        ],
        ttl="3600s",  # 1 hora
    )
)
print(f"Cache criado com sucesso: {cache.name}")

prompt = "Qual o prazo da vigência da ata de registro de preço?"

# Usar o cache na consulta
response = client.models.generate_content(
    model=model,
    contents=prompt,
    config=types.GenerateContentConfig(
        cached_content=cache.name,
        response_mime_type='application/json',
        response_schema=LegalResponse,
        temperature=0.2,
    )
)

# Mostrar os metadados de uso (incluindo informações sobre o cache)
print("\nMetadados de uso:")
print(f"Total de tokens: {response.usage_metadata.total_token_count}")
print(f"Tokens em cache: {response.usage_metadata.cached_content_token_count}")
print(f"Tokens do prompt: {response.usage_metadata.prompt_token_count}")
print(f"Tokens da resposta: {response.usage_metadata.candidates_token_count}")

# Extrair e mostrar a resposta estruturada
try:
    resultado = json.loads(response.text)
    print(f"\nResposta: {resultado['resposta']}")
    print(f"Páginas de referência: {resultado['paginas_referencia']}")
    print("\nJSON completo:")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Erro ao processar resposta estruturada: {e}")
    print("Resposta original:")
    print(response.text)

# Exemplo de função para fazer consultas adicionais usando o mesmo cache
def consultar_documento(pergunta):
    resp = client.models.generate_content(
        model=model,
        contents=pergunta,
        config=types.GenerateContentConfig(
            cached_content=cache.name,
            response_mime_type='application/json',
            response_schema=LegalResponse,
            temperature=0.2,
        )
    )
    
    try:
        result = json.loads(resp.text)
        return result
    except Exception as e:
        print(f"Erro ao processar resposta: {e}")
        return {"resposta": resp.text, "paginas_referencia": []}

# Exemplo de como fazer consultas adicionais (descomente para usar)
# nova_pergunta = "Quais são as modalidades de licitação previstas na lei?"
# resultado_nova = consultar_documento(nova_pergunta)
# print(f"\nNova pergunta: {nova_pergunta}")
# print(f"Resposta: {resultado_nova['resposta']}")
# print(f"Páginas de referência: {resultado_nova['paginas_referencia']}")

# Para excluir o cache quando não for mais necessário
# client.caches.delete(cache.name)