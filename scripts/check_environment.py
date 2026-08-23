import sys
import importlib.metadata

REQUIRED_PACKAGES = [
    "fastapi",
    "pydantic",
    "pydantic-settings",
    "google-adk",
    "google-genai",
    "google-cloud-firestore",
    "google-cloud-pubsub",
    "google-cloud-storage",
    "google-cloud-secret-manager",
    "reportlab",
    "python-dotenv",
    "pytest",
    "httpx",
    "uvicorn",
]


def check_python_version() -> bool:
    """Verify that Python version is >= 3.10."""
    major, minor = sys.version_info[:2]
    status = major > 3 or (major == 3 and minor >= 10)
    print(f"Python Version: {sys.version.split()[0]} -> {'OK' if status else 'FAIL'}")
    return status


def check_package_versions() -> dict[str, str]:
    """Inspect actual installed package versions."""
    versions = {}
    print("\n--- Installed Dependency Audit ---")
    for pkg in REQUIRED_PACKAGES:
        try:
            ver = importlib.metadata.version(pkg)
            versions[pkg] = ver
            print(f"  {pkg:30s}: {ver}")
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "NOT INSTALLED"
            print(f"  {pkg:30s}: NOT INSTALLED")
    return versions


def verify_sdk_imports() -> bool:
    """Verify core SDK module imports."""
    print("\n--- Core SDK Import Verification ---")
    all_passed = True
    imports_to_test = [
        ("FastAPI", "import fastapi"),
        ("Pydantic", "import pydantic"),
        ("Google ADK", "import google.adk"),
        ("Google GenAI", "import google.genai"),
        ("Google Cloud Firestore", "import google.cloud.firestore"),
        ("Google Cloud PubSub", "import google.cloud.pubsub"),
        ("Google Cloud Storage", "import google.cloud.storage"),
        ("Google Cloud Secret Manager", "import google.cloud.secretmanager"),
        ("ReportLab", "import reportlab"),
        ("HTTPX", "import httpx"),
        ("Pytest", "import pytest"),
    ]

    for name, statement in imports_to_test:
        try:
            exec(statement)
            print(f"  {name:30s}: SUCCESS")
        except Exception as err:
            all_passed = False
            print(f"  {name:30s}: FAILED ({err})")
    return all_passed


def main():
    print("================================================")
    print(" PaperTrail AI — Environment & Dependency Check ")
    print("================================================")
    py_ok = check_python_version()
    versions = check_package_versions()
    imports_ok = verify_sdk_imports()

    print("\n------------------------------------------------")
    if py_ok and imports_ok and all(v != "NOT INSTALLED" for v in versions.values()):
        print("RESULT: ALL ENVIRONMENT CHECKS PASSED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print("RESULT: ENVIRONMENT CHECKS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
