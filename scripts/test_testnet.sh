#!/bin/bash
# Script para testar em testnet com monitoramento

set -e

echo "════════════════════════════════════════════════════════"
echo "🧪 TESTE EM TESTNET"
echo "════════════════════════════════════════════════════════"
echo ""

# Verificar se .env existe
if [ ! -f .env ]; then
    echo "❌ Arquivo .env não encontrado!"
    echo ""
    echo "Crie o arquivo .env com:"
    echo "  cp .env.example .env"
    echo "  # Edite .env e adicione sua HYPERLIQUID_PRIVATE_KEY"
    exit 1
fi

# Verificar se testnet está ativado no config
if grep -q "testnet: true" config/config.yaml; then
    echo "✅ Testnet ativado no config"
else
    echo "⚠️  ATENÇÃO: Testnet NÃO está ativado no config!"
    echo ""
    echo "Edite config/config.yaml e configure:"
    echo "  exchange:"
    echo "    testnet: true"
    echo ""
    read -p "Continuar mesmo assim? (s/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

# Criar diretório de logs se não existir
mkdir -p logs

# Limpar logs antigos
> logs/trading.log

echo ""
echo "🚀 Iniciando bot em testnet..."
echo ""
echo "Monitoramento:"
echo "  - Logs: tail -f logs/trading.log"
echo "  - Performance: tail -f logs/trading.log | grep performance_report"
echo "  - Fills: tail -f logs/trading.log | grep fill_received"
echo ""
echo "Para parar: Ctrl+C"
echo ""
echo "════════════════════════════════════════════════════════"
echo ""

# Executar bot
python3 src/main.py
