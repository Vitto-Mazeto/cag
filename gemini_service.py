import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Carrega variáveis de ambiente
load_dotenv()

# Configuração do modelo e API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Classe para a resposta estruturada
class LegalResponse(BaseModel):
    resposta: str = Field(..., description="Resposta textual à pergunta")
    paginas_referencia: List[int] = Field(default_factory=list, description="Números das páginas de referência")

class GeminiService:
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = 'gemini-2.0-flash-001'  # Modelo com suporte a cache
        self.cache = None
        self.cache_name = None
        self.system_instruction = (
            'Você é um especialista em análise de documentos. '
            'Sua função é responder perguntas com base no conteúdo do documento, '
            'citando sempre os números das páginas de referência para cada informação. '
            'Se não encontrar a informação no documento, informe claramente que a informação '
            'não foi encontrada e não faça suposições.'
        )
    
    def create_cache_for_pdf(self, pdf_bytes, display_name="documento_cache", ttl="3600s"):
        """Cria um cache para um documento PDF e retorna o ID do cache."""
        try:
            # Criar cache com o documento PDF
            self.cache = self.client.caches.create(
                model=self.model_name,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    system_instruction=self.system_instruction,
                    contents=[
                        types.Part.from_bytes(
                            data=pdf_bytes,
                            mime_type='application/pdf'
                        )
                    ],
                    ttl=ttl,  # Tempo de vida do cache (padrão: 1 hora)
                )
            )
            self.cache_name = self.cache.name
            
            # Retornar metadados do cache
            return {
                "cache_id": self.cache.name,
                "display_name": display_name,
                "expire_time": self.cache.expire_time,
            }
            
        except Exception as e:
            raise Exception(f"Erro ao criar cache para o documento: {str(e)}")
    
    def query_document(self, prompt: str) -> Dict[str, Any]:
        """
        Consulta o documento usando o cache atual e retorna a resposta estruturada.
        Retorna um dicionário com a resposta e metadados.
        """
        if not self.cache_name:
            raise Exception("Nenhum cache foi criado. Carregue um documento primeiro.")
        
        try:
            # Fazer a consulta ao modelo
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    cached_content=self.cache_name,
                    response_mime_type='application/json',
                    response_schema=LegalResponse,
                    temperature=0.2,
                )
            )
            
            # Obter texto da resposta (para debug)
            raw_text = response.text
            print(f"Resposta bruta do modelo: {raw_text}")
            
            # Extrair a resposta estruturada
            try:
                # Tentar processar como JSON
                result = json.loads(raw_text)
                
                # Garantir que temos os campos esperados
                if 'resposta' not in result:
                    result['resposta'] = raw_text
                if 'paginas_referencia' not in result:
                    result['paginas_referencia'] = []
                
            except Exception as e:
                print(f"Erro ao processar JSON: {str(e)}")
                # Verificar se há texto na resposta
                if hasattr(response, 'candidates') and response.candidates:
                    # Extrair texto diretamente dos candidatos se disponível
                    text_content = response.candidates[0].content.parts[0].text
                    result = {
                        "resposta": text_content or raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": []
                    }
                else:
                    # Fallback para o texto bruto
                    result = {
                        "resposta": raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": []
                    }
            
            # Verificação adicional para garantir que resposta não seja vazia
            if not result.get('resposta'):
                result['resposta'] = "O modelo retornou uma resposta vazia. Por favor, reformule sua pergunta."
            
            # Adicionar metadados de uso
            metadata = {
                "total_tokens": response.usage_metadata.total_token_count,
                "cached_tokens": response.usage_metadata.cached_content_token_count,
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "response_tokens": response.usage_metadata.candidates_token_count
            }
            
            return {
                "result": result,
                "metadata": metadata
            }
            
        except Exception as e:
            raise Exception(f"Erro ao consultar o documento: {str(e)}")
    
    def update_cache_ttl(self, ttl="3600s"):
        """Atualiza o TTL do cache atual."""
        if not self.cache_name:
            raise Exception("Nenhum cache para atualizar.")
        
        try:
            self.client.caches.update(
                name=self.cache_name,
                config=types.UpdateCachedContentConfig(ttl=ttl)
            )
            return True
        except Exception as e:
            raise Exception(f"Erro ao atualizar TTL do cache: {str(e)}")
    
    def delete_cache(self):
        """Exclui o cache atual se existir."""
        if self.cache_name:
            try:
                self.client.caches.delete(self.cache_name)
                self.cache_name = None
                return True
            except Exception as e:
                raise Exception(f"Erro ao excluir cache: {str(e)}")
        return False
    
    def has_active_cache(self):
        """Verifica se há um cache ativo."""
        return self.cache_name is not None 