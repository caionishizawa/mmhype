#!/usr/bin/env python3
"""
Script para validar configuração antes de executar o bot.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import load_config, load_settings
from decimal import Decimal
import structlog

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


def validate_config():
    """Valida a configuração do sistema."""
    print("=" * 60)
    print("🔍 VALIDAÇÃO DE CONFIGURAÇÃO")
    print("=" * 60)
    print()

    errors = []
    warnings = []

    # 1. Carregar configuração
    print("1️⃣  Carregando configuração...")
    try:
        config = load_config("config/config.yaml")
        print("   ✅ Config carregado com sucesso")
    except Exception as e:
        errors.append(f"Erro ao carregar config.yaml: {e}")
        print(f"   ❌ Erro: {e}")
        return False

    # 2. Carregar settings
    print("\n2️⃣  Carregando variáveis de ambiente...")
    try:
        settings = load_settings()
        print("   ✅ Settings carregados")
    except Exception as e:
        errors.append(f"Erro ao carregar .env: {e}")
        print(f"   ❌ Erro: {e}")
        return False

    # 3. Validar private key
    print("\n3️⃣  Validando credenciais...")
    if not settings.hyperliquid_private_key:
        errors.append("HYPERLIQUID_PRIVATE_KEY não configurado no .env")
        print("   ❌ Private key não encontrada")
    else:
        # Ocultar a maior parte da chave
        key_preview = settings.hyperliquid_private_key[:6] + "..." + settings.hyperliquid_private_key[-4:]
        print(f"   ✅ Private key encontrada: {key_preview}")

    # 4. Validar parâmetros de trading
    print("\n4️⃣  Validando parâmetros de trading...")

    if config.trading.order_notional_usd < Decimal("0.1"):
        warnings.append("Order notional muito pequeno (< $0.10)")
        print(f"   ⚠️  Notional muito pequeno: ${config.trading.order_notional_usd}")
    else:
        print(f"   ✅ Order notional: ${config.trading.order_notional_usd}")

    if config.trading.base_spread_bps < Decimal("6.0"):
        warnings.append("Spread menor que o mínimo recomendado (6 bps)")
        print(f"   ⚠️  Spread abaixo do mínimo: {config.trading.base_spread_bps} bps")
    else:
        print(f"   ✅ Base spread: {config.trading.base_spread_bps} bps")

    # 5. Validar limites de risco
    print("\n5️⃣  Validando limites de risco...")

    if config.risk.max_inventory_usd < config.trading.order_notional_usd:
        errors.append("Max inventory menor que order notional!")
        print(f"   ❌ Max inventory (${config.risk.max_inventory_usd}) < Order notional (${config.trading.order_notional_usd})")
    else:
        print(f"   ✅ Max inventory: ${config.risk.max_inventory_usd}")

    if config.risk.max_daily_loss_usd < Decimal("1.0"):
        warnings.append("Daily loss limit muito baixo - pode ativar circuit breaker facilmente")
        print(f"   ⚠️  Max daily loss baixo: ${config.risk.max_daily_loss_usd}")
    else:
        print(f"   ✅ Max daily loss: ${config.risk.max_daily_loss_usd}")

    print(f"   ✅ Circuit breaker cooldown: {config.risk.circuit_breaker_cooldown_seconds}s")

    # 6. Validar modo de operação
    print("\n6️⃣  Validando modo de operação...")

    if config.exchange.testnet:
        print("   ℹ️  Modo TESTNET ativado ✅")
    else:
        if not settings.simulation_mode:
            print("   ⚠️  Modo PRODUÇÃO - DINHEIRO REAL será usado!")
            warnings.append("Modo produção ativo - certifique-se de testar em testnet primeiro")
        else:
            print("   ✅ Modo SIMULAÇÃO ativado")

    # 7. Validar logging
    print("\n7️⃣  Validando logging...")

    log_dir = Path(config.logging.file_path).parent
    if not log_dir.exists():
        print(f"   📁 Criando diretório de logs: {log_dir}")
        log_dir.mkdir(parents=True, exist_ok=True)

    print(f"   ✅ Log level: {config.logging.level}")
    print(f"   ✅ Log file: {config.logging.file_path}")

    # 8. Resumo
    print("\n" + "=" * 60)
    print("📊 RESUMO DA VALIDAÇÃO")
    print("=" * 60)

    if errors:
        print("\n❌ ERROS ENCONTRADOS:")
        for i, error in enumerate(errors, 1):
            print(f"   {i}. {error}")

    if warnings:
        print("\n⚠️  AVISOS:")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")

    if not errors and not warnings:
        print("\n✅ Nenhum problema encontrado!")

    print("\n" + "=" * 60)

    if errors:
        print("❌ VALIDAÇÃO FALHOU - Corrija os erros antes de continuar")
        return False
    elif warnings:
        print("⚠️  VALIDAÇÃO PASSOU COM AVISOS - Revise antes de continuar")
        return True
    else:
        print("✅ VALIDAÇÃO PASSOU - Sistema pronto para uso!")
        return True


if __name__ == "__main__":
    success = validate_config()
    sys.exit(0 if success else 1)
