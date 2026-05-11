# backend/utils.py
from sqlalchemy.orm import Session
from models import User

def make_admin(email: str, db: Session):
    """Сделать пользователя администратором"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.role = "admin"
        db.commit()
        db.refresh(user)
        print(f"✅ Пользователь {email} теперь администратор!")
        return True
    else:
        print(f"❌ Пользователь {email} не найден")
        return False