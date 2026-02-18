import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("PYTHON:", sys.version)
print("CWD:", os.getcwd())

try:
    from config import REPOS, SERVICES, LIBRARIAN_DB, SAPPHIRE_DB
    print("CONFIG: OK")
    print("  LIBRARIAN_DB:", LIBRARIAN_DB, "exists:", LIBRARIAN_DB.exists())
    print("  SAPPHIRE_DB:", SAPPHIRE_DB, "exists:", SAPPHIRE_DB.exists())
    for name, path in REPOS.items():
        print(f"  REPO {name}: {path} exists: {path.exists()}")
except Exception as e:
    print("CONFIG ERR:", e)

try:
    import httpx
    print("HTTPX: OK")
except ImportError:
    print("HTTPX: MISSING - install with: pip install httpx")

try:
    from scanner import scan_repo, scan_librarian
    print("SCANNER: OK")
    lib = scan_librarian(LIBRARIAN_DB)
    print(f"  LIBRARIAN: readable={lib.readable}, total={lib.total_guidance}, focus={lib.current_focus_count}")
except Exception as e:
    print("SCANNER ERR:", e)

print("DONE")
