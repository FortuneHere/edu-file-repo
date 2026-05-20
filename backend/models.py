# backend/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False)
    role = Column(String, default="user")          # "user" или "admin"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связь с файлами и тикетами
    uploaded_files = relationship("File", back_populates="uploaded_by_user")
    tickets = relationship("Ticket", back_populates="user")


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    s3_key = Column(String, unique=True, nullable=False)        # путь в Yandex Object Storage
    folder_path = Column(String, default="root")
    summary = Column(Text, nullable=True)                       # от YandexGPT
    tags = Column(String, nullable=True)                        # "алгоритмы,сортировка,лаб3"
    hidden = Column(Boolean, default=False)
    uploaded_by = Column(String, ForeignKey("users.email"))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    uploaded_by_user = relationship("User", back_populates="uploaded_files")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, unique=True, index=True, nullable=False)
    created_by = Column(String, ForeignKey("users.email"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    attachment_s3_key = Column(String, nullable=True)           # если пользователь прикрепил файл/фото
    status = Column(String, default="new")                      # new, reviewed, added, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="tickets")
    attachments = relationship(
        "TicketAttachment",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    filename = Column(String, nullable=False)
    s3_key = Column(String, unique=True, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="attachments")