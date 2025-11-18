# Guia de Testes - Hyperliquid Market Maker

## 1. Testes Unitários (Recomendado Primeiro)

### Configuração Inicial

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Rodar todos os testes
pytest tests/ -v

# 3. Rodar com relatório de cobertura
pytest tests/ --cov=src --cov-report=html --cov-report=term

# 4. Ver relatório de cobertura no navegador
open htmlcov/index.html  # MacOS
xdg-open htmlcov/index.html  # Linux
```

### Testes Específicos

```bash
# Testar apenas o calculador de fees
pytest tests/unit/test_fee_calculator.py -v

# Testar apenas o gerenciador de posições
pytest tests/unit/test_position_manager.py -v

# Testar apenas o controlador de risco
pytest tests/unit/test_risk_controller.py -v
```

## 2. Modo Simulação (Sem Dinheiro Real)

### Configurar Simulação

Edite `.env`:
```bash
SIMULATION_MODE=true
ENVIRONMENT=development
DEBUG=true
```

Execute:
```bash
python src/main.py
```

**O que acontece no modo simulação:**
- ✅ Todas as funções são executadas
- ✅ Logs são gerados
- ✅ Lógica é testada
- ❌ Nenhuma ordem real é enviada
- ❌ Nenhum dinheiro é usado

## 3. Testnet Hyperliquid (Recomendado)

### Passo 1: Obter Credenciais de Testnet

1. Acesse: https://app.hyperliquid-testnet.xyz/
2. Conecte sua carteira de teste
3. Obtenha tokens de teste (testnet USDC)
4. Copie sua private key de teste

### Passo 2: Configurar para Testnet

Edite `config/config.yaml`:
```yaml
exchange:
  testnet: true  # ← IMPORTANTE: Ativar testnet

trading:
  symbol: BTC
  order_notional_usd: 1.0  # Começar pequeno

risk:
  max_inventory_usd: 5.0
  max_daily_loss_usd: 10.0
```

Edite `.env`:
```bash
HYPERLIQUID_PRIVATE_KEY=sua_chave_privada_de_testnet
ENVIRONMENT=testnet
SIMULATION_MODE=false
DEBUG=true
```

### Passo 3: Executar em Testnet

```bash
python src/main.py
```

### Passo 4: Monitorar

Em outro terminal:
```bash
# Ver logs em tempo real
tail -f logs/trading.log

# Filtrar apenas eventos importantes
tail -f logs/trading.log | grep -E "(order_placed|fill_received|hedge_completed|performance_report)"
```

## 4. Validação Pré-Produção

### Checklist de Segurança

Antes de usar dinheiro real, verifique:

```bash
# 1. Rodar script de validação
python scripts/validate_config.py
```

Verificações manuais:

- [ ] Testnet funcionou corretamente por pelo menos 1 hora
- [ ] Ordens foram colocadas e preenchidas
- [ ] Hedges foram executados automaticamente
- [ ] Circuit breakers funcionaram (teste forçando condições)
- [ ] Logs estão sendo gravados corretamente
- [ ] Métricas de performance fazem sentido
- [ ] WebSocket reconectou após desconexão (teste desligando internet)

### Teste de Circuit Breakers

```bash
# Editar config/config.yaml temporariamente para testar
risk:
  max_inventory_usd: 0.1  # Muito baixo - vai ativar rapidamente
  max_consecutive_failures: 2  # Vai ativar fácil
  latency_threshold_ms: 10  # Vai detectar latência normal
```

Execute e verifique se o circuit breaker ativa:
```bash
python src/main.py
# Deve ver: "circuit_breaker_activated" nos logs
```

## 5. Testes de Stress (Opcional)

### Criar Teste de Stress

Crie `tests/stress/test_high_frequency.py`:

```python
import asyncio
import pytest
from src.engines.market_maker import MarketMaker

@pytest.mark.asyncio
async def test_rapid_order_placement():
    """Testa colocação rápida de múltiplas ordens."""
    # Simular 100 ordens em sequência rápida
    for i in range(100):
        # Testar lógica de orders
        pass
```

Execute:
```bash
pytest tests/stress/ -v
```

## 6. Produção com Capital Mínimo

### Configuração Ultra-Conservadora

```yaml
trading:
  order_notional_usd: 1.0  # Mínimo possível
  base_spread_bps: 10.0    # Spread maior = mais seguro

risk:
  max_inventory_usd: 2.0   # Apenas $2 de exposição
  max_daily_loss_usd: 5.0  # Parar após $5 de perda
  max_unhedged_duration_seconds: 15  # Hedge rápido
```

### Monitoramento em Produção

```bash
# Terminal 1: Executar bot
python src/main.py

# Terminal 2: Monitorar logs
tail -f logs/trading.log | jq .

# Terminal 3: Monitorar performance
watch -n 5 'tail -20 logs/trading.log | grep performance_report | tail -1 | jq .'
```

## 7. Testes Recomendados (Ordem)

### Fase 1: Validação Local (1 hora)
```bash
# 1. Testes unitários
pytest tests/unit/ -v

# 2. Verificar imports
python -c "from src.main import TradingSystem; print('OK')"

# 3. Validar configuração
python -c "from src.utils.config import load_config; c=load_config(); print('OK')"
```

### Fase 2: Testnet (4-8 horas)
```bash
# 1. Configurar testnet
# 2. Rodar por 1 hora
# 3. Verificar métricas
# 4. Testar desconexões
# 5. Forçar circuit breakers
```

### Fase 3: Produção Mínima (24 horas)
```bash
# 1. Capital mínimo ($5-10)
# 2. Spreads conservadores
# 3. Monitorar constantemente
# 4. Verificar PnL real vs esperado
```

### Fase 4: Escalar Gradualmente
- Aumentar capital gradualmente
- Ajustar spreads baseado em dados
- Otimizar parâmetros

## 8. Debugging

### Ativar Logs Detalhados

```yaml
# config/config.yaml
logging:
  level: DEBUG  # Muito verboso
  format: json
  console_enabled: true
```

### Logs Importantes

```bash
# Ver apenas erros
tail -f logs/trading.log | grep '"level":"error"'

# Ver ordens colocadas
tail -f logs/trading.log | grep order_placed

# Ver hedges completados
tail -f logs/trading.log | grep hedge_completed

# Ver ativações de circuit breaker
tail -f logs/trading.log | grep circuit_breaker
```

## 9. Métricas de Sucesso

### O que observar nos testes:

**Bom:**
- ✅ Fill rate > 50%
- ✅ Hedge latency < 200ms
- ✅ Spread capturado > 6 bps
- ✅ Net profit > 0
- ✅ 0 ativações de circuit breaker não esperadas

**Ruim:**
- ❌ Muitos erros de conexão
- ❌ Hedges falhando
- ❌ Perda líquida
- ❌ Circuit breakers ativando frequentemente
- ❌ Latência alta (>500ms)

## 10. Problemas Comuns

### Problema: "WebSocket connection failed"
**Solução:**
```bash
# Verificar conectividade
curl https://api.hyperliquid.xyz/info
# Verificar se testnet está configurado corretamente
```

### Problema: "Orders not filling"
**Solução:**
- Aumentar spread (base_spread_bps)
- Verificar liquidez do mercado
- Usar símbolo mais líquido (BTC, ETH)

### Problema: "Circuit breaker keeps activating"
**Solução:**
- Revisar limites de risco (podem estar muito apertados)
- Verificar latência de rede
- Verificar se há problemas na exchange

## 11. Script de Teste Rápido

Crie `scripts/quick_test.sh`:

```bash
#!/bin/bash
set -e

echo "🧪 Iniciando testes rápidos..."

echo "1️⃣ Testes unitários..."
pytest tests/unit/ -v --tb=short

echo "2️⃣ Verificando imports..."
python -c "from src.main import TradingSystem"

echo "3️⃣ Validando configuração..."
python -c "from src.utils.config import load_config; load_config()"

echo "✅ Todos os testes passaram!"
```

Execute:
```bash
chmod +x scripts/quick_test.sh
./scripts/quick_test.sh
```

## 12. Contato e Suporte

Se encontrar problemas:

1. Verificar logs em `logs/trading.log`
2. Rodar testes: `pytest tests/ -v`
3. Ativar DEBUG mode
4. Verificar configuração de rede
5. Testar em testnet primeiro

**Importante:** NUNCA use dinheiro real sem testar completamente em testnet primeiro!
