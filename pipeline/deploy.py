import os
import subprocess
from dotenv import load_dotenv

# Load configs — override ensures .env beats any system env vars
load_dotenv(override=True)
DEPLOY_METHOD = os.getenv("DEPLOY_METHOD", "none")  # git | none

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = BASE_DIR


def run_cmd(args, cwd=None):
    """Runs a command and yields output lines."""
    try:
        env_vars = os.environ.copy()
        env_vars["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=cwd,
            shell=(os.name == "nt"),
            env=env_vars,
        )
        for line in iter(process.stdout.readline, ""):
            yield line
        process.wait()
    except Exception as e:
        yield f"Erro ao executar comando: {e}\n"


def git_push(message="Auto-update library content"):
    """
    Stage all changes, commit, and push to trigger a Vercel rebuild.
    Vercel builds the Astro site on its own servers — we never run `npm build` locally.
    Returns True if something was pushed, False if nothing changed.
    """
    if DEPLOY_METHOD == "none":
        yield "[Deploy] Desativado (DEPLOY_METHOD=none).\n"
        return

    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        yield "[Deploy] Erro: repositório git não inicializado.\n"
        return

    # Check if there are any changes to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if not status.stdout.strip():
        yield "[Deploy] Sem alterações novas para publicar.\n"
        return

    changed_lines = status.stdout.strip().split("\n")
    yield f"[Deploy] {len(changed_lines)} ficheiro(s) alterados. A publicar...\n"

    for line in run_cmd(["git", "add", "."], cwd=BASE_DIR):
        pass  # silent

    for line in run_cmd(["git", "commit", "-m", message], cwd=BASE_DIR):
        yield line

    yield "[Deploy] A fazer push para GitHub (Vercel irá compilar automaticamente)...\n"
    for line in run_cmd(["git", "push"], cwd=BASE_DIR):
        yield line

    yield "[Deploy] Push concluido. O Vercel vai atualizar o site em 1-2 minutos.\n"


# Keep 'deploy' as an alias so run_pipeline.py import still works
def deploy():
    yield from git_push()


if __name__ == "__main__":
    for line in deploy():
        print(line, end="")
