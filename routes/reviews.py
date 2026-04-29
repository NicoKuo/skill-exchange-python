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

    if request.method == "POST":
        m = Match.query.get_or_404(int(request.form.get("match_id")))

        if current_user.id not in [m.requester_id, m.receiver_id]:
            abort(403)

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
        return redirect(url_for("review"))

    return render_template("review.html", completed=completed)
