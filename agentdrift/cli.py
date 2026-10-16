"""AgentDrift terminal CLI — replaces the web dashboard.

Talks to the daemon at http://127.0.0.1:8901.

Usage:
    python3 cli.py health
    python3 cli.py scan --threshold 0.92
    python3 cli.py ingest --agent-id demo --session-id s1 --payload '{"key": "val"}'
    python3 cli.py evaluate --premise "the cat sits" --hypothesis "the cat sits"
    python3 cli.py test-all
    python3 cli.py watch --session-id s1 --interval 1.0 --threshold 0.92
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import deque
from datetime import datetime

import requests
import typer
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DAEMON = os.getenv("AGENTDRIFT_DAEMON", "http://127.0.0.1:8901").rstrip("/")
TIMEOUT = 10

app = typer.Typer(help="AgentDrift CLI — terminal-native daemon client.")
console = Console()


# ---------------------------------------------------------------------------
# HTTP helpers (no tracebacks on connection failure)
# ---------------------------------------------------------------------------


def _get(path: str) -> dict | list:
    try:
        r = requests.get(f"{DAEMON}{path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        console.print(
            Panel(
                f"[bold]Daemon offline[/bold] at {DAEMON}\n"
                "Start it with:\n"
                "  [cyan]uvicorn app.main:app --port 8901 --reload --reload-dir app[/cyan]",
                title="Connection failed",
                style="red",
            )
        )
        raise typer.Exit(1)
    except requests.Timeout:
        console.print(Panel(f"Daemon at {DAEMON} timed out on GET {path}.", style="red"))
        raise typer.Exit(1)
    except requests.HTTPError as exc:
        console.print(Panel(f"GET {path} failed: {exc}", style="red"))
        raise typer.Exit(1)


def _post(path: str, payload: object) -> dict | list:
    try:
        r = requests.post(f"{DAEMON}{path}", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        console.print(
            Panel(
                f"[bold]Daemon offline[/bold] at {DAEMON}\n"
                "Start it with:\n"
                "  [cyan]uvicorn app.main:app --port 8901 --reload --reload-dir app[/cyan]",
                title="Connection failed",
                style="red",
            )
        )
        raise typer.Exit(1)
    except requests.Timeout:
        console.print(Panel(f"Daemon at {DAEMON} timed out on POST {path}.", style="red"))
        raise typer.Exit(1)
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = f"\n{exc.response.text[:500]}"
        except Exception:
            pass
        console.print(Panel(f"POST {path} failed: {exc}{detail}", style="red"))
        raise typer.Exit(1)


def _fetch_stats() -> dict:
    for path in ("/stats", "/v1/stats", "/api/stats"):
        try:
            r = requests.get(f"{DAEMON}{path}", timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                return data if isinstance(data, dict) else {}
        except requests.RequestException:
            continue
    return {}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def health() -> None:
    """Query GET /health and show status, uptime, backend and counters."""
    data = _get("/health")
    if not isinstance(data, dict):
        console.print(Panel(f"Unexpected /health response: {data!r}", style="red"))
        raise typer.Exit(1)
    stats = _fetch_stats()

    table = Table(title="AgentDrift daemon", box=box.ROUNDED)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("Status", str(data.get("status", "?")))
    table.add_row("Version", str(data.get("version", "?")))
    table.add_row("DB connected", str(data.get("db_connected", "?")))
    table.add_row("Mode", str(data.get("mode", data.get("db_mode", "?"))))
    table.add_row("Backend", str(data.get("embeddings", data.get("backend", "?"))))
    table.add_row("Uptime (s)", str(data.get("uptime_seconds", "?")))
    table.add_row("Sessions", str(stats.get("sessions", "?")))
    table.add_row("Executions", str(stats.get("executions", "?")))
    table.add_row("Detections", str(stats.get("detections", "?")))
    console.print(table)


@app.command()
def scan(threshold: float = typer.Option(0.92, help="Loop similarity threshold.")) -> None:
    """POST /v1/sentinel/scan and display ping-pong loop results."""
    data = _post("/v1/sentinel/scan", {"threshold": threshold})
    if not isinstance(data, dict):
        console.print(Panel(f"Unexpected scan response: {data!r}", style="red"))
        raise typer.Exit(1)
    detections = int(data.get("detections", 0) or 0)
    thr = data.get("threshold", threshold)
    if detections > 0:
        console.print(
            Panel(
                f"[bold]Ping-pong loop detected[/bold]\n"
                f"Detections: [bold red]{detections}[/bold red]\n"
                f"Threshold: {thr}",
                title="Sentinel scan",
                style="red",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold]No loops found[/bold]\nThreshold: {thr}",
                title="Sentinel scan",
                style="green",
            )
        )
    loops = data.get("loops") or []
    if loops:
        table = Table(title="Loops", box=box.ROUNDED)
        table.add_column("Session")
        table.add_column("Execution")
        table.add_column("Prior")
        table.add_column("Similarity", justify="right")
        for loop in loops[:20]:
            table.add_row(
                str(loop.get("session_id", "")),
                str(loop.get("execution_id", "")),
                str(loop.get("prior_execution_id", "")),
                str(loop.get("similarity", "")),
            )
        console.print(table)


@app.command()
def ingest(
    agent_id: str = typer.Option("demo-agent", "--agent-id", help="Agent ID."),
    session_id: str = typer.Option("demo-session", "--session-id", help="Session ID."),
    node_id: str = typer.Option("default", "--node-id", help="Node ID."),
    payload: str = typer.Option('{"key": "val"}', "--payload", help="JSON payload dict."),
    state_hash: str = typer.Option("", "--state-hash", help="Optional state hash."),
) -> None:
    """Package input into a TelemetryBatch and POST /v1/ingest."""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        console.print(Panel(f"Invalid --payload JSON: {exc}", style="red"))
        raise typer.Exit(1)
    if not isinstance(parsed, dict):
        console.print(Panel("--payload must decode to a JSON object.", style="red"))
        raise typer.Exit(1)

    if "input_payload" in parsed or "output_payload" in parsed:
        input_payload = parsed.get("input_payload", {})
        output_payload = parsed.get("output_payload", {})
    else:
        input_payload, output_payload = parsed, parsed

    event: dict = {
        "session_id": session_id,
        "agent_id": agent_id,
        "node_id": node_id,
        "input_payload": input_payload,
        "output_payload": output_payload,
    }
    if state_hash:
        event["state_hash"] = state_hash

    data = _post("/v1/ingest", {"executions": [event]})
    if not isinstance(data, dict):
        console.print(Panel(f"Unexpected ingest response: {data!r}", style="red"))
        raise typer.Exit(1)
    table = Table(title="Ingest result", box=box.ROUNDED)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key in ("ok", "accepted", "persisted", "rejected", "errors"):
        table.add_row(key, str(data.get(key, "?")))
    console.print(table)
    if data.get("errors"):
        raise typer.Exit(1)


@app.command()
def evaluate(
    premise: str = typer.Option(..., "--premise", help="Premise text."),
    hypothesis: str = typer.Option(..., "--hypothesis", help="Hypothesis text."),
) -> None:
    """POST /v1/evaluate with one pair and render the NLI Gate table."""
    item_id = f"cli_{uuid.uuid4().hex[:8]}"
    data = _post("/v1/evaluate", [{"id": item_id, "premise": premise, "hypothesis": hypothesis}])
    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        console.print(Panel(f"No NLI results returned: {data!r}", style="red"))
        raise typer.Exit(1)

    table = Table(title="NLI Gate evaluation", box=box.ROUNDED)
    table.add_column("ID")
    table.add_column("Label", style="bold")
    table.add_column("Entailment", justify="right")
    table.add_column("Neutral", justify="right")
    table.add_column("Contradiction", justify="right")
    table.add_column("Margin", justify="right")
    for res in results:
        label = str(res.get("label", "?"))
        color = {"entailment": "green", "contradiction": "red"}.get(label, "yellow")
        table.add_row(
            str(res.get("id", "")),
            f"[{color}]{label}[/{color}]",
            str(res.get("entailment", "?")),
            str(res.get("neutral", "?")),
            str(res.get("contradiction", "?")),
            str(res.get("margin", "?")),
        )
    console.print(table)


@app.command()
def watch(
    session_id: str | None = typer.Option(None, "--session-id", help="Only tail this session."),
    interval: float = typer.Option(1.0, "--interval", help="Polling interval in seconds."),
    threshold: float = typer.Option(0.92, "--threshold", help="Loop similarity threshold."),
    bell: bool = typer.Option(True, "--bell/--no-bell", help="Terminal bell when drift triggers."),
) -> None:
    """Live-tail executions with terminal alerts when drift occurs."""
    interval = min(max(interval, 0.2), 30.0)
    stream: deque[Text] = deque(maxlen=15)
    seen_exe: set[str] = set()
    known_loops: set[tuple[str, str]] = set()
    last_alert: str | None = None
    alert_count = 0
    online = False

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="stream", ratio=1),
        Layout(name="alert", size=7),
    )
    filt = session_id or "all sessions"
    layout["header"].update(
        Panel(
            f"Daemon: {DAEMON}  •  filter: {filt}  •  every {interval:g}s  •  threshold {threshold}  •  Ctrl+C to stop",
            title="agentdrift watch",
            style="cyan",
        )
    )
    layout["stream"].update(Panel("Waiting for executions…", title="Execution stream"))
    layout["alert"].update(Panel("No drift detected.", title="Alerts", style="dim"))

    def poll_json(method: str, path: str, payload: object = None):
        try:
            if method == "GET":
                r = requests.get(f"{DAEMON}{path}", timeout=min(TIMEOUT, interval + 5))
            else:
                r = requests.post(
                    f"{DAEMON}{path}", json=payload, timeout=min(TIMEOUT, interval + 5)
                )
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            return None

    def render() -> Layout:
        stream_panel = Panel(
            Text("\n").join(stream) if stream else Text("Waiting for executions…", style="dim"),
            title="Execution stream",
        )
        layout["stream"].update(stream_panel)
        if last_alert:
            layout["alert"].update(
                Panel(last_alert, title=f"Alerts ({alert_count})", style="bold red")
            )
        return layout

    try:
        with Live(render(), console=console, refresh_per_second=4, transient=False) as live:
            while True:
                exes = poll_json("GET", "/v1/executions?limit=200")
                if exes is None:
                    if online:
                        online = False
                        stream.append(Text("connection lost — retrying…", style="yellow"))
                    layout["header"].update(
                        Panel(
                            f"Daemon: {DAEMON}  •  OFFLINE, retrying every {interval:g}s  •  Ctrl+C to stop",
                            title="agentdrift watch",
                            style="red",
                        )
                    )
                    live.update(render())
                    time.sleep(interval)
                    continue
                online = True
                layout["header"].update(
                    Panel(
                        f"Daemon: {DAEMON}  •  filter: {filt}  •  every {interval:g}s"
                        f"  •  threshold {threshold}  •  alerts {alert_count}  •  Ctrl+C to stop",
                        title="agentdrift watch",
                        style="cyan",
                    )
                )
                if isinstance(exes, list):
                    ordered = sorted(
                        exes, key=lambda e: e.get("sequence", 0) if isinstance(e, dict) else 0
                    )
                    for exe in ordered:
                        if not isinstance(exe, dict):
                            continue
                        if session_id and exe.get("session_id") != session_id:
                            continue
                        eid = str(exe.get("execution_id", ""))
                        if not eid or eid in seen_exe:
                            continue
                        seen_exe.add(eid)
                        stream.append(
                            Text.from_markup(
                                f"[dim]{_short_time(exe.get('created_at'))}[/dim] "
                                f"[bold]\\[seq {exe.get('sequence', '?')}] "
                                f"{exe.get('agent_id', '?')}:{exe.get('node_id', '?')}[/bold]"
                                f" -> {_summarize_payload(exe)}"
                            )
                        )

                scan = poll_json("POST", "/v1/sentinel/scan", {"threshold": threshold})
                loops: list = []
                if isinstance(scan, dict) and scan.get("loops"):
                    loops = [lp for lp in scan["loops"] if isinstance(lp, dict)]
                    if session_id:
                        loops = [lp for lp in loops if lp.get("session_id") == session_id]
                else:
                    dets = poll_json("GET", "/v1/detections?limit=200")
                    if isinstance(dets, list):
                        for d in dets:
                            if not isinstance(d, dict) or d.get("kind") != "ping_pong_loop":
                                continue
                            if session_id and d.get("session_id") != session_id:
                                continue
                            loops.append(
                                {
                                    "session_id": d.get("session_id"),
                                    "execution_id": d.get("execution_id"),
                                    "prior_execution_id": d.get("prior_execution_id"),
                                    "similarity": d.get("similarity"),
                                }
                            )
                for loop in loops:
                    key = (str(loop.get("session_id")), str(loop.get("execution_id")))
                    if key in known_loops:
                        continue
                    known_loops.add(key)
                    alert_count += 1
                    last_alert = (
                        f"🚨 DRIFT DETECTED: Ping-Pong Loop in Session {loop.get('session_id')} "
                        f"between execution {loop.get('prior_execution_id')} and {loop.get('execution_id')} "
                        f"(similarity: {loop.get('similarity')})"
                    )
                    if bell:
                        try:
                            console.bell()
                        except Exception:
                            pass
                    stream.append(Text("🚨 drift alert — see Alerts pane", style="bold red"))

                live.update(render())
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("[dim]Stopped watching.[/dim]")


def _short_time(value: object) -> str:
    """Format an ISO timestamp as HH:MM:SS; fall back to now."""
    if isinstance(value, str) and value:
        try:
            return (
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                .astimezone()
                .strftime("%H:%M:%S")
            )
        except ValueError:
            pass
    return datetime.now().strftime("%H:%M:%S")


def _summarize_payload(exe: dict, width: int = 100) -> str:
    """One-line summary of an execution's payload for the tail view."""
    for key in ("output_payload", "input_payload"):
        payload = exe.get(key)
        if payload:
            try:
                text = (
                    payload
                    if isinstance(payload, str)
                    else json.dumps(payload, sort_keys=True, default=str)
                )
            except (TypeError, ValueError):
                text = str(payload)
            text = " ".join(text.split())
            if exe.get("state_hash"):
                text += f"  [state={exe.get('state_hash')}]"
            return text[:width] + ("…" if len(text) > width else "")
    if exe.get("state_hash"):
        return f"[state={exe.get('state_hash')}]"
    return "(empty payload)"


