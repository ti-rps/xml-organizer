import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import logging
import sqlite3
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import hashlib

# ==================== CONFIGURAÇÕES ====================
# Para WSL
SOURCE_DIRECTORY = Path("/mnt/c/Automations")
DESTINATION_NETWORK_DIRECTORY = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")
ERROR_DIRECTORY = DESTINATION_NETWORK_DIRECTORY / "_ERROS"

# Banco de dados no disco C: (acessível de qualquer ambiente)
DATABASE_FILE = "/mnt/c/xml_organizer_data/xml_organizer.db"
LOG_FILE = "/mnt/c/xml_organizer_data/xml_organizer.log"

# Para Windows (descomente se for usar no Windows)
# SOURCE_DIRECTORY = Path(r"C:\Automations")
# DESTINATION_NETWORK_DIRECTORY = Path(r"R:\XML_ASINCRONIZAR\ZZZ_XML_BOT")
# ERROR_DIRECTORY = DESTINATION_NETWORK_DIRECTORY / "_ERROS"
# DATABASE_FILE = r"C:\xml_organizer_data\xml_organizer.db"
# LOG_FILE = r"C:\xml_organizer_data\xml_organizer.log"

# Parâmetros de desempenho
MAX_WORKERS = 4  # Número de threads paralelas
SCAN_INTERVAL = 30  # Intervalo em segundos entre verificações
BATCH_SIZE = 50  # Processa arquivos em lotes

os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

db_lock = Lock()

