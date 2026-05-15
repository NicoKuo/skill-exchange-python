# helpers.py: 向後相容的 shim（轉接層）
# 此檔案僅作為舊版引用的相容橋接，實際函數定義在 utils/helpers.py
# 若新程式碼請直接從 utils 匯入
from utils.helpers import (
    user_average_rating,
    user_completed_matches,
    user_points,
    user_badges,
    unread_notifications_count,
    add_notification,
    skill_match_score
)

__all__ = [
    'user_average_rating',
    'user_completed_matches',
    'user_points',
    'user_badges',
    'unread_notifications_count',
    'add_notification',
    'skill_match_score',
]
