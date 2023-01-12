"""Flask app to autocomplete text with OpenAI GPT-3."""

# Import from standard library
import os

# Import from 3rd party libraries
from flask import Flask, request, render_template, send_from_directory, session
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask_wtf.csrf import CSRFProtect
import func_timeout

# Import modules
import oai

# Instantiate and configure Flask app
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET"),
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)
csrf = CSRFProtect()
csrf.init_app(app)
if not app.config["DEBUG"]:
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
    )


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(directory="static", path="favicon.ico")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/suggest", methods=["POST"])
def suggest() -> dict:
    """Suggest a continuation of the prompt.

    Expected request body:
        {
            "type": str,
            "content": str,
            "topic": str (optional),
            "style": str (optional),
            "audience": str (optional),
            "notes": str (optional)
        }
    """
    session["n_requests"] = session.get("n_requests", 0) + 1
    request_data = request.json
    request_data["session_token"] = session["csrf_token"]
    request_data["n_session_requests"] = session["n_requests"]
    request_data["ip"] = request.remote_addr
    app.logger.info(request_data)

    if session["n_requests"] % 50 == 0:
        return "Too many requests, please wait a few seconds", 429
    if session["n_requests"] <= 20:
        model = "text-davinci-003"
    else:
        model = "text-curie-001"

    any_criteria = (
        request.json["topic"]
        or request.json["style"]
        or request.json["audience"]
        or request.json["notes"]
    )
    prompt = (
        "You are an expert in your field and an excellent writer. "
        "Your content is insightful and engaging."
        "You structure your text to be easy to read and understand, "
        "for example by using headlines and lists.\n"
        "\n"
        f"You are now writing a {request.json['type']}"
        f"{' with these criteria' if any_criteria else ''}:\n"
        f"{'Topic:' + request.json['topic'] + chr(10) if request.json['topic'] else ''}"
        f"{'Style: ' + request.json['style'] + chr(10) if request.json['style'] else ''}"
        f"{'Audience: ' + request.json['audience'] + chr(10) if request.json['audience'] else ''}"
        f"{'Other notes: ' + request.json['notes'] + chr(10) if request.json['notes'] else ''}"
        "\n"
        "Here is your final version:\n"
        "\n"
        f"{request.json['content']}"
    )[-2000:]
    openai = oai.Openai(app.logger)
    # TODO: Add moderation without making the overall response time too slow
    # flagged = openai.moderate(prompt)
    # if flagged:
    #     app.logger.info("Prompt flagged")
    #     return "Inappropriate prompt", 400
    try:
        completion = func_timeout.func_timeout(5, openai.complete, args=(prompt, model))
    except func_timeout.exceptions.FunctionTimedOut:
        app.logger.error("OpenAI timed out")
        return "OpenAI timed out", 500
    if completion["status"] == "error":
        app.logger.error(completion["text"])
        return completion["text"], 500
    return {"suggestion": completion["text"]}


if __name__ == "__main__":
    app.run()
