from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from flask import Flask, flash, redirect, request, url_for, session
import flask
from flask_socketio import SocketIO
import functools
from threading import Timer

sock = """<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
document.addEventListener("DOMContentLoaded", () => {
    const socket = io();  // connects to the same origin automatically

    socket.on("connect", () => {
        console.log("Connected with SID:", socket.id);
    });

    socket.on("refresh", (data) => {
        console.log("Refresh event:", data);

        let pathParts = window.location.pathname.split("/").filter(Boolean);
        let currentPage = "/" + pathParts.join("/"); // full path like "/a/b"
        console.log("Current page:", currentPage);

        let shouldRefresh = data.pages.some(page => {
            if (page === "*") return true; // always refresh
            // exact match
            if (page === currentPage) return true;
            // prefix match for first segment
            let pageParts = page.split("/").filter(Boolean);
            if (pageParts.length === 1 && pageParts[0] === pathParts[0]) return true;
            return false;
        });
        console.log("Should refresh:", shouldRefresh);

        if (data.redirect) {
            console.log("Redirecting to:", data.redirect);
            window.location.href = data.redirect;
            return;
        }

        if (shouldRefresh) {
            console.log("Refreshing page:", currentPage);
            window.location.reload();
            return;
        }
    });
});
</script>
"""


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
    DONE = "done"
    SUBMIT_REQUEST = "submit_request"
    SUBMITTED = "submitted"


@dataclass
class Team:
    name: str
    password: str
    state: TeamState = TeamState.INACTIVE
    about: str = ""
    elo: int = 1000
    wins: int = 0
    losses: int = 0
    draws: int = 0
    match_history: list = field(default_factory=list)
    elo_history: list = field(default_factory=lambda: [1000])


def exec_at(dt: datetime, func, *args, **kwargs):
    delay = (dt - datetime.now()).total_seconds()
    if delay < 0:
        delay = 0
    Timer(delay, func, args=args, kwargs=kwargs).start()


game_length = timedelta(minutes=10)
ready_lead_time = timedelta(minutes=4)
verify_time = timedelta(minutes=1)


@dataclass
class Game:
    team_a: Team
    team_b: Team
    get_ready_time: datetime = None
    start_time: datetime = None
    end_time: datetime = None
    team_a_score: int = 0
    team_b_score: int = 0

    @property
    def expected_start_time(self):
        return self.get_ready_time + ready_lead_time

    @property
    def expected_end_time(self):
        if self.start_time is None:
            return self.expected_start_time + game_length
        return self.start_time + game_length

    def get_ready(self):
        self.team_a.state = TeamState.READY_REQUEST
        self.team_b.state = TeamState.READY_REQUEST
        request_refresh({self.team_a.name, self.team_b.name}, ["/game"], redirect="/game")
        # TODO kick the teams if they don't ready up in time
        # TODO kick when verify time is up
        # TODO end game when time is up
        # TODO add a timer for submission


@dataclass
class Table:
    active_game: Game = None
    scheduled_games: list[Game] = field(default_factory=list)


