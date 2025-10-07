import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging

SOURCE_DIRECTORY = Path("/mnt/c/Automations")
DESTINATION_NETWORK_DIRECTORY = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")
GOOGLE_SHEET_NAME = "HIST. XML BOTS"
CREDENTIALS_FILE = "credentials.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("xml_organizer.log"),
        logging.StreamHandler()
    ]
)

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
        nome_empresa = emit.find('nfe:xNome', ns).text

        return {
            "data_leitura": datetime.now().strftime('%Y-%m-%d'),
            "hora_leitura": datetime.now().strftime('%H:%M:%S'),
            "data_emissao": data_emissao_dt.strftime('%Y-%m-%d'),
            "chave_acesso": chave_acesso,
            "empresa": nome_empresa,
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


def update_google_sheet(data: dict):
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        
        df_row = pd.DataFrame([{
            "Data Leitura": data["data_leitura"],
            "Hora Leitura": data["hora_leitura"],
            "Data Emissão": data["data_emissao"],
            "Chave Acesso": data["chave_acesso"],
            "Empresa": data["empresa"],
            "CNPJ": data["cnpj"],
            "Tipo Documento": data["tipo_documento"]
        }])

        sheet.append_rows(df_row.values.tolist(), value_input_option='USER_ENTERED')
        logging.info(f"Dados da nota {data['chave_acesso']} registrados na planilha.")
        return True

    except Exception as e:
        logging.error(f"Falha ao atualizar a planilha do Google Sheets: {e}")
        return False


def move_file_to_destination(xml_file: Path, info: dict):
    try:
        destination_path = (
            DESTINATION_NETWORK_DIRECTORY /
            f"{info['empresa']} - {info['cnpj']}" /
            info['tipo_documento'] /
            info['ano_emissao'] /
            info['mes_ano_emissao'] /
            info['dia_emissao']
        )
        
        destination_path.mkdir(parents=True, exist_ok=True)

        shutil.move(str(xml_file), str(destination_path / xml_file.name))
        logging.info(f"Arquivo '{xml_file.name}' movido para '{destination_path}'.")
        return True

    except Exception as e:
        logging.error(f"Falha ao mover o arquivo '{xml_file.name}': {e}")
        return False

def main():
    
    logging.info("--- INICIANDO SCRIPT DE ORGANIZAÇÃO DE XML ---")
    
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
        
        # 1. Extrair informações do XML
        info = get_xml_info(xml_file)
        if not info:
            error_count += 1
            
            continue
            
        # 2. Registrar na planilha
        if not update_google_sheet(info):
            error_count += 1
            logging.warning(f"Não foi possível registrar o arquivo '{xml_file.name}' na planilha. O arquivo NÃO será movido.")
            continue
            
        # 3. Mover o arquivo
        if not move_file_to_destination(xml_file, info):
            error_count += 1
            logging.error(f"O arquivo '{xml_file.name}' foi registrado na planilha, mas FALHOU ao ser movido.")
            continue
            
        processed_count += 1

    logging.info("--- SCRIPT FINALIZADO ---")
    logging.info(f"Resumo: {processed_count} arquivos processados com sucesso, {error_count} arquivos com erro.")


if __name__ == "__main__":
    main()