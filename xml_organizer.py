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
processed_keys = set()

def setup_database():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS nota_fiscal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_acesso TEXT NOT NULL UNIQUE,
            hash_arquivo TEXT NOT NULL UNIQUE,
            empresa_id INTEGER NOT NULL,
            data_processamento TEXT NOT NULL,
            data_emissao TEXT NOT NULL,
            tipo_documento TEXT NOT NULL,
            caminho_arquivo TEXT NOT NULL,
            status TEXT DEFAULT 'PROCESSADO',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresa (id)
        )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chave_acesso ON nota_fiscal(chave_acesso)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash_arquivo ON nota_fiscal(hash_arquivo)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_empresa_cnpj ON empresa(cnpj)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_empresa_id ON nota_fiscal(empresa_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_data_emissao ON nota_fiscal(data_emissao)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tipo_documento ON nota_fiscal(tipo_documento)')
        
        conn.commit()
        conn.close()
        logging.info("✓ Banco de dados inicializado")
    except Exception as e:
        logging.critical(f"✗ Falha ao inicializar banco: {e}")
        raise

def migrate_old_database():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(empresa)")
        columns = [row[1] for row in cursor.fetchall()]
        
        has_old_columns = 'nome_original' in columns or 'nome_padronizado' in columns
        
        if has_old_columns:
            logging.info("→ Detectadas colunas antigas, consolidando...")
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS empresa_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            if 'nome_padronizado' in columns:
                cursor.execute('''
                INSERT OR IGNORE INTO empresa_new (id, cnpj, nome, created_at)
                SELECT id, cnpj, nome_padronizado, created_at FROM empresa
                ''')
            elif 'nome_original' in columns:
                cursor.execute('''
                INSERT OR IGNORE INTO empresa_new (id, cnpj, nome, created_at)
                SELECT id, cnpj, nome_original, created_at FROM empresa
                ''')
            
            cursor.execute('DROP TABLE empresa')
            cursor.execute('ALTER TABLE empresa_new RENAME TO empresa')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_empresa_cnpj ON empresa(cnpj)')
            
            conn.commit()
            logging.info("✓ Migração concluída - coluna 'nome' consolidada")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='EMPRESAS'")
        has_old_tables = cursor.fetchone() is not None
        
        if has_old_tables:
            logging.info("→ Migrando de tabelas antigas (EMPRESAS/NOTAS_FISCAIS)...")
            
            cursor.execute('''
                INSERT OR IGNORE INTO empresa (id, cnpj, nome, created_at)
                SELECT ID_EMPRESA, CNPJ_EMPRESA, 
                       COALESCE(NOME_PADRONIZADO_EMPRESA, NOME_ORIGINAL_EMPRESA),
                       CREATED_AT
                FROM EMPRESAS
            ''')
            
            cursor.execute('''
                INSERT OR IGNORE INTO nota_fiscal (id, chave_acesso, hash_arquivo, empresa_id, 
                    data_processamento, data_emissao, tipo_documento, caminho_arquivo, status, created_at)
                SELECT ID_NF, CHAVE_ACESSO_NF, HASH_ARQUIVO, ID_EMPRESA,
                    DATA_LEITURA_NF, DATA_EMISSAO_NF, TIPO_DOCUMENTO_NF, 
                    CAMINHO_ARQUIVO_NF, STATUS, CREATED_AT
                FROM NOTAS_FISCAIS
            ''')
            
            migrated = cursor.rowcount
            conn.commit()
            
            cursor.execute('ALTER TABLE EMPRESAS RENAME TO EMPRESAS_OLD_BACKUP')
            cursor.execute('ALTER TABLE NOTAS_FISCAIS RENAME TO NOTAS_FISCAIS_OLD_BACKUP')
            conn.commit()
            
            logging.info(f"✓ {migrated} registros migrados (backup: *_OLD_BACKUP)")
        
        conn.close()
    except Exception as e:
        logging.warning(f"Aviso na migração: {e}")

def load_caches():
    global company_cache, processed_hashes, processed_keys
    
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT cnpj, id, nome FROM empresa")
        for cnpj, empresa_id, nome in cursor.fetchall():
            company_cache[cnpj] = {"id": empresa_id, "nome": nome}
        
        cursor.execute("SELECT hash_arquivo, chave_acesso FROM nota_fiscal")
        for hash_arq, chave in cursor.fetchall():
            processed_hashes.add(hash_arq)
            processed_keys.add(chave)
        
        conn.close()
        logging.info(f"✓ Cache: {len(company_cache)} empresas, {len(processed_hashes)} registros")
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

def get_or_create_company(cnpj: str, nome_xml: str) -> int:
    nome_padronizado = standardize_company_name(nome_xml)
    
    with cache_lock:
        if cnpj in company_cache:
            cached = company_cache[cnpj]
            
            if cached["nome"] != nome_padronizado:
                logging.info(f"  ↻ Nome atualizado para CNPJ {cnpj}")
                logging.info(f"    Antigo: {cached['nome']}")
                logging.info(f"    Novo: {nome_padronizado}")
                
                with db_lock:
                    conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE empresa SET nome = ?, updated_at = CURRENT_TIMESTAMP WHERE cnpj = ?",
                        (nome_padronizado, cnpj)
                    )
                    conn.commit()
                    conn.close()
                
                company_cache[cnpj]["nome"] = nome_padronizado
            
            return cached["id"]
        
        with db_lock:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, nome FROM empresa WHERE cnpj = ?", (cnpj,))
            result = cursor.fetchone()
            
            if result:
                company_id, nome_atual = result
                
                if nome_atual != nome_padronizado:
                    logging.info(f"  ↻ Nome atualizado para CNPJ {cnpj}")
                    logging.info(f"    Antigo: {nome_atual}")
                    logging.info(f"    Novo: {nome_padronizado}")
                    
                    cursor.execute(
                        "UPDATE empresa SET nome = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (nome_padronizado, company_id)
                    )
                    conn.commit()
            else:
                cursor.execute(
                    "INSERT INTO empresa (cnpj, nome) VALUES (?, ?)",
                    (cnpj, nome_padronizado)
                )
                conn.commit()
                company_id = cursor.lastrowid
                logging.info(f"  + Nova empresa: {nome_padronizado} ({cnpj})")
            
            conn.close()
            
            company_cache[cnpj] = {"id": company_id, "nome": nome_padronizado}
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
            "data_processamento": datetime.now().strftime('%Y-%m-%d'),
            "data_emissao": data_emissao_dt.strftime('%Y-%m-%d'),
            "chave_acesso": chave_acesso,
            "empresa_nome_xml": nome_empresa,  # Nome original do XML
            "empresa_nome_padronizado": standardize_company_name(nome_empresa),
            "cnpj": cnpj,
            "tipo_documento": tipo_documento,
            "ano_emissao": data_emissao_dt.strftime('%Y'),
            "mes_ano_emissao": data_emissao_dt.strftime('%m-%Y'),
            "dia_emissao": data_emissao_dt.strftime('%d')
        }

    except Exception:
        return None

