import streamlit as st
import os
import time
from datetime import datetime
import validators
from dotenv import load_dotenv
from pdf_service import PDFService
from gemini_service import GeminiService
import re

# Carregar variáveis de ambiente
load_dotenv()

# Configurar a página do Streamlit
st.set_page_config(
    page_title="Consulta Legal - Documentos PDF com IA",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar estado da sessão, se necessário
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pdf_loaded" not in st.session_state:
    st.session_state.pdf_loaded = False
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name = None
if "cache_info" not in st.session_state:
    st.session_state.cache_info = None
if "api_key" not in st.session_state:
    st.session_state.api_key = None
if "services_initialized" not in st.session_state:
    st.session_state.services_initialized = False

# Inicializar serviços
@st.cache_resource
def get_pdf_service():
    return PDFService()

def get_gemini_service(api_key):
    return GeminiService(api_key=api_key)

pdf_service = get_pdf_service()

# Inicializar o serviço Gemini apenas quando a API key estiver disponível
def initialize_services(api_key):
    if api_key and not st.session_state.services_initialized:
        st.session_state.gemini_service = get_gemini_service(api_key)
        st.session_state.services_initialized = True
        return True
    return st.session_state.services_initialized

# Função para processar o PDF (upload ou URL)
def process_pdf(option, file_upload=None, url=None):
    # Verificar se a API key está configurada
    if not st.session_state.api_key or not st.session_state.services_initialized:
        st.error("Por favor, configure sua chave da API Gemini primeiro!")
        return False
        
    with st.spinner("Processando documento..."):
        try:
            if option == "upload" and file_upload:
                # Validar que é um PDF
                if not pdf_service.validate_pdf(file_upload):
                    st.error("O arquivo enviado não é um PDF válido!")
                    return False
                
                # Salvar o PDF enviado
                pdf_path = pdf_service.save_uploaded_pdf(file_upload)
                st.session_state.pdf_name = file_upload.name
                
            elif option == "url" and url:
                # Validar URL
                if not validators.url(url):
                    st.error("URL inválida! Por favor, forneça uma URL válida.")
                    return False
                
                # Baixar o PDF
                pdf_path = pdf_service.download_pdf_from_url(url)
                st.session_state.pdf_name = pdf_service.get_current_pdf_name()
            else:
                st.error("Opção inválida ou nenhum arquivo/URL fornecido.")
                return False
            
            # Obter os bytes do PDF
            pdf_bytes = pdf_service.get_pdf_bytes()
            if not pdf_bytes:
                st.error("Falha ao ler o documento PDF.")
                return False
            
            # Criar cache para o PDF no Gemini
            with st.spinner("Criando cache do documento no Gemini..."):
                cache_info = st.session_state.gemini_service.create_cache_for_pdf(
                    pdf_bytes,
                    display_name=f"pdf_cache_{int(time.time())}",
                    ttl="3600s"  # 1 hora
                )
                st.session_state.cache_info = cache_info
            
            # Atualizar o estado da sessão
            st.session_state.pdf_loaded = True
            st.session_state.chat_history = []  # Limpar histórico quando novo PDF for carregado
            
            # Exibir mensagem de sucesso
            st.success(f"PDF carregado com sucesso: {st.session_state.pdf_name}")
            return True
            
        except Exception as e:
            st.error(f"Erro ao processar o documento: {str(e)}")
            return False

# Função para processar as buscas sugeridas
def process_suggested_search(search_term):
    """Processa uma busca sugerida pelo modelo e retorna o resultado."""
    if not st.session_state.gemini_service.has_active_cache():
        return None
    
    try:
        # Formatar a busca como uma consulta específica para referência cruzada
        query = f"Forneça um resumo claro e bem formatado sobre {search_term} mencionado no documento. Não cole o texto bruto do documento, mas sim explique o conteúdo de forma organizada e legível."
        
        # Consultar o Gemini (sem incluir todo o histórico para evitar confusão de contexto)
        response_data = st.session_state.gemini_service.query_document(query)
        
        # Extrair resposta e metadados
        result = response_data.get("result", {})
        metadata = response_data.get("metadata", {})
        
        # Garantir que temos uma resposta textual
        resposta_texto = result.get("resposta", "")
        if not resposta_texto:
            resposta_texto = f"Não foi possível encontrar detalhes específicos sobre {search_term} no documento."
        
        # Criar dados de resposta
        search_result = {
            "term": search_term,
            "content": resposta_texto,
            "pages": result.get("paginas_referencia", []),
            "metadata": metadata
        }
        
        return search_result
    
    except Exception as e:
        print(f"Erro ao processar referência cruzada '{search_term}': {str(e)}")
        return None

# Função para processar as consultas
def process_query(query):
    if not st.session_state.gemini_service.has_active_cache():
        st.error("Nenhum documento carregado! Por favor, carregue um documento primeiro.")
        return
    
    try:
        # Adicionar a pergunta ao histórico
        st.session_state.chat_history.append({"role": "user", "content": query})
        
        # Consultar o Gemini com contexto
        with st.spinner("Consultando o documento..."):
            response_data = st.session_state.gemini_service.query_document_with_context(
                query, 
                st.session_state.chat_history
            )
            
            # Extrair resposta e metadados
            result = response_data.get("result", {})
            metadata = response_data.get("metadata", {})
            
            # Debug - imprimir conteúdo da resposta
            print(f"Resultado: {result}")
            
            # Garantir que temos uma resposta textual
            resposta_texto = result.get("resposta", "")
            if not resposta_texto:
                resposta_texto = "Não foi possível obter uma resposta válida. Por favor, tente outra pergunta."
            
            # Obter buscas sugeridas
            buscas_sugeridas = result.get("buscas_sugeridas", [])
            
            # Adicionar a resposta ao histórico
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": resposta_texto,
                "pages": result.get("paginas_referencia", []),
                "metadata": metadata,
                "buscas_sugeridas": buscas_sugeridas
            })
            
            # Processar automaticamente as buscas sugeridas
            if buscas_sugeridas:
                # Apenas mostrar que estamos processando (sem listar as referências individuais)
                st.session_state.chat_history.append({
                    "role": "system",
                    "content": f"🔍 Analisando referências cruzadas no documento..."
                })
                
                # Ir direto para o consolidado, sem processar cada referência individualmente
                with st.spinner("Gerando análise das referências cruzadas..."):
                    # Verificar se há referências suficientes para consolidar
                    if len(buscas_sugeridas) > 0:
                        # Gerar diretamente o consolidado incluindo a pergunta original
                        summary_result = generate_cross_references_summary(buscas_sugeridas, query)
                        
                        if summary_result:
                            # Adicionar o consolidado ao histórico
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": summary_result['content'],
                                "pages": summary_result['pages'],
                                "metadata": summary_result['metadata'],
                                "is_consolidated": True
                            })
            
            # Forçar atualização da UI
            st.rerun()
    
    except Exception as e:
        st.error(f"Erro ao processar consulta: {str(e)}")
        st.session_state.chat_history.append({"role": "system", "content": f"Erro: {str(e)}"})
        # Forçar atualização da UI em caso de erro
        st.rerun()

