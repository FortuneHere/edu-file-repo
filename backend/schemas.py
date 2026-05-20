# backend/schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

# ====================== Пользователи ======================
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_verified: bool
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

# ====================== Файлы ======================
class FileBase(BaseModel):
    filename: str
    folder_path: str = "root"
    summary: Optional[str] = None
    tags: Optional[str] = None

class FileResponse(FileBase):
    id: int
    s3_key: str
    uploaded_by: str
    uploaded_at: datetime
    hidden: bool

    class Config:
        from_attributes = True


class DownloadLinkResponse(BaseModel):
    download_url: str
    filename: str
    expires_in: int


class FolderCreate(BaseModel):
    path: str


class FolderTreeNode(BaseModel):
    name: str
    path: str
    children: List["FolderTreeNode"] = Field(default_factory=list)


class FileUpdate(BaseModel):
    filename: Optional[str] = None
    hidden: Optional[bool] = None
    folder_path: Optional[str] = None

# ====================== Тикеты ======================
class TicketCreate(BaseModel):
    title: str
    description: Optional[str] = None


class TicketAttachmentResponse(BaseModel):
    id: int
    filename: str
    s3_key: str
    uploaded_at: datetime

    class Config:
        from_attributes = True

class TicketResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    attachment_s3_key: Optional[str]
    created_at: datetime
    user_email: Optional[str]
    attachments: List[TicketAttachmentResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

# ====================== JWT ======================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None


if hasattr(FolderTreeNode, "model_rebuild"):
    FolderTreeNode.model_rebuild()
else:
    FolderTreeNode.update_forward_refs()