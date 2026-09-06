import pytest
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from framed.api import build_app
from framed.compositor import Compositor
from framed.config import Config
from framed.layers import Layer, LayerStack
from framed.photos import PhotoLibrary
from framed.pixoo import Pixoo
from tests.test_pixoo import FakeSession


@pytest.fixture
async def client(tmp_path):
    session = FakeSession()
    pixoo = Pixoo("h", session, min_interval=0, frame_interval=0)
    photos = PhotoLibrary(tmp_path / "photos", None)
    Image.new("RGB", (64, 64), (5, 5, 5)).save(tmp_path / "photos" / "a.png")
    stack = LayerStack()
    stack.upsert(Layer("base", 0, {"type": "photos"}))
    compositor = Compositor(Config(), pixoo, stack, photos, session)
    app = build_app(compositor, "secret")
    async with TestClient(TestServer(app)) as tc:
        tc.compositor = compositor
        tc.device_calls = session.calls
        yield tc


async def test_auth_required_except_healthz(client):
    assert (await client.get("/healthz")).status == 200
    assert (await client.get("/status")).status == 401
    resp = await client.get("/status", headers={"Authorization": "Bearer secret"})
    assert resp.status == 200
    assert (await resp.json())["layers"][0]["id"] == "base"


async def test_layer_lifecycle_and_render(client):
    h = {"Authorization": "Bearer secret"}
    body = {
        "id": "greet-elijah",
        "priority": 80,
        "ttl": 60,
        "cooldown": 1800,
        "content": {"type": "greeting", "name": "Elijah"},
    }
    resp = await client.post("/layers", json=body, headers=h)
    assert resp.status == 200 and (await resp.json())["accepted"]
    await client.compositor._tick()
    assert client.compositor.showing[0] == "greet-elijah"
    assert client.device_calls[-1][1]["PicNum"] == 16
    resp = await client.post("/layers", json=body, headers=h)
    assert not (await resp.json())["accepted"]
    resp = await client.delete("/layers/greet-elijah", headers=h)
    assert (await resp.json())["removed"]
    await client.compositor._tick()
    assert client.compositor.showing[0] == "base"
    assert client.device_calls[-1][1]["PicNum"] == 1


async def test_greeting_with_several_names(client):
    h = {"Authorization": "Bearer secret"}
    body = {
        "id": "greet-elijah-ram",
        "priority": 80,
        "content": {"type": "greeting", "names": ["Elijah", "Ram"]},
    }
    await client.post("/layers", json=body, headers=h)
    await client.compositor._tick()
    assert client.compositor.showing[0] == "greet-elijah-ram"
    assert client.compositor._greeting_names(body["content"])[1][0] == "RAM"


async def test_bad_content_type_is_400(client):
    h = {"Authorization": "Bearer secret"}
    resp = await client.post("/layers", json={"id": "x", "content": {"type": "nope"}}, headers=h)
    assert resp.status == 400


async def test_unrenderable_layer_is_dropped(client):
    h = {"Authorization": "Bearer secret"}
    body = {"id": "art", "priority": 40, "content": {"type": "image", "url": "/relative"}}
    await client.post("/layers", json=body, headers=h)
    await client.compositor._tick()
    assert [layer.id for layer in client.compositor.stack.all()] == ["base"]