def setup_database():
    """Cria o banco de dados e tabelas se não existirem"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS EMPRESAS (
            ID_EMPRESA INTEGER PRIMARY KEY AUTOINCREMENT,
            CNPJ_EMPRESA TEXT NOT NULL UNIQUE,
            NOME_ORIGINAL_EMPRESA TEXT NOT NULL,
            NOME_PADRONIZADO_EMPRESA TEXT NOT NULL,
            CREATED_AT TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS NOTAS_FISCAIS (
            ID_NF INTEGER PRIMARY KEY AUTOINCREMENT,
            CHAVE_ACESSO_NF TEXT NOT NULL UNIQUE,
            HASH_ARQUIVO TEXT NOT NULL,
            ID_EMPRESA INTEGER,
            DATA_LEITURA_NF TEXT NOT NULL,
            DATA_EMISSAO_NF TEXT NOT NULL,
            TIPO_DOCUMENTO_NF TEXT NOT NULL,
            CAMINHO_ARQUIVO_NF TEXT,
            STATUS TEXT DEFAULT 'PROCESSADO',
            CREATED_AT TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ID_EMPRESA) REFERENCES EMPRESAS (ID_EMPRESA)
        )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chave_acesso ON NOTAS_FISCAIS(CHAVE_ACESSO_NF)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON NOTAS_FISCAIS(HASH_ARQUIVO)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cnpj ON EMPRESAS(CNPJ_EMPRESA)')
        
        conn.commit()
        conn.close()
        logging.info("✓ Banco de dados inicializado")
    except Exception as e:
        logging.critical(f"✗ Falha ao inicializar banco: {e}")
        raise

def calculate_file_hash(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def standardize_company_name(name: str) -> str:
    name = re.sub(r'[.\-/\\]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

def get_or_create_company(cnpj: str, nome_original: str) -> int:
    with db_lock:
        conn = sqlite3.connect(DATABASE_FILE, timeout=10)
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
            
        conn.close()
        return company_id

def get_xml_info(xml_file: Path) -> dict:
    namespaces = [
        {'nfe': 'http://www.portalfiscal.inf.br/nfe'},
        {},
    ]
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        infNFe = None
        for ns in namespaces:
            infNFe = root.find('.//nfe:infNFe', ns) if ns else root.find('.//infNFe')
            if infNFe is not None:
                break
        
        if infNFe is None:
            for elem in root.iter():
                if elem.tag.endswith('infNFe'):
                    infNFe = elem
                    break
        
        if infNFe is None:
            return None

        chave_acesso = infNFe.get('Id', '').replace('NFe', '').replace('nfe', '')

        ide = None
        emit = None
        for ns in namespaces:
            if ns:
                ide = infNFe.find('nfe:ide', ns)
                emit = infNFe.find('nfe:emit', ns)
            else:
                ide = infNFe.find('ide')
                emit = infNFe.find('emit')
            if ide is not None and emit is not None:
                break

        if ide is None or emit is None:
            return None

        data_emissao_str = None
        for tag_name in ['dhEmi', 'dEmi']:
            for ns in namespaces:
                elem = ide.find(f'nfe:{tag_name}', ns) if ns else ide.find(tag_name)
                if elem is not None:
                    data_emissao_str = elem.text.split('T')[0] if 'T' in elem.text else elem.text
                    break
            if data_emissao_str:
                break
        
        if not data_emissao_str:
            return None
            
        data_emissao_dt = datetime.strptime(data_emissao_str, '%Y-%m-%d')

        modelo = None
        for ns in namespaces:
            mod_elem = ide.find('nfe:mod', ns) if ns else ide.find('mod')
            if mod_elem is not None:
                modelo = mod_elem.text
                break
        
        tipo_documento = 'NFE' if modelo == '55' else 'NFCE' if modelo == '65' else f"MOD{modelo}"

        cnpj = None
        nome_empresa = None
        for ns in namespaces:
            cnpj_elem = emit.find('nfe:CNPJ', ns) if ns else emit.find('CNPJ')
            nome_elem = emit.find('nfe:xNome', ns) if ns else emit.find('xNome')
            if cnpj_elem is not None:
                cnpj = cnpj_elem.text
            if nome_elem is not None:
                nome_empresa = nome_elem.text
            if cnpj and nome_empresa:
                break

        if not cnpj or not nome_empresa:
            return None

        return {
            "data_leitura": datetime.now().strftime('%Y-%m-%d'),
            "data_emissao": data_emissao_dt.strftime('%Y-%m-%d'),
            "chave_acesso": chave_acesso,
            "empresa_original": nome_empresa,
            "empresa_padronizada": standardize_company_name(nome_empresa),
            "cnpj": cnpj,
            "tipo_documento": tipo_documento,
            "ano_emissao": data_emissao_dt.strftime('%Y'),
            "mes_ano_emissao": data_emissao_dt.strftime('%m-%Y'),
            "dia_emissao": data_emissao_dt.strftime('%d')
        }

    except Exception as e:
        logging.debug(f"Erro ao processar {xml_file.name}: {e}")
        return None

def register_invoice_in_db(data: dict, file_path: str, file_hash: str) -> bool:
    try:
        with db_lock:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT ID_NF FROM NOTAS_FISCAIS WHERE CHAVE_ACESSO_NF = ? OR HASH_ARQUIVO = ?", 
                (data["chave_acesso"], file_hash)
            )
            if cursor.fetchone():
                conn.close()
                return False

            company_id = get_or_create_company(data["cnpj"], data["empresa_original"])

            cursor.execute(
                '''INSERT INTO NOTAS_FISCAIS 
                (CHAVE_ACESSO_NF, HASH_ARQUIVO, ID_EMPRESA, DATA_LEITURA_NF, DATA_EMISSAO_NF, TIPO_DOCUMENTO_NF, CAMINHO_ARQUIVO_NF)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (data["chave_acesso"], file_hash, company_id, data["data_leitura"], 
                 data["data_emissao"], data["tipo_documento"], file_path)
            )
            
            conn.commit()
            conn.close()
            return True

    except Exception as e:
        logging.error(f"Erro ao registrar no banco: {e}")
        return False

def move_file_to_destination(xml_file: Path, info: dict) -> bool:
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
        destination_file = destination_path / xml_file.name
        
        shutil.move(str(xml_file), str(destination_file))
        
        with db_lock:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE NOTAS_FISCAIS SET CAMINHO_ARQUIVO_NF = ? WHERE CHAVE_ACESSO_NF = ?", 
                (str(destination_file), info['chave_acesso'])
            )
            conn.commit()
            conn.close()

        return True

    except Exception as e:
        logging.error(f"Erro ao mover {xml_file.name}: {e}")
        return False

def move_to_error_folder(xml_file: Path, reason: str = "erro_processamento"):
    try:
        ERROR_DIRECTORY.mkdir(parents=True, exist_ok=True)
        error_subdir = ERROR_DIRECTORY / reason
        error_subdir.mkdir(exist_ok=True)
        
        destination = error_subdir / xml_file.name
        shutil.move(str(xml_file), str(destination))
        
    except Exception as e:
        logging.error(f"Erro ao mover arquivo para pasta de erros: {e}")

def process_single_file(xml_file: Path) -> dict:
    result = {"file": xml_file.name, "status": "erro", "reason": ""}
    
    try:
        file_hash = calculate_file_hash(xml_file)
        
        info = get_xml_info(xml_file)
        if not info:
            result["reason"] = "xml_invalido"
            move_to_error_folder(xml_file, "xml_invalido")
            return result
        
        if not register_invoice_in_db(info, str(xml_file), file_hash):
            result["status"] = "duplicado"
            xml_file.unlink()
            return result
        
        if move_file_to_destination(xml_file, info):
            result["status"] = "sucesso"
        else:
            result["reason"] = "erro_mover"
            move_to_error_folder(xml_file, "erro_movimentacao")
    
    except Exception as e:
        result["reason"] = f"exception: {str(e)[:50]}"
        move_to_error_folder(xml_file, "erro_geral")
    
    return result

def process_batch(xml_files: list) -> dict:
    stats = {"sucesso": 0, "duplicado": 0, "erro": 0}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, f): f for f in xml_files}
        
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "sucesso":
                stats["sucesso"] += 1
            elif result["status"] == "duplicado":
                stats["duplicado"] += 1
            else:
                stats["erro"] += 1
    
    return stats

def scan_and_process():
    if not SOURCE_DIRECTORY.exists():
        logging.error(f"Diretório de origem não encontrado: {SOURCE_DIRECTORY}")
        return
    
    xml_files = list(SOURCE_DIRECTORY.rglob("*.xml"))
    
    if not xml_files:
        return
    
    total = len(xml_files)
    logging.info(f"→ {total} arquivo(s) encontrado(s)")
    
    for i in range(0, total, BATCH_SIZE):
        batch = xml_files[i:i+BATCH_SIZE]
        stats = process_batch(batch)
        
        if any(stats.values()):
            logging.info(
                f"✓ Lote {i//BATCH_SIZE + 1}: "
                f"{stats['sucesso']} ok | {stats['duplicado']} dup | {stats['erro']} erro"
            )

def main():
    logging.info("="*60)
    logging.info("XML ORGANIZER v2.0 - INICIANDO")
    logging.info(f"Monitorando: {SOURCE_DIRECTORY}")
    logging.info(f"Destino: {DESTINATION_NETWORK_DIRECTORY}")
    logging.info(f"Banco de dados: {DATABASE_FILE}")
    logging.info(f"Intervalo de verificação: {SCAN_INTERVAL}s")
    logging.info("="*60)
    
    setup_database()
    
    cycle = 0
    while True:
        try:
            cycle += 1
            scan_and_process()
            time.sleep(SCAN_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("\n⊗ Finalizando por solicitação do usuário")
            break
        except Exception as e:
            logging.error(f"✗ Erro no ciclo {cycle}: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()