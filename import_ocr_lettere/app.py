import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import (
    init_db, save_letter, get_all_letters, get_letter, delete_letter,
    export_excel, UPLOAD_DIR,
)
from ocr_engine import run_ocr

app = FastAPI(title="OCR Lettere dal Fronte", version="1.0.0")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


@app.on_event("startup")
def startup():
    init_db()
    UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            saved.append({"filename": f.filename, "error": f"Formato non supportato: {ext}"})
            continue
        dest = UPLOAD_DIR / f.filename
        with open(dest, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved.append({"filename": f.filename, "path": str(dest), "size": dest.stat().st_size})
    return {"files": saved}


@app.post("/api/ocr/{filename}")
def process_ocr(filename: str):
    img_path = UPLOAD_DIR / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"File non trovato: {filename}")

    try:
        data = run_ocr(str(img_path))
        data["_file_path"] = str(img_path)
        rid = save_letter(data)
        return {"id": rid, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ocr-batch")
def process_ocr_batch(filenames: list[str] = None):
    results = []
    if filenames:
        files_to_process = [UPLOAD_DIR / f for f in filenames]
    else:
        files_to_process = list(UPLOAD_DIR.iterdir())

    for img_path in files_to_process:
        if img_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            data = run_ocr(str(img_path))
            data["_file_path"] = str(img_path)
            rid = save_letter(data)
            results.append({"id": rid, "filename": img_path.name, "status": "ok", "data": data})
        except Exception as e:
            results.append({"filename": img_path.name, "status": "error", "error": str(e)})

    return {"results": results, "total": len(results)}


@app.get("/api/letters")
def list_letters():
    return {"letters": get_all_letters()}


@app.get("/api/letters/{rid}")
def get_letter_detail(rid: int):
    letter = get_letter(rid)
    if not letter:
        raise HTTPException(status_code=404, detail="Lettera non trovata")
    return letter


@app.delete("/api/letters/{rid}")
def remove_letter(rid: int):
    if not delete_letter(rid):
        raise HTTPException(status_code=404, detail="Lettera non trovata")
    return {"deleted": True}


@app.get("/api/export/excel")
def download_excel():
    output = export_excel()
    return FileResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="export_lettere.xlsx",
    )


@app.get("/api/uploads")
def list_uploads():
    files = []
    for p in UPLOAD_DIR.iterdir():
        if p.suffix.lower() in ALLOWED_EXTENSIONS:
            files.append({
                "filename": p.name,
                "size": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            })
    return {"files": sorted(files, key=lambda x: x["modified"], reverse=True)}


@app.get("/api/uploads/{filename}")
def serve_upload(filename: str):
    img_path = UPLOAD_DIR / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")
    return FileResponse(str(img_path))
