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

MAX_WORKERS = 8
SCAN_INTERVAL = 30
BATCH_SIZE = 200
BATCH_INSERT_SIZE = 50

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

company_cache = {}
cache_lock = Lock()

processed_hashes = set()

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

def load_caches():
    global company_cache, processed_hashes
    
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT CNPJ_EMPRESA, ID_EMPRESA, NOME_PADRONIZADO_EMPRESA FROM EMPRESAS")
        for cnpj, id_empresa, nome in cursor.fetchall():
            company_cache[cnpj] = {"id": id_empresa, "nome": nome}
        
        cursor.execute("SELECT HASH_ARQUIVO FROM NOTAS_FISCAIS")
        processed_hashes = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        logging.info(f"✓ Cache carregado: {len(company_cache)} empresas, {len(processed_hashes)} hashes")
    except Exception as e:
        logging.error(f"Erro ao carregar cache: {e}")

def calculate_file_hash(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return None

def standardize_company_name(name: str) -> str:
    name = re.sub(r'[.\-/\\]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

def get_or_create_company_cached(cnpj: str, nome_original: str) -> int:
    with cache_lock:
        if cnpj in company_cache:
            return company_cache[cnpj]["id"]
        
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
            
            company_cache[cnpj] = {"id": company_id, "nome": standardize_company_name(nome_original)}
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

    except Exception:
        return None

def batch_insert_notas(batch_data: list) -> int:
    if not batch_data:
        return 0
    
    try:
        with db_lock:
            conn = sqlite3.connect(DATABASE_FILE, timeout=20)
            cursor = conn.cursor()
            
            cursor.executemany(
                '''INSERT OR IGNORE INTO NOTAS_FISCAIS 
                (CHAVE_ACESSO_NF, HASH_ARQUIVO, ID_EMPRESA, DATA_LEITURA_NF, DATA_EMISSAO_NF, TIPO_DOCUMENTO_NF, CAMINHO_ARQUIVO_NF)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                batch_data
            )
            
            inserted = cursor.rowcount
            conn.commit()
            conn.close()
            
            return inserted
    except Exception as e:
        logging.error(f"Erro no batch insert: {e}")
        return 0

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
        
        return True

    except Exception:
        return False

def move_to_error_folder(xml_file: Path, reason: str = "erro_processamento"):
    try:
        ERROR_DIRECTORY.mkdir(parents=True, exist_ok=True)
        error_subdir = ERROR_DIRECTORY / reason
        error_subdir.mkdir(exist_ok=True)
        
        destination = error_subdir / xml_file.name
        if destination.exists():
            destination.unlink()
        shutil.move(str(xml_file), str(destination))
        
    except Exception:
        pass

def process_single_file(xml_file: Path) -> dict:
    result = {"file": xml_file.name, "status": "erro", "reason": "", "data": None}
    
    try:
        file_hash = calculate_file_hash(xml_file)
        if not file_hash:
            result["reason"] = "erro_leitura"
            return result
        
        if file_hash in processed_hashes:
            result["status"] = "duplicado"
            xml_file.unlink()
            return result
        
        info = get_xml_info(xml_file)
        if not info:
            result["reason"] = "xml_invalido"
            move_to_error_folder(xml_file, "xml_invalido")
            return result
        
        company_id = get_or_create_company_cached(info["cnpj"], info["empresa_original"])
        
        result["data"] = (
            info["chave_acesso"],
            file_hash,
            company_id,
            info["data_leitura"],
            info["data_emissao"],
            info["tipo_documento"],
            str(xml_file)
        )
        result["info"] = info
        result["hash"] = file_hash
        result["status"] = "preparado"
        
        return result
    
    except Exception:
        result["reason"] = "exception"
        return result

def process_batch(xml_files: list) -> dict:
    stats = {"sucesso": 0, "duplicado": 0, "erro": 0}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, f): f for f in xml_files}
        
        results = []
        for future in as_completed(futures):
            try:
                result = future.result(timeout=20)
                if result["status"] == "duplicado":
                    stats["duplicado"] += 1
                elif result["status"] == "preparado":
                    results.append(result)
                else:
                    stats["erro"] += 1
            except:
                stats["erro"] += 1
    
    if results:
        batch_data = [r["data"] for r in results]
        inserted = batch_insert_notas(batch_data)
        
        for r in results:
            processed_hashes.add(r["hash"])
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            move_futures = []
            for r in results:
                xml_file = Path(r["data"][6])
                if xml_file.exists():
                    future = executor.submit(move_file_to_destination, xml_file, r["info"])
                    move_futures.append((future, xml_file, r["info"]))
            
            for future, xml_file, info in move_futures:
                try:
                    if future.result(timeout=15):
                        stats["sucesso"] += 1
                    else:
                        move_to_error_folder(xml_file, "erro_movimentacao")
                        stats["erro"] += 1
                except:
                    if xml_file.exists():
                        move_to_error_folder(xml_file, "erro_movimentacao")
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
    
    start_time = time.time()
    total_stats = {"sucesso": 0, "duplicado": 0, "erro": 0}
    batch_num = 0
    
    for i in range(0, total, BATCH_SIZE):
        batch = xml_files[i:i+BATCH_SIZE]
        batch_num += 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        
        stats = process_batch(batch)
        
        for key in total_stats:
            total_stats[key] += stats[key]
        
        processed = sum(total_stats.values())
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        
        logging.info(
            f"✓ Lote {batch_num}/{total_batches}: {stats['sucesso']} ok | "
            f"{stats['duplicado']} dup | {stats['erro']} erro | "
            f"{processed}/{total} ({rate:.1f} arq/s)"
        )
        
    elapsed = time.time() - start_time
    if sum(total_stats.values()) > 0:
        logging.info(
            f"✓ CONCLUÍDO: {total_stats['sucesso']} novos | "
            f"{total_stats['duplicado']} duplicados | {total_stats['erro']} erros | "
            f"Tempo: {elapsed:.1f}s | Taxa: {total/elapsed:.1f} arq/s"
        )

def main():
    logging.info("="*60)
    logging.info("XML ORGANIZER v2.0 TURBO - INICIANDO")
    logging.info(f"Monitorando: {SOURCE_DIRECTORY}")
    logging.info(f"Destino: {DESTINATION_NETWORK_DIRECTORY}")
    logging.info(f"Banco de dados: {DATABASE_FILE}")
    logging.info(f"Workers: {MAX_WORKERS} | Batch: {BATCH_SIZE}")
    logging.info("="*60)
    
    setup_database()
    load_caches()
    
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