@app.command(name="test-all")
def test_all() -> None:
    """End-to-end checks: health → ingest x2 → scan → evaluate → scorecard."""
    scorecard: list[tuple[str, bool, str]] = []

    # 1. /health
    try:
        h = _get("/health")
        ok = isinstance(h, dict) and h.get("status") == "ok"
        scorecard.append(("health", ok, str(h.get("version", "?")) if ok else repr(h)[:120]))
    except typer.Exit:
        scorecard.append(("health", False, "connection failed"))
        _print_scorecard(scorecard)
        raise

    # 2. Ingest two consecutive identical events (ping-pong trigger)
    session_id = f"cli-e2e-{uuid.uuid4().hex[:8]}"
    ping_hash = f"cli-ping-{uuid.uuid4().hex[:8]}"
    event_payload = {"state": "waiting-for-tool", "action": "repeat-check"}
    ingest_ok = True
    ingest_detail = ""
    for i in range(2):
        try:
            res = _post(
                "/v1/ingest",
                {
                    "executions": [
                        {
                            "session_id": session_id,
                            "agent_id": "cli-e2e-agent",
                            "node_id": "e2e-node",
                            "input_payload": {"goal": "cli e2e loop check"},
                            "output_payload": event_payload,
                            "state_hash": ping_hash,
                        }
                    ]
                },
            )
            if not (isinstance(res, dict) and res.get("persisted", 0) >= 1):
                ingest_ok = False
                ingest_detail = repr(res)[:120]
        except typer.Exit:
            ingest_ok = False
            ingest_detail = "connection failed"
            break
    scorecard.append(("ingest x2", ingest_ok, "2 events persisted" if ingest_ok else ingest_detail))

    # 3. Sentinel scan asserts >= 1 detection
    try:
        s = _post("/v1/sentinel/scan", {"threshold": 0.92})
        dets = int(s.get("detections", 0) or 0) if isinstance(s, dict) else 0
        scorecard.append(("sentinel scan", dets >= 1, f"detections={dets}"))
    except typer.Exit:
        scorecard.append(("sentinel scan", False, "connection failed"))

    # 4. NLI evaluate scoring
    try:
        e = _post(
            "/v1/evaluate",
            [
                {
                    "id": "cli-e2e-nli",
                    "premise": "the cat sits on the mat",
                    "hypothesis": "the cat sits on the mat",
                }
            ],
        )
        results = e.get("results", []) if isinstance(e, dict) else []
        nli_ok = bool(results) and all(
            all(k in r for k in ("entailment", "neutral", "contradiction", "label", "margin"))
            for r in results
        )
        label = results[0].get("label", "?") if results else "?"
        scorecard.append(("nli evaluate", nli_ok, f"label={label}" if nli_ok else repr(e)[:120]))
    except typer.Exit:
        scorecard.append(("nli evaluate", False, "connection failed"))

    _print_scorecard(scorecard)
    if not all(passed for _, passed, _ in scorecard):
        raise typer.Exit(1)


def _print_scorecard(scorecard: list[tuple[str, bool, str]]) -> None:
    table = Table(title="AgentDrift E2E scorecard", box=box.ROUNDED)
    table.add_column("Check", style="bold cyan")
    table.add_column("Result")
    table.add_column("Detail")
    for name, passed, detail in scorecard:
        table.add_row(name, "[green]PASS[/green]" if passed else "[red]FAIL[/red]", detail)
    console.print(table)
    if all(p for _, p, _ in scorecard):
        console.print(Panel("All checks passed.", style="green"))
    else:
        console.print(Panel("One or more checks failed — see scorecard.", style="red"))


def main() -> None:
    """Console-script entrypoint (`agentdrift` command)."""
    app()


if __name__ == "__main__":
    main()