# Função para iniciar um novo chat
def start_new_chat():
    st.session_state.chat_history = []
    st.rerun()

# Função para gerar um resumo consolidado das referências cruzadas
def generate_cross_references_summary(buscas_sugeridas, pergunta_original):
    """Gera um resumo consolidado de todas as referências cruzadas encontradas."""
    if not buscas_sugeridas or len(buscas_sugeridas) == 0:
        return None
    
    try:
        # Formatar a consulta para pedir um consolidado, incluindo a pergunta original como contexto
        query = f"""Com base na pergunta "{pergunta_original}", analise as seguintes referências do documento e forneça um resumo consolidado: {', '.join(buscas_sugeridas)}. 
        
        Importante:
        1. NÃO reproduza o texto bruto do documento
        2. Explique o significado e a importância dessas referências de forma clara e organizada
        3. Como elas se relacionam entre si no contexto da pergunta original
        4. Qual a conclusão ou entendimento geral que se pode extrair dessas referências em conjunto
        5. Organize sua resposta em parágrafos curtos e bem formatados
        """
        
        # Consultar o Gemini
        response_data = st.session_state.gemini_service.query_document(query)
        
        # Extrair resposta e metadados
        result = response_data.get("result", {})
        metadata = response_data.get("metadata", {})
        
        # Garantir que temos uma resposta textual
        resposta_texto = result.get("resposta", "")
        if not resposta_texto:
            resposta_texto = "Não foi possível gerar um resumo consolidado das referências."
        
        # Criar dados de resposta
        summary_result = {
            "content": resposta_texto,
            "pages": result.get("paginas_referencia", []),
            "metadata": metadata
        }
        
        return summary_result
    
    except Exception as e:
        print(f"Erro ao gerar resumo consolidado: {str(e)}")
        return None

