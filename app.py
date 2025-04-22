import streamlit as st
import os
import time
from datetime import datetime
import validators
from dotenv import load_dotenv
from pdf_service import PDFService
from gemini_service import GeminiService

# Carregar variáveis de ambiente
load_dotenv()

# Verificar se a API KEY está configurada
if not os.getenv('GEMINI_API_KEY'):
    st.error("⚠️ GEMINI_API_KEY não encontrada! Crie um arquivo .env com sua chave.")
    st.stop()

# Configurar a página do Streamlit
st.set_page_config(
    page_title="Consulta Legal - Documentos PDF com IA",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar serviços
@st.cache_resource
def get_pdf_service():
    return PDFService()

@st.cache_resource
def get_gemini_service():
    return GeminiService()

pdf_service = get_pdf_service()
gemini_service = get_gemini_service()

# Inicializar estado da sessão, se necessário
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pdf_loaded" not in st.session_state:
    st.session_state.pdf_loaded = False
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name = None
if "cache_info" not in st.session_state:
    st.session_state.cache_info = None

# Função para processar o PDF (upload ou URL)
def process_pdf(option, file_upload=None, url=None):
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
                cache_info = gemini_service.create_cache_for_pdf(
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

# Função para processar as consultas
def process_query(query):
    if not gemini_service.has_active_cache():
        st.error("Nenhum documento carregado! Por favor, carregue um documento primeiro.")
        return
    
    try:
        # Adicionar a pergunta ao histórico
        st.session_state.chat_history.append({"role": "user", "content": query})
        
        # Consultar o Gemini
        with st.spinner("Consultando o documento..."):
            response_data = gemini_service.query_document(query)
            
            # Extrair resposta e metadados
            result = response_data.get("result", {})
            metadata = response_data.get("metadata", {})
            
            # Debug - imprimir conteúdo da resposta
            print(f"Resultado: {result}")
            
            # Garantir que temos uma resposta textual
            resposta_texto = result.get("resposta", "")
            if not resposta_texto:
                resposta_texto = "Não foi possível obter uma resposta válida. Por favor, tente outra pergunta."
            
            # Adicionar a resposta ao histórico
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": resposta_texto,
                "pages": result.get("paginas_referencia", []),
                "metadata": metadata
            })
            
            # Forçar atualização da UI
            st.rerun()
    
    except Exception as e:
        st.error(f"Erro ao processar consulta: {str(e)}")
        st.session_state.chat_history.append({"role": "system", "content": f"Erro: {str(e)}"})
        # Forçar atualização da UI em caso de erro
        st.rerun()

# Interface do Streamlit
st.title("📚 Consulta Legal - Documentos PDF com IA")

# Sidebar para carregar documento
with st.sidebar:
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
                gemini_service.update_cache_ttl("3600s")
                st.success("Cache renovado por mais 1 hora!")
                # Atualizar informações do cache
                # (Numa implementação completa, seria necessário obter as novas informações do cache)
            except Exception as e:
                st.error(f"Erro ao renovar cache: {str(e)}")

# Container principal para o chat
if st.session_state.pdf_loaded:
    # Layout de duas colunas
    col1, col2 = st.columns([7, 3])
    
    # Coluna do chat
    with col1:
        st.subheader(f"Chat sobre: {st.session_state.pdf_name}")
        
        # Exibir histórico do chat
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    st.chat_message("user").write(message["content"])
                elif message["role"] == "assistant":
                    with st.chat_message("assistant"):
                        # Garantir que o conteúdo nunca está vazio
                        content = message.get("content", "")
                        if not content:
                            content = "Não foi possível obter uma resposta. Por favor, tente outra pergunta."
                        
                        # Exibir a resposta
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
                    st.image(img_bytes, use_column_width=True)
            else:
                st.info("Não foi possível renderizar as páginas referenciadas.")
        else:
            st.info("Faça uma pergunta para ver as páginas referenciadas aqui.")

else:
    # Mensagem para guiar o usuário a carregar um documento
    st.info("👈 Comece carregando um documento PDF no painel lateral.")
    
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