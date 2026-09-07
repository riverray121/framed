# framed

A scene server for the Divoom Pixoo-64. Clients (Home Assistant, agents, scripts) push
*layers* over HTTP; framed keeps the panel showing the highest-priority live layer and
handles every firmware quirk in one place. A greeting for three minutes, album art while
music plays, a photo carousel underneath: each is one layer with a priority and a lifetime.

## How it works

```
POST /layers {id, priority, ttl, content}
   -> layer stack (highest priority wins; expired layers fall away)
   -> renderer (Pillow, 64x64, bitmap font)
   -> device driver (one writer, spaced commands, GIF-id reset, brightness cap)
   -> Pixoo-64 over its local HTTP API
```

The stack is the whole model. There is no "mode" to switch; a client adds a layer and
optionally gives it a `ttl`. When the layer expires or is deleted, whatever is beneath it
comes back on its own. A `cooldown` on a layer id stops the same event from replaying
(GPS jitter re-triggering a welcome, for example). Posting a layer again with the same
content restarts its lifetime without redrawing, so a second signal can shorten or extend
what is already on screen.

Content types:

| type | fields | renders |
|---|---|---|
| `photos` | | the photo carousel (see below) |
| `image` | `url` | a fetched image, square-cropped and resampled |
| `greeting` | `names` (or `name`), `color?`, `speed?` | a short looping animation with the names, one line each |
| `text` | `text` or `lines`, `color?`, `background?` | up to five centered lines |
| `color` | `color` | a solid fill |
| `clock` | `id` | one of the device's built-in clock faces (no frame pushes) |
| `channel` | `index` | a device channel: 0 faces, 1 cloud, 2 visualizer, 3 custom |

## Photo carousel

Point `photos.album` at a public iCloud Shared Album link. framed mirrors the album
into its data directory as pre-rendered 64x64 frames, re-checks it on `photos.refresh`,
and cycles frames every `photos.interval` seconds while the carousel is the top layer.
Adding a photo to the album on a phone puts it in rotation on the next refresh; removing
it drops the frame.

## Stability

The Pixoo-64 firmware is easy to wedge. The driver enforces the known limits:

- One command at a time, at least `pixoo.min_interval` seconds apart.
- `Draw/ResetHttpGifId` before every push (`pixoo.reset_every`), otherwise the device
  silently stops accepting frames after a few hundred.
- Animations capped at `pixoo.max_frames`; stills everywhere else.
- Brightness capped at `pixoo.max_brightness`.
- A watchdog probes the device and restores brightness and the current layer after a
  power cycle, so a smart plug on the display is a complete recovery path.

## HTTP API

All routes except `/healthz` require `Authorization: Bearer <token>`.

| route | body | effect |
|---|---|---|
| `GET /healthz` | | 200 while the compositor loop is alive |
| `GET /status` | | device state, layers, photo library |
| `GET /layers` | | live layers, top first |
| `POST /layers` | `{id, priority, content, ttl?, cooldown?}` | add or replace a layer |
| `DELETE /layers/{id}` | | remove a layer |
| `POST /brightness` | `{level}` | 0 to `max_brightness` |
| `POST /screen` | `{on}` | screen on or off |
| `POST /photos/refresh` | | re-check the album now |

```sh
curl -X POST http://127.0.0.1:8090/layers -H "Authorization: Bearer $FRAMED_TOKEN" \
  -d '{"id":"greet-elijah","priority":80,"ttl":180,"cooldown":1800,
       "content":{"type":"greeting","name":"Elijah"}}'
```

## Running

```sh
pip install .
FRAMED_TOKEN=... framed --config config.yaml
```

Or with Docker, mounting a config file at `/config/config.yaml` and a volume at `/data`.
Copy `example-config.yaml` to start. Every setting is documented there.

## Home Assistant

framed has no HA-specific code. HA drives it with `rest_command` entries and reads
`/status` with a `rest` binary sensor, so the display's health shows up as an entity.
An automation on `zone.home` greets whoever arrives, one on a media player pushes album
art, and time triggers set brightness. See the example config for the layer priorities
those automations assume.

## License

MIT
