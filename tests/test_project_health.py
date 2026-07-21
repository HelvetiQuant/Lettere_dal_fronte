"""Test 'living' di salute del progetto — non testano una singola funzione,
ma un invariante strutturale dell'intero repo. Vanno rieseguiti ad ogni PR
che aggiunge un modulo o una dipendenza: per costruzione si aggiornano da
soli scansionando il repo, senza bisogno di toccare questo file.

Copre in particolare la regressione storica di requirements.txt (vedi
TODO.md #1 "Fix tecnici" #2): il file elencava solo 7 pacchetti mentre il
codice ne importava anche bs4, mistralai, pymupdf, pdfplumber, schedule.
Se un domani si aggiunge un modulo con una nuova dipendenza esterna e ci si
scorda di aggiungerla a requirements.txt, questo test fallisce SUBITO,
invece di scoprirlo quando un `pip install -r requirements.txt` fresco non
fa girare la pipeline.
"""
import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Import il cui nome differisce dal nome del pacchetto PyPI da cercare in
# requirements.txt. Aggiornare quando si introduce una nuova dipendenza con
# nome import != nome pacchetto (succede piu' spesso di quanto sembri).
IMPORT_TO_PACKAGE = {
    "fitz": "pymupdf",
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "dotenv": "python-dotenv",
    "openpyxl": "openpyxl",
    "yaml": "pyyaml",
    "mistralai": "mistralai",
    "cv2": "opencv-python",
}

# Moduli locali del progetto (non pacchetti PyPI): esclusi automaticamente
# perche' calcolati scansionando i file .py presenti nel repo (vedi
# _local_module_names()), non serve mantenerli a mano qui.

# Nomi che a volte compaiono come import ma sono in realta' sotto-pacchetti
# di qualcosa gia' coperto (es. 'source_providers.base' -> 'source_providers').
IGNORE_TOP_LEVEL = {"__future__"}


def _local_module_names() -> set:
    """Nomi di modulo che vanno considerati 'locali' (non pacchetti PyPI).

    Include sia i .py in root (import diretto, es. `import database`) sia
    ogni .py annidato in sottocartelle SENZA __init__.py che vengono
    comunque eseguite come mini-app standalone col proprio sys.path
    (es. import_ocr_lettere/app.py che fa `from ocr_engine import run_ocr`
    risolvendo ocr_engine.py come modulo top-level a runtime). Scansionare
    tutto l'albero (esclusi tests/, __pycache__, .venv e .git) evita falsi positivi
    senza dover elencare eccezioni a mano ogni volta che si aggiunge una
    sotto-app con questo stesso pattern.
    """
    names = set()
    skip = {"tests", "__pycache__", ".venv", ".git"}
    for py_file in REPO_ROOT.rglob("*.py"):
        rel_parts = py_file.relative_to(REPO_ROOT).parts
        if rel_parts[0] in skip or any(p in skip for p in rel_parts):
            continue
        names.add(py_file.stem)
    for init_file in REPO_ROOT.glob("*/__init__.py"):
        if any(p in skip for p in init_file.relative_to(REPO_ROOT).parts):
            continue
        names.add(init_file.parent.name)
    return names


def _iter_project_py_files():
    skip = {"tests", "__pycache__", ".venv", ".git"}
    for py_file in REPO_ROOT.rglob("*.py"):
        rel = py_file.relative_to(REPO_ROOT)
        parts = rel.parts
        if parts[0] in skip or any(p in skip for p in parts):
            continue
        yield py_file


def _extract_top_level_imports(py_file: Path) -> set:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # import relativo (es. "from . import x"): sempre locale
            if node.module:
                names.add(node.module.split(".")[0])
    return names


class TestRequirementsCoverage(unittest.TestCase):
    """Ogni import di terze parti usato nel codice deve comparire in
    requirements.txt. Aggiungere un modulo nuovo con un import esterno nuovo
    fara' fallire questo test finche' non viene aggiunto a requirements.txt
    — e' il comportamento voluto."""

    @classmethod
    def setUpClass(cls):
        cls.local_modules = _local_module_names()
        req_path = REPO_ROOT / "requirements.txt"
        cls.requirements_raw = req_path.read_text(encoding="utf-8").lower() if req_path.exists() else ""

        cls.found_third_party = set()
        for py_file in _iter_project_py_files():
            for name in _extract_top_level_imports(py_file):
                if name in IGNORE_TOP_LEVEL or name in cls.local_modules:
                    continue
                if name in sys.stdlib_module_names:
                    continue
                cls.found_third_party.add(name)

    def test_requirements_txt_esiste(self):
        self.assertTrue((REPO_ROOT / "requirements.txt").exists())

    def test_ogni_import_esterno_e_in_requirements(self):
        mancanti = []
        for name in sorted(self.found_third_party):
            package = IMPORT_TO_PACKAGE.get(name, name)
            if package.lower() not in self.requirements_raw:
                mancanti.append(f"{name} (pacchetto atteso: {package})")
        self.assertFalse(
            mancanti,
            "Import di terze parti usati nel codice ma assenti da requirements.txt: "
            + ", ".join(mancanti) +
            ". Se e' un nuovo import legittimo, aggiungilo a requirements.txt. "
            "Se e' un modulo locale non riconosciuto come tale, aggiungilo a "
            "IGNORE_TOP_LEVEL o verifica _local_module_names() in questo file."
        )


class TestSchemaBaseSanity(unittest.TestCase):
    """Controlli generici sullo schema creato da database.init_db(), utili
    come guardrail quando si aggiungono nuove tabelle/colonne."""

    def test_init_db_non_richiede_argomenti_di_configurazione(self):
        """init_db() deve restare chiamabile senza parametri (e' invocata
        cosi' da app.py allo startup): se in futuro richiedesse argomenti,
        romperebbe lo startup dell'app."""
        import inspect
        import database
        sig = inspect.signature(database.init_db)
        obbligatori = [p for p in sig.parameters.values()
                       if p.default is inspect.Parameter.empty
                       and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
        self.assertEqual(obbligatori, [])


if __name__ == "__main__":
    unittest.main()