def insert_nota_fiscal(data: tuple) -> bool:
    try:
        with db_lock:
            conn = sqlite3.connect(DATABASE_FILE, timeout=20)
            cursor = conn.cursor()
            
            cursor.execute(
                '''INSERT INTO nota_fiscal 
                (chave_acesso, hash_arquivo, empresa_id, data_processamento, 
                 data_emissao, tipo_documento, caminho_arquivo)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                data
            )
            
            conn.commit()
            inserted = cursor.rowcount > 0
            conn.close()
            
            return inserted
            
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        logging.error(f"Erro ao inserir nota: {e}")
        return False

def move_file_to_destination(xml_file: Path, info: dict) -> bool:
    try:
        destination_path = (
            DESTINATION_NETWORK_DIRECTORY /
            f"{info['empresa_nome_padronizado']} - {info['cnpj']}" /
            info['tipo_documento'] /
            info['ano_emissao'] /
            info['mes_ano_emissao'] /
            info['dia_emissao']
        )
        
        destination_path.mkdir(parents=True, exist_ok=True)
        destination_file = destination_path / xml_file.name
        
        if destination_file.exists():
            xml_file.unlink()
            return True
        
        shutil.move(str(xml_file), str(destination_file))
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
        if destination.exists():
            destination.unlink()
        shutil.move(str(xml_file), str(destination))
        
    except Exception as e:
        logging.error(f"Erro ao mover para pasta de erros {xml_file.name}: {e}")

def process_single_file(xml_file: Path) -> dict:
    result = {"file": xml_file.name, "status": "erro", "reason": ""}
    
    try:
        file_hash = calculate_file_hash(xml_file)
        if not file_hash:
            result["reason"] = "erro_leitura"
            move_to_error_folder(xml_file, "erro_leitura")
            return result
        
        if file_hash in processed_hashes:
            result["status"] = "duplicado_hash"
            xml_file.unlink()
            return result
        
        info = get_xml_info(xml_file)
        if not info:
            result["reason"] = "xml_invalido"
            move_to_error_folder(xml_file, "xml_invalido")
            return result

        if info["chave_acesso"] in processed_keys:
            result["status"] = "duplicado_chave"
            xml_file.unlink()
            return result
        
        company_id = get_or_create_company(info["cnpj"], info["empresa_nome_xml"])
        
        nome_empresa_final = company_cache[info["cnpj"]]["nome"]
        info["empresa_nome_padronizado"] = nome_empresa_final
        
        destination_path = (
            DESTINATION_NETWORK_DIRECTORY /
            f"{nome_empresa_final} - {info['cnpj']}" /
            info['tipo_documento'] /
            info['ano_emissao'] /
            info['mes_ano_emissao'] /
            info['dia_emissao'] /
            xml_file.name
        )
        
        nota_data = (
            info["chave_acesso"],
            file_hash,
            company_id,
            info["data_processamento"],
            info["data_emissao"],
            info["tipo_documento"],
            str(destination_path)
        )
        
        if not insert_nota_fiscal(nota_data):
            result["status"] = "duplicado_banco"
            xml_file.unlink()
            return result
        
        processed_hashes.add(file_hash)
        processed_keys.add(info["chave_acesso"])
        
        if move_file_to_destination(xml_file, info):
            result["status"] = "sucesso"
            result["info"] = info
        else:
            result["status"] = "erro"
            result["reason"] = "erro_movimentacao"
            with db_lock:
                conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM nota_fiscal WHERE chave_acesso = ?", 
                             (info["chave_acesso"],))
                conn.commit()
                conn.close()
            processed_hashes.discard(file_hash)
            processed_keys.discard(info["chave_acesso"])
            move_to_error_folder(xml_file, "erro_movimentacao")
        
        return result
    
    except Exception as e:
        result["reason"] = f"exception: {str(e)}"
        move_to_error_folder(xml_file, "erro_geral")
        return result

def process_batch(xml_files: list) -> dict:
    stats = {
        "sucesso": 0, 
        "duplicado": 0,
        "erro": 0
    }
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, f): f for f in xml_files}
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=30)
                
                if result["status"] == "sucesso":
                    stats["sucesso"] += 1
                elif "duplicado" in result["status"]:
                    stats["duplicado"] += 1
                else:
                    stats["erro"] += 1
                    
            except Exception as e:
                stats["erro"] += 1
                logging.error(f"Erro no future: {e}")
    
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

def verify_database_integrity():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM nota_fiscal")
        total_notas = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM empresa")
        total_empresas = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT tipo_documento, COUNT(*) 
            FROM nota_fiscal 
            GROUP BY tipo_documento
        """)
        tipos = cursor.fetchall()
        
        conn.close()
        
        logging.info(f"  📊 Banco: {total_notas} notas de {total_empresas} empresas")
        if tipos:
            tipo_str = ", ".join([f"{t[0]}: {t[1]}" for t in tipos])
            logging.info(f"     Tipos: {tipo_str}")
        
    except Exception as e:
        logging.warning(f"Aviso ao verificar integridade: {e}")

def main():
    logging.info("="*60)
    logging.info("XML ORGANIZER v2.1 - IDENTIFICAÇÃO POR CNPJ")
    logging.info(f"Monitorando: {SOURCE_DIRECTORY}")
    logging.info(f"Destino: {DESTINATION_NETWORK_DIRECTORY}")
    logging.info(f"Banco de dados: {DATABASE_FILE}")
    logging.info(f"Workers: {MAX_WORKERS} | Batch: {BATCH_SIZE}")
    logging.info("="*60)
    
    setup_database()
    migrate_old_database()
    load_caches()
    verify_database_integrity()
    
    logging.info("\n🔍 Modo de operação:")
    logging.info("  • Empresas identificadas APENAS por CNPJ")
    logging.info("  • Nome atualizado automaticamente se mudar no XML")
    logging.info("  • Duplicatas detectadas por: hash + chave + banco\n")
    
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