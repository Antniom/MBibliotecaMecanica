import os
import shutil
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

def refactor():
    print("Starting refactor to move Astro site to the root directory...")
    
    # 1. Move all files from web/ to the root
    if not os.path.exists(WEB_DIR):
        print(f"Error: web directory does not exist at {WEB_DIR}")
        return
        
    for item in os.listdir(WEB_DIR):
        src_path = os.path.join(WEB_DIR, item)
        dst_path = os.path.join(BASE_DIR, item)
        
        # Skip node_modules and .astro cache directory (safer to let them regenerate or move them directly if needed)
        if item in ["node_modules", ".astro", "dist"]:
            print(f"Deleting temp/build folder to prevent conflicts: {item}")
            try:
                if os.path.isdir(src_path):
                    shutil.rmtree(src_path)
                else:
                    os.remove(src_path)
            except Exception as e:
                print(f"Could not delete {item}: {e}")
            continue
            
        print(f"Moving {item} to root...")
        try:
            if os.path.exists(dst_path):
                if os.path.isdir(dst_path):
                    shutil.rmtree(dst_path)
                else:
                    os.remove(dst_path)
            shutil.move(src_path, dst_path)
        except Exception as e:
            print(f"Error moving {item}: {e}")

    # 2. Merge gitignore files if both exist
    gitignore_root = os.path.join(BASE_DIR, ".gitignore")
    # If the moved one became .gitignore, make sure it has the entries
    # Or just write a fresh unified .gitignore
    unified_gitignore = """# Unified gitignore for MBibliotecaMecanica

# Python
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
pip-log.txt
pip-delete-this-directory.txt
metadata.db
metadata.db-shm
metadata.db-wal
pipeline_run.log
temp_*.png

# Node / Astro
node_modules/
.astro/
dist/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# Environment
.env
.env.production
.env.local
.env.development.local

# OS
.DS_Store
Thumbs.db
"""
    with open(gitignore_root, "w", encoding="utf-8") as f:
        f.write(unified_gitignore)
    print("Unified .gitignore created.")

    # 3. Update paths in Python script files
    files_to_update = [
        ("pipeline/assemble.py", 
         r'WEB_CONTENT_DIR\s*=\s*os\.path\.join\(\s*BASE_DIR,\s*"web",\s*"src",\s*"content",\s*"biblioteca"\s*\)',
         'WEB_CONTENT_DIR = os.path.join(BASE_DIR, "src", "content", "biblioteca")'),
         
        ("pipeline/deploy.py",
         r'WEB_DIR\s*=\s*os\.path\.join\(\s*BASE_DIR,\s*"web"\s*\)',
         'WEB_DIR = BASE_DIR'),
         
        ("pipeline/make_placeholders.py",
         r'WEB_CONTENT_DIR\s*=\s*os\.path\.join\(\s*BASE_DIR,\s*"web",\s*"src",\s*"content",\s*"biblioteca"\s*\)',
         'WEB_CONTENT_DIR = os.path.join(BASE_DIR, "src", "content", "biblioteca")'),
         
        ("pipeline/upload_assets.py",
         r'os\.path\.join\(\s*BASE_DIR,\s*"web",\s*"src",\s*"content",\s*"biblioteca",\s*tag,\s*semestre_str,\s*disciplina,\s*tipo_str,\s*base_name\s*\+\s*"\.md"\s*\)',
         'os.path.join(BASE_DIR, "src", "content", "biblioteca", tag, semestre_str, disciplina, tipo_str, base_name + ".md")')
    ]
    
    for filename, pattern, replacement in files_to_update:
        filepath = os.path.join(BASE_DIR, filename)
        if not os.path.exists(filepath):
            print(f"Skipping path update for missing file: {filepath}")
            continue
            
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Successfully updated paths in {filename} ({count} replacement(s)).")
        else:
            print(f"Warning: Pattern not found in {filename}.")

    # 4. Remove empty web directory
    try:
        if os.path.exists(WEB_DIR) and len(os.listdir(WEB_DIR)) == 0:
            os.rmdir(WEB_DIR)
            print("Empty web directory removed.")
        elif os.path.exists(WEB_DIR):
            print(f"Warning: web directory is not empty: {os.listdir(WEB_DIR)}")
    except Exception as e:
        print(f"Error removing web directory: {e}")

    print("Refactor complete!")

if __name__ == "__main__":
    refactor()
