import sys
import os
import hashlib
import re
import sqlite3
import unicodedata

# Force stdout/stderr to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from db_utils import get_db_connection, init_db

# Directory where user drops input files
INPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrada")

# Taxonomy definition matching user choices:
# Option I: desenho-de-construcao-mecanica
# Option II: projeto-mecanico
# Option III: simulacao-computacional-projeto-mecanico
# Option IV: estagio
# Option V: controlo-de-gestao
UC_MAP = {
    # 1-ano, 1-semestre
    "analise-matematica": (1, 1, ["analise matematica", "am1", "am i", "matematica i"]),
    "algebra-linear": (1, 1, ["algebra linear", "al", "algebra"]),
    "fisica": (1, 1, ["fisica"]),
    "programacao": (1, 1, ["programacao", "scilab"]),
    "ingles": (1, 1, ["ingles", "english"]),
    "quimica-e-materiais": (1, 1, ["quimica", "quimica e materiais"]),
    
    # 1-ano, 2-semestre
    "matematica-aplicada": (1, 2, ["matematica aplicada", "ma"]),
    "estatistica": (1, 2, ["estatistica", "probability"]),
    "desenho-tecnico": (1, 2, ["desenho tecnico", "desenho"]),
    "tecnologia-dos-materiais": (1, 2, ["tecnologia dos materiais", "materiais"]),
    "tecnologia-mecanica-i": (1, 2, ["tecnologia mecanica i", "tec mec i"]),
    "mecanica-aplicada": (1, 2, ["mecanica aplicada", "mecapl", "pe2mecapl"]),
    
    # 2-ano, 1-semestre
    "resistencia-dos-materiais": (2, 1, ["resistencia dos materiais", "resistencia", "resmat", "rm"]),
    "tecnologia-mecanica-ii": (2, 1, ["tecnologia mecanica ii", "tec mec ii"]),
    "termodinamica": (2, 1, ["termodinamica", "termo"]),
    "mecanica-dos-fluidos": (2, 1, ["mecanica dos fluidos", "fluidos"]),
    "processos-transformacao-plasticos": (2, 1, ["processos transformacao plasticos", "transformacao plasticos", "plasticos"]),
    "modelacao-assistida-por-computador": (2, 1, ["modelacao assistida por computador", "mac", "cad"]),
    
    # 2-ano, 2-semestre
    "orgaos-de-maquinas-i": (2, 2, ["orgaos de maquinas i", "orgaos i", "omi"]),
    "processamento-mecanica-compositos": (2, 2, ["processamento mecanica compositos", "compositos"]),
    "engenharia-assistida-por-computador": (2, 2, ["engenharia assistida por computador", "eac", "cae"]),
    "fabrico-assistido-por-computador": (2, 2, ["fabrico assistido por computador", "fac", "cam"]),
    "desenho-de-construcao-mecanica": (2, 2, ["desenho de construcao mecanica", "construcao mecanica", "dcm"]), # Option I (Alternative A)
    "desenho-de-moldes-e-plasticos": (2, 2, ["desenho de moldes e plasticos", "desenho de moldes", "moldes e plasticos"]), # Option I (Alternative B)
    "eletrotecnia-e-eletronica-industrial": (2, 2, ["eletrotecnia e eletronica industrial", "eletrotecnia", "eletronica"]),
    
    # 3-ano, 1-semestre
    "orgaos-de-maquinas-ii": (3, 1, ["orgaos de maquinas ii", "orgaos ii", "omii"]),
    "processos-avancados-de-fabrico": (3, 1, ["processos avancados de fab", "paf"]),
    "projeto-mecanico": (3, 1, ["projeto mecanico", "proj mec"]), # Option II (Alternative A)
    "projeto-de-moldes": (3, 1, ["projeto de moldes", "projeto moldes", "moldes"]), # Option II (Alternative B)
    "concecao-e-desenvolvimento-de-produto": (3, 1, ["concecao e desenvolvimento de produto", "cdp", "produto"]),
    "simulacao-computacional-projeto-mecanico": (3, 1, ["simulacao computacional projeto mecanico", "scpm"]), # Option III (Alternative A)
    "automacao-industrial": (3, 1, ["automacao industrial", "automacao"]),
    
    # 3-ano, 2-semestre
    "qualidade-e-gestao-de-recursos": (3, 2, ["qualidade e gestao de recursos", "qualidade", "gestao", "qgr"]),
    "gestao-da-producao-e-manutencao": (3, 2, ["gestao da producao e manutencao", "manutencao", "gpm"]),
    "estagio": (3, 2, ["estagio", "internship"]), # Option IV
    "seminario": (3, 2, ["seminario"]),
    "controlo-de-gestao": (3, 2, ["controlo de gestao", "controlo gestao", "cog"]), # Option V (Alternative A)
    "redes-de-fluidos": (3, 2, ["redes de fluidos", "rede fluidos"]), # Option V (Alternative B)
    "inovacao-e-empreendedorismo": (3, 2, ["inovacao e empreendedorismo", "inovacao", "empreendedorismo"])
}

