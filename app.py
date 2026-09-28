from flask import Flask, render_template

from config.config import Config


def create_app() -> Flask:

    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    return flask_app


app = create_app()


@app.route("/")
def index():

    return render_template(
        "index.html",
        system_name=app.config["SYSTEM_NAME"],
        system_subtitle=app.config["SYSTEM_SUBTITLE"],
    )


@app.route("/autenticacao")
def authentication():

    return render_template(
        "authentication.html",
        system_name=app.config["SYSTEM_NAME"],
        system_subtitle=app.config["SYSTEM_SUBTITLE"],
    )


if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", True), host="127.0.0.1", port=5000)
