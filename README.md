# XML Organizer v2.0 🚀

Sistema inteligente e robusto para processamento automático 24/7 de arquivos XML de notas fiscais (NF-e/NFC-e).

## ✨ Novidades da Versão 2.0

### 🎯 Melhorias de Inteligência
- **Leitura flexível de XML**: Reconhece múltiplos formatos e namespaces
- **Detecção de duplicatas por hash**: Evita processar o mesmo arquivo duas vezes
- **Tratamento robusto de erros**: Arquivos problemáticos são movidos para pasta de erros organizada
- **Padronização inteligente**: Nome de empresas normalizados automaticamente

### ⚡ Melhorias de Performance
- **Processamento paralelo**: Usa múltiplas threads (4 workers padrão)
- **Processamento em lotes**: Otimizado para grandes volumes
- **Banco de dados indexado**: Consultas rápidas com índices otimizados
- **Cache eficiente**: Reduz operações repetitivas

### 🛡️ Melhorias de Confiabilidade
- **Operação 24/7**: Loop contínuo com tratamento de exceções
- **Thread-safe**: Operações seguras em ambiente paralelo
- **Banco no disco C:**: Dados persistentes e acessíveis
- **Logs enxutos**: Informações resumidas e objetivas
- **Auto-recuperação**: Continua funcionando mesmo após erros

### 📊 Sistema de Organização
- **Pasta de erros**: Arquivos problemáticos separados por tipo de erro
  - `_ERROS/xml_invalido/` - XMLs que não puderam ser lidos
  - `_ERROS/erro_movimentacao/` - Problemas ao mover arquivo
  - `_ERROS/erro_geral/` - Outros erros
- **Estrutura mantida**: Mesma organização por empresa/tipo/ano/mês/dia

## 📋 Pré-requisitos

- **Python 3.6+**
- **WSL** (recomendado) ou **Windows**
- **Acesso ao drive de rede** onde os XMLs serão armazenados

## 🚀 Instalação Rápida

### 1. Preparar o Ambiente

```bash
# Clone ou baixe os arquivos do projeto
cd /caminho/do/projeto

# Instale as dependências (nenhuma biblioteca externa necessária!)
# O Python padrão já tem tudo que precisamos
```

### 2. Configurar Caminhos

Edite o arquivo `xml_organizer.py` e ajuste as configurações:

```python
# Para WSL (padrão):
SOURCE_DIRECTORY = Path("/mnt/c/Automations")
DESTINATION_NETWORK_DIRECTORY = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")
DATABASE_FILE = "/mnt/c/xml_organizer_data/xml_organizer.db"
LOG_FILE = "/mnt/c/xml_organizer_data/xml_organizer.log"

# Para Windows:
# SOURCE_DIRECTORY = Path(r"C:\Automations")
# DESTINATION_NETWORK_DIRECTORY = Path(r"R:\XML_ASINCRONIZAR\ZZZ_XML_BOT")
# DATABASE_FILE = r"C:\xml_organizer_data\xml_organizer.db"
# LOG_FILE = r"C:\xml_organizer_data\xml_organizer.log"
```

### 3. Configurar como Serviço 24/7 (WSL)

```bash
# Tornar o script executável
chmod +x setup_service.sh

# Executar configuração
./setup_service.sh
```

O script estará rodando automaticamente! 🎉

## 📖 Uso Manual

Se preferir executar manualmente:

```bash
python3 xml_organizer.py
```

Para parar: `Ctrl+C`

## 🔧 Parâmetros de Configuração

Ajuste no início do script conforme necessário:

```python
MAX_WORKERS = 4          # Threads paralelas (4-8 recomendado)
SCAN_INTERVAL = 30       # Segundos entre verificações
BATCH_SIZE = 50          # Arquivos por lote
```

## 📊 Estrutura do Banco de Dados

