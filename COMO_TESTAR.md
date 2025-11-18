# 🧪 Como Testar o Bot - Guia Rápido em Português

## 📋 Opções de Teste (Do mais seguro ao mais arriscado)

```
1. ✅ Testes Unitários        → 100% seguro, sem dinheiro
2. ✅ Modo Simulação          → 100% seguro, sem ordens reais
3. ✅ Testnet Hyperliquid     → Seguro, dinheiro fake
4. ⚠️  Produção (Capital Min) → DINHEIRO REAL, começar pequeno
```

---

## 🚀 Início Rápido (5 minutos)

### Passo 1: Instalar Dependências

```bash
# Instalar Python 3.11+
python3 --version

# Instalar dependências
pip install -r requirements.txt
```

### Passo 2: Teste Rápido Automatizado

```bash
# Rodar script de teste
./scripts/quick_test.sh
```

Se tudo passar ✅, pode prosseguir!

---

## 📝 Opção 1: Testes Unitários (RECOMENDADO PRIMEIRO)

**Tempo:** 2 minutos
**Custo:** $0
**Risco:** Nenhum

```bash
# Rodar todos os testes
pytest tests/unit/ -v

# Com relatório detalhado
pytest tests/unit/ --cov=src --cov-report=html

# Ver relatório no navegador
open htmlcov/index.html
```

**O que é testado:**
- ✅ Cálculo de fees e spreads
- ✅ Gerenciamento de posições
- ✅ Limites de risco e circuit breakers
- ✅ Lógica de hedging

---

## 🎮 Opção 2: Modo Simulação (SEM ORDENS REAIS)

**Tempo:** 10 minutos
**Custo:** $0
**Risco:** Nenhum

### Configurar:

**1. Criar arquivo `.env`:**
```bash
cp .env.example .env
```

**2. Editar `.env`:**
```bash
# Pode usar qualquer private key (não precisa ser real em simulação)
HYPERLIQUID_PRIVATE_KEY=0x1234567890abcdef...
SIMULATION_MODE=true
ENVIRONMENT=development
DEBUG=true
```

### Executar:

```bash
python src/main.py
```

### Monitorar:

```bash
# Em outro terminal
tail -f logs/trading.log
```

**O que acontece:**
- ✅ Bot executa toda a lógica
- ✅ Logs são gerados
- ✅ Métricas são calculadas
- ❌ NENHUMA ordem é enviada
- ❌ NENHUM dinheiro é usado

---

## 🧪 Opção 3: Testnet Hyperliquid (RECOMENDADO ANTES DE PRODUÇÃO)

**Tempo:** 1-4 horas
**Custo:** $0 (dinheiro fake)
**Risco:** Nenhum

### Passo 1: Obter Credenciais de Testnet

1. Acesse: https://app.hyperliquid-testnet.xyz/
2. Conecte uma carteira de teste (MetaMask com rede de teste)
3. Peça tokens de teste no Discord da Hyperliquid
4. Copie a private key da sua carteira de teste

### Passo 2: Configurar

**Editar `config/config.yaml`:**
```yaml
exchange:
  testnet: true  # ← IMPORTANTE!

trading:
  symbol: BTC
  order_notional_usd: 1.0

risk:
  max_inventory_usd: 5.0
  max_daily_loss_usd: 10.0
```

**Editar `.env`:**
```bash
HYPERLIQUID_PRIVATE_KEY=sua_private_key_de_testnet_aqui
SIMULATION_MODE=false
ENVIRONMENT=testnet
DEBUG=true
```

### Passo 3: Validar Configuração

```bash
python scripts/validate_config.py
```

Deve retornar: ✅ **VALIDAÇÃO PASSOU**

### Passo 4: Executar

```bash
# Opção 1: Script automatizado
./scripts/test_testnet.sh

# Opção 2: Manual
python src/main.py
```

### Passo 5: Monitorar (abrir em outro terminal)

```bash
# Ver todos os logs
tail -f logs/trading.log

# Ver apenas ordens
tail -f logs/trading.log | grep order_placed

# Ver apenas fills
tail -f logs/trading.log | grep fill_received

# Ver performance
tail -f logs/trading.log | grep performance_report
```

### O que Observar:

**Bom ✅:**
- Ordens sendo colocadas
- Algumas ordens sendo preenchidas (fills)
- Hedges sendo executados automaticamente
- Net profit > 0 após algumas trades
- Sem erros no log

**Ruim ❌:**
- Muitos erros de conexão
- Circuit breaker ativando constantemente
- Ordens não sendo preenchidas (spreads muito largos)
- Latência muito alta (>1000ms)

### Deixar Rodar:

Deixe o bot rodar por **pelo menos 1 hora** em testnet antes de considerar produção.

---

## 💰 Opção 4: Produção com Capital Mínimo

**Tempo:** 24+ horas
**Custo:** $5-20 recomendado
**Risco:** DINHEIRO REAL ⚠️

### ⚠️ AVISOS IMPORTANTES:

```
🚨 APENAS após testar COMPLETAMENTE em testnet
🚨 Começar com capital MÍNIMO ($5-20)
🚨 Monitorar CONSTANTEMENTE nas primeiras horas
🚨 Estar preparado para PARAR imediatamente se algo der errado
```

