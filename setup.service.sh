# Script para configurar o XML Organizer como serviço systemd no WSL

echo "=================================="
echo "XML Organizer - Configuração 24/7"
echo "=================================="

echo "→ Criando diretório de dados..."
mkdir -p /mnt/c/xml_organizer_data
chmod 755 /mnt/c/xml_organizer_data

PYTHON_PATH=$(which python3)
SCRIPT_DIR=$(pwd)
SCRIPT_PATH="$SCRIPT_DIR/xml_organizer.py"

echo "→ Python encontrado em: $PYTHON_PATH"
echo "→ Script em: $SCRIPT_PATH"

echo "→ Criando serviço systemd..."
sudo tee /etc/systemd/system/xml-organizer.service > /dev/null <<EOF
[Unit]
Description=XML Organizer - Processamento Automatico de Notas Fiscais
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_PATH $SCRIPT_PATH
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "→ Recarregando systemd..."
sudo systemctl daemon-reload

echo "→ Habilitando serviço..."
sudo systemctl enable xml-organizer.service

echo "→ Iniciando serviço..."
sudo systemctl start xml-organizer.service

echo ""
echo "✓ Configuração concluída!"
echo ""
echo "Comandos úteis:"
echo "  - Ver status:      sudo systemctl status xml-organizer"
echo "  - Ver logs:        sudo journalctl -u xml-organizer -f"
echo "  - Parar serviço:   sudo systemctl stop xml-organizer"
echo "  - Reiniciar:       sudo systemctl restart xml-organizer"
echo "  - Desabilitar:     sudo systemctl disable xml-organizer"
echo ""
echo "Verificando status atual..."
sudo systemctl status xml-organizer --no-pager