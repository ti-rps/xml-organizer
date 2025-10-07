# XML Organizer

`XML Organizer` é um script de automação em Python projetado para monitorar um diretório, processar arquivos XML de documentos fiscais (NF-e/NFC-e), registrar as informações em uma planilha do Google Sheets e mover os arquivos para um diretório de rede organizado.

## ✨ Funcionalidades

* **Busca Recursiva**: Procura por todos os arquivos `.xml` dentro de um diretório de origem e suas subpastas.
* **Extração de Dados**: Lê os arquivos XML para extrair informações essenciais como CNPJ, nome da empresa, data de emissão, chave de acesso e tipo de documento.
* **Registro em Planilha**: Conecta-se à API do Google Sheets para registrar um histórico detalhado de cada XML processado.
* **Organização de Arquivos**: Move os arquivos processados para um diretório de rede, criando uma estrutura de pastas lógica e padronizada: `[Empresa] - [CNPJ]/[Tipo de Documento]/[Ano]/[Mês-Ano]/[Dia]`.
* **Logging Detalhado**: Gera um arquivo de log (`xml_organizer.log`) para rastrear todas as operações, sucessos e erros.
* **Compatibilidade**: O script possui configurações para rodar tanto em ambiente Windows quanto em WSL (Subsistema do Windows para Linux).

## ⚙️ Pré-requisitos

1.  **Python 3.6+**
2.  **Conta Google** e uma planilha no Google Sheets.
3.  **Acesso de Rede**: Acesso ao diretório de rede onde os arquivos serão armazenados. Para execução no WSL, o diretório de rede deve estar mapeado como um drive no Windows.

## 🚀 Instalação e Configuração

### 1. Clone ou Baixe o Projeto

Faça o download dos arquivos do projeto (`xml_organizer.py`, `requirements.txt`, etc.) para uma pasta em sua máquina.

### 2. Instale as Dependências

Abra um terminal ou prompt de comando na pasta do projeto e instale as bibliotecas Python necessárias:

```bash
pip install -r requirements.txt
```

### 3. Configure a API do Google Sheets

Para que o script possa escrever na sua planilha, você precisa autorizá-lo:

1.  Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2.  Crie um novo projeto ou selecione um existente.
3.  No menu de busca, encontre e ative a **Google Drive API** e a **Google Sheets API**.
4.  Vá para **APIs e Serviços > Credenciais**.
5.  Clique em **Criar Credenciais** e selecione **Conta de Serviço**.
6.  Dê um nome à conta de serviço (ex: `xml-organizer-bot`), conceda a ela o papel de **Editor** e clique em **Concluir**.
7.  Na tela de Credenciais, encontre a conta de serviço que você criou e clique nela.
8.  Vá para a aba **CHAVES**, clique em **ADICIONAR CHAVE** > **Criar nova chave**.
9.  Selecione o formato **JSON** e clique em **CRIAR**. Um arquivo `.json` será baixado.
10. **Renomeie o arquivo baixado para `credentials.json`** e coloque-o na mesma pasta do seu script `xml_organizer.py`.
11. Abra o arquivo `credentials.json`, encontre e copie o valor da chave `"client_email"`.
12. Abra sua planilha do Google Sheets (ex: "HIST. XML BOTS") e compartilhe-a com o email que você copiou, dando a ele permissão de **Editor**.

### 4. Configure os Caminhos no Script

Abra o arquivo `xml_organizer.py` e ajuste as variáveis na seção de **CONFIGURAÇÕES** para corresponder ao seu ambiente:

```python
# --- CONFIGURAÇÕES ---
# Para Windows:
SOURCE_DIRECTORY = Path(r"C:\Automations")
DESTINATION_NETWORK_DIRECTORY = Path(r"R:\XML_ASINCRONIZAR\ZZZ_XML_BOT")

# Para WSL:
SOURCE_DIRECTORY = Path("/mnt/c/Automations")
DESTINATION_NETWORK_DIRECTORY = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")

GOOGLE_SHEET_NAME = "HIST. XML BOTS"
CREDENTIALS_FILE = "credentials.json"
```

## ▶️ Como Executar

Com tudo configurado, abra um terminal na pasta do projeto e execute o script:

```bash
python xml_organizer.py
```

O script começará a processar os arquivos. Você poderá acompanhar o progresso no terminal e no arquivo `xml_organizer.log` que será criado.