@dataclass
class Manager:
    teams: dict[str, Team] = field(default_factory=dict)
    table: Table = field(default_factory=Table)
    past_games: list[Game] = field(default_factory=list)
    connections: dict[str, list[str]] = field(default_factory=dict)  # team name -> [connection id]
    searching_teams: set[str] = field(default_factory=set)

    def schedule_game(self, game: Game):
        if self.table.active_game is None:
            self.table.active_game = game
            game.get_ready_time = datetime.now()
        else:
            print("omg what the hell im literally shaking and crying rn")
            raise Exception("There is already an active game")
        exec_at(game.get_ready_time, game.get_ready)

    def add_team(self, team: Team):
        self.teams[team.name] = team

    def set_team_state(self, team_name: str, state: TeamState):
        self.teams[team_name].state = state

    def add_searching_team(self, team_name: str):
        self.set_team_state(team_name, TeamState.SEARCHING)
        self.searching_teams.add(team_name)

    def try_match_teams(self):
        if len(self.searching_teams) >= 2:
            team_a = self.teams[self.searching_teams.pop()]
            team_b = self.teams[self.searching_teams.pop()]
            game = Game(
                team_a=team_a,
                team_b=team_b,
            )
            team_a.state = TeamState.MATCHED
            team_b.state = TeamState.MATCHED
            self.schedule_game(game)
            request_refresh({team_a.name, team_b.name}, ["/game"], redirect="/game")

    def set_team_ready(self, team_name: str):
        self.set_team_state(team_name, TeamState.READY)
        game = self.table.active_game
        both_ready = game.team_a.state == TeamState.READY and game.team_b.state == TeamState.READY
        if both_ready:
            game.team_a.state = TeamState.PLAYING
            game.team_b.state = TeamState.PLAYING
            game.start_time = datetime.now()
        request_refresh({game.team_a.name, game.team_b.name}, ["/game"], redirect="/game")

    def set_team_done(self, team_name: str):
        self.set_team_state(team_name, TeamState.DONE)
        game = self.table.active_game
        both_done = game.team_a.state == TeamState.DONE and game.team_b.state == TeamState.DONE
        if both_done:
            game.team_a.state = TeamState.SUBMIT_REQUEST
            game.team_b.state = TeamState.SUBMIT_REQUEST
            game.end_time = datetime.now()
        request_refresh({game.team_a.name, game.team_b.name}, ["/game"], redirect="/game")

    def set_team_submitted(self, team_name: str):
        self.set_team_state(team_name, TeamState.SUBMITTED)
        game = self.table.active_game
        both_submitted = game.team_a.state == TeamState.SUBMITTED and game.team_b.state == TeamState.SUBMITTED
        if both_submitted:
            sa = int(request.form["team_a_score"])
            sb = int(request.form["team_b_score"])
            if sa == game.team_a_score and sb == game.team_b_score:
                game.end_time = datetime.now()
                game.team_a.state = TeamState.INACTIVE
                game.team_b.state = TeamState.INACTIVE
                self.past_games.append(game)
                self.table.active_game = None
                request_refresh({game.team_a.name, game.team_b.name}, ["*"], redirect="/result")
                request_refresh([None], ["/leaderboard"], redirect=None)
                update_elo(game)
                return redirect(url_for("result_get"))
            else:
                flash("Scores do not match, please resubmit")
                game.team_a.state = TeamState.SUBMIT_REQUEST
                game.team_b.state = TeamState.SUBMIT_REQUEST
                request_refresh({game.team_a.name, game.team_b.name}, ["/game"], redirect="/game")
        else:
            game.team_a_score = int(request.form["team_a_score"])
            game.team_b_score = int(request.form["team_b_score"])

    def set_about(self, team_name: str, about: str):
        self.teams[team_name].about = about
        request_refresh({team_name}, ["/team/" + team_name], redirect=None)
        request_refresh([None], ["/team/" + team_name], redirect=None)


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


def request_refresh(team_names: set[str], pages: list[str], redirect: str = None):
    if None in team_names:
        team_names = set(manager.teams.keys())
    for team_name in team_names:
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
        new_team = Team(name=username, password=password)
        manager.add_team(new_team)
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
    return redirect(url_for("team_get", team_name=session["team"]))


@app.get("/login")
def login_get():
    if "team" in session:
        return redirect(url_for("team_get", team_name=session["team"]))
    return render_template("login.html")


@app.get("/")
def index_get():
    return redirect(url_for("leaderboard_get"))


@app.post("/logout")
def logout_post():
    session.pop("team", None)
    return redirect(url_for("leaderboard_get"))


gamestate_map = {k: f"game_states/{k.value}.html" for k in TeamState}


@app.get("/game")
def game_get():
    team_name = session.get("team")
    if team_name is None:
        return render_template("game_states/not_logged_in.html")

    team = manager.teams.get(team_name)
    template = gamestate_map.get(team.state)
    if team.state in (TeamState.MATCHED, TeamState.READY_REQUEST, TeamState.READY, TeamState.PLAYING, TeamState.DONE, TeamState.SUBMIT_REQUEST, TeamState.SUBMITTED):
        game = manager.table.active_game
        if game and (game.team_a == team or game.team_b == team):
            return render_template(template, team=team, game=game)
    return render_template(template, team=team)


