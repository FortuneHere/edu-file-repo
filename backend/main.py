# backend/main.py
from datetime import datetime
from io import BytesIO
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import engine, Base, get_db
from models import Folder, User, File as FileModel, Ticket, TicketAttachment
from schemas import (
    DownloadLinkResponse,
    FileUpdate,
    FolderCreate,
    TicketCreate,
    Token,
    UserCreate,
)
from auth import get_password_hash, verify_password, create_access_token, get_current_user
from ai_service import AISummaryService, AIConfigurationError
from s3_service import S3Service, S3ConfigurationError, S3UploadError
from utils import make_admin

load_dotenv()

MAX_TICKETS_PER_USER = 5
MAX_ATTACHMENTS_PER_TICKET = 10

app = FastAPI(title="Edu File Repository")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def apply_runtime_migrations() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "files" in table_names:
        file_columns = {column["name"] for column in inspector.get_columns("files")}
        if "hidden" not in file_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE files ADD COLUMN hidden BOOLEAN DEFAULT FALSE"))


apply_runtime_migrations()

try:
    s3_service = S3Service()
    s3_init_error = None
except S3ConfigurationError as exc:
    s3_service = None
    s3_init_error = str(exc)

try:
    ai_summary_service = AISummaryService()
    ai_init_error = None
except AIConfigurationError as exc:
    ai_summary_service = None
    ai_init_error = str(exc)

# ====================== ЭНДПОИНТЫ ======================


def normalize_folder_path(path: str) -> str:
    normalized = (path or "root").strip().replace("\\", "/")
    normalized = "/".join([part for part in normalized.split("/") if part])
    return normalized or "root"


def ensure_folder_path_exists(folder_path: str, db: Session, created_by: Optional[str] = None) -> None:
    normalized = normalize_folder_path(folder_path)
    parts = normalized.split("/")
    current_path = ""
    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part
        exists = db.query(Folder).filter(Folder.path == current_path).first()
        if not exists:
            db.add(Folder(path=current_path, created_by=created_by))
    db.flush()


def get_all_folder_paths(db: Session):
    folder_paths = {row[0] for row in db.query(Folder.path).all()}
    file_paths = {row[0] for row in db.query(FileModel.folder_path).all()}
    return {"root"} | folder_paths | file_paths


def build_folder_tree(paths):
    nodes = {"root": {"name": "root", "path": "root", "children_map": {}}}
    for full_path in sorted(paths):
        normalized = normalize_folder_path(full_path)
        if normalized == "root":
            continue
        parts = normalized.split("/")
        current = nodes["root"]
        current_path = "root"
        if parts[0] == "root":
            parts = parts[1:]
        for part in parts:
            current_path = f"{current_path}/{part}"
            if part not in current["children_map"]:
                current["children_map"][part] = {
                    "name": part,
                    "path": current_path,
                    "children_map": {},
                }
            current = current["children_map"][part]

    def to_payload(node):
        children = [to_payload(child) for child in node["children_map"].values()]
        children.sort(key=lambda item: item["name"])
        return {"name": node["name"], "path": node["path"], "children": children}

    return to_payload(nodes["root"])


def serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "attachment_s3_key": ticket.attachment_s3_key,
        "created_at": ticket.created_at,
        "user_email": ticket.user.email if ticket.user else None,
        "attachments": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "s3_key": attachment.s3_key,
                "uploaded_at": attachment.uploaded_at,
            }
            for attachment in ticket.attachments
        ],
    }


def require_admin(current_user: User) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Только администратор может выполнять это действие")


def delete_ticket_attachments(ticket_id: int, db: Session) -> None:
    attachments = db.query(TicketAttachment).filter(TicketAttachment.ticket_id == ticket_id).all()
    if s3_service is not None:
        for attachment in attachments:
            try:
                s3_service.delete_object(attachment.s3_key)
            except S3UploadError as exc:
                raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(exc)}")

    for attachment in attachments:
        db.delete(attachment)

@app.get("/")
def root():
    return {"message": "Edu File Repository API работает! 🚀"}

