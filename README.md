# Tenko local bridge

Python replacement for the **captured Tenko 8.2w1.2** cloud exchange in
[`prompt.md`](prompt.md). Receives boiler telemetry over HTTP, publishes MQTT
Home Assistant discovery, and sends settings back on the next boiler poll.
The only Python dependency is `paho-mqtt`. There is **no SQLite or database
server**: reports, pending settings, and editor drafts live in one atomic JSON
file.

## Run with Docker Compose

```sh
cp .env.example .env
# Edit .env: set EDITOR_PASSWORD, MQTT_HOST, MQTT_USERNAME, MQTT_PASSWORD,
# EDITOR_URL, FRAME_ANCESTORS and your boiler serial.
./build.sh
docker compose up -d
docker compose logs -f tenko
```

`docker-compose up -d` also works with the standalone Compose command. Compose
can build the image itself with `docker compose up -d --build`. `build.sh`
accepts `IMAGE_NAME` for an alternate image tag; update Compose's `image` if
using that option.

Open `EDITOR_URL` and sign in with `EDITOR_USERNAME` / `EDITOR_PASSWORD`.
The device appears after its first report. The default HTTP port is **9080**.
Configure the boiler/network to send its existing cloud HTTP requests to this
host. If the boiler uses `my.tenko.ua:80`, a DNS override alone changes only
the address, not the port: map a private LAN listener on port 80 to this
service's port 9080, or explicitly configure the boiler's server/port if its
firmware supports that. The service does not modify the boiler, router, DNS,
or firewall automatically.

The `tenko-data` named volume preserves `/data/state.json` and its process-lock
file across container recreation. Do not remove the volume to upgrade.
Only one process may use a state file. To back up, stop the service and copy
`state.json`; restore it with ownership allowing UID/GID `10001` to write the
file **and its parent directory**. Atomic replacement requires a directory
mount, not a bind mount of only the JSON file. Invalid persisted JSON causes
startup failure, rather than resetting settings. This design targets a small
number of boilers, not a high-volume telemetry archive.

## Environment configuration

Compose passes these variables to the application. For native Python they
are read from the process environment; `.env` is loaded by Compose, not by
Python itself.

| Variable | Default | Meaning |
|---|---|---|
| `HTTP_HOST` | `0.0.0.0` | Native HTTP listen address; Compose fixes this inside the container |
| `HTTP_PORT` | `9080` | HTTP port, also used by Compose's port mapping |
| `HTTP_BIND_ADDRESS` | `0.0.0.0` | Compose-only host bind address |
| `MQTT_HOST` | `localhost` native / `host.docker.internal` Compose | Broker hostname/address |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | empty | Broker authentication; password is passed unchanged |
| `MQTT_CLIENT_ID` | `tenko-local` | Must be unique per bridge instance |
| `MQTT_TLS` | `false` | Enable TLS certificate and hostname verification |
| `MQTT_CA_FILE` | empty | Optional CA bundle path inside the container; system trust used otherwise |
| `MQTT_PREFIX` | `tenko` | Data/command topic prefix; no wildcards |
| `DISCOVERY_PREFIX` | `homeassistant` | Discovery prefix and HA birth-topic prefix |
| `FRESHNESS_TIMEOUT` | `180` | Seconds since a parameter report before the boiler becomes unavailable |
| `CONFIRMATION_TIMEOUT` | `600` | Seconds before unconfirmed pending settings are marked error; retries continue |
| `STATE_PATH` | `data/state.json` native / `/data/state.json` Compose | Persistent JSON state file |
| `EDITOR_USERNAME` | `admin` | HTTP Basic authentication user |
| `EDITOR_PASSWORD` | **required** | Authentication password; startup refuses empty credentials |
| `EDITOR_URL` | `http://localhost:9080` | Browser-reachable root URL used in HA device configuration links |
| `FRAME_ANCESTORS` | `'self'` | CSP frame allowlist; space-separated exact HTTP(S) origins |
| `STATUS_PATH`, `STATUS_METHOD` | empty, disabled | Both required to enable the separately captured status exchange |
| `NO_CHANGE_BODY` | `nochange` | Exact no-update body; may explicitly be empty |
| `ALLOWED_SERIALS` | empty native | Optional comma-separated serial allowlist; example `.env` restricts to captured serial |
| `LOG_LEVEL` | `INFO` | Python logging level |

For TLS with a private MQTT CA, mount it read-only in a Compose override,
for example `./broker-ca.pem:/certs/broker-ca.pem:ro`, set
`MQTT_CA_FILE=/certs/broker-ca.pem`, and use the broker's TLS port.
Do not disable TLS verification. The supplied Compose file uses an existing
MQTT broker; it does not install a second broker.

