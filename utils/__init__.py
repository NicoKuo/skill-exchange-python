# utils/__init__.py: 工具套件初始化
# 統一從 helpers.py 匯出所有輔助函數，讓外部可用 from utils import xxx 直接取用
from .helpers import (
    user_average_rating,          # 計算使用者平均評分
    user_completed_matches,       # 計算已完成的媒合數
    user_points,                  # 計算使用者積分
    user_pending_review_count,    # 計算待評分的媒合數
    user_badges,                  # 取得使用者的成就徽章清單
    unread_notifications_count,   # 取得未讀通知數
    add_notification,             # 新增通知
    skill_match_score,            # 計算技能媒合分數
    exchange_candidate_skills,    # 找出雙方可交換的技能清單
    split_tags,                   # 分割標籤字串為清單
    detect_attachment_type,       # 偵測附件類型（image / pdf / file）
    skill_attachment_url,         # 取得技能附件的存取 URL
    normalize_skill_attachment_url,  # 規範化技能附件 URL
    format_taiwan_time,           # 將 UTC 時間轉換為台灣時區並格式化
    render_skill_description,     # 渲染技能描述（自動處理附件標記）
)

__all__ = [
    'user_average_rating',
    'user_completed_matches',
    'user_points',
    'user_pending_review_count',
    'user_badges',
    'unread_notifications_count',
    'add_notification',
    'skill_match_score',
    'exchange_candidate_skills',
    'split_tags',
    'detect_attachment_type',
    'skill_attachment_url',
    'normalize_skill_attachment_url',
    'format_taiwan_time',
    'render_skill_description',
]