@app.post("/register", status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    try:
        hashed_password = get_password_hash(user.password)
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Не удалось обработать пароль")

    new_user = User(email=user.email, hashed_password=hashed_password, role="user")
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    db.refresh(new_user)
    return {"message": "Пользователь создан"}

@app.post("/token", response_model=Token)
async def login(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    email = None
    password = None

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        email = form.get("username") or form.get("email")
        password = form.get("password")
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        email = payload.get("email") or payload.get("username")
        password = payload.get("password")

    if not email or not password:
        raise HTTPException(
            status_code=422,
            detail="Нужно передать email/username и password",
        )

    db_user = db.query(User).filter(User.email == email).first()
    if not db_user or not verify_password(password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# ====================== ЗАГРУЗКА ФАЙЛА (только админ) ======================
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Form("root"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(403, detail="Только администратор может загружать файлы")

    if s3_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"S3 сервис не настроен: {s3_init_error}",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="Разрешены только PDF файлы")

    normalized_folder = normalize_folder_path(folder)
    object_name = f"{normalized_folder}/{file.filename}"

    try:
        file.file.seek(0)
        file_bytes = file.file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Файл пустой")

        s3_service.upload_file(
            BytesIO(file_bytes),
            object_name,
            content_type=file.content_type or "application/pdf",
        )
        ensure_folder_path_exists(normalized_folder, db, created_by=current_user.email)

        summary = None
        summary_warning = None
        if ai_summary_service is not None:
            try:
                summary = ai_summary_service.summarize_pdf(file_bytes)
            except Exception as exc:
                summary_warning = str(exc)
        else:
            summary_warning = f"AI суммаризация отключена: {ai_init_error}"

        new_file = FileModel(
            filename=file.filename,
            s3_key=object_name,
            folder_path=normalized_folder,
            uploaded_by=current_user.email,
            summary=summary,
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return {
            "message": "Файл успешно загружен в Yandex Object Storage",
            "filename": file.filename,
            "s3_key": object_name,
            "summary": summary,
            "summary_warning": summary_warning,
        }
    except S3UploadError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(e)}")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/files")
def get_files(
    folder: str = "root",
    include_hidden: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_folder = normalize_folder_path(folder)
    files_query = db.query(FileModel).filter(FileModel.folder_path == normalized_folder)
    if not include_hidden or current_user.role != "admin":
        files_query = files_query.filter(FileModel.hidden.is_(False))
    files = files_query.order_by(FileModel.filename.asc()).all()
    return files


@app.get("/files/download-link", response_model=DownloadLinkResponse)
def get_file_download_link(
    s3_key: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    if s3_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"S3 сервис не настроен: {s3_init_error}",
        )

    file_record = db.query(FileModel).filter(FileModel.s3_key == s3_key).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Файл не найден")

    try:
        url = s3_service.generate_presigned_url(
            s3_key,
            expires_in=expires_in,
            download_filename=file_record.filename,
        )
        return {
            "download_url": url,
            "filename": file_record.filename,
            "expires_in": expires_in,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка генерации ссылки для скачивания: {str(e)}",
        )


@app.post("/folders", status_code=201)
def create_folder(
    payload: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    normalized = normalize_folder_path(payload.path)
    ensure_folder_path_exists(normalized, db, created_by=current_user.email)
    db.commit()
    return {"path": normalized}


@app.get("/folders/tree")
def get_folder_tree(db: Session = Depends(get_db)):
    paths = get_all_folder_paths(db)
    return build_folder_tree(paths)


@app.patch("/files/{file_id}")
def update_file(
    file_id: int,
    payload: FileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    db_file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="Файл не найден")

    target_folder = normalize_folder_path(payload.folder_path or db_file.folder_path)
    target_filename = (payload.filename or db_file.filename).strip()
    if not target_filename:
        raise HTTPException(status_code=400, detail="Имя файла не может быть пустым")

    target_s3_key = f"{target_folder}/{target_filename}"
    requires_storage_rename = target_s3_key != db_file.s3_key

    if requires_storage_rename:
        if s3_service is None:
            raise HTTPException(
                status_code=500,
                detail=f"S3 сервис не настроен: {s3_init_error}",
            )
        try:
            s3_service.rename_object(db_file.s3_key, target_s3_key)
        except S3UploadError as exc:
            raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(exc)}")

    db_file.filename = target_filename
    db_file.folder_path = target_folder
    db_file.s3_key = target_s3_key

    if payload.hidden is not None:
        db_file.hidden = payload.hidden

    ensure_folder_path_exists(target_folder, db, created_by=current_user.email)
    db.commit()
    db.refresh(db_file)
    return db_file


@app.delete("/files/{file_id}")
def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    db_file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="Файл не найден")

    if s3_service is not None:
        try:
            s3_service.delete_object(db_file.s3_key)
        except S3UploadError as exc:
            raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(exc)}")

    db.delete(db_file)
    db.commit()
    return {"message": "Файл удален"}


@app.delete("/folders")
def delete_folder(
    path: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    normalized = normalize_folder_path(path)
    if normalized == "root":
        raise HTTPException(status_code=400, detail="Нельзя удалить корневую папку root")

    has_files = (
        db.query(FileModel)
        .filter(FileModel.folder_path == normalized)
        .first()
        is not None
    )
    if has_files:
        raise HTTPException(status_code=400, detail="Нельзя удалить непустую папку: в ней есть файлы")

    child_prefix = f"{normalized}/"
    has_child_folders = (
        db.query(Folder)
        .filter(Folder.path.like(f"{child_prefix}%"))
        .first()
        is not None
    )
    if has_child_folders:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить папку: сначала удалите вложенные подпапки",
        )

    folder = db.query(Folder).filter(Folder.path == normalized).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Папка не найдена")

    db.delete(folder)
    db.commit()
    return {"message": "Папка удалена"}


@app.delete("/users/me")
def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploaded_files_count = (
        db.query(FileModel).filter(FileModel.uploaded_by == current_user.email).count()
    )
    if uploaded_files_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить аккаунт: у пользователя есть загруженные методички",
        )

    my_tickets = db.query(Ticket).filter(Ticket.user_id == current_user.id).all()
    for ticket in my_tickets:
        delete_ticket_attachments(ticket.id, db)
        db.delete(ticket)

    db.delete(current_user)
    db.commit()
    return {"message": "Аккаунт удален"}


