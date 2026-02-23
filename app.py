from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import pdfplumber
import re
import os

app = Flask(__name__)

# # ================= CONFIG =================
app.config['SECRET_KEY'] = 'supersecretkey'

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ================= MODELS =================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100))
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="user")

class MockTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    category = db.Column(db.String(100))

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mock_test_id = db.Column(db.Integer, db.ForeignKey('mock_test.id'))
    question = db.Column(db.Text)
    option_a = db.Column(db.String(200))
    option_b = db.Column(db.String(200))
    option_c = db.Column(db.String(200))
    option_d = db.Column(db.String(200))
    correct_answer = db.Column(db.String(1))

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    mock_test_id = db.Column(db.Integer)
    score = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route("/")
def home():
    tests = MockTest.query.all()
    return render_template("index.html", tests=tests)

# ---------- REGISTER ----------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful!")
        return redirect(url_for("login"))

    return render_template("register.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("home"))
        flash("Invalid credentials")

    return render_template("login.html")

# ---------- LOGOUT ----------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

# ---------- ATTEND MOCK TEST ----------
@app.route("/mocktest/<int:test_id>", methods=["GET","POST"])
@login_required
def mocktest(test_id):
    questions = Question.query.filter_by(mock_test_id=test_id).all()

    if request.method == "POST":
        score = 0
        user_answers = {}

        for q in questions:
            selected = request.form.get(str(q.id))
            user_answers[q.id] = selected

            if selected == q.correct_answer:
                score += 1

        result = Result(
            user_id=current_user.id,
            mock_test_id=test_id,
            score=score
        )
        db.session.add(result)
        db.session.commit()

        return render_template(
            "result.html",
            score=score,
            total=len(questions),
            questions=questions,
            user_answers=user_answers
        )

    return render_template("mocktest.html", questions=questions)

# ---------- ADMIN PDF UPLOAD ----------
@app.route("/upload", methods=["GET","POST"])
@login_required
def upload():
    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        title = request.form["title"]
        category = request.form["category"]
        file = request.files["pdf"]

        test = MockTest(title=title, category=category)
        db.session.add(test)
        db.session.commit()

        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)

        extract_questions(file_path, test.id)

        flash("Mock Test Uploaded Successfully")
        return redirect(url_for("home"))

    return render_template("upload.html")

# ---------- PDF EXTRACT FUNCTION ----------
def extract_questions(file_path, test_id):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()

    pattern = r"\d+\.\s(.*?)\nA\.\s(.*?)\nB\.\s(.*?)\nC\.\s(.*?)\nD\.\s(.*?)\nAnswer:\s([A-D])"
    matches = re.findall(pattern, text, re.DOTALL)

    for q in matches:
        question = Question(
            mock_test_id=test_id,
            question=q[0],
            option_a=q[1],
            option_b=q[2],
            option_c=q[3],
            option_d=q[4],
            correct_answer=q[5]
        )
        db.session.add(question)

    db.session.commit()
# =================LEADERBOARD =================

@app.route("/leaderboard/<int:test_id>")
def leaderboard(test_id):
    results = Result.query.filter_by(mock_test_id=test_id)\
                .order_by(Result.score.desc()).all()
    return render_template("leaderboard.html", results=results)


# ===== TEMPORARY ROUTE TO CREATE TABLES =====
@app.route("/create_tables")
def create_tables():
    db.create_all()
    return "Tables Created Successfully!"
# ================= MAIN =================
if __name__ == "__main__":
    if not os.path.exists("uploads"):
        os.makedirs("uploads")

    with app.app_context():
        db.create_all()


    app.run(debug=True)
