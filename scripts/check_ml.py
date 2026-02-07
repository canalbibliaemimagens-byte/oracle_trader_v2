try:
    import torch
    print(f"✅ Torch OK: {torch.__version__} (CUDA: {torch.cuda.is_available()})")
except ImportError:
    print("⚠️ Torch não instalado")
except Exception as e:
    print(f"❌ Torch Quebrado: {e}")

try:
    import tensorflow as tf
    print(f"✅ TensorFlow OK: {tf.__version__}")
except ImportError:
    print("⚠️ TensorFlow não instalado")
except Exception as e:
    print(f"❌ TensorFlow Quebrado: {e}")
