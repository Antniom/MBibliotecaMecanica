import os
import subprocess
from dotenv import load_dotenv

# Load configs
load_dotenv()
DEPLOY_METHOD = os.getenv("DEPLOY_METHOD", "none") # git | wrangler | none
CF_PROJECT_NAME = os.getenv("CLOUDFLARE_PROJECT_NAME", "mbibliotecamecanica")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

def run_cmd(args, cwd=None, shell=False):
    """Runs a shell command and yields output lines."""
    try:
        env_vars = os.environ.copy()
        env_vars["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=cwd,
            shell=shell,
            env=env_vars
        )
        for line in iter(process.stdout.readline, ""):
            yield line
        process.wait()
    except Exception as e:
        yield f"Command execution failed: {e}\n"

def deploy():
    """Builds and deploys the site according to the configured DEPLOY_METHOD."""
    if DEPLOY_METHOD == "none":
        yield "Deployment is disabled (DEPLOY_METHOD=none in .env).\n"
        return
        
    yield f"Starting deployment using method: {DEPLOY_METHOD}...\n"
    
    # 1. Ensure build is fresh
    yield "Building Astro site and Pagefind search index...\n"
    shell = True if os.name == 'nt' else False
    for line in run_cmd(["npm", "run", "build"], cwd=WEB_DIR, shell=shell):
        yield line
        
    # 2. Deploy
    if DEPLOY_METHOD == "git":
        # Check if git is initialized
        if not os.path.exists(os.path.join(BASE_DIR, ".git")):
            yield "Error: Git repository is not initialized. Run 'git init' first.\n"
            return
            
        yield "Staging changes with git...\n"
        for line in run_cmd(["git", "add", "."], cwd=BASE_DIR):
            yield line
            
        yield "Committing changes...\n"
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True)
        if not status.stdout.strip():
            yield "No new changes to commit. Site is up to date.\n"
            return
            
        for line in run_cmd(["git", "commit", "-m", "Auto-update library content"], cwd=BASE_DIR):
            yield line
            
        yield "Pushing commits to remote origin...\n"
        for line in run_cmd(["git", "push"], cwd=BASE_DIR):
            yield line
            
        yield "Git push complete. If connected, Cloudflare Pages/Vercel will begin building on the cloud.\n"
        
    elif DEPLOY_METHOD == "wrangler":
        yield f"Deploying directly to Cloudflare Pages project '{CF_PROJECT_NAME}' via Wrangler CLI...\n"
        # Run: npx wrangler pages deploy dist --project-name CF_PROJECT_NAME
        cmd = ["npx", "wrangler", "pages", "deploy", "dist", "--project-name", CF_PROJECT_NAME]
        for line in run_cmd(cmd, cwd=WEB_DIR, shell=shell):
            yield line
            
        yield "Direct Wrangler deploy complete!\n"
        
    elif DEPLOY_METHOD == "vercel":
        yield "Deploying directly to Vercel via Vercel CLI...\n"
        # Run: npx vercel --prod --yes
        cmd = ["npx", "vercel", "--prod", "--yes"]
        
        # Pass vercel token if available in .env
        vercel_token = os.getenv("VERCEL_TOKEN")
        env_vars = os.environ.copy()
        if vercel_token:
            cmd.extend(["--token", vercel_token])
            
        for line in run_cmd(cmd, cwd=WEB_DIR, shell=shell):
            yield line
            
        yield "Direct Vercel deploy complete!\n"

if __name__ == "__main__":
    for line in deploy():
        print(line, end="")