# Interface do Streamlit
st.title("📚 Consulta Legal - Documentos PDF com IA")

# Sidebar para configuração da API e carregamento de documentos
with st.sidebar:
    st.header("Configuração")
    
    # Campo para inserção da API key do Gemini
    api_key = st.text_input("Insira sua chave da API Gemini:", 
                           type="password", 
                           help="Você precisa de uma chave da API Gemini para usar este aplicativo. Obtenha uma em: https://ai.google.dev/")
    
    if api_key:
        st.session_state.api_key = api_key
        if initialize_services(api_key):
            st.success("API key configurada com sucesso!")
        else:
            st.error("Erro ao configurar a API key.")
    else:
        st.warning("⚠️ Você precisa fornecer uma chave da API Gemini para usar este aplicativo.")
    
    if st.session_state.api_key:
        st.divider()
        st.header("Carregar Documento")
        
        # Opções para carregar o documento
        option = st.radio("Escolha como carregar o documento:", ["upload", "url"])
        
        if option == "upload":
            file_upload = st.file_uploader("Enviar arquivo PDF:", type=["pdf"])
            if file_upload:
                if st.button("Processar documento enviado"):
                    process_pdf("upload", file_upload=file_upload)
        
        elif option == "url":
            url = st.text_input("URL do documento PDF:")
            if url:
                if st.button("Baixar e processar PDF"):
                    process_pdf("url", url=url)
        
        # Exibir informações do cache se existir
        if st.session_state.cache_info:
            st.divider()
            st.subheader("Informações do Cache")
            expiry = st.session_state.cache_info.get("expire_time", "")
            if expiry:
                try:
                    # Converter para datetime se for string
                    if isinstance(expiry, str):
                        expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
                    
                    # Calcular tempo restante
                    now = datetime.now().astimezone()
                    remaining = expiry - now
                    if remaining.total_seconds() > 0:
                        minutes, seconds = divmod(remaining.total_seconds(), 60)
                        st.info(f"Cache expira em: {int(minutes)}m {int(seconds)}s")
                    else:
                        st.warning("Cache expirado!")
                except:
                    st.info(f"Data de expiração: {expiry}")
            
            # Botão para renovar o cache
            if st.button("Renovar Cache (+ 1 hora)"):
                try:
                    st.session_state.gemini_service.update_cache_ttl("3600s")
                    st.success("Cache renovado por mais 1 hora!")
                    # Atualizar informações do cache
                    # (Numa implementação completa, seria necessário obter as novas informações do cache)
                except Exception as e:
                    st.error(f"Erro ao renovar cache: {str(e)}")

