"""啟動煙霧測試（A3，2026-06-13）。

只驗證 app 可組裝、路由齊全；不發請求（避免 lifespan 副作用：備份排程等）。
執行：cd backend && pytest tests/test_app_smoke.py
"""


def test_app_imports_and_routes():
    from main import app

    paths = {r.path for r in app.routes}
    # 16 routers、129+ routes（2026-06-10 煙霧基準）
    assert len(app.routes) >= 120

    # 各功能域代表路由（缺一即代表 router 掛載壞了）
    for expected in (
        "/api/v1/art/generate",
        "/api/v1/art/generate-async",
        "/api/v1/art/inpaint",
        "/api/v1/art/upscale",
        "/api/v1/generation-history",
        "/api/v1/projects",
        "/api/v1/characters",
    ):
        assert any(p.startswith(expected) or p == expected for p in paths), f"missing route: {expected}"
