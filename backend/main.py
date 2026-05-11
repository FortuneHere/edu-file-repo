# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os

from database import engine, Base, get_db
from models import User, File as FileModel, Ticket
from schemas import UserCreate, UserLogin, Token, TicketCreate, DownloadLinkResponse
from auth import get_password_hash, verify_password, create_access_token, get_current_user
from s3_service import S3Service, S3ConfigurationError, S3UploadError
from utils import make_admin

load_dotenv()

app = FastAPI(title="Edu File Repository")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

try:
    s3_service = S3Service()
    s3_init_error = None
except S3ConfigurationError as exc:
    s3_service = None
    s3_init_error = str(exc)

# ====================== ЭНДПОИНТЫ ======================


def serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "attachment_s3_key": ticket.attachment_s3_key,
        "created_at": ticket.created_at,
        "user_email": ticket.user.email if ticket.user else None,
    }

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
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
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

    object_name = f"{folder}/{file.filename}"

    try:
        file.file.seek(0)
        s3_service.upload_file(file.file, object_name)

        new_file = FileModel(
            filename=file.filename,
            s3_key=object_name,
            folder_path=folder,
            uploaded_by=current_user.email
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return {
            "message": "Файл успешно загружен в Yandex Object Storage",
            "filename": file.filename,
            "s3_key": object_name
        }
    except S3UploadError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Ошибка S3: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/files")
def get_files(folder: str = "root", db: Session = Depends(get_db)):
    files = db.query(FileModel).filter(FileModel.folder_path == folder).all()
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


@app.get("/tickets")
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tickets = db.query(Ticket).filter(Ticket.user_id == current_user.id).all()
    return [serialize_ticket(ticket) for ticket in tickets]


@app.post("/tickets", status_code=201)
def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_ticket = Ticket(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return serialize_ticket(new_ticket)

if __name__ == "__main__":
    import uvicorn
    from database import SessionLocal

    # Делаем первого пользователя администратором
    db = SessionLocal()
    make_admin("admin@project.ru", db)
    db.close()

    uvicorn.run(app, host="127.0.0.1", port=8000)