# Container principal para o chat
if st.session_state.api_key and st.session_state.pdf_loaded:
    # Layout de duas colunas
    col1, col2 = st.columns([7, 3])
    
    # Coluna do chat
    with col1:
        # Adicionar o botão "Novo Chat" na parte superior
        col_title, col_button = st.columns([4, 1])
        with col_title:
            st.subheader(f"Chat sobre: {st.session_state.pdf_name}")
        with col_button:
            if st.button("🔄 Novo Chat"):
                start_new_chat()
        
        # Exibir histórico do chat
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    st.chat_message("user").write(message["content"])
                elif message["role"] == "assistant":
                    with st.chat_message("assistant"):
                        # Verificar se é uma busca relacionada
                        is_related = message.get("is_related_search", False)
                        
                        # Garantir que o conteúdo nunca está vazio
                        content = message.get("content", "")
                        if not content:
                            content = "Não foi possível obter uma resposta. Por favor, tente outra pergunta."
                        
                        # Exibir a resposta com estilo diferente para buscas relacionadas
                        if is_related:
                            with st.container():
                                st.info(content)
                        elif message.get("is_consolidated", False):
                            with st.container():
                                st.success(content)
                        else:
                            st.markdown(content)
                        
                        # Exibir páginas de referência
                        if message.get("pages"):
                            st.info(f"📄 Páginas referenciadas: {', '.join(map(str, message['pages']))}")
                        # Mostrar metadados de tokens
                        if message.get("metadata"):
                            with st.expander("Ver metadados de tokens"):
                                metadata = message["metadata"]
                                st.text(f"Total de tokens: {metadata.get('total_tokens', 'N/A')}")
                                st.text(f"Tokens em cache: {metadata.get('cached_tokens', 'N/A')}")
                                st.text(f"Tokens do prompt: {metadata.get('prompt_tokens', 'N/A')}")
                                st.text(f"Tokens da resposta: {metadata.get('response_tokens', 'N/A')}")
                elif message["role"] == "system":
                    st.info(message["content"])
        
        # Campo para nova pergunta
        query = st.chat_input("Digite sua pergunta sobre o documento...")
        if query:
            process_query(query)

    # Coluna de visualização das páginas
    with col2:
        st.subheader("Visualização de Páginas")
        
        # Obter páginas referenciadas na última resposta
        ref_pages = []
        if st.session_state.chat_history and len(st.session_state.chat_history) > 0:
            for msg in reversed(st.session_state.chat_history):
                if msg["role"] == "assistant" and "pages" in msg:
                    ref_pages = msg["pages"]
                    break
        
        if ref_pages:
            # Renderizar as páginas referenciadas
            page_images = pdf_service.get_pdf_page_images(ref_pages)
            
            if page_images:
                for page_num, img_bytes in page_images:
                    st.subheader(f"Página {page_num}")
                    st.image(img_bytes, use_container_width=True)
            else:
                st.info("Não foi possível renderizar as páginas referenciadas.")
        else:
            st.info("Faça uma pergunta para ver as páginas referenciadas aqui.")
elif not st.session_state.api_key:
    st.info("👆 Por favor, insira sua chave da API Gemini na barra lateral para começar.")
elif not st.session_state.pdf_loaded:
    st.info("👆 Por favor, carregue um documento PDF na barra lateral para começar.")

# Exemplos de perguntas que podem ser feitas
with st.expander("Exemplos de perguntas que você pode fazer após carregar um documento"):
    st.markdown("""
    - Qual o conteúdo principal deste documento?
    - Resuma o capítulo sobre X.
    - Explique o que diz o documento sobre Y.
    - Quais são os pontos principais da seção Z?
    - O que este documento fala sobre [termo específico]?
    """)

# Informações sobre a aplicação
st.divider()
st.markdown("""
### Sobre esta aplicação

Esta aplicação permite carregar documentos PDF e fazer perguntas sobre seu conteúdo usando a API Gemini.

**Recursos:**
- Carregue documentos por upload ou URL
- Cache inteligente que economiza tokens em consultas subsequentes
- Chat interativo com contexto mantido
- Visualização das páginas referenciadas nas respostas
- Métricas de uso de tokens

**Como utilizar:**
1. Carregue um documento PDF
2. Faça perguntas no chat
3. Veja a resposta com as páginas referenciadas
4. Continue a conversa sobre o documento
""") 