@app.get("/tickets")
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tickets = (
        db.query(Ticket)
        .filter(Ticket.user_id == current_user.id)
        .order_by(Ticket.created_at.desc())
        .all()
    )
    return [serialize_ticket(ticket) for ticket in tickets]


@app.get("/admin/tickets")
def get_all_tickets_for_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    return [serialize_ticket(ticket) for ticket in tickets]


@app.get("/admin/tickets/{ticket_id}/attachments/{attachment_id}/download-link", response_model=DownloadLinkResponse)
def get_ticket_attachment_download_link(
    ticket_id: int,
    attachment_id: int,
    expires_in: int = Query(default=3600, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    if s3_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"S3 сервис не настроен: {s3_init_error}",
        )
    attachment = (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.id == attachment_id,
            TicketAttachment.ticket_id == ticket_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Вложение тикета не найдено")

    try:
        url = s3_service.generate_presigned_url(
            attachment.s3_key,
            expires_in=expires_in,
            download_filename=attachment.filename,
        )
        return {
            "download_url": url,
            "filename": attachment.filename,
            "expires_in": expires_in,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка генерации ссылки для скачивания: {str(e)}",
        )


@app.post("/tickets", status_code=201)
def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_tickets = db.query(Ticket).filter(Ticket.user_id == current_user.id).count()
    if current_tickets >= MAX_TICKETS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Ограничение: максимум {MAX_TICKETS_PER_USER} тикетов на пользователя",
        )

    new_ticket = Ticket(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return serialize_ticket(new_ticket)


@app.post("/tickets/{ticket_id}/attachments")
async def add_ticket_attachments(
    ticket_id: int,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if s3_service is None:
        raise HTTPException(
            status_code=500,
            detail=f"S3 сервис не настроен: {s3_init_error}",
        )

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == current_user.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")

    if not files:
        raise HTTPException(status_code=400, detail="Не выбраны файлы для загрузки")

    existing_count = db.query(TicketAttachment).filter(TicketAttachment.ticket_id == ticket_id).count()
    if existing_count + len(files) > MAX_ATTACHMENTS_PER_TICKET:
        raise HTTPException(
            status_code=400,
            detail=f"Ограничение: максимум {MAX_ATTACHMENTS_PER_TICKET} файлов на тикет",
        )

    uploaded_attachments = []
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    for index, attachment in enumerate(files):
        clean_name = attachment.filename.replace("/", "_").replace("\\", "_")
        object_name = f"tickets/{current_user.id}/{ticket_id}/{timestamp}_{index}_{clean_name}"
        try:
            attachment.file.seek(0)
            s3_service.upload_file(
                attachment.file,
                object_name,
                content_type=attachment.content_type or "application/octet-stream",
            )
        except S3UploadError as exc:
            db.rollback()
            raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(exc)}")

        uploaded_attachments.append(
            TicketAttachment(
                ticket_id=ticket_id,
                filename=attachment.filename,
                s3_key=object_name,
            )
        )

    db.add_all(uploaded_attachments)
    db.commit()
    db.refresh(ticket)
    return serialize_ticket(ticket)


@app.delete("/admin/tickets/{ticket_id}")
def delete_ticket_for_admin(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")

    delete_ticket_attachments(ticket_id, db)
    if ticket.attachment_s3_key and s3_service is not None:
        try:
            s3_service.delete_object(ticket.attachment_s3_key)
        except S3UploadError as exc:
            raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(exc)}")

    db.delete(ticket)
    db.commit()
    return {"message": "Тикет удален"}

if __name__ == "__main__":
    import uvicorn
    from database import SessionLocal

    # Делаем первого пользователя администратором
    db = SessionLocal()
    make_admin("admin@project.ru", db)
    db.close()

    uvicorn.run(app, host="127.0.0.1", port=8000)