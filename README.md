# 📚 Consulta Legal - Documentos PDF com IA

Uma aplicação Streamlit que permite carregar documentos PDF e fazer perguntas sobre seu conteúdo usando o modelo Gemini da Google, com visualização de páginas referenciadas e uso eficiente de cache.

## ✨ Recursos

- 📄 Carregue documentos PDF por upload ou URL
- 🧠 Cache inteligente que economiza tokens em consultas subsequentes
- 💬 Chat interativo com contexto mantido durante toda a conversa
- 🔍 Visualização das páginas referenciadas nas respostas
- 📊 Métricas de uso de tokens
- ⏱️ Gerenciamento do tempo de vida do cache

## 🚀 Instalação

1. Clone o repositório:

```bash
git clone [URL_DO_REPOSITÓRIO]
cd [NOME_DO_DIRETÓRIO]
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Crie um arquivo `.env` na raiz do projeto e adicione sua chave API do Gemini:

```
GEMINI_API_KEY=sua_chave_aqui
```

## 🏃‍♂️ Como executar

Execute a aplicação Streamlit:

```bash
streamlit run app.py
```

A aplicação estará disponível em `http://localhost:8501`.

## 📖 Como usar

1. Carregue um documento PDF usando uma das opções:

   - Upload de arquivo local
   - URL de um documento PDF online

2. Após o documento ser carregado e cacheado, faça perguntas no chat.

3. A aplicação responderá baseando-se no conteúdo do documento e mostrará:

   - A resposta textual
   - Os números das páginas referenciadas
   - Visualização das páginas referenciadas
   - Métricas de uso de tokens (incluindo economia pelo cache)

4. Continue a conversa sobre o documento - todas as consultas usarão o mesmo cache.

5. O cache tem duração de 1 hora por padrão, mas pode ser renovado através do botão na interface.

## 🛠️ Estrutura do projeto

- `app.py` - Aplicação Streamlit principal
- `gemini_service.py` - Serviço para gerenciar o cache do Gemini e as consultas
- `pdf_service.py` - Serviço para processamento de PDFs (download, renderização)
- `requirements.txt` - Dependências do projeto
- `.env` - Arquivo para configuração da API key (local, não comitado)

## 📋 Requisitos

- Python 3.8+
- Conta Google AI Studio com API key para o Gemini
- Conexão com a internet

## 📝 Notas

- O cache do documento tem um TTL (time-to-live) padrão de 1 hora
- Quanto maior o documento PDF, mais tokens serão usados no carregamento inicial
- As páginas visualizadas são renderizadas diretamente do PDF
- A aplicação economiza tokens em consultas subsequentes usando o recurso de cache do Gemini
