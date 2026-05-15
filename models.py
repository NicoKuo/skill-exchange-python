# models.py: SQLAlchemy 資料模型定義與 db 實例
# 每個 class 對應資料庫中的一張資料表
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# 建立 SQLAlchemy 實例，稍後在 create_app() 中用 db.init_app(app) 綁定
db = SQLAlchemy()


class User(UserMixin, db.Model):
    """
    使用者帳號資料表（users）。
    UserMixin 提供 Flask-Login 所需的 is_authenticated、is_active 等屬性。
    """
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)               # 顯示名稱
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)  # 登入用 Email
    password_hash = db.Column(db.String(255), nullable=False)      # 雜湊後的密碼
    role = db.Column(db.String(20), default='user', nullable=False) # 角色：user / admin / super_admin
    bio = db.Column(db.Text, default='')                           # 自我介紹
    avatar = db.Column(db.String(255))                             # 頭像 URL
    department = db.Column(db.String(100), nullable=True)          # 系所
    grade = db.Column(db.String(50), nullable=True)                # 年級
    offered_skills_intro = db.Column(db.Text, nullable=True)       # 可提供的技能簡介
    wanted_skills_intro = db.Column(db.Text, nullable=True)        # 想學習的技能簡介
    status = db.Column(db.String(20), default='active', nullable=False)  # 帳號狀態：active / suspended / banned
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)  # 累計登入失敗次數
    locked_until = db.Column(db.DateTime, nullable=True)           # 帳號鎖定到此時間（防暴力破解）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)   # 帳號建立時間

    # 一對多關係：一個使用者可以有多個技能，刪除使用者時一併刪除技能
    skills = db.relationship('Skill', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        """將明文密碼雜湊後儲存（使用 Werkzeug 的 generate_password_hash）。"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """驗證輸入的明文密碼是否與儲存的雜湊值相符。"""
        return check_password_hash(self.password_hash, password)


class SkillCategory(db.Model):
    """
    技能分類資料表（skill_categories）。
    用於將技能歸類，如「學業課業」、「語言學習」等。
    """
    __tablename__ = 'skill_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)    # 分類名稱（唯一）
    description = db.Column(db.String(255))                        # 分類描述


class Skill(db.Model):
    """
    技能資料表（skills）。
    記錄使用者上架的技能，包含提供或想學的技能、地點、時間、附件等資訊。
    """
    __tablename__ = 'skills'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)          # 擁有者
    category_id = db.Column(db.Integer, db.ForeignKey('skill_categories.id'))           # 所屬分類
    title = db.Column(db.String(50), nullable=False)                                    # 技能標題（最多50字）
    description = db.Column(db.Text, nullable=False)                                    # 技能描述
    tags = db.Column(db.Text)                                                           # 標籤（逗號分隔）
    type = db.Column(db.String(20), nullable=False)      # 技能類型：offer（提供）/ learn（想學）
    method = db.Column(db.String(20), default='online')  # 教學方式：online / offline / both
    location_type = db.Column(db.String(20))             # 地點類型：online / campus / off_campus
    location_area = db.Column(db.String(50))             # 地區（如「台北」）
    location_detail = db.Column(db.String(100))          # 詳細地點說明
    available_day = db.Column(db.String(20))             # 可配合星期（如 mon / weekend / flexible）
    start_time = db.Column(db.Time)                      # 可配合開始時間
    end_time = db.Column(db.Time)                        # 可配合結束時間
    status = db.Column(db.String(20), default='open')    # 技能狀態：open / closed
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 是否上架中（下架為 False）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)     # 上架時間
    # 附件相關欄位（儲存在資料庫 BLOB 中）
    attachment_data = db.Column(db.LargeBinary, nullable=True)   # 附件二進位資料
    attachment_name = db.Column(db.Text, nullable=True)          # 原始檔名
    attachment_mime = db.Column(db.Text, nullable=True)          # MIME 類型（如 image/png）
    attachment_type = db.Column(db.Text, nullable=True)          # 附件種類：image / pdf / file
    attachment_url = db.Column(db.Text, nullable=True)           # 外部附件 URL（舊版相容）

    # 多對一關係：技能屬於某個分類
    category = db.relationship('SkillCategory')


class Match(db.Model):
    """
    媒合（配對）資料表（matches）。
    記錄使用者之間的技能交換申請與狀態。
    狀態流程：pending（待回應）→ accepted（已接受）→ completed（已完成）
    """
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)        # 目標技能
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)     # 申請方
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)      # 被申請方
    message = db.Column(db.String(255))                                                 # 申請附帶訊息
    status = db.Column(db.String(20), default='pending')  # 狀態：pending / accepted / rejected / completed / cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skill = db.relationship('Skill')
    requester = db.relationship('User', foreign_keys=[requester_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Message(db.Model):
    """
    聊天訊息資料表（messages）。
    記錄媒合雙方在聊天室中的對話，支援文字與檔案附件。
    """
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))                       # 所屬媒合
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)        # 發送者
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)      # 接收者
    content = db.Column(db.Text, nullable=False)        # 訊息內容（純文字）
    file_url = db.Column(db.String(255))                # 附件檔案 URL
    file_name = db.Column(db.String(255))               # 附件原始檔名
    file_type = db.Column(db.String(30))                # 附件類型：image / file
    is_read = db.Column(db.Boolean, default=False)      # 是否已讀
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    match = db.relationship('Match')
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Review(db.Model):
    """
    互評資料表（reviews）。
    媒合完成後，雙方可對彼此進行 1-5 星評分與文字評論。
    """
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)       # 所屬媒合
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)      # 評分者
    reviewee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)      # 被評分者
    rating = db.Column(db.Integer, nullable=False)      # 評分（1-5 星）
    comment = db.Column(db.Text)                        # 文字評論
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    match = db.relationship('Match')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])
    reviewee = db.relationship('User', foreign_keys=[reviewee_id])


class Notification(db.Model):
    """
    通知資料表（notifications）。
    系統事件（媒合邀請、新訊息、評價等）會自動產生通知給相關使用者。
    """
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # 接收通知的使用者
    type = db.Column(db.String(30), nullable=False)      # 通知類型：match_request / message / review / system 等
    content = db.Column(db.String(255), nullable=False)  # 通知內容文字
    is_read = db.Column(db.Boolean, default=False)       # 是否已讀
    related_id = db.Column(db.Integer)                   # 關聯物件 ID（如 match_id）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


class ActivityLog(db.Model):
    """
    活動日誌資料表（activity_logs）。
    記錄使用者的重要操作（登入、上架技能、建立媒合等），供管理員審計使用。
    """
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)  # 操作者
    action = db.Column(db.String(50), nullable=False, index=True)  # 操作類型（如 login / create_skill）
    detail = db.Column(db.Text)                                    # 操作詳情
    ip_address = db.Column(db.String(45))                          # 操作者 IP 位址（支援 IPv6）
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User')


class Report(db.Model):
    """
    檢舉資料表（reports）。
    使用者可檢舉技能、訊息或媒合對象，管理員審查後更新狀態。
    """
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)       # 檢舉者
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)  # 被檢舉者
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)    # 關聯媒合（可選）
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=True)     # 關聯技能（可選）
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True) # 關聯訊息（可選）
    reason = db.Column(db.String(50), nullable=False)  # 檢舉原因代碼：inappropriate_language / harassment / no_show / scam / other
    description = db.Column(db.Text)                   # 補充說明
    evidence_file_url = db.Column(db.String(500), nullable=True)   # 檢舉附件 URL（圖片）
    evidence_file_name = db.Column(db.String(255), nullable=True)  # 附件原始檔名
    evidence_file_type = db.Column(db.String(20), nullable=True)   # 附件類型
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)  # 狀態：pending / reviewed / rejected / resolved / punished
    admin_note = db.Column(db.Text, nullable=True)     # 管理員內部備註
    feedback = db.Column(db.Text, nullable=True)       # 回饋給使用者的說明
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)   # 處理此檢舉的管理員
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    reported_user = db.relationship('User', foreign_keys=[reported_user_id])
    match = db.relationship('Match')
    skill = db.relationship('Skill')
    message = db.relationship('Message')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by])
