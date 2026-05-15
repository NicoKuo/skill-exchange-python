# config.py: 應用程式設定（從環境變數載入）
# 所有敏感設定（金鑰、資料庫 URL）應寫在 .env 檔案中，不應硬編碼在程式碼裡
import os
from dotenv import load_dotenv

# 讀取 .env 檔案中的環境變數
load_dotenv()

class Config:
    # 應用程式密鑰，用於 Session 加密與 CSRF 保護，正式環境必須使用強隨機字串
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # 資料庫連線 URI，預設使用本機 SQLite；正式環境可設為 PostgreSQL URL
    # 將舊版 postgres:// 協議自動轉換為 SQLAlchemy 支援的 postgresql://
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///skill_exchange.db").replace(
        "postgres://", "postgresql://"
    )

    # 關閉 SQLAlchemy 物件修改追蹤，節省記憶體
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# 設定字典，可依需求擴充為 development / production / testing 等不同環境
config = {
    "default": Config
}
