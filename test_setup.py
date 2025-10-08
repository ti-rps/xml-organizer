"""
Script de teste para validar configuração do XML Organizer
"""

import os
import sys
import sqlite3
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓{Colors.END} {text}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}")

def print_error(text):
    print(f"{Colors.RED}✗{Colors.END} {text}")

def print_info(text):
    print(f"{Colors.BLUE}→{Colors.END} {text}")

def check_python_version():
    print_info("Verificando versão do Python...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 6:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} ✓")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor} é muito antigo. Necessário 3.6+")
        return False

def check_paths():
    print_info("Verificando caminhos configurados...")
    
    if os.path.exists("/mnt/c"):
        print_success("Ambiente WSL detectado")
        source = Path("/mnt/c/Automations")
        dest = Path("/mnt/r/XML_ASINCRONIZAR/ZZZ_XML_BOT")
        db_path = Path("/mnt/c/xml_organizer_data")
    else:
        print_success("Ambiente Windows detectado")
        source = Path(r"C:\Automations")
        dest = Path(r"R:\XML_ASINCRONIZAR\ZZZ_XML_BOT")
        db_path = Path(r"C:\xml_organizer_data")
    
    checks = []
    
    if source.exists():
        print_success(f"Diretório de origem existe: {source}")
        checks.append(True)
    else:
        print_warning(f"Diretório de origem NÃO existe: {source}")
        print_info("  → Crie o diretório ou ajuste SOURCE_DIRECTORY no script")
        checks.append(False)
    
    if dest.exists():
        print_success(f"Diretório de destino existe: {dest}")
        checks.append(True)
    else:
        print_error(f"Diretório de destino NÃO existe: {dest}")
        print_info("  → Verifique se o drive de rede está mapeado")
        checks.append(False)
    
    if not db_path.exists():
        try:
            db_path.mkdir(parents=True, exist_ok=True)
            print_success(f"Diretório de dados criado: {db_path}")
            checks.append(True)
        except Exception as e:
            print_error(f"Erro ao criar diretório de dados: {e}")
            checks.append(False)
    else:
        print_success(f"Diretório de dados existe: {db_path}")
        checks.append(True)
    
    return all(checks)

def check_database():
    print_info("Verificando banco de dados...")
    
    if os.path.exists("/mnt/c"):
        db_file = "/mnt/c/xml_organizer_data/xml_organizer.db"
    else:
        db_file = r"C:\xml_organizer_data\xml_organizer.db"
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'EMPRESAS' in tables and 'NOTAS_FISCAIS' in tables:
            print_success("Estrutura do banco OK")
            
            cursor.execute("SELECT COUNT(*) FROM EMPRESAS")
            empresas = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM NOTAS_FISCAIS")
            notas = cursor.fetchone()[0]
            
            print_info(f"  → {empresas} empresa(s) cadastrada(s)")
            print_info(f"  → {notas} nota(s) processada(s)")
            
            conn.close()
            return True
        else:
            print_warning("Banco existe mas tabelas não foram criadas")
            print_info("  → Execute o script uma vez para criar as tabelas")
            conn.close()
            return False
            
    except sqlite3.Error as e:
        print_warning(f"Banco não existe ainda (será criado na primeira execução)")
        return True
    except Exception as e:
        print_error(f"Erro ao verificar banco: {e}")
        return False

def check_permissions():
    print_info("Verificando permissões de escrita...")
    
    if os.path.exists("/mnt/c"):
        test_file = Path("/mnt/c/xml_organizer_data/test_write.tmp")
    else:
        test_file = Path(r"C:\xml_organizer_data\test_write.tmp")
    
    try:
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("teste")
        test_file.unlink()
        print_success("Permissões de escrita OK")
        return True
    except Exception as e:
        print_error(f"Sem permissão de escrita: {e}")
        return False

def show_script_status():
    print_info("Verificando arquivo do script...")
    
    script_path = Path("xml_organizer.py")
    if script_path.exists():
        size = script_path.stat().st_size
        print_success(f"Script encontrado ({size} bytes)")
        return True
    else:
        print_error("Arquivo xml_organizer.py não encontrado!")
        return False

def show_next_steps(all_ok):
    print_header("PRÓXIMOS PASSOS")
    
    if all_ok:
        print_success("Configuração validada com sucesso!")
        print("\nPara iniciar o processamento:\n")
        print("  1. Teste manual:")
        print(f"     {Colors.BOLD}python3 xml_organizer.py{Colors.END}\n")
        print("  2. Configure como serviço 24/7:")
        if os.path.exists("/mnt/c"):
            print(f"     {Colors.BOLD}./setup_service.sh{Colors.END}")
        else:
            print(f"     {Colors.BOLD}setup_windows_service.bat{Colors.END}")
            print("     (como Administrador)")
    else:
        print_warning("Alguns problemas foram encontrados.")
        print("\nCorrija os itens marcados com ✗ ou ⚠ e execute novamente.")

def main():
    print_header("XML ORGANIZER - TESTE DE CONFIGURAÇÃO")
    
    checks = []
    
    checks.append(check_python_version())
    checks.append(check_paths())
    checks.append(check_database())
    checks.append(check_permissions())
    checks.append(show_script_status())
    
    all_ok = all(checks)
    show_next_steps(all_ok)
    
    print()
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()