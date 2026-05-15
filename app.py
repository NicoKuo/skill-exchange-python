# app.py: Flask 應用程式工廠（Application Factory）與藍圖（Blueprint）註冊
# 供 gunicorn 使用的入口點：gunicorn app:app
import os
from dotenv import load_dotenv
from flask import Flask, url_for as flask_url_for, flash, redirect, request
from flask_login import LoginManager

from config import Config
from models import db, User
from utils import (
    user_average_rating,
    user_completed_matches,
    user_points,
    user_badges,
    unread_notifications_count,
    skill_match_score,
    split_tags,
    detect_attachment_type,
    skill_attachment_url,
    normalize_skill_attachment_url,
    format_taiwan_time,
    render_skill_description,
    user_pending_review_count,
)
from routes import (
    main_bp,
    auth_bp,
    profile_bp,
    skills_bp,
    matches_bp,
    chat_bp,
    reviews_bp,
    notifications_bp,
    admin_bp
)

# 載入 .env 環境變數檔案（SECRET_KEY、DATABASE_URL 等）
load_dotenv()

# 技能地點類型的中文標籤對照表
SKILL_LOCATION_TYPE_LABELS = {
    'online': '線上',
    'campus': '校內',
    'off_campus': '校外',
}

# 技能可配合星期的中文標籤對照表
SKILL_AVAILABLE_DAY_LABELS = {
    'mon': '星期一',
    'tue': '星期二',
    'wed': '星期三',
    'thu': '星期四',
    'fri': '星期五',
    'sat': '星期六',
    'sun': '星期日',
    'weekend': '週末',
    'flexible': '彈性',
}


def skill_location_type_label(value):
    """將地點類型代碼（如 'online'）轉換為中文標籤（如 '線上'）。"""
    return SKILL_LOCATION_TYPE_LABELS.get(value, '未設定')


def skill_available_day_label(value):
    """將星期代碼（如 'mon'）轉換為中文標籤（如 '星期一'）。"""
    return SKILL_AVAILABLE_DAY_LABELS.get(value, '未設定')


def format_skill_time(value):
    """將時間物件格式化為 HH:MM 字串，若無值則顯示「未設定」。"""
    return value.strftime('%H:%M') if value else '未設定'

# 舊端點名稱到新藍圖端點名稱的對照表（向後相容用）
ENDPOINT_ALIASES = {
    'index': 'main.index',
    'register': 'auth.register',
    'login': 'auth.login',
    'logout': 'auth.logout',
    'dashboard': 'profile.dashboard',
    'profile': 'profile.profile',
    'skills': 'skills.skills',
    'add_skill': 'skills.add_skill',
    'match_center': 'matches.match_center',
    'chat': 'chat.chat',
    'chat_room': 'chat.chat',
    'chat.chat_room': 'chat.chat',
    'review': 'reviews.review',
    'notifications': 'notifications.notifications',
    'admin': 'admin.dashboard',
}


def url_for_compat(endpoint, **kwargs):
    """
    url_for 的向後相容包裝器。
    自動將舊的端點名稱轉換為新的「藍圖.端點」格式，
    讓模板在重構後仍可正常運作。
    """
    if endpoint in ENDPOINT_ALIASES:
        endpoint = ENDPOINT_ALIASES[endpoint]
    return flask_url_for(endpoint, **kwargs)


def create_app():
    """
    Flask 應用程式工廠函數。
    建立並設定 Flask 應用、初始化擴充套件、註冊所有藍圖。
    回傳已設定完畢的 Flask 應用實例。
    """
    # 使用 Flask 預設的 templates/ 和 static/ 資料夾
    app = Flask(__name__)

    # 從 Config 類別載入設定（SECRET_KEY、資料庫 URI 等）
    app.config.from_object(Config)
    # 全域上傳檔案大小上限：10MB
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    # 技能附件大小上限：5MB
    app.config['SKILL_ATTACHMENT_MAX_SIZE'] = 5 * 1024 * 1024
    # 聊天附件大小上限：10MB
    app.config['CHAT_ATTACHMENT_MAX_SIZE'] = 10 * 1024 * 1024

    # 初始化 SQLAlchemy 資料庫
    db.init_app(app)

    # 初始化 Flask-Login 使用者管理，未登入時導向登入頁
    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        """根據 user_id 從資料庫載入使用者物件（Flask-Login 必要）。"""
        return User.query.get(int(user_id))

    # 將輔助函數注入所有 Jinja2 模板，讓模板可直接呼叫
    @app.context_processor
    def inject_helpers():
        return dict(
            user_average_rating=user_average_rating,        # 計算平均評分
            user_completed_matches=user_completed_matches,  # 計算已完成交換數
            user_points=user_points,                        # 計算積分
            user_badges=user_badges,                        # 取得成就徽章
            unread_notifications_count=unread_notifications_count,  # 未讀通知數
            skill_match_score=skill_match_score,            # 技能媒合分數
            split_tags=split_tags,                          # 分割標籤字串
            detect_attachment_type=detect_attachment_type,  # 偵測附件類型
            skill_attachment_url=skill_attachment_url,      # 取得附件 URL
            normalize_skill_attachment_url=normalize_skill_attachment_url,  # 規範化附件 URL
            format_taiwan_time=format_taiwan_time,          # 台灣時區時間格式化
            render_skill_description=render_skill_description,  # 渲染技能描述（含附件）
            user_pending_review_count=user_pending_review_count,  # 待評分媒合數
            skill_location_type_label=skill_location_type_label,  # 地點類型中文標籤
            skill_available_day_label=skill_available_day_label,  # 可配合星期中文標籤
            format_skill_time=format_skill_time,            # 時間格式化
            url_for=url_for_compat  # 替換 url_for 為向後相容版本
        )

    @app.errorhandler(413)
    def request_entity_too_large(error):
        """處理 HTTP 413 錯誤：上傳檔案超過大小限制時顯示錯誤訊息。"""
        flash("檔案大小超過限制，請上傳 5MB 以下的檔案。", "error")
        return redirect(request.referrer or flask_url_for("skills.add_skill"))

    # 註冊所有功能藍圖
    app.register_blueprint(main_bp)          # 首頁
    app.register_blueprint(auth_bp)          # 認證（登入/註冊/登出）
    app.register_blueprint(profile_bp)       # 個人資料
    app.register_blueprint(skills_bp)        # 技能管理
    app.register_blueprint(matches_bp)       # 媒合中心
    app.register_blueprint(chat_bp)          # 聊天室
    app.register_blueprint(reviews_bp)       # 互評系統
    app.register_blueprint(notifications_bp) # 通知中心
    app.register_blueprint(admin_bp)         # 管理後台

    return app


# 建立應用實例，供 gunicorn 使用：gunicorn app:app
app = create_app()


if __name__ == "__main__":
    # 直接執行時啟動開發伺服器，從環境變數讀取 PORT，預設 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