Native execution (Python 3.11+, Linux):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export EDITOR_PASSWORD='choose-a-strong-unique-password'
export MQTT_HOST=192.168.1.10
export EDITOR_URL=http://192.168.1.20:9080
.venv/bin/python -m tenko
```

## Protocol and confirmation

* `POST /update/param` accepts `application/x-www-form-urlencoded`.
  Field names are case-sensitive. `&` separates fields; schedule semicolons
  remain inside their values. No executable parsing/eval is used.
* Original raw values, unknown fields, fault codes, all ten schedule slots,
  leading-zero hours, and received duplicate-hour points remain inspectable.
  Incoming settings such as `TMP=Off,6.9` are not clamped to UI limits.
* Structurally malformed known fields are persisted with explicit parse
  errors and produce HTTP 400, not fabricated zero readings or a settings
  upload. Invalid serials, duplicate form keys, invalid content types and
  oversized bodies are rejected. Numeric fault tokens are retained as
  diagnostics, while their numeric HA entities become unavailable.
* With no pending changes, the response is HTTP 200 and exact `nochange`
  (or an empty body if configured).
* Changes are validated and persisted **before** being accepted. Every upload
  uses the captured complete layout:
  `USE,TMP,MO,TU,WE,TH,FR,SA,SU,ED,FI,RE,PMT,pNA,STU,MOD`, inside
  `NewData:...;EndData`, with slash-separated unbracketed schedules and
  captured numeric padding. No partial wire commands are invented.
* The first complete parameter report supplies the baseline for unchanged
  settings. A command is rejected if that baseline is incomplete or cannot
  safely be serialized. Unchanged captured schedules, including duplicate
  hours, can be passed through; stricter validation applies to edited days.
* User changes remain separate from telemetry. A sent HTTP response is
  **pending**, not applied. Subsequent reports must agree with the requested
  setting fields. Until then the command is retried on parameter polls.
  Confirmation timeout is visible as an error without silently deleting the
  desired settings. Cancel stops retries but cannot recall a response already
  delivered to the boiler. Physical control-panel changes may conflict with a
  pending bridge command; cancel it if the local change should win.
* `ST1`/`ST2` and `STU` duplicate-enable equivalence is an explicit assumption.
  A disagreement is exposed, and neither representation silently wins.
  Resolve it using a complete `STU` tuple from the editor or structured MQTT
  command. Manual-stage permission is never interpreted as actual heating.
* The separate status request path/method are **not known**. Do not guess an
  endpoint from the response text. Set both variables once captured or
  intentionally configured; supported form-body methods are POST, PUT, PATCH.
  This handler returns exact `status updated`. Its raw status and timestamp
  are independent of MOD/TEN telemetry. Only the explicitly assumed
  `0=off, 1=on` derived state is exposed; other codes remain unknown.

The original historical captures remain in `prompt.md`, unchanged. Header
lengths in those captures are not reused. The matching old saved page is the
primary supporting UI reference; the newer SMART page and
<https://my.tenko.ua/api/> are not substituted for this firmware's wire format.

### New-setting validation

| Setting | Accepted input |
|---|---|
| `USE` | `Temp`, `GraphD`, `GraphW` |
| `TMP` | `[On/Off, 7..40]`, target step 0.1 C |
| `FI`, `RE` | `[10..75, 1..9]`, whole degrees |
| `PMT` | `[On/Off, 6..15, 7..17]`, whole degrees; lower strictly below upper |
| `pNA` | `[1..15, 1..15]`, whole minutes |
| `STU` | `[On/Off, On/Off]` |
| `MOD` | `On` or `Off` only |
| `ED`, `MO`...`SU` | Exactly ten `[hour,target]` pairs; strictly increasing integer hours 0..23; target 0=OFF or 7..40 C, step 0.1 |

## MQTT and Home Assistant

Enable the standard MQTT integration in HA using the same broker. Each serial
gets a separate stable device identifier `tenko_<serial>`, device name
**Tenko Boiler**, manufacturer Tenko and reported firmware. All applicable
sensors, binary sensors, switches, numbers and mode select are discovered.
No custom integration, HACS, or cloud asset is needed.

Discovery configurations, state, schedule attributes, diagnostics and
availability are retained. The bridge republishes discovery on broker
reconnection and on `<DISCOVERY_PREFIX>/status` = `online` (HA birth). A retained
command delivered on subscription is ignored, never replayed at startup.
Commands should always be sent **without retain**. The MQTT account should
have read/write permission on the bridge prefix, write permission on discovery
configuration topics, and read permission on the HA status topic.

For the default prefixes and serial `211229_005`:

| Topic | Payload / purpose |
|---|---|
| `tenko/bridge/availability` | Bridge `online` / LWT `offline` |
| `tenko/211229_005/availability` | Parameter-report freshness |
| `tenko/211229_005/status_availability` | Independent separate-status freshness |
| `tenko/211229_005/state` | Flat JSON of confirmed reported components and upload status |
| `tenko/211229_005/diagnostics` | Raw/decoded fields, faults, assumptions, pending values, reported settings, monthly array |
| `tenko/211229_005/schedules/ED` | `{points, pending, draft}`; same layout for MO-SU |
| `tenko/211229_005/command/<entity-key>` | Single control payload, plain `On`/`Off`, number, or mode |
| `tenko/211229_005/command/settings` | JSON object mapping demonstrated response keys to complete values |
| `homeassistant/<component>/tenko_211229_005/<entity-key>/config` | Full discovery payload including state and command mappings |

Discovery payloads are generated centrally in `tenko/entities.py` and can be
inspected directly on the broker. Read-only entities have no command topic.
The complete configurable entity mapping is:

| Entity key | Setting/component | Command payload |
|---|---|---|
| `mode` | `USE` | `Temp`, `GraphD`, `GraphW` |
| `constant_enabled` | `TMP[0]` | `On`, `Off` |
| `constant_target` | `TMP[1]` | Number |
| `flow_cutoff`, `flow_hysteresis` | `FI[0]`, `FI[1]` | Number |
| `return_cutoff`, `return_hysteresis` | `RE[0]`, `RE[1]` | Number |
| `pmt_enabled` | `PMT[0]` | `On`, `Off` |
| `pmt_min`, `pmt_max` | `PMT[1]`, `PMT[2]` | Number |
| `modulation` | `MOD` enable only | `On`, `Off` |
| `manual_1`, `manual_2` | `STU[0]`, `STU[1]` | `On`, `Off`; applicable only with modulation off |
| `pump_start`, `pump_stop` | `pNA[0]`, `pNA[1]` | Number, minutes |

Example structured command, useful for atomic PMT-pair changes:

```sh
mosquitto_pub -h BROKER -u USER -P PASSWORD \
  -t tenko/211229_005/command/settings \
  -m '{"PMT":["On",10,14],"STU":["Off","On"],"MOD":"Off"}'