def update_elo(game: Game):
    a = game.team_a
    b = game.team_b
    sa = game.team_a_score
    sb = game.team_b_score
    if sa > sb:
        a.wins += 1
        b.losses += 1
        result_a = 1.0
    elif sa < sb:
        a.losses += 1
        b.wins += 1
        result_a = 0.0
    else:
        a.draws += 1
        b.draws += 1
        result_a = 0.5
    result_b = 1.0 - result_a
    qa = 10 ** (a.elo / 400)
    qb = 10 ** (b.elo / 400)
    ea = qa / (qa + qb)
    eb = qb / (qa + qb)
    k = 32
    a.elo += int(k * (result_a - ea))
    b.elo += int(k * (result_b - eb))
    a.elo_history.append(a.elo)
    b.elo_history.append(b.elo)
    a.match_history.append(game)
    b.match_history.append(game)


@app.post("/game")
def game_post():
    team_name = session.get("team")
    if team_name is None:
        flash("You must be logged in to perform this action")
        return redirect(url_for("login_get"))
    # team = manager.teams.get(team_name)

    if "start_search" in request.form:
        manager.add_searching_team(team_name)
        manager.try_match_teams()
    if "ready" in request.form:
        manager.set_team_ready(team_name)
    if "done" in request.form:
        manager.set_team_done(team_name)
    if "submit" in request.form:
        ret = manager.set_team_submitted(team_name)
        if ret is not None:
            print(ret)
            return ret
    return redirect(url_for("game_get"))


@app.get("/team/<string:team_name>")
def team_get(team_name: str):
    self_team_name = session.get("team")
    if team_name is None:
        flash("This team does not exist")
        return redirect(url_for("leaderboard_get"))
    team = manager.teams.get(team_name)
    editable = self_team_name == team_name
    return render_template("team.html", team=team, editable=editable)


@app.post("/team/<string:team_name>")
def team_post(team_name: str):
    self_team_name = session.get("team")
    if self_team_name is None:
        flash("You must be logged in to perform this action")
        return redirect(url_for("login_get"))
    if team_name != self_team_name:
        flash("You can only edit your own team")
        return redirect(url_for("team_get", team_name=team_name))
    team = manager.teams.get(team_name)
    if "about" in request.form:
        manager.set_about(team_name, request.form["about"])
    return redirect(url_for("team_get", team_name=team_name))


@app.get("/schedule")
def schedule_get():
    return render_template("schedule.html", table=manager.table)


@app.get("/leaderboard")
def leaderboard_get():
    teams = sorted(manager.teams.values(), key=lambda t: t.elo, reverse=True)
    return render_template("leaderboard.html", teams=teams)


def get_latest_game(team: Team):
    for game in reversed(manager.past_games):
        if game.team_a == team or game.team_b == team:
            return game
    return None


@app.get("/result")
def result_get():
    team_name = session.get("team")
    if team_name is None:
        flash("You must be logged in to view results")
        return redirect(url_for("login_get"))
    latest_game = get_latest_game(manager.teams[team_name])
    if latest_game is None:
        flash("You have no completed games")
        return redirect(url_for("game_get"))
    if latest_game.team_a_score > latest_game.team_b_score:
        winner = latest_game.team_a.name
    elif latest_game.team_a_score < latest_game.team_b_score:
        winner = latest_game.team_b.name
    else:
        winner = None
    if winner is None:
        return render_template("draw.html", game=latest_game, team=manager.teams[team_name])
    if team_name == winner:
        return render_template("win.html", game=latest_game, team=manager.teams[team_name])
    else:
        return render_template("lose.html", game=latest_game, team=manager.teams[team_name])


if __name__ == "__main__":
    socketio.run(app, debug=True)