TYPE_MAP = {
    "teoria": ["slide", "aula", "teorica", "sebentas", "manual", "livro", "apresentacao", "teorico"],
    "fichas-exercicios": ["ficha", "exercicio", "problema", "pratica", "lista"],
    "resumos": ["resumo", "apontamentos", "formulario"],
    "resolucoes": ["resolucao", "resolvido", "respostas", "solucao", "resolvida"],
    "testes-exames": ["teste", "exame", "recurso", "t1", "t2", "avaliacao", "pauta", "nota"],
    "trabalhos-projetos": ["trabalho", "projeto", "relatorio", "cad", "scilab", "excel", "codigo"]
}

def calculate_sha256(filepath):
    """Calculates the SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def clean_string(s):
    """Normalize string to compare easily (lowercase, strip, remove accents/diacritics)."""
    s = s.lower()
    # Normalize unicode to decompose accents (NFD form)
    s = unicodedata.normalize('NFD', s)
    # Filter out combining diacritical marks
    s = "".join([c for c in s if not unicodedata.combining(c)])
    # Normalize back to NFC for consistency
    s = unicodedata.normalize('NFC', s)
    # Manual replacement of remaining ordinal characters
    s = s.replace('º', 'o').replace('ª', 'a')
    return s

def classify_file(filepath):
    """
    Classify file based on path structure first, and regex matching second.
    Returns: (discipline, type_str, year, semester)
    """
    # 1. Path-based analysis (e.g. 1-ano/1-semestre/fisica/teoria/xxx.pdf)
    norm_path = filepath.replace("\\", "/")
    parts = norm_path.split("/")
    
    # Try to find year/semester/uc/type from path structure
    # Look for parts matching taxonomy
    year = None
    semestre = None
    discipline = None
    tipo = None
    
    for i, part in enumerate(parts):
        part_clean = clean_string(part)
        
        # Check years (e.g., 1-ano, 1_ano, 1o ano, 1oano, 1ºano, 1º ano)
        if ("1o" in part_clean or "1-" in part_clean or "1_" in part_clean) and "ano" in part_clean:
            year = 1
        elif ("2o" in part_clean or "2-" in part_clean or "2_" in part_clean) and "ano" in part_clean:
            year = 2
        elif ("3o" in part_clean or "3-" in part_clean or "3_" in part_clean) and "ano" in part_clean:
            year = 3
            
        # Check semesters (e.g., 1-semestre, 1_semestre, 1o semestre, 1o sem, 1ºsemestre, 1º sem)
        if ("1o" in part_clean or "1-" in part_clean or "1_" in part_clean) and "sem" in part_clean:
            semestre = 1
        elif ("2o" in part_clean or "2-" in part_clean or "2_" in part_clean) and "sem" in part_clean:
            semestre = 2

    # Check if any path segments match canonical UC names or aliases or types
    # Sort UC map entries by the longest alias to avoid subset errors in directory matching
    flat_uc_aliases = []
    for uc_key, (uc_yr, uc_sem, aliases) in UC_MAP.items():
        flat_uc_aliases.append((uc_key, uc_key, uc_yr, uc_sem))
        for alias in aliases:
            flat_uc_aliases.append((alias, uc_key, uc_yr, uc_sem))
    flat_uc_aliases.sort(key=lambda x: len(x[0]), reverse=True)

    for part in parts[:-1]: # exclude filename
        part_clean = clean_string(part)
        part_words = re.findall(r'\b[a-z0-9]+\b', part_clean)
        
        # Check UCs (keys and aliases)
        if not discipline:
            for alias, uc_key, uc_yr, uc_sem in flat_uc_aliases:
                alias_clean = clean_string(alias)
                alias_words = re.findall(r'\b[a-z0-9]+\b', alias_clean)
                
                # Match if:
                # 1. The folder name exactly equals the alias
                # 2. Or the alias words appear exactly in sequence as separate words in the folder name
                if part_clean == alias_clean:
                    discipline = uc_key
                    year, semestre = uc_yr, uc_sem
                    break
                elif len(alias_words) > 0 and len(part_words) >= len(alias_words):
                    match_found = False
                    for idx in range(len(part_words) - len(alias_words) + 1):
                        if part_words[idx : idx + len(alias_words)] == alias_words:
                            match_found = True
                            break
                    if match_found:
                        discipline = uc_key
                        year, semestre = uc_yr, uc_sem
                        break
        
        # Check Types
        if not tipo:
            for type_key, aliases in TYPE_MAP.items():
                if part_clean == type_key or any(alias in part_clean for alias in aliases):
                    tipo = type_key
                    break

    filename = clean_string(parts[-1]).replace('_', ' ')

    # 2. Regex / Substring Fallback for UC
    if not discipline:
        # Prioritize longer aliases to avoid subset matches (e.g. "resistencia dos materiais" matching "materiais" first)
        flat_aliases = []
        for uc_name, (y, s, aliases) in UC_MAP.items():
            for alias in aliases:
                flat_aliases.append((alias, uc_name, y, s))
        flat_aliases.sort(key=lambda x: len(x[0]), reverse=True)

        for alias, uc_name, y, s in flat_aliases:
            alias_clean = clean_string(alias)
            # Word boundary match to avoid false positives (e.g., "al" matching "algebra")
            pattern = r'\b' + re.escape(alias_clean) + r'\b'
            if re.search(pattern, filename):
                discipline = uc_name
                year = y
                semestre = s
                break

    # 3. Regex / Substring Fallback for Type
    if not tipo:
        for type_key, keywords in TYPE_MAP.items():
            for keyword in keywords:
                if keyword in filename:
                    tipo = type_key
                    break
            if tipo:
                break

    # Fallbacks if still not found
    if not discipline:
        discipline = "desconhecido"
    if not tipo:
        tipo = "teoria" # Default fallback
    if not year:
        # Check if UC mapping exists for discovered discipline
        if discipline in UC_MAP:
            year, semestre, _ = UC_MAP[discipline]
        else:
            year = 1
            semestre = 1

    # Overrides from environment (set by worker.py for Cloud submissions)
    force_d = os.getenv("FORCE_DISCIPLINA")
    force_t = os.getenv("FORCE_TIPO")
    force_y = os.getenv("FORCE_ANO")
    force_s = os.getenv("FORCE_SEMESTRE")

    if force_d:
        discipline = force_d
    if force_t:
        tipo = force_t
    if force_y:
        try:
            year = int(force_y)
        except ValueError:
            pass
    if force_s:
        try:
            semestre = int(force_s)
        except ValueError:
            pass

    return discipline, tipo, year, semestre

def run_inventory():
    """Scans INPUT_DIR, hashes files, classifies them, and inserts them into the DB."""
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory does not exist: {INPUT_DIR}")
        return

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Load existing paths from DB to skip hashing and duplicate logging
    cursor.execute("SELECT path_original FROM documents")
    existing_paths = {row[0] for row in cursor.fetchall()}

    print(f"Scanning directory: {INPUT_DIR}")
    files_processed = 0
    duplicates_found = 0

    # Walk through the input directory
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            # Skip hidden files or temp files
            if file.startswith(".") or file.startswith("~$"):
                continue

            # Only process known document types — skip binaries / system files
            ALLOWED_EXTS = {
                ".pdf", ".docx", ".doc", ".pptx", ".ppt",
                ".xlsx", ".xls", ".csv", ".txt", ".html",
                ".htm", ".odt", ".odp", ".ods", ".rtf"
            }
            if os.path.splitext(file)[1].lower() not in ALLOWED_EXTS:
                continue

            filepath = os.path.join(root, file)
            
            # 1. Quick path check: if already processed, skip hashing and console prints
            if filepath in existing_paths:
                duplicates_found += 1
                continue
                
            # 2. Otherwise calculate SHA-256 hash for new files
            file_hash = calculate_sha256(filepath)
            
            # Check if file content already exists in DB (same hash, different path)
            cursor.execute("SELECT id, path_original FROM documents WHERE id = ?", (file_hash,))
            existing = cursor.fetchone()
            
            if existing:
                duplicates_found += 1
                continue

            # Classify
            discipline, tipo, year, semestre = classify_file(filepath)
            
            print(f"[NEW] {file} -> UC: {discipline}, Type: {tipo}, Year: {year}, Sem: {semestre}")
            
            cursor.execute(
                """
                INSERT INTO documents (id, path_original, disciplina, tipo, ano, semestre, status)
                VALUES (?, ?, ?, ?, ?, ?, 'inventory_done')
                """,
                (file_hash, filepath, discipline, tipo, year, semestre)
            )
            files_processed += 1

    conn.commit()
    conn.close()
    print(f"\nInventory Complete: {files_processed} new files, {duplicates_found} duplicates ignored.")

if __name__ == "__main__":
    run_inventory()