### Tabela EMPRESAS
- `ID_EMPRESA`: Identificador único
- `CNPJ_EMPRESA`: CNPJ da empresa
- `NOME_ORIGINAL_EMPRESA`: Nome original do XML
- `NOME_PADRONIZADO_EMPRESA`: Nome normalizado
- `CREATED_AT`: Data de cadastro

### Tabela NOTAS_FISCAIS
- `ID_NF`: Identificador único
- `CHAVE_ACESSO_NF`: Chave de acesso da nota
- `HASH_ARQUIVO`: Hash MD5 do arquivo (detecta duplicatas)
- `ID_EMPRESA`: Referência à empresa
- `DATA_LEITURA_NF`: Data de processamento
- `DATA_EMISSAO_NF`: Data de emissão da nota
- `TIPO_DOCUMENTO_NF`: NFE, NFCE, etc.
- `CAMINHO_ARQUIVO_NF`: Localização final do arquivo
- `STATUS`: Status do processamento
- `CREATED_AT`: Timestamp de registro

## 📁 Estrutura de Diretórios

```
C:\xml_organizer_data\           # Dados do sistema
├── xml_organizer.db             # Banco de dados SQLite
└── xml_organizer.log            # Arquivo de log

R:\XML_ASINCRONIZAR\ZZZ_XML_BOT\
├── EMPRESA EXEMPLO - 12345678000190\
│   ├── NFE\
│   │   └── 2024\
│   │       └── 10-2024\
│   │           └── 08\
│   │               └── nota.xml
│   └── NFCE\
└── _ERROS\                      # Arquivos com problema
    ├── xml_invalido\
    ├── erro_movimentacao\
    └── erro_geral\
```

## 🎛️ Comandos do Serviço (WSL)

```bash
# Ver status do serviço
sudo systemctl status xml-organizer

# Ver logs em tempo real
sudo journalctl -u xml-organizer -f

# Parar o serviço
sudo systemctl stop xml-organizer

# Reiniciar o serviço
sudo systemctl restart xml-organizer

# Desabilitar inicialização automática
sudo systemctl disable xml-organizer

# Habilitar novamente
sudo systemctl enable xml-organizer
```

## 📈 Monitoramento

### Logs Enxutos
Os logs agora mostram apenas informações essenciais:

```
2024-10-08 14:30:15 [INFO] ✓ Banco de dados inicializado
2024-10-08 14:30:20 [INFO] → 15 arquivo(s) encontrado(s)
2024-10-08 14:30:25 [INFO] ✓ Lote 1: 12 ok | 2 dup | 1 erro
```

### Consultas no Banco

```bash
# Acessar o banco de dados
sqlite3 /mnt/c/xml_organizer_data/xml_organizer.db

# Contar notas processadas
SELECT COUNT(*) FROM NOTAS_FISCAIS;

# Ver últimas 10 notas
SELECT * FROM NOTAS_FISCAIS ORDER BY CREATED_AT DESC LIMIT 10;

# Estatísticas por empresa
SELECT 
    e.NOME_PADRONIZADO_EMPRESA,
    COUNT(*) as total_notas,
    n.TIPO_DOCUMENTO_NF
FROM NOTAS_FISCAIS n
JOIN EMPRESAS e ON n.ID_EMPRESA = e.ID_EMPRESA
GROUP BY e.ID_EMPRESA, n.TIPO_DOCUMENTO_NF;
```

## 🐛 Resolução de Problemas

### O serviço não inicia
```bash
# Verificar permissões
ls -l xml_organizer.py

# Ver logs de erro
sudo journalctl -u xml-organizer -n 50
```

### Muitos arquivos com erro
- Verifique a pasta `_ERROS/` para ver o tipo de problema
- XMLs inválidos: podem estar corrompidos
- Erro de movimentação: verificar permissões no drive de rede

### Performance lenta
- Aumente `MAX_WORKERS` (até 8)
- Aumente `BATCH_SIZE` (até 100)
- Verifique velocidade da rede

