from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from flask import Flask, flash, redirect, request, url_for, session
import flask
from flask_socketio import SocketIO
import functools


sock = """<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
    document.addEventListener("DOMContentLoaded", () => {
        const socket = io();  // connects to the same origin automatically

        socket.on("connect", () => {
            console.log("Connected with SID:", socket.id);
        });

        socket.on("refresh", (data) => {
            console.log("Refresh event:", data);
        });
    });
</script>"""


@functools.wraps(flask.render_template)
def render_template(template_name_or_list, **context):
    original = flask.render_template(template_name_or_list, **context)
    return f"{sock}\n{original}"


class TeamState(Enum):
    INACTIVE = "inactive"
    SEARCHING = "searching"
    MATCHED = "matched"
    READY_REQUEST = "ready_request"
    READY = "ready"
    PLAYING = "playing"
    SUBMIT_REQUEST = "submit_request"
    SUBMITTED = "submitted"


@dataclass
class Team:
    name: str
    password: str
    state: TeamState
    elo: int


class GameState(Enum):
    WAIT_READY = "wait_ready"
    WAIT_DONE = "wait_done"
    WAIT_SUBMIT = "wait_submit"
    COMPLETED = "completed"


@dataclass
class Game:
    team_a: Team
    team_b: Team
    state: GameState
    start_time: datetime
    end_time: datetime = None


@dataclass
class Table:
    active_game: Game = None
    scheduled_games: list[Game] = field(default_factory=list)


@dataclass
class Manager:
    teams: dict[str, Team] = field(default_factory=dict)
    tables: list[Table] = field(default_factory=list)
    past_games: list[Game] = field(default_factory=list)
    connections: dict[str, list[str]] = field(default_factory=dict)  # team name -> [connection id]


app = Flask(__name__)
app.secret_key = "your-secret-key"
socketio = SocketIO(app)
manager = Manager()


def is_valid(username: str, password: str, confirm_password: str) -> str | None:
    if not username or not password:
        return "Username and password cannot be empty"
    if len(username) > 20:
        return "Username must be at most 20 characters"
    for team_name in manager.teams:
        if team_name == username:
            return "Username already taken"
    if password != confirm_password:
        return "Passwords do not match"
    return None


# sockets


@socketio.on("connect")
def connect():
    team_name = session.get("team")
    conn_id = request.sid
    if team_name not in manager.connections:
        manager.connections[team_name] = []
    manager.connections[team_name].append(conn_id)
    print(f"Team {team_name} connected with connection id {conn_id}, {sum(len(v) for v in manager.connections.values())} total connections")


@socketio.on("disconnect")
def disconnect():
    team_name = session.get("team")
    conn_id = request.sid
    if team_name in manager.connections:
        manager.connections[team_name].remove(conn_id)
        if not manager.connections[team_name]:
            del manager.connections[team_name]
    print(f"Team {team_name} disconnected from connection id {conn_id}")


def request_refresh(teams: set[str], pages: list[str], redirect: str = None):
    if None in teams:
        teams = set(manager.teams.keys())
    for team_name in teams:
        if team_name in manager.connections:
            for conn_id in manager.connections[team_name]:
                socketio.emit(
                    "refresh",
                    {"pages": pages, "redirect": redirect},
                    to=conn_id,
                )


# routes
@app.post("/login")
def login_post():
    if "register" in request.form:
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        error = is_valid(username, password, confirm_password)
        if error is not None:
            flash(error)
            return redirect(url_for("login_get"))
        new_team = Team(name=username, password=password, state=TeamState.INACTIVE, elo=1000)
        manager.teams[new_team.name] = new_team
        session["team"] = new_team.name
    elif "login" in request.form:
        username = request.form["username"]
        password = request.form["password"]
        team = manager.teams.get(username)
        if team is None:
            flash("Unknown username")
            return redirect(url_for("login_get"))
        if team.password != password:
            flash("Wrong password")
            return redirect(url_for("login_get"))
        session["team"] = team.name
    else:
        flash("Invalid form submission")
    return redirect(url_for(f"team/{session['team']}"))


@app.get("/login")
def login_get():
    if "team" in session:
        return redirect(url_for("leaderboard"))
    return render_template("login.html")


@app.get("/")
def index_get():
    return redirect(url_for("leaderboard"))


@app.get("/logout")
def logout_get():
    session.pop("team", None)
    return redirect(url_for("leaderboard"))


gamestate_map = {k: f"game_states/{k.value}.html" for k in TeamState}


@app.get("/game")
def game_get():
    team_name = session.get("team")
    if team_name is None:
        return render_template("game_states/not_logged_in.html")

    team = manager.teams.get(team_name)
    template = gamestate_map.get(team.state, "game_states/unknown.html")
    return render_template(template, team=team)


@app.post("/game")
def game_post(): ...


@app.get("/team/<string:team_name>")
def team_get(team_name: str):
    self_team_name = session.get("team")
    if team_name is None:
        flash("This team does not exist")
        return redirect(url_for("leaderboard"))
    team = manager.teams.get(team_name)
    editable = self_team_name == team_name
    return render_template("team.html", team=team, editable=editable)


@app.get("/leaderboard")
def leaderboard():
    teams = sorted(manager.teams.values(), key=lambda t: t.elo, reverse=True)
    return render_template("leaderboard.html", teams=teams)


if __name__ == "__main__":
    socketio.run(app, debug=True)
