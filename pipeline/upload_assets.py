import os
import sqlite3
import requests
import subprocess
from dotenv import load_dotenv
from db_utils import get_db_connection

# Load configurations — override=True forces .env values over any Windows system env vars
load_dotenv(override=True)
GITHUB_REPO = os.getenv("GITHUB_REPO", "Antniom/MBibliotecaMecanica")
# Always use gh CLI — no API token needed (uses local gh auth session)
GITHUB_TOKEN = None  # API path disabled: gh CLI is more reliable

def create_release_if_not_exists(tag, token):
    """Creates a GitHub release for a given tag if it doesn't exist yet via GitHub API."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    
    # Check if release exists
    check_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag}"
    res = requests.get(check_url, headers=headers)
    if res.status_code == 200:
        return res.json()["id"]
        
    # Create it
    payload = {
        "tag_name": tag,
        "name": f"Materiais do {tag.replace('-', ' ').title()}",
        "body": f"Arquivo de ficheiros originais digitalizados e nativos para o {tag.replace('-', ' ')}.",
        "draft": False,
        "prerelease": False
    }
    
    res = requests.post(url, json=payload, headers=headers)
    if res.status_code == 201:
        print(f"Created GitHub Release for tag: {tag}")
        return res.json()["id"]
    else:
        print(f"Failed to create/find release for tag {tag}: {res.text}")
        return None

def upload_asset_via_api(release_id, filepath, token):
    """Uploads a file to a specific GitHub release using the API."""
    filename = os.path.basename(filepath)
    url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets?name={filename}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream"
    }
    
    with open(filepath, "rb") as f:
        file_bytes = f.read()
        
    print(f"Uploading {filename} to GitHub Release {release_id} via API...")
    res = requests.post(url, data=file_bytes, headers=headers)
    if res.status_code == 201:
        download_url = res.json()["browser_download_url"]
        print(f"Uploaded successfully. URL: {download_url}")
        return download_url
    elif res.status_code == 422: # Asset already exists
        print(f"Asset {filename} already exists in this release.")
        # Predict download URL format
        return f"https://github.com/{GITHUB_REPO}/releases/download/{release_id}/{filename}"
    else:
        print(f"Failed to upload asset {filename}: {res.text}")
        return None

def upload_asset_via_cli(tag, filepath):
    """Fallback: Uploads a file to a specific GitHub release using the gh CLI."""
    filename = os.path.basename(filepath)
    print(f"Attempting to upload {filename} via gh CLI...")
    try:
        # Clean environment to prevent gh CLI from using a contaminated/expired token
        env = os.environ.copy()
        if "GITHUB_TOKEN" in env:
            del env["GITHUB_TOKEN"]
            
        # Create release if not exists (ignores error if already exists)
        subprocess.run(
            ["gh", "release", "create", tag, "--repo", GITHUB_REPO, "--notes", "Ficheiros originais"],
            capture_output=True,
            env=env
        )
        
        # Upload
        res = subprocess.run(
            ["gh", "release", "upload", tag, filepath, "--repo", GITHUB_REPO, "--clobber"],
            capture_output=True,
            text=True,
            env=env
        )
        
        if res.returncode == 0:
            download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{filename}"
            print(f"Uploaded successfully via CLI. URL: {download_url}")
            return download_url
        else:
            print(f"gh CLI upload failed: {res.stderr}")
            return None
    except Exception as e:
        print(f"gh CLI execution failed: {e}")
        return None

def run_uploads():
    """Finds documents without storage URLs and uploads their original files."""
    import time
    import re
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query documents that don't have a storage_url yet, regardless of processing status
    cursor.execute(
        """
        SELECT id, path_original, ano, storage_url, disciplina, tipo, semestre
        FROM documents 
        WHERE (storage_url IS NULL OR storage_url = '')
        """
    )
    docs = cursor.fetchall()
    
    if not docs:
        print("No documents pending upload.")
        conn.close()
        return
 
    print(f"Found {len(docs)} document(s) pending upload.")
 
    for doc in docs:
        doc_id = doc["id"]
        filepath = doc["path_original"]
        ano = doc["ano"] if doc["ano"] is not None else 1
        semestre = doc["semestre"] if doc["semestre"] is not None else 1
        disciplina = doc["disciplina"] if doc["disciplina"] else "desconhecido"
        tipo = doc["tipo"] if doc["tipo"] else "teoria"
        
        # Check if physical file exists
        if not os.path.exists(filepath):
            print(f"Physical file not found for upload, skipping: {filepath}")
            continue
            
        tag = f"{ano}-ano"
        download_url = None
        
        # Prefer gh CLI (uses local authenticated session) over API token
        # Only try API if token is explicitly valid
        if GITHUB_TOKEN:
            release_id = create_release_if_not_exists(tag, GITHUB_TOKEN)
            if release_id:
                download_url = upload_asset_via_api(release_id, filepath, GITHUB_TOKEN)
        
        # Always fall back to (or prefer) gh CLI
        if not download_url:
            download_url = upload_asset_via_cli(tag, filepath)
            
        if download_url:
            # Update database
            cursor.execute(
                "UPDATE documents SET storage_release_tag = ?, storage_url = ? WHERE id = ?",
                (tag, download_url, doc_id)
            )
            conn.commit()
            print(f"Database updated with storage URL for: {os.path.basename(filepath)}")
            
            # Update markdown file on disk if it exists
            dest_dir = os.path.join(
                BASE_DIR, "web", "src", "content", "biblioteca",
                f"{ano}-ano", f"{semestre}-semestre", disciplina, tipo
            )
            base_name = os.path.splitext(os.path.basename(filepath))[0].replace("#", "_").replace("?", "_")
            md_path = os.path.join(dest_dir, f"{base_name}.md")
            
            if os.path.exists(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Replace storage_url in YAML frontmatter
                    new_content = re.sub(
                        r'storage_url:\s*"[^"]*"',
                        f'storage_url: "{download_url}"',
                        content
                    )
                    if new_content == content:
                        new_content = re.sub(
                            r"storage_url:\s*'[^']*'",
                            f'storage_url: "{download_url}"',
                            content
                        )
                        
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Updated storage_url in markdown file: {md_path}")
                except Exception as e:
                    print(f"Error updating markdown file: {e}")
                    
            # Pause briefly to prevent hitting GitHub abuse rate-limits
            time.sleep(2)
        else:
            print(f"Failed to upload original file: {filepath}")
 
    conn.close()
    print("Upload run complete.")
 
if __name__ == "__main__":
    run_uploads()
