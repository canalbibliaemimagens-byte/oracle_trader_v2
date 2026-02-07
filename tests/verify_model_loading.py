"""
Oracle Trader v2.0 — Verificação de Carregamento de Modelo RL
===============================================================

Script manual para testar carregamento de modelos PPO treinados.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent


def main():
    print("🧠 Verificando Carregamento de Modelo RL...")

    models_dir = ROOT / "models"
    if not models_dir.exists():
        print(f"❌ Diretório não encontrado: {models_dir}")
        return

    zips = list(models_dir.glob("*.zip"))
    if not zips:
        print(f"❌ Nenhum arquivo .zip encontrado em {models_dir}")
        print("   Treine um modelo no notebook e coloque o arquivo aqui.")
        return

    print(f"✅ Encontrados {len(zips)} modelos.")
    target_model = zips[0]
    print(f"   Testando carregamento de: {target_model.name}")

    try:
        from stable_baselines3 import PPO
    except ImportError:
        print("❌ Bibliotecas de ML ausentes.")
        print("   Instale: pip install stable-baselines3 torch shimmy")
        return

    try:
        model = PPO.load(target_model)
        print("✅ PPO.load() com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao carregar modelo: {e}")
        return

    print("\n🎉 Modelo validado e pronto para uso!")


if __name__ == "__main__":
    main()
