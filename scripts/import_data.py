"""
Batch import script: recursively scan a directory and upload files to LLM Wiki.

Usage:
    python scripts/import_data.py /path/to/your/materials --api-url http://localhost:8000
"""

import argparse
import mimetypes
from pathlib import Path

import httpx

SUPPORTED_EXTENSIONS = {
    # Source code
    ".c", ".h", ".cpp", ".hpp", ".java", ".py", ".js", ".ts", ".rs", ".go",
    # Documents
    ".md", ".txt", ".pdf", ".doc", ".docx", ".ini", ".cfg", ".conf",
    ".json", ".yaml", ".yml",
    # Schematics
    ".sch", ".schdoc", ".kicad_sch", ".brd", ".pcbdoc",
}


def scan_directory(path: Path) -> list[Path]:
    """Recursively find all supported files."""
    files = []
    for f in path.rglob("*"):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return sorted(files)


def upload_file(api_url: str, file_path: Path, base_dir: Path, api_key: str):
    """Upload a single file to the wiki."""
    relative_path = file_path.relative_to(base_dir)
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    with open(file_path, "rb") as f:
        response = httpx.post(
            f"{api_url}/api/upload/",
            files={"file": (file_path.name, f, mime_type)},
            data={
                "title": str(relative_path),
                "tags": ",".join(relative_path.parts[:-1]),  # Use directory path as tags
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    if response.status_code == 200:
        data = response.json()
        print(f"  ✓ {relative_path} → {data['document_id']} ({data['doc_type']})")
    else:
        print(f"  ✗ {relative_path} → {response.status_code}: {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Batch import files into LLM Wiki")
    parser.add_argument("directory", type=Path, help="Directory to scan")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--api-key", default="change_me_in_production", help="API key")
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a directory")
        return

    files = scan_directory(args.directory)
    print(f"Found {len(files)} files to import from {args.directory}\n")

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Uploading {file_path.name}...")
        upload_file(args.api_url, file_path, args.directory, args.api_key)

    print(f"\nDone! Imported {len(files)} files.")


if __name__ == "__main__":
    main()
