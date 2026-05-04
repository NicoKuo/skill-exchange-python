"""Create or repair the initial super admin account safely."""

from app import app
from models import db, User


TARGET_EMAIL = 'admin@gmail.com'
TARGET_NAME = '系統管理者'
TARGET_PASSWORD = 'admin123456'
TARGET_ROLE = 'super_admin'
TARGET_STATUS = 'active'


def main():
    with app.app_context():
        user = User.query.filter_by(email=TARGET_EMAIL).first()

        if user is None:
            user = User(
                name=TARGET_NAME,
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

        changed = False

        if user.name != TARGET_NAME:
            user.name = TARGET_NAME
            changed = True

        if user.role != TARGET_ROLE:
            user.role = TARGET_ROLE
            changed = True

        if getattr(user, 'status', None) != TARGET_STATUS:
            user.status = TARGET_STATUS
            changed = True

        if not user.check_password(TARGET_PASSWORD):
            user.set_password(TARGET_PASSWORD)
            changed = True

        if changed:
            db.session.commit()
            print(f'已更新既有帳號為 super_admin: {TARGET_EMAIL}')
        else:
            print(f'super_admin 已存在，未重複建立: {TARGET_EMAIL}')


if __name__ == '__main__':
    main()