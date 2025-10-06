# xml_organizer.py
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import time
import sqlite3
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SOURCE_DIR = os.getenv('SOURCE_DIR', r"/data/source")
DEST_DIR = os.getenv('DEST_DIR', r"/data/destination")
DB_PATH = os.getenv('DB_PATH', '/data/db/history.db')
SLEEP_INTERVAL_SECONDS = int(os.getenv('SLEEP_INTERVAL_SECONDS', 300))

GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'HISTORICO XML A SINCRONIZAR')
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS xml_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social TEXT NOT NULL,
            cnpj TEXT NOT NULL,
            data_emissao_xml DATE,
            tipo_documento TEXT,
            nome_arquivo TEXT,
            caminho_destino TEXT,
            data_movimentacao DATETIME NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def log_to_db(data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO xml_history (
            razao_social, cnpj, data_emissao_xml, tipo_documento, 
            nome_arquivo, caminho_destino, data_movimentacao, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get("razao_social"), data.get("cnpj"), data.get("data_emissao"), 
        data.get("doc_type"), data.get("filename"), data.get("dest_path"),
        datetime.now(), data.get("status")
    ))
    conn.commit()
    conn.close()

def find_xml_files(directory):
    xml_files = []
    print(f"Iniciando varredura em: {directory}")
    if not os.path.exists(directory):
        print(f"ERRO CRÍTICO: O diretório de origem '{directory}' não foi encontrado.")
        return []
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.xml'):
                xml_files.append(os.path.join(root, file))
    return xml_files

def parse_xml_data(xml_path):
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

        infNFe = root.find('.//nfe:infNFe', ns)
        if infNFe is None:
            infNFe = root.find('.//infNFe')
            if infNFe is None: return None, "Tag 'infNFe' não encontrada"
            ns = {}

        emit_xnome_element = infNFe.find('nfe:emit/nfe:xNome', ns) if ns else infNFe.find('emit/xNome')
        razao_social = emit_xnome_element.text if emit_xnome_element is not None else "RAZAO_SOCIAL_NAO_ENCONTRADA"

        emit_cnpj_element = infNFe.find('nfe:emit/nfe:CNPJ', ns) if ns else infNFe.find('emit/CNPJ')
        cnpj = emit_cnpj_element.text if emit_cnpj_element is not None else "CNPJ_NAO_ENCONTRADO"

        ide_dhemi_element = infNFe.find('nfe:ide/nfe:dhEmi', ns) if ns else infNFe.find('ide/dhEmi')
        if ide_dhemi_element is None:
            return None, "Data de emissão (dhEmi) não encontrada"
        
        data_emissao_str = ide_dhemi_element.text.split('T')[0]
        data_emissao = datetime.strptime(data_emissao_str, '%Y-%m-%d').date()

        ide_mod_element = infNFe.find('nfe:ide/nfe:mod', ns) if ns else infNFe.find('ide/mod')
        doc_type = "TIPO_DESCONHECIDO"
        if ide_mod_element is not None:
            if ide_mod_element.text == '55': doc_type = "NFe"
            elif ide_mod_element.text == '65': doc_type = "NFCe"
            else: doc_type = f"MOD_{ide_mod_element.text}"

        return {
            "razao_social": razao_social,
            "cnpj": cnpj,
            "data_emissao": data_emissao_str,
            "doc_type": doc_type,
        }, None

    except ET.ParseError:
        return None, "XML mal formatado"
    except Exception as e:
        return None, f"Erro inesperado no parse: {e}"

def update_google_sheet():
    try:
        print("Atualizando planilha do Google Sheets...")
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM xml_history ORDER BY data_movimentacao DESC", conn)
        conn.close()

        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("-> Planilha atualizada com sucesso!")
    except FileNotFoundError:
        print(f"ERRO: Arquivo de credenciais '{GOOGLE_CREDENTIALS_FILE}' não encontrado. A atualização da planilha foi ignorada.")
    except Exception as e:
        print(f"ERRO ao atualizar a planilha: {e}")

def process_files():
    xml_files = find_xml_files(SOURCE_DIR)
    total_files = len(xml_files)

    if total_files == 0:
        print("Nenhum arquivo XML encontrado para processar.")
        return

    print(f"Encontrados {total_files} arquivos .xml para processar.")
    
    for i, xml_path in enumerate(xml_files):
        filename = os.path.basename(xml_path)
        print(f"\n[{i+1}/{total_files}] Processando: {filename}")
        
        data, error_msg = parse_xml_data(xml_path)

        if data:
            try:
                company_folder_name = sanitize_filename(f"{data['razao_social']} - {data['cnpj']}")
                
                data_emissao_dt = datetime.strptime(data['data_emissao'], '%Y-%m-%d')
                ano = data_emissao_dt.strftime('%Y')
                mes_ano = data_emissao_dt.strftime('%m-%Y')
                data_str = data_emissao_dt.strftime('%d-%m-%Y')

                final_path = os.path.join(DEST_DIR, company_folder_name, data['doc_type'], ano, mes_ano, data_str)
                os.makedirs(final_path, exist_ok=True)
                
                dest_file_path = os.path.join(final_path, filename)
                shutil.move(xml_path, dest_file_path)
                
                print(f"-> Sucesso! Movido para: {dest_file_path}")
                log_to_db({**data, "filename": filename, "dest_path": dest_file_path, "status": "SUCCESS"})

            except Exception as e:
                print(f"-> ERRO ao mover o arquivo: {e}")
                log_to_db({"razao_social": "ERRO", "cnpj": "ERRO", "filename": filename, "dest_path": "", "status": f"ERROR_MOVE: {e}"})
        else:
            print(f"-> Falha ao ler os dados do XML: {error_msg}. O arquivo será ignorado.")
            log_to_db({"razao_social": "ERRO", "cnpj": "ERRO", "filename": filename, "dest_path": "", "status": f"ERROR_PARSE: {error_msg}"})

if __name__ == "__main__":
    print("--- Iniciando Organizador de XMLs ---")
    init_db()
    
    while True:
        print(f"\n--- {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---")
        process_files()
        update_google_sheet()
        print(f"--- Ciclo concluído. Aguardando {SLEEP_INTERVAL_SECONDS} segundos para a próxima verificação. ---")
        time.sleep(SLEEP_INTERVAL_SECONDS)