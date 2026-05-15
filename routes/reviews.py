# routes/reviews.py: 互評系統路由
# 功能：查看待評價的媒合、提交評分與評論
# 規則：只有 completed 狀態的媒合才可互評，且每個媒合每人只能評一次
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, Match, Review
from utils import add_notification

reviews_bp = Blueprint('reviews', __name__)


@reviews_bp.route("/review", methods=["GET", "POST"], endpoint='review')
@login_required
def review():
    """
    互評頁面路由。需登入才可存取。

    GET：顯示所有已完成媒合的評價狀態，分為「待評分」和「已評分」兩區塊。
    POST：提交對指定媒合的評分（1-5 星）和文字評論，
          成功後通知對方並導回此頁。

    防重複：若已對此媒合評過分，顯示錯誤訊息，不允許再次提交。
    """
    # 取得此使用者參與的所有已完成媒合
    completed = Match.query.filter(
        Match.status == "completed",
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).all()

    # 取得此使用者已評分過的媒合 ID 集合（用於判斷哪些已評分）
    reviewed_match_ids = set(
        Review.query.filter_by(reviewer_id=current_user.id).with_entities(Review.match_id).all()
    )
    reviewed_match_ids = {r[0] for r in reviewed_match_ids}

    # 分離待評分和已評分的媒合清單
    pending_reviews = [m for m in completed if m.id not in reviewed_match_ids]
    reviewed = [m for m in completed if m.id in reviewed_match_ids]

    if request.method == "POST":
        m = Match.query.get_or_404(int(request.form.get("match_id")))

        # 只有媒合的雙方才能提交評價
        if current_user.id not in [m.requester_id, m.receiver_id]:
            abort(403)

        # 只有 completed 狀態的媒合才能評價
        if m.status != "completed":
            flash("只有完成的媒合才能評價。", "error")
            return redirect(url_for(".review"))

        # 防止重複評分：每個媒合每人只能評一次
        existing_review = Review.query.filter_by(
            match_id=m.id,
            reviewer_id=current_user.id
        ).first()

        if existing_review:
            flash("你已對此媒合評分過了。", "error")
        else:
            # 確認被評分的對象是對方（非自己）
            reviewee_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
            # 確保評分在 1-5 的合法範圍內
            rating = max(1, min(5, int(request.form.get("rating", 5))))

            db.session.add(
                Review(
                    match_id=m.id,
                    reviewer_id=current_user.id,
                    reviewee_id=reviewee_id,
                    rating=rating,
                    comment=request.form.get("comment", "").strip()
                )
            )

            db.session.commit()
            # 通知被評分的對方
            add_notification(reviewee_id, "review", "你收到新的評價。", m.id)

            flash("評價已送出。", "success")
            return redirect(url_for(".review"))

    return render_template("review.html", pending_reviews=pending_reviews, reviewed=reviewed)
