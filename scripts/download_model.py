import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Carrega variáveis de ambiente
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRO: SUPABASE_URL e SUPABASE_KEY devem estar definidos no .env")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Baixa modelos do Supabase Storage")
    parser.add_argument("--bucket", default="oracle_models", help="Nome do bucket (default: oracle_models)")
    parser.add_argument("--output", default="models", help="Diretório de saída (default: models)")
    parser.add_argument("filename", nargs="?", help="Nome do arquivo ou símbolo para baixar (opcional)")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    print(f"Conectando ao Supabase: {SUPABASE_URL}")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        # 1. Listar arquivos no bucket
        print(f"Buscando arquivos no bucket '{args.bucket}'...")
        res = supabase.storage.from_(args.bucket).list()
        
        if not res:
            print("Nenhum arquivo encontrado no bucket.")
            return

        available_items = [item['name'] for item in res]

        # Se nenhum arquivo especificado, listar todos
        if not args.filename:
            print("Arquivos disponíveis:")
            for name in available_items:
                print(f" - {name}")
            print("\nUse: python scripts/download_model.py <symbol_timeframe> para baixar.")
            return

        # 2. Lógica de busca e download
        target_input = args.filename.strip()
        # Remove .zip para normalizar nome base (assumimos que o input é o símbolo_tf)
        base_name = target_input[:-4] if target_input.lower().endswith(".zip") else target_input
        
        # Tenta encontrar match na lista da raiz (pode ser arquivo ou pasta)
        found_item = None
        for item in res:
            if item['name'].lower() == base_name.lower():
                found_item = item
                break
            if item['name'].lower() == f"{base_name}.zip".lower():
                found_item = item
                break
        
        target_path_in_bucket = ""
        
        if found_item:
            # Se encontrou algo com o nome
            name = found_item['name']
            # Se termina com .zip, é o arquivo direto
            if name.lower().endswith(".zip"):
                target_path_in_bucket = name
            else:
                # Provavelmente é uma pasta. Tenta path/path.zip case-insensitive?
                # Vamos assumir que dentro da pasta X, o arquivo é X.zip (mesmo casing da pasta)
                target_path_in_bucket = f"{name}/{name}.zip"
        else:
             # Se não encontrou na listagem da raiz, tenta construir o caminho direto
             # Assumindo Uppercase padrão se não achou match
             target_path_in_bucket = f"{base_name.upper()}/{base_name.upper()}.zip"
             print(f"Não encontrado na raiz. Tentando caminho direto: {target_path_in_bucket}")

        print(f"Baixando '{target_path_in_bucket}' do bucket '{args.bucket}'...")
        
        try:
            data = supabase.storage.from_(args.bucket).download(target_path_in_bucket)
        except Exception as e:
             # Fallback: Tenta uppercase se o original falhou
             if target_path_in_bucket != f"{base_name.upper()}/{base_name.upper()}.zip":
                 target_path_in_bucket = f"{base_name.upper()}/{base_name.upper()}.zip"
                 print(f"Falha. Tentando UpperCase: {target_path_in_bucket}")
                 data = supabase.storage.from_(args.bucket).download(target_path_in_bucket)
             else:
                 raise e
        
        # Define nome local (sempre .zip)
        local_filename = f"{base_name}.zip"
            
        target_path = output_dir / local_filename
        with open(target_path, "wb") as f:
            f.write(data)
            
        print(f"Sucesso! Arquivo salvo em: {target_path}")
        
    except Exception as e:
        print(f"Erro ao acessar storage: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