## 🔒 Segurança

- **Banco de dados local**: Dados armazenados em `C:\xml_organizer_data\`
- **Sem credenciais externas**: Não precisa mais de Google Sheets
- **Thread-safe**: Operações seguras em ambiente paralelo
- **Validação de dados**: Verificação de integridade dos XMLs

## 📊 Diferenças da Versão Anterior

| Recurso | v1.0 | v2.0 |
|---------|------|------|
| Google Sheets | ✓ Necessário | ✗ Removido |
| Processamento | Sequencial | Paralelo (4 threads) |
| Detecção duplicatas | Por chave | Por chave + hash |
| Tratamento erros | Básico | Avançado com categorização |
| Logs | Verbosos | Enxutos e objetivos |
| Operação 24/7 | Manual | Automático via systemd |
| Banco de dados | WSL | Disco C: (persistente) |
| Performance | 1 arquivo/vez | Lotes de 50 |
| Namespace XML | Fixo | Múltiplos padrões |

## 💡 Dicas de Otimização

### Para Alto Volume (>1000 arquivos/dia)
```python
MAX_WORKERS = 8          # Mais threads
SCAN_INTERVAL = 15       # Verificação mais frequente
BATCH_SIZE = 100         # Lotes maiores
```

### Para Baixo Volume (<100 arquivos/dia)
```python
MAX_WORKERS = 2          # Menos recursos
SCAN_INTERVAL = 60       # Verificação menos frequente
BATCH_SIZE = 20          # Lotes menores
```

### Para Rede Lenta
```python
MAX_WORKERS = 2          # Evita sobrecarga
BATCH_SIZE = 10          # Lotes pequenos
```

## 🔄 Migração da v1.0 para v2.0

Se você estava usando a versão anterior:

1. **Backup dos dados** (se tinha Google Sheets, exporte antes)
2. **Substitua o arquivo** `xml_organizer.py`
3. **Remova** `credentials.json` (não é mais necessário)
4. **Execute uma vez** manualmente para criar o novo banco
5. **Configure o serviço** se desejar operação 24/7

O novo banco de dados será criado vazio. Os XMLs já processados serão detectados como duplicatas se ainda estiverem na pasta de origem.

## 🆘 Suporte e Logs

### Arquivo de Log
Localização: `C:\xml_organizer_data\xml_organizer.log`

```bash
# Ver últimas 50 linhas (WSL)
tail -50 /mnt/c/xml_organizer_data/xml_organizer.log

# Acompanhar em tempo real
tail -f /mnt/c/xml_organizer_data/xml_organizer.log
```

### Mensagens Importantes

- `✓` - Operação bem sucedida
- `→` - Informação
- `✗` - Erro
- `⊗` - Finalização

## 📝 Exemplos de Uso

### Consultar Estatísticas

```bash
sqlite3 /mnt/c/xml_organizer_data/xml_organizer.db << EOF
-- Total de notas por tipo
SELECT 
    TIPO_DOCUMENTO_NF, 
    COUNT(*) as total
FROM NOTAS_FISCAIS 
GROUP BY TIPO_DOCUMENTO_NF;

-- Notas processadas hoje
SELECT COUNT(*) 
FROM NOTAS_FISCAIS 
WHERE DATE(DATA_LEITURA_NF) = DATE('now');

-- Top 5 empresas com mais notas
SELECT 
    e.NOME_PADRONIZADO_EMPRESA,
    COUNT(*) as total
FROM NOTAS_FISCAIS n
JOIN EMPRESAS e ON n.ID_EMPRESA = e.ID_EMPRESA
GROUP BY e.ID_EMPRESA
ORDER BY total DESC
LIMIT 5;
EOF
```

### Exportar Dados para CSV

```bash
sqlite3 -header -csv /mnt/c/xml_organizer_data/xml_organizer.db \
"SELECT 
    e.NOME_PADRONIZADO_EMPRESA as Empresa,
    e.CNPJ_EMPRESA as CNPJ,
    n.TIPO_DOCUMENTO_NF as Tipo,
    n.DATA_EMISSAO_NF as Data_Emissao,
    n.CHAVE_ACESSO_NF as Chave
FROM NOTAS_FISCAIS n
JOIN EMPRESAS e ON n.ID_EMPRESA = e.ID_EMPRESA
ORDER BY n.DATA_EMISSAO_NF DESC;" > relatorio.csv
```

### Limpar Dados Antigos (Manutenção)

```bash
# Remover registros com mais de 2 anos (mantenha os arquivos!)
sqlite3 /mnt/c/xml_organizer_data/xml_organizer.db << EOF
DELETE FROM NOTAS_FISCAIS 
WHERE DATE(DATA_EMISSAO_NF) < DATE('now', '-2 years');

-- Limpar empresas sem notas
DELETE FROM EMPRESAS 
WHERE ID_EMPRESA NOT IN (SELECT DISTINCT ID_EMPRESA FROM NOTAS_FISCAIS);

-- Compactar banco
VACUUM;
EOF
```

## 🎯 Casos de Uso

### Escritório Contábil
- Processa XMLs de múltiplos clientes automaticamente
- Organiza por empresa/tipo/período
- Histórico completo no banco de dados
- Operação 24/7 sem intervenção

### Empresa Individual
- Monitora pasta de downloads
- Move XMLs para servidor de arquivos
- Detecta duplicatas automaticamente
- Logs simples para auditoria

### Integração com Outros Sistemas
- Banco SQLite pode ser consultado por outros softwares
- Estrutura padronizada facilita integrações
- Exportação fácil para CSV/Excel

## ⚠️ Avisos Importantes

1. **Backup Regular**: Faça backup da pasta `C:\xml_organizer_data\`
2. **Espaço em Disco**: Monitore o espaço no drive de rede
3. **Permissões**: Certifique-se de ter acesso de escrita no destino
4. **Firewall**: Libere acesso ao drive de rede se necessário
5. **Teste Primeiro**: Execute manualmente antes de configurar como serviço

## 🔧 Personalização Avançada

### Adicionar Notificações por Email

```python
# No final da função scan_and_process(), adicione:
import smtplib
from email.mime.text import MIMEText

def send_summary_email(stats):
    if stats['erro'] > 10:  # Só envia se houver muitos erros
        msg = MIMEText(f"Erros detectados: {stats['erro']}")
        msg['Subject'] = 'XML Organizer - Alerta'
        msg['From'] = 'seu_email@gmail.com'
        msg['To'] = 'destino@empresa.com'
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login('seu_email@gmail.com', 'sua_senha')
            server.send_message(msg)
```

### Webhook para Integrações

```python
# Adicionar após processar arquivo com sucesso:
import requests

def notify_webhook(data):
    requests.post('https://seu-sistema.com/webhook', json={
        'chave': data['chave_acesso'],
        'empresa': data['cnpj'],
        'tipo': data['tipo_documento']
    })
```

## 📚 Recursos Adicionais

- **SQLite Documentation**: https://www.sqlite.org/docs.html
- **Python Threading**: https://docs.python.org/3/library/threading.html
- **Systemd Services**: https://www.freedesktop.org/software/systemd/man/systemd.service.html

## 🤝 Contribuindo

Sugestões de melhorias:
1. Adicionar suporte para CTe (Conhecimento de Transporte Eletrônico)
2. Interface web para visualização de estatísticas
3. Compressão automática de XMLs antigos
4. Integração com sistemas ERP

## 📄 Licença

Este projeto é de código aberto para uso interno.

---

**Versão**: 2.0  
**Última Atualização**: Outubro 2024  
**Autor**: Sistema Automatizado de Gestão Fiscal