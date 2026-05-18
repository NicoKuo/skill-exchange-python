# models.py: SQLAlchemy 資料模型定義與 db 實例
# 每個 class 對應資料庫中的一張資料表
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)
    bio = db.Column(db.Text, default='')
    avatar = db.Column(db.String(255))
    department = db.Column(db.String(100), nullable=True)
    grade = db.Column(db.String(50), nullable=True)
    offered_skills_intro = db.Column(db.Text, nullable=True)
    wanted_skills_intro = db.Column(db.Text, nullable=True)
    portfolio = db.Column(db.Text, nullable=True)              # 作品集 JSON
    status = db.Column(db.String(20), default='active', nullable=False)
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    skills = db.relationship('Skill', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SkillCategory(db.Model):
    __tablename__ = 'skill_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))


class Skill(db.Model):
    __tablename__ = 'skills'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('skill_categories.id'))
    title = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.Text)
    type = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), default='online')
    location_type = db.Column(db.String(20))
    location_area = db.Column(db.String(50))
    location_detail = db.Column(db.String(100))
    available_day = db.Column(db.String(20))
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    status = db.Column(db.String(20), default='open')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attachment_data = db.Column(db.LargeBinary, nullable=True)
    attachment_name = db.Column(db.Text, nullable=True)
    attachment_mime = db.Column(db.Text, nullable=True)
    attachment_type = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.Text, nullable=True)

    category = db.relationship('SkillCategory')


class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skill = db.relationship('Skill')
    requester = db.relationship('User', foreign_keys=[requester_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_url = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    file_type = db.Column(db.String(30))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    match = db.relationship('Match')
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    match = db.relationship('Match')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])
    reviewee = db.relationship('User', foreign_keys=[reviewee_id])


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    content = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    related_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    detail = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User')


class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)
    reason = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    evidence_file_url = db.Column(db.String(500), nullable=True)
    evidence_file_name = db.Column(db.String(255), nullable=True)
    evidence_file_type = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    admin_note = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    reported_user = db.relationship('User', foreign_keys=[reported_user_id])
    match = db.relationship('Match')
    skill = db.relationship('Skill')
    message = db.relationship('Message')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by])