```

Each individual control is merged with the latest reported or pending tuple,
then validated as a complete tuple. HA controls show **reported**, not
optimistic desired, values until the boiler confirms. Check the
**Settings upload status**, **Settings command error** and raw diagnostic
attributes for pending/error details. If changing a threshold individually
would violate ordering, use the structured tuple command or editor instead.

### Entity semantics

TA/TF/TR, PM-associated temperature and numeric pressure are measurement
sensors. Nonnumeric faults remain separately visible in raw diagnostics.
NA keeps pump on/off/pause/fault states. TEN1/TEN2 and MOD heating have raw
operating-state sensors plus binary sensors only for unambiguous On/Off.
MOD counts, PM state, AF phase, raw Err, raw weekday, boiler clock, sensor type,
serial/firmware, last reports, schedule summaries and all consumption
components are exposed. AF Off is **standby**, On is **checking**; unknown
heating/error codes are not guessed. `Err=1` is **not** decoded as `Err1`.
Unknown channel/current-sensor identifiers remain in raw diagnostics; no
universal physical-channel grouping is inferred.

Nominal `Pow` and stage capacities are **rated kW**, not current consumption.
FI/RE targets remain separate from TF/TR measurements. PMT settings remain
separate from PM operating state. Only two manual-stage control entities are
created, not duplicate ST1/ST2/STU controls. Boiler error, clock, sensor
selection and frost protection are read-only; unsupported writes are absent.

Entity availability requires the bridge connection, fresh parameter reports,
and a non-null component value. Separate-status entities additionally require
fresh separate status. A running bridge, MQTT connection, or status-only poll
does not make old temperature readings fresh.

### Schedule editor and dashboard embedding

The responsive editor at `/` has daily and Monday-Sunday weekly views,
24 whole-hour step timelines, explicit OFF values, and all ten editable slots.
Choose a timeline slot/target and click an hour to edit graphically, or use
the point list. Copy from another day or copy the selected day to multiple
checked weekdays. There is no implicit sorting, padding, deduplication, or
midnight-wrap assumption. Duplicate-hour programs are inspectable and warned
about; their ambiguous timeline is shown as unknown until explicitly resolved.
An interval preceding the first point is also shown as unknown.

Reported, draft, and pending layers are separate. Drafts are persisted on
editing without upload and are not overwritten by new reports. Concurrent
editor draft conflicts are rejected rather than silently merged. Edits that
fail to save remain in the open page with a visible error; resolve/reload
before applying. Draft schedules upload only with **Apply draft schedules**.
The separate settings Apply button activates Temp/GraphD/GraphW explicitly.
Drafts remain after upload for inspection/reuse; discard them explicitly when
done. Do not edit the same device from multiple tabs simultaneously.

MQTT discovery cannot create dashboard cards. Add a standard **Webpage**
card once, or adapt [`examples/home-assistant.yaml`](examples/home-assistant.yaml),
which separates live readings, settings, schedule and reference consumption.
HA-generated entity IDs depend on naming/conflicts: select the actual entities
from your discovered device when adapting the example.

```yaml
type: iframe
url: https://tenko.example.net/?serial=211229_005
aspect_ratio: 120%
```

**HTTPS HA cannot embed an HTTP editor.** Use an HTTPS reverse proxy and set
`EDITOR_URL=https://tenko.example.net` and, for example,
`FRAME_ANCESTORS="'self' https://ha.example.net"`. A root-mounted Caddy
example is in [`examples/Caddyfile`](examples/Caddyfile); attach the proxy to
the same Docker network as the service and adapt its upstream port if needed.
Only permit a trusted LAN/VPN to reach it. The boiler still talks private
plain HTTP, independently of the editor's HTTPS browser URL.

