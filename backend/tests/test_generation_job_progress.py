"""生圖 job 進度 SSE（2026-09-24）。

根因：前端 GenerateTab.streamJobProgress 訂閱 GET /art/jobs/{id}/progress，
後端自 eb4425f（06-18）只做了 generation_jobs 的 queue 推送、從未掛 SSE 路由 → 404，
EventSource.onerror 立刻 reject，文字→生圖永遠顯示「進度連線中斷」，背景 job 其實有跑完。

測試分三層：
1. stream_job_events 產生器行為（晚訂閱、正常收尾、heartbeat 不斷流、終結事件遺失保底）
2. HTTP 路由（404 / 已完成 job 立即收尾）
3. 前端↔後端契約：列舉前端原始碼裡所有 /art/ 路徑，反向驗證後端都有路由
   （只驗「被點名的路由」測不出前端多呼叫了一條後端沒有的路由）
"""
import asyncio
import json
import pathlib
import re

from app.services.ai import generation_jobs as gj


def _collect(job, until_done_actions=None):
    """跑產生器直到結束；until_done_actions(n, ev) 可在第 n 個事件後注入推送。"""
    async def run():
        out = []
        async for ev in gj.stream_job_events(job):
            out.append(ev)
            if until_done_actions:
                until_done_actions(len(out), ev)
        return out
    return asyncio.run(asyncio.wait_for(run(), timeout=5))


def _finish(job, status="done"):
    """模擬 run_txt2img_job 的 finally 收尾。"""
    job.status = status
    job.progress.update(pct=100 if status == "done" else job.progress["pct"], status=status)
    gj._push_progress(job.id, {**job.progress, "event": job.status})
    gj._push_progress(job.id, None)


def test_late_subscriber_gets_terminal_event_immediately():
    job = gj.create_job(meta={})
    job.status = "done"
    events = _collect(job)
    assert [e["event"] for e in events] == ["done"]
    assert job.id not in gj._progress_queues  # 取消訂閱後不留空 key


def test_live_stream_snapshot_progress_then_done():
    job = gj.create_job(meta={})
    job.status = "running"

    def inject(n, ev):
        if n == 1:  # 收到 snapshot 後才推，確保已訂閱
            gj._push_progress(job.id, {"pct": 40, "value": 8, "max": 20, "event": "progress"})
            _finish(job, "done")

    events = _collect(job, inject)
    assert [e["event"] for e in events] == ["snapshot", "progress", "done"]
    assert events[-1]["pct"] == 100
    assert job.id not in gj._progress_queues


def test_heartbeat_does_not_end_stream(monkeypatch):
    monkeypatch.setattr(gj, "_SSE_HEARTBEAT_SECONDS", 0.01)
    job = gj.create_job(meta={})
    job.status = "running"

    def inject(n, ev):
        if ev.get("heartbeat"):
            _finish(job, "done")

    events = _collect(job, inject)
    assert events[0]["event"] == "snapshot"
    assert any(e.get("heartbeat") for e in events)
    assert events[-1]["event"] == "done"


def test_missed_terminal_event_recovered_on_heartbeat(monkeypatch):
    monkeypatch.setattr(gj, "_SSE_HEARTBEAT_SECONDS", 0.01)
    job = gj.create_job(meta={})
    job.status = "running"

    def inject(n, ev):
        if n == 1:
            job.status = "error"  # 狀態變了但沒推事件
            job.progress["status"] = "error"

    events = _collect(job, inject)
    assert events[-1]["event"] == "error"


def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)  # 不用 with → 不跑 lifespan（同 smoke test 原則）


def test_progress_route_unknown_job_404():
    r = _client().get("/api/v1/art/jobs/does-not-exist/progress")
    assert r.status_code == 404


def test_progress_route_streams_terminal_event_for_finished_job():
    job = gj.create_job(meta={})
    job.status = "done"
    job.progress.update(pct=100, status="done")
    with _client().stream("GET", f"/api/v1/art/jobs/{job.id}/progress") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in r.iter_lines() if ln.startswith("data: ")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    assert payloads == [{**job.progress, "event": "done"}]


_FRONTEND_SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
_ART_PATH_RE = re.compile(r"[`'\"](/art/[^`'\"?\s]*)")


def test_every_frontend_art_path_has_backend_route():
    from main import app
    route_res = [
        re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$")
        for r in app.routes if hasattr(r, "path")
    ]
    used = set()
    for f in _FRONTEND_SRC.rglob("*.js*"):
        used.update(m.group(1) for m in _ART_PATH_RE.finditer(f.read_text(encoding="utf-8")))
    assert used, "沒掃到任何前端 /art/ 路徑，掃描規則可能失效"
    missing = [
        p for p in sorted(used)
        if not any(rx.match("/api/v1" + re.sub(r"\$\{[^}]+\}", "X", p)) for rx in route_res)
    ]
    assert not missing, f"前端呼叫但後端沒有的路由：{missing}"
