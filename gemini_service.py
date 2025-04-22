import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Carrega variáveis de ambiente
load_dotenv()

# Classe para a resposta estruturada
class LegalResponse(BaseModel):
    resposta: str = Field(..., description="Resposta textual à pergunta")
    paginas_referencia: List[int] = Field(default_factory=list, description="Números das páginas de referência")
    buscas_sugeridas: List[str] = Field(default_factory=list, description="Termos ou artigos relacionados para busca adicional")

class GeminiService:
    def __init__(self, api_key=None):
        # Usa a API key fornecida ou tenta obter do ambiente
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-2.0-flash-001'  # Modelo com suporte a cache
        self.cache = None
        self.cache_name = None
        self.system_instruction = (
            'Você é um especialista em análise de documentos jurídicos. '
            'Sua função é responder perguntas com base no conteúdo do documento, '
            'citando sempre os números das páginas de referência para cada informação. '
            'Além disso, identifique de 0 a 3 referências cruzadas no documento que são mencionadas '
            'na resposta atual. Por exemplo, se sua resposta menciona um "Artigo 5º" ou uma "Cláusula X" '
            'ou remete a "Anexo Y" ou "Seção Z" do mesmo documento, inclua essas referências para busca '
            'adicional. Não inclua termos genéricos, apenas referências específicas a outras partes do '
            'documento que são citadas ou relacionadas à resposta atual. '
            'Se não houver referências cruzadas, retorne uma lista vazia. '
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
                if 'buscas_sugeridas' not in result:
                    result['buscas_sugeridas'] = []
                
            except Exception as e:
                print(f"Erro ao processar JSON: {str(e)}")
                # Verificar se há texto na resposta
                if hasattr(response, 'candidates') and response.candidates:
                    # Extrair texto diretamente dos candidatos se disponível
                    text_content = response.candidates[0].content.parts[0].text
                    result = {
                        "resposta": text_content or raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": [],
                        "buscas_sugeridas": []
                    }
                else:
                    # Fallback para o texto bruto
                    result = {
                        "resposta": raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": [],
                        "buscas_sugeridas": []
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
    
    def query_document_with_context(self, prompt: str, chat_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consulta o documento usando o cache atual e mantendo o contexto das mensagens anteriores.
        
        Args:
            prompt: A pergunta atual do usuário
            chat_history: Lista de mensagens anteriores no formato [{"role": "user/assistant", "content": "..."}]
            
        Returns:
            Dicionário com a resposta e metadados
        """
        if not self.cache_name:
            raise Exception("Nenhum cache foi criado. Carregue um documento primeiro.")
        
        try:
            # Construir o contexto a partir do histórico (últimas 10 mensagens para evitar tokens excessivos)
            context_messages = chat_history[-10:] if len(chat_history) > 10 else chat_history
            
            # Formatar o contexto para o Gemini
            formatted_context = ""
            for msg in context_messages:
                role = "Usuário" if msg["role"] == "user" else "Assistente"
                formatted_context += f"{role}: {msg['content']}\n\n"
            
            # Adicionar a pergunta atual com instruções para buscas sugeridas
            full_prompt = (
                f"{formatted_context}Usuário: {prompt}\n\n"
                f"Assistente: (Responda à pergunta e identifique de 0 a 3 referências cruzadas específicas no documento "
                f"como artigos, cláusulas, seções ou anexos que são mencionados na sua resposta ou diretamente relacionados. "
                f"Inclua apenas referências explícitas a outras partes do documento, não termos genéricos. "
                f"Deixe a lista vazia se não houver referências cruzadas relevantes.)"
            )
            
            # Fazer a consulta ao modelo com o contexto completo
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    cached_content=self.cache_name,
                    response_mime_type='application/json',
                    response_schema=LegalResponse,
                    temperature=0.2,
                )
            )
            
            # Processar a resposta da mesma forma que no método query_document
            raw_text = response.text
            print(f"Resposta bruta do modelo com contexto: {raw_text}")
            
            # Extrair a resposta estruturada
            try:
                # Tentar processar como JSON
                result = json.loads(raw_text)
                
                # Garantir que temos os campos esperados
                if 'resposta' not in result:
                    result['resposta'] = raw_text
                if 'paginas_referencia' not in result:
                    result['paginas_referencia'] = []
                if 'buscas_sugeridas' not in result:
                    result['buscas_sugeridas'] = []
                
            except Exception as e:
                print(f"Erro ao processar JSON: {str(e)}")
                # Verificar se há texto na resposta
                if hasattr(response, 'candidates') and response.candidates:
                    # Extrair texto diretamente dos candidatos se disponível
                    text_content = response.candidates[0].content.parts[0].text
                    result = {
                        "resposta": text_content or raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": [],
                        "buscas_sugeridas": []
                    }
                else:
                    # Fallback para o texto bruto
                    result = {
                        "resposta": raw_text or "Não foi possível obter uma resposta válida.",
                        "paginas_referencia": [],
                        "buscas_sugeridas": []
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
            raise Exception(f"Erro ao consultar o documento com contexto: {str(e)}")
    
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