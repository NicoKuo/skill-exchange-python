# routes/main.py: Blueprint for main public routes (homepage)
from flask import Blueprint, render_template

from models import db, User, Skill, Match, Review

main_bp = Blueprint('main', __name__)


@main_bp.route("/", endpoint='index')
def index():
    stats = {
        "users": User.query.filter_by(role="student").count(),
        "skills": Skill.query.filter_by(status="open").count(),
        "matches": Match.query.filter(Match.status.in_(["accepted", "completed", "pending"])).count(),
        "reviews": Review.query.count(),
    }

    popular_skills = Skill.query.filter_by(status="open").order_by(Skill.created_at.desc()).limit(6).all()
    top_users = User.query.filter_by(role="student").limit(5).all()

    return render_template(
        "index.html",
        stats=stats,
        popular_skills=popular_skills,
        top_users=top_users
    )
