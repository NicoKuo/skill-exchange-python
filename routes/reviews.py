# routes/reviews.py: Blueprint for submitting and viewing reviews
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, Match, Review
from utils import add_notification

reviews_bp = Blueprint('reviews', __name__)


@reviews_bp.route("/review", methods=["GET", "POST"], endpoint='review')
@login_required
def review():
    completed = Match.query.filter(
        Match.status == "completed",
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).all()

    # 標記已評分的媒合
    reviewed_match_ids = set(
        Review.query.filter_by(reviewer_id=current_user.id).with_entities(Review.match_id).all()
    )
    reviewed_match_ids = {r[0] for r in reviewed_match_ids}

    # 分離已評分和未評分的媒合
    pending_reviews = [m for m in completed if m.id not in reviewed_match_ids]
    reviewed = [m for m in completed if m.id in reviewed_match_ids]

    if request.method == "POST":
        m = Match.query.get_or_404(int(request.form.get("match_id")))

        if current_user.id not in [m.requester_id, m.receiver_id]:
            abort(403)

        if m.status != "completed":
            flash("只有完成的媒合才能評價。", "error")
            return redirect(url_for(".review"))

        # 檢查是否已評過
        existing_review = Review.query.filter_by(
            match_id=m.id,
            reviewer_id=current_user.id
        ).first()

        if existing_review:
            flash("你已對此媒合評分過了。", "error")
        else:
            reviewee_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
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
            add_notification(reviewee_id, "review", "你收到新的評價。", m.id)

            flash("評價已送出。", "success")
            return redirect(url_for(".review"))

    return render_template("review.html", pending_reviews=pending_reviews, reviewed=reviewed)
