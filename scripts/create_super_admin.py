"""
scripts/create_super_admin.py: 建立或修復超級管理員帳號。
使用方式：在專案根目錄執行 python scripts/create_super_admin.py
若目標 Email 的帳號不存在，則建立新帳號；若已存在，則強制更新其角色和密碼。
"""

from app import app
from models import db, User


# 超級管理員帳號的預設設定
TARGET_EMAIL = 'admin@gmail.com'
TARGET_PASSWORD = 'admin123456'
TARGET_ROLE = 'super_admin'
TARGET_STATUS = 'active'


def main():
    """
    主執行函數。
    在 Flask 應用程式上下文中執行，確保可以存取資料庫。
    建立或更新超級管理員帳號，執行結果印出到終端機。
    """
    with app.app_context():
        # 查詢是否已存在此 Email 的帳號
        user = User.query.filter_by(email=TARGET_EMAIL).first()

        if user is None:
            # 帳號不存在，建立新的超級管理員
            user = User(
                name='系統管理者',
                email=TARGET_EMAIL,
                role=TARGET_ROLE,
                status=TARGET_STATUS,
                bio='最高權限管理員',
            )
            user.set_password(TARGET_PASSWORD)
            db.session.add(user)
            db.session.commit()
            print(f'已建立 super_admin 帳號: {TARGET_EMAIL}')
            return

        # 帳號已存在，強制更新角色、狀態和密碼（用於修復被降權的管理員帳號）
        user.role = TARGET_ROLE
        user.status = TARGET_STATUS
        user.set_password(TARGET_PASSWORD)
        db.session.commit()
        print(f'已更新既有帳號為 super_admin: {TARGET_EMAIL}')


if __name__ == '__main__':
    main()
