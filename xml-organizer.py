import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import logging
import sqlite3
import re

# Para WSL:
SOURCE_DIRECTORY = Path("/mnt/c/Automations")
DESTINATION_NETWORK_DIRECTORY = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")
DATABASE_FILE = "xml_organizer.db"

# Para Windows:
# SOURCE_DIRECTORY = Path(r"C:\Automations")
# DESTINATION_NETWORK_DIRECTORY = Path(r"R:\XML_ASINCRONIZAR\ZZZ_XML_BOT")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("xml_organizer.log"),
        logging.StreamHandler()
    ]
)

def setup_database():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS EMPRESAS (
            ID_EMPRESA INTEGER PRIMARY KEY AUTOINCREMENT,
            CNPJ_EMPRESA TEXT NOT NULL UNIQUE,
            NOME_ORIGINAL_EMPRESA TEXT NOT NULL,
            NOME_PADRONIZADO_EMPRESA TEXT NOT NULL
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS NOTAS_FISCAIS (
            ID_NF INTEGER PRIMARY KEY AUTOINCREMENT,
            CHAVE_ACESSO_NF TEXT NOT NULL UNIQUE,
            ID_EMPRESA INTEGER,
            DATA_LEITURA_NF TEXT NOT NULL,
            HORA_LEITURA_NF TEXT NOT NULL,
            DATA_EMISSAO_NF TEXT NOT NULL,
            TIPO_DOCUMENTO_NF TEXT NOT NULL,
            CAMINHO_ARQUIVO_NF TEXT,
            FOREIGN KEY (ID_EMPRESA) REFERENCES EMPRESAS (ID_EMPRESA)
        )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("Banco de dados verificado/criado com sucesso.")
    except Exception as e:
        logging.critical(f"Falha ao criar ou conectar ao banco de dados: {e}")
        raise

def standardize_company_name(name: str) -> str:
    name = re.sub(r'[.\-/]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

def get_or_create_company(cnpj: str, nome_original: str) -> int:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT ID_EMPRESA FROM EMPRESAS WHERE CNPJ_EMPRESA = ?", (cnpj,))
    result = cursor.fetchone()
    
    if result:
        company_id = result[0]
    else:
        nome_padronizado = standardize_company_name(nome_original)
        cursor.execute(
            "INSERT INTO EMPRESAS (CNPJ_EMPRESA, NOME_ORIGINAL_EMPRESA, NOME_PADRONIZADO_EMPRESA) VALUES (?, ?, ?)",
            (cnpj, nome_original, nome_padronizado)
        )
        conn.commit()
        company_id = cursor.lastrowid
        logging.info(f"Nova empresa registrada: '{nome_padronizado}' (CNPJ: {cnpj})")
        
    conn.close()
    return company_id

def get_xml_info(xml_file: Path) -> dict:
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        infNFe = root.find('.//nfe:infNFe', ns)
        if infNFe is None:
            logging.warning(f"Arquivo '{xml_file.name}' não é uma NF-e/NFC-e válida (tag 'infNFe' não encontrada).")
            return None

        chave_acesso = infNFe.get('Id', '')[3:]

        ide = infNFe.find('nfe:ide', ns)
        emit = infNFe.find('nfe:emit', ns)

        if ide is None or emit is None:
            logging.warning(f"Arquivo '{xml_file.name}' não possui as tags 'ide' ou 'emit'.")
            return None

        dhEmi_element = ide.find('nfe:dhEmi', ns)
        data_emissao_str = dhEmi_element.text.split('T')[0] if dhEmi_element is not None else ''
        data_emissao_dt = datetime.strptime(data_emissao_str, '%Y-%m-%d')

        mod_element = ide.find('nfe:mod', ns)
        modelo = mod_element.text if mod_element is not None else ''
        if modelo == '55':
            tipo_documento = 'NFE'
        elif modelo == '65':
            tipo_documento = 'NFCE'
        else:
            tipo_documento = f"Modelo_{modelo}"

        cnpj = emit.find('nfe:CNPJ', ns).text
        nome_empresa_original = emit.find('nfe:xNome', ns).text
        nome_empresa_padronizado = standardize_company_name(nome_empresa_original)

        return {
            "data_leitura": datetime.now().strftime('%Y-%m-%d'),
            "hora_leitura": datetime.now().strftime('%H:%M:%S'),
            "data_emissao": data_emissao_dt.strftime('%Y-%m-%d'),
            "chave_acesso": chave_acesso,
            "empresa_original": nome_empresa_original,
            "empresa_padronizada": nome_empresa_padronizado,
            "cnpj": cnpj,
            "tipo_documento": tipo_documento,
            "ano_emissao": data_emissao_dt.strftime('%Y'),
            "mes_ano_emissao": data_emissao_dt.strftime('%m-%Y'),
            "dia_emissao": data_emissao_dt.strftime('%d')
        }

    except ET.ParseError:
        logging.error(f"Erro de parsing no XML '{xml_file.name}'. O arquivo pode estar corrompido.")
        return None
    except Exception as e:
        logging.error(f"Erro inesperado ao processar o arquivo '{xml_file.name}': {e}")
        return None


def register_invoice_in_db(data: dict, file_path: str) -> bool:
    try:
        company_id = get_or_create_company(data["cnpj"], data["empresa_original"])
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT ID_NF FROM NOTAS_FISCAIS WHERE CHAVE_ACESSO_NF = ?", (data["chave_acesso"],))
        if cursor.fetchone():
            logging.warning(f"Nota fiscal com chave de acesso {data['chave_acesso']} já registrada no banco de dados.")
            conn.close()
            return False

        cursor.execute(
            '''
            INSERT INTO NOTAS_FISCAIS (CHAVE_ACESSO_NF, ID_EMPRESA, DATA_LEITURA_NF, HORA_LEITURA_NF, DATA_EMISSAO_NF, TIPO_DOCUMENTO_NF, CAMINHO_ARQUIVO_NF)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data["chave_acesso"],
                company_id,
                data["data_leitura"],
                data["hora_leitura"],
                data["data_emissao"],
                data["tipo_documento"],
                file_path
            )
        )
        
        conn.commit()
        conn.close()
        logging.info(f"Dados da nota {data['chave_acesso']} registrados no banco de dados.")
        return True

    except Exception as e:
        logging.error(f"Falha ao registrar a nota no banco de dados: {e}")
        return False


def move_file_to_destination(xml_file: Path, info: dict):
    try:
        destination_path = (
            DESTINATION_NETWORK_DIRECTORY /
            f"{info['empresa_padronizada']} - {info['cnpj']}" /
            info['tipo_documento'] /
            info['ano_emissao'] /
            info['mes_ano_emissao'] /
            info['dia_emissao']
        )
        
        destination_path.mkdir(parents=True, exist_ok=True)
        
        destination_file_path = destination_path / xml_file.name
        shutil.move(str(xml_file), str(destination_file_path))

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE NOTAS_FISCAIS SET CAMINHO_ARQUIVO_NF = ? WHERE CHAVE_ACESSO_NF = ?", (str(destination_file_path), info['chave_acesso']))
        conn.commit()
        conn.close()

        logging.info(f"Arquivo '{xml_file.name}' movido para '{destination_path}'.")
        return True

    except Exception as e:
        logging.error(f"Falha ao mover o arquivo '{xml_file.name}': {e}")
        return False

def main():
    
    logging.info("--- INICIANDO SCRIPT DE ORGANIZAÇÃO DE XML ---")
    
    setup_database()

    if not SOURCE_DIRECTORY.exists():
        logging.critical(f"O diretório de origem '{SOURCE_DIRECTORY}' não foi encontrado. Abortando.")
        return

    xml_files = list(SOURCE_DIRECTORY.rglob("*.xml"))
    
    if not xml_files:
        logging.info("Nenhum arquivo .xml encontrado no diretório de origem.")
        return

    logging.info(f"Encontrados {len(xml_files)} arquivos .xml para processar.")
    
    processed_count = 0
    error_count = 0

    for xml_file in xml_files:
        logging.info(f"Processando arquivo: {xml_file}...")
        
        info = get_xml_info(xml_file)
        if not info:
            error_count += 1
            continue
            
        if not register_invoice_in_db(info, str(xml_file)):
            logging.info(f"Arquivo '{xml_file.name}' já processado anteriormente. Pulando.")
            continue
            
        if not move_file_to_destination(xml_file, info):
            error_count += 1
            logging.error(f"O arquivo '{xml_file.name}' foi registrado no banco, mas FALHOU ao ser movido.")
            continue
            
        processed_count += 1

    logging.info("--- SCRIPT FINALIZADO ---")
    logging.info(f"Resumo: {processed_count} arquivos novos processados com sucesso, {error_count} arquivos com erro.")


if __name__ == "__main__":
    main()