### Configuração Ultra-Conservadora:

**`config/config.yaml`:**
```yaml
exchange:
  testnet: false  # PRODUÇÃO

trading:
  order_notional_usd: 1.0      # Mínimo
  base_spread_bps: 10.0        # Spread maior = mais seguro

risk:
  max_inventory_usd: 2.0       # Apenas $2 de exposição
  max_daily_loss_usd: 5.0      # Para após $5 de perda
  max_unhedged_duration_seconds: 15
```

**`.env`:**
```bash
HYPERLIQUID_PRIVATE_KEY=sua_private_key_REAL_aqui
SIMULATION_MODE=false
ENVIRONMENT=production
DEBUG=false
```

### Executar:

```bash
# Validar primeiro!
python scripts/validate_config.py

# Se passar, executar
python src/main.py
```

### Monitoramento Intensivo:

```bash
# Terminal 1: Bot
python src/main.py

# Terminal 2: Logs em tempo real
tail -f logs/trading.log | jq .

# Terminal 3: Performance a cada 30s
watch -n 30 'tail -100 logs/trading.log | grep performance_report | tail -1 | jq .'
```

### Quando Parar:

**Parar IMEDIATAMENTE se:**
- ❌ Perda > $5
- ❌ Circuit breaker ativando repetidamente
- ❌ Hedges falhando consistentemente
- ❌ Latência muito alta
- ❌ Qualquer comportamento estranho

---

## 🔍 Validação de Configuração

Antes de rodar, SEMPRE valide:

```bash
python scripts/validate_config.py
```

Isso verifica:
- ✅ Credenciais configuradas
- ✅ Parâmetros fazem sentido
- ✅ Limites de risco adequados
- ✅ Modo de operação correto
- ✅ Arquivos de log acessíveis

---

## 📊 Métricas de Sucesso

### Durante Testes:

**Procurar por:**
- Fill rate: > 30%
- Hedge latency: < 300ms
- Spread capturado: > 6 bps
- Net profit: > 0
- Uptime: > 95%

### No Log:

```json
{
  "event": "performance_report",
  "total_trades": 50,
  "successful_trades": 48,
  "net_profit": 2.35,
  "average_spread_bps": 7.2,
  "average_hedge_latency_ms": 156
}
```

---

## 🐛 Problemas Comuns

### 1. "WebSocket connection failed"

**Solução:**
```bash
# Verificar conectividade
curl https://api.hyperliquid.xyz/info

# Verificar se testnet está certo no config
grep testnet config/config.yaml
```

### 2. "Orders not filling"

**Causas:**
- Spread muito largo
- Mercado sem liquidez
- Símbolo errado

**Solução:**
```yaml
# Diminuir spread
trading:
  base_spread_bps: 6.0  # Em vez de 10.0
```

### 3. "Circuit breaker activated"

**Causas:**
- Limites muito apertados
- Latência alta
- Muitos erros

**Solução:**
```bash
# Ver razão nos logs
tail -f logs/trading.log | grep circuit_breaker

# Ajustar limites no config
```

### 4. Importação falhando

**Solução:**
```bash
# Reinstalar dependências
pip install -r requirements.txt --force-reinstall

# Verificar Python version
python --version  # Precisa ser 3.11+
```

---

## 📚 Comandos Úteis

```bash
# Testes
pytest tests/unit/ -v                    # Testes unitários
./scripts/quick_test.sh                  # Teste rápido completo

# Validação
python scripts/validate_config.py        # Validar configuração

# Execução
python src/main.py                       # Rodar bot
./scripts/test_testnet.sh               # Rodar em testnet

# Monitoramento
tail -f logs/trading.log                 # Ver logs
tail -f logs/trading.log | grep error    # Ver apenas erros
tail -f logs/trading.log | jq .          # Logs formatados

# Docker
docker-compose up -d                     # Subir em Docker
docker-compose logs -f                   # Ver logs Docker
docker-compose down                      # Parar Docker
```

---

## ✅ Checklist Final

Antes de produção, verificar:

- [ ] ✅ Testes unitários passando
- [ ] ✅ Testnet funcionou por 1+ hora
- [ ] ✅ Ordens foram preenchidas e hedgeadas
- [ ] ✅ Circuit breakers testados
- [ ] ✅ Configuração validada
- [ ] ✅ Capital mínimo ($5-20)
- [ ] ✅ Spreads conservadores (10+ bps)
- [ ] ✅ Monitoramento preparado
- [ ] ✅ Plano de ação se algo der errado

---

## 🆘 Precisa de Ajuda?

1. Verificar logs: `tail -f logs/trading.log`
2. Rodar validação: `python scripts/validate_config.py`
3. Ver testes: `pytest tests/ -v`
4. Ativar DEBUG no config
5. Verificar TESTING_GUIDE.md

---

## ⚖️ Disclaimer

**IMPORTANTE:** Este software é experimental. Use por sua conta e risco.

- ❌ Não há garantias de lucro
- ❌ Pode haver bugs
- ❌ Mercados são imprevisíveis
- ✅ Sempre teste em testnet primeiro
- ✅ Comece com capital mínimo
- ✅ Monitore constantemente

**Você é responsável por suas perdas e ganhos!**