Authentication is intentionally required on the editor, assets and management
API. Open the editor directly and authenticate before embedding; browser
cross-origin credential restrictions can prevent interactive login inside an
iframe. A same-origin reverse-proxy hostname/routing arrangement is preferable
where browser policies require it. This application expects root mounting,
not an unconfigured subpath. Do not put credentials in iframe URLs, disable
browser security, remove authentication, or expose the boiler's HTTP listener
to the Internet. JSON mutations additionally require a custom CSRF header,
and the API does not enable cross-origin reads/writes. CSP allows only the
configured embedding origins. Basic authentication over plain HTTP is
appropriate only on a trusted isolated network; use HTTPS for browser access.
The boiler protocol itself has no captured authentication mechanism, so
network isolation and firewall rules remain essential.

### Statistics are reference data, not Energy meters

STA's selected period and amount, StD, StW and all twelve YSt indexes are
separate diagnostic/reference sensors. Units are explicitly **presumed kWh**;
scaling, window/reset boundaries and calendar-month identities are unverified.
They have **no energy device class and no total/total_increasing state class**.
Never sum successive reports, accumulate positive differences, backdate them
into HA statistics, or add them as additional Energy dashboard loads.

Use an independent verified cumulative electricity meter for the Energy
dashboard. No estimated live power sensor, nominal-capacity-as-power signal,
energy integration, historical statistics import, or second schedule authority
is enabled by this bridge. HA's Schedule helper does not upload boiler
schedules; use the supplied editor/structured schedule commands.

## Management API and diagnostics

All management endpoints require HTTP Basic authentication.

| Method/path | Body / result |
|---|---|
| `GET /health` | Unauthenticated liveness and `mqtt_connected`; HTTP stays usable if MQTT is down |
| `GET /api/boilers` | Known serials and last parameter report timestamps |
| `GET /api/boilers/<serial>` | Reported, raw, pending, draft, timestamps, warnings and revisions |
| `POST /api/boilers/<serial>/settings` | `{"settings":{"MOD":"Off"},"revision":CURRENT_REVISION}` |
| `PUT /api/boilers/<serial>/draft` | `{"draft":{...},"revision":CURRENT_DRAFT_REVISION}`; replace draft only |
| `POST /api/boilers/<serial>/cancel` | `{}`; cancel pending retries |

Mutations require `Content-Type: application/json` and `X-Tenko-Request: 1`.
Bodies are limited to 64 KiB; chunked requests are not supported. An unknown
or unconfigured route is not treated as a status request. MQTT outages do not
prevent durable report handling or boiler command responses; the latest state
and discovery are republished when the broker reconnects. Logs report
malformed reports, duplicate-stage conflicts, rejected commands and I/O errors.
If storage cannot be written the HTTP operation fails rather than reporting
a durable success.

## Development checks

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check tenko/static/editor.js
EDITOR_PASSWORD=validation-only docker compose config --quiet
./build.sh
```

The tests use the unmodified captured payload and exact settings response from
`prompt.md`, and cover serialization, fault preservation, input constraints,
JSON restart recovery/atomic writes, locking, confirmation/retry, independent
status, HTTP authentication/CSRF, MQTT command mapping, availability and
discovery. Physical boiler acceptance and the uncaptured status endpoint still
require verification against the actual installation.
