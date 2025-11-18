#!/bin/bash
# Script de teste rápido

set -e

echo "════════════════════════════════════════════════════════"
echo "🧪 TESTE RÁPIDO - Hyperliquid Market Maker"
echo "════════════════════════════════════════════════════════"
echo ""

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Verificar Python
echo "1️⃣  Verificando Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "   ${GREEN}✅ $PYTHON_VERSION${NC}"
else
    echo -e "   ${RED}❌ Python3 não encontrado${NC}"
    exit 1
fi

# 2. Verificar dependências
echo ""
echo "2️⃣  Verificando dependências..."
if pip3 show pytest &> /dev/null; then
    echo -e "   ${GREEN}✅ Dependências instaladas${NC}"
else
    echo -e "   ${YELLOW}⚠️  Instalando dependências...${NC}"
    pip3 install -r requirements.txt
fi

# 3. Testes unitários
echo ""
echo "3️⃣  Executando testes unitários..."
if pytest tests/unit/ -v --tb=short -q; then
    echo -e "   ${GREEN}✅ Todos os testes passaram${NC}"
else
    echo -e "   ${RED}❌ Alguns testes falharam${NC}"
    exit 1
fi

# 4. Verificar imports
echo ""
echo "4️⃣  Verificando imports..."
if python3 -c "from src.main import TradingSystem; from src.utils.config import load_config" 2>/dev/null; then
    echo -e "   ${GREEN}✅ Imports OK${NC}"
else
    echo -e "   ${RED}❌ Erro nos imports${NC}"
    exit 1
fi

# 5. Validar configuração
echo ""
echo "5️⃣  Validando configuração..."
if python3 scripts/validate_config.py; then
    echo -e "   ${GREEN}✅ Configuração válida${NC}"
else
    echo -e "   ${YELLOW}⚠️  Verifique a configuração${NC}"
fi

# Resumo
echo ""
echo "════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ TESTE RÁPIDO COMPLETO!${NC}"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Próximos passos:"
echo "  1. Configurar .env com suas credenciais"
echo "  2. Testar em testnet: python src/main.py"
echo "  3. Monitorar logs: tail -f logs/trading.log"
echo ""
