"""Create or repair the initial super admin account safely."""

from app import app
from models import db, User


TARGET_EMAIL = 'admin@gmail.com'
TARGET_PASSWORD = 'admin123456'
TARGET_ROLE = 'super_admin'
TARGET_STATUS = 'active'


def main():
    with app.app_context():
        user = User.query.filter_by(email=TARGET_EMAIL).first()

        if user is None:
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

        user.role = TARGET_ROLE
        user.status = TARGET_STATUS
        user.set_password(TARGET_PASSWORD)
        db.session.commit()
        print(f'已更新既有帳號為 super_admin: {TARGET_EMAIL}')


if __name__ == '__main__':
    main()