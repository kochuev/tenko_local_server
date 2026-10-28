# Tenko local server

Python bridge for the captured Tenko 8.2w1.2 boiler protocol in
[`prompt.md`](prompt.md). The boiler reports over HTTP; Home Assistant reads
and configures it using **native MQTT entities only**. No iframe, web editor,
custom card, HACS integration, cloud service, or SQLite is needed.

The boiler stores and executes applied settings and schedules. The bridge
holds pending commands and schedule drafts in a small atomic JSON file,
plus a cache of the last report for discovery/diagnostics. That cache is
**not** an independent active configuration: a fresh boiler report always
supplies the confirmed state. Once a later report confirms pending settings,
the pending command and any matching submitted draft are cleared. Newer edits
are preserved. HA and the bridge need not stay online for a confirmed boiler
schedule to execute.

## Run

```sh
cp .env.example .env
# Set MQTT_HOST, MQTT_USERNAME, MQTT_PASSWORD and ALLOWED_SERIALS.
./build.sh
docker compose up -d
docker compose logs -f tenko
```

`docker-compose up -d` also works with standalone Compose.
`docker compose up -d --build` can build the image without the separate script.
`build.sh` accepts an optional `IMAGE_NAME`; match Compose's `image` if changing
that tag.

Configure the boiler/network to direct its cloud requests to this service.
The default listener is port **9080**. If the boiler sends to
`my.tenko.ua:80`, a DNS override changes the address but not the port: arrange
a private LAN port-80 listener/forwarder to port 9080, or configure the boiler
server/port if supported. The bridge does not change DNS/router settings.

Use the same broker in Home Assistant's standard MQTT integration. A
**Tenko Boiler** device is discovered for each allowed serial after its first
report (a status-only report also creates the device, but settings remain
unavailable until parameter data arrives). Open its device page for all native
controls, or use the standard cards in
[`examples/home-assistant.yaml`](examples/home-assistant.yaml). Discovery
creates entities, not dashboard cards or views. Paste the YAML into a manual
dashboard using HA's raw configuration editor; adapt entity IDs to your registry.
It includes separate **Boiler** and **Schedule** views, with no custom cards.

## Native Home Assistant configuration

### Ordinary settings

Switches configure constant-temperature enable, PMT enable, automatic
modulation, and the two manual stage permissions. Number entities configure
the stored air target, flow/return cutoff and restart drop, PMT restart/stop
thresholds, and pump lead-in/run-on delays. A select chooses:

| Control mode | Meaning |
|---|---|
| `Temp` | Constant air-temperature target |
| `GraphD` | Repeating daily timetable, ED |
| `GraphW` | Weekly Monday-Sunday timetables, MO-SU |

These controls show **boiler-reported values**, not optimistic values.
A change queues a command for the next boiler poll. **Settings upload status**
remains `pending` until a later report confirms it. Inspect
**Settings command error** if a command is rejected or not confirmed.
Accepted uploads keep retrying until the boiler confirms them; there is no
pending-upload cancellation control.

Main parameter meanings and accepted *new* values:

| Wire setting | Native control / interpretation | Accepted values |
|---|---|---|
| `TMP[0]` | Constant temperature enabled | On/Off |
| `TMP[1]` | Stored **air target**, not measured TA | 7-40 C, step 0.1 |
| `FI[0]` | Flow-temperature heating cutoff | 10-75 C, whole degrees |
| `FI[1]` | Flow restart drop below cutoff | 1-9 C, whole degrees |
| `RE[0]` | Return-temperature heating cutoff | 10-75 C, whole degrees |
| `RE[1]` | Return restart drop below cutoff | 1-9 C, whole degrees |
| `PMT[0]` | Minimum-temperature preset enabled | On/Off |
| `PMT[1]` | PMT lower/restart threshold | 6-15 C, whole degrees |
| `PMT[2]` | PMT upper/stop threshold | 7-17 C, whole degrees; strictly above lower |
| `pNA[0]` | Pump start to heating lead-in | 1-15 whole minutes |
| `pNA[1]` | Heating stop to pump stop run-on | 1-15 whole minutes |
| `MOD` | Automatic modulation enable, not actual heating | On/Off |
| `STU[0/1]` | Manual stage 1/2 permission, not actual heating | On/Off, applicable with modulation off |

Reported values outside UI limits, such as the captured stored target 6.9 C,
are retained without clamping. Set a valid target before enabling that preset.
PMT threshold changes are validated as a pair; adjust them in an order that
keeps lower < upper, or send an atomic tuple through MQTT.

If ST1/ST2 enable flags conflict with STU, neither silently wins. The two
manual-stage controls become unavailable until the conflict is resolved.
Choose **Manual-stage conflict source** (`ST1/ST2` or `STU`), then press
**Resolve manual-stage conflict using selected source**. This explicitly
queues the chosen complete STU tuple; it is not considered applied until
consistent boiler reports confirm it. There are still only two manual-stage
enable controls, not duplicated ST1/ST2 and STU switches.

### Schedule: individual point rows

The **Schedule** dashboard view has eight sections: **Whole week** (ED) and
**Monday-Sunday** (MO-SU). Every section shows all **ten numbered rows**, with
independently editable **Hour** and **Target** fields side by side: 80 points
and 160 native number entities in total. There is no shared day/slot cursor.
You can edit inactive schedules without activating them.

Edit a day's points, then press **Apply Monday draft** (or the corresponding
day), or **Apply all schedule drafts** for an atomic upload of all drafts.
Wait for `applied` upload status and the day's layer to return to `reported`.
**Schedule mode** selects **Whole week** (`GraphD`, ED repeated daily) or
**Individual days** (`GraphW`, Monday-Sunday). **Constant temperature** (`Temp`)
is also shown so an existing nonschedule mode is represented accurately.
This selector and the ordinary Control mode select configure the same USE
setting, and both show confirmed state.

Point fields show local **draft or pending** values, not confirmation.
Each day's **schedule layer** distinguishes `reported`, `draft`, `pending`,
and `no data`; its **schedule validation** reports whether the displayed day
can be submitted. Schedule sensor attributes expose all ten displayed points,
the separate boiler-reported, draft and pending arrays, and validation errors.

Exactly ten slots must be supplied, with strictly increasing whole-hour times.
A target is **0 = OFF**, or **7-40 C** in steps of 0.1. Values between 0 and 7
other than zero are rejected, even though a native number's min/max UI cannot
represent that gap. Hours can temporarily be out of order while editing;
Apply validates the whole day (or all draft days atomically). Received
duplicate hours are preserved, shown as invalid for new uploads, and must be
resolved explicitly. There is no implicit sorting, padding or deduplication.

**Discard Monday draft** (and its equivalents) and **Discard all drafts**
abandon local edits only: already-queued uploads remain pending and keep
retrying. Drafts and pending uploads survive bridge restarts. Telemetry never
overwrites a draft; confirming a submitted draft removes it only if it still
matches what was submitted. Commands for different fixed points cannot be
redirected by another client's day/slot selection.

The dashboard uses standard HA sections, grids and Entities cards with native
number inputs, not an iframe or the HA Schedule helper. Schedule points are
step changes, not interpolated curves; duplicate-hour resolution and midnight
wraparound remain unverified. HA's Schedule helper is not another active
schedule authority and is not synchronized implicitly.

After upgrading from the compact editor, replace the old dashboard YAML.
The bridge clears obsolete compact-editor and cancellation discovery topics
automatically, without deleting pending settings or drafts. The repetitive
Schedule view can be regenerated with `python -m examples.generate_dashboard`;
do this before adapting entity IDs, since regeneration resets that view.

## Environment parameters

Only bridge infrastructure uses ENV; **all supported boiler settings use
native HA MQTT controls**. Compose reads `.env` and passes these values.
Native Python reads process environment directly.

| Variable | Default | Explanation |
|---|---|---|
| `HTTP_HOST` | `0.0.0.0` | Native listen address; Compose fixes it inside the container |
| `HTTP_PORT` | `9080` | Boiler HTTP port; also used by Compose's host mapping |
| `HTTP_BIND_ADDRESS` | `0.0.0.0` | Compose-only host interface binding |
| `MQTT_HOST` | `localhost` native / `host.docker.internal` Compose | Broker address |
| `MQTT_PORT` | `1883` | Broker port; commonly 8883 for TLS |
| `MQTT_USERNAME` | empty | Broker username |
| `MQTT_PASSWORD` | empty | Broker password, passed unchanged |
| `MQTT_CLIENT_ID` | `tenko-local` | Unique per running bridge instance |
| `MQTT_TLS` | `false` | Enable verified TLS; set true for TLS brokers |
| `MQTT_CA_FILE` | empty | Optional CA bundle; uses system trust otherwise |
| `MQTT_PREFIX` | `tenko` | Data/command topic prefix |
| `DISCOVERY_PREFIX` | `homeassistant` | Discovery prefix and HA birth-topic prefix |
| `FRESHNESS_TIMEOUT` | `180` | Seconds without parameter reports before boiler availability becomes offline |
| `CONFIRMATION_TIMEOUT` | `600` | Seconds before unconfirmed commands become errors; pending retries are retained |
| `STATE_PATH` | `data/state.json` native / `/data/state.json` Compose | JSON cache/draft/pending file |
| `STATUS_PATH`, `STATUS_METHOD` | `/update/status`, `POST` | Status exchange endpoint; blank legacy values use these defaults |
| `NO_CHANGE_BODY` | `nochange` | Exact no-update response; can explicitly be empty |
| `ALLOWED_SERIALS` | empty native | Optional comma-separated serial allowlist; example restricts to captured serial |
| `LOG_LEVEL` | `INFO` | Python logging level; `DEBUG` or `debug` dumps incoming/outgoing HTTP and MQTT payloads |

There are no `EDITOR_*` or `FRAME_ANCESTORS` settings anymore. Old versions'
JSON files are migrated automatically to add new diagnostic metadata without
deleting existing reports, pending settings or drafts.

For private MQTT certificate authorities, mount a CA bundle read-only, e.g.
`./broker-ca.pem:/certs/broker-ca.pem:ro`, and set the container's
`MQTT_CA_FILE=/certs/broker-ca.pem`. Do not disable hostname verification.
The Compose file uses an existing broker; it does not install a second broker.

Native execution (Python 3.11+, Linux):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export MQTT_HOST=192.168.1.10
export MQTT_USERNAME=tenko
export MQTT_PASSWORD='your-broker-password'
.venv/bin/python -m tenko
```

## MQTT interface

For default prefixes and serial `211229_005`:

| Topic | Payload / purpose |
|---|---|
| `tenko/bridge/availability` | Bridge online / LWT offline |
| `tenko/211229_005/availability` | Parameter-report freshness |
| `tenko/211229_005/status_availability` | Independent separate-status freshness |
| `tenko/211229_005/state` | Confirmed components, editor values and upload status |
| `tenko/211229_005/diagnostics` | Raw/decoded parameters, last raw status request/method/path, reported settings, pending commands, drafts and assumptions |
| `tenko/211229_005/schedules/ED` | `{points, displayed_points, pending, draft, layer, validation_error, ...}`; equivalent topics for MO-SU |
| `tenko/211229_005/command/<entity-key>` | Native control command, never retained |
| `tenko/211229_005/command/settings` | Atomic JSON patch of demonstrated response keys |
| `homeassistant/<component>/tenko_211229_005/<entity-key>/config` | Retained HA discovery configuration |

Ordinary command keys:

| Keys | Wire field |
|---|---|
| `mode` | USE |
| `constant_enabled`, `constant_target` | TMP[0/1] |
| `flow_cutoff`, `flow_hysteresis` | FI[0/1] |
| `return_cutoff`, `return_hysteresis` | RE[0/1] |
| `pmt_enabled`, `pmt_min`, `pmt_max` | PMT[0/1/2] |
| `modulation` | MOD enable flag |
| `manual_1`, `manual_2` | STU[0/1] |
| `pump_start`, `pump_stop` | pNA[0/1] |

Schedule point commands use `schedule_<DAY>_<POINT>_hour` and
`schedule_<DAY>_<POINT>_target`, e.g. `schedule_MO_01_hour` with `6` and
`schedule_MO_01_target` with `21.5`. DAY is ED/MO/TU/WE/TH/FR/SA/SU;
POINT is 01-10. `schedule_mode` accepts `Whole week`, `Individual days`, or
`Constant temperature`.

Native button keys are `schedule_<DAY>_apply`, `schedule_<DAY>_discard`,
`editor_apply_all`, `editor_discard_all`, and `resolve_stages`.
Every button uses exact payload `PRESS`. There is no `cancel_pending` command.
`stage_resolution_source` accepts `ST1/ST2` or `STU`. All entities and their
full discovery payloads are defined centrally in `tenko/entities.py`.

Example atomic command for automations:

```sh
mosquitto_pub -h BROKER -u USER -P PASSWORD \
  -t tenko/211229_005/command/settings \
  -m '{"PMT":["On",10,14],"STU":["Off","On"],"MOD":"Off"}'
```

Do **not** retain commands. Retained commands delivered on subscription are
ignored. Retained *pending state* from the JSON file is different: it is an
already-accepted user request and is retried until confirmation.
Discovery/state are republished after broker reconnect and
`<DISCOVERY_PREFIX>/status` = `online` (HA birth).

Use broker authentication and ACLs: only trusted HA/users should publish
`tenko/+/command/+`. Give the bridge read permission on its command and HA
birth topics and write permission on state/availability/discovery topics.
The boiler HTTP protocol has no captured authentication mechanism; keep
that listener on an isolated trusted LAN and never expose it to the Internet.
No browser-facing HTTP configuration routes or credentials are required.

## Protocol, readings and statistics

`POST /update/param` accepts form encoding, not JSON. `&` separates fields;
schedule semicolons stay in values. Capitalization is significant, leading
zeros are parsed without eval, and raw values/unknown fields remain visible.
Malformed structures are preserved with diagnostics and HTTP 400; sensor
fault tokens such as NC/WP/minErr stay raw while numeric entities become
unavailable, never zero.

With pending settings, the bridge returns the complete captured
`NewData:...;EndData` layout in order
`USE,TMP,MO,TU,WE,TH,FR,SA,SU,ED,FI,RE,PMT,pNA,STU,MOD`.
No partial wire-command behavior is assumed. The latest valid report supplies
unchanged fields, including received duplicate-hour schedules. No-change
responses are HTTP 200 with `nochange` or an explicitly configured empty body.
Sending a response is not proof of application; subsequent reports must agree.
The original historical captures remain unchanged in `prompt.md`.

`POST /update/status` is enabled by default, as confirmed by the boiler's
access log. It accepts form data such as `sn=211229_005&status=1` and returns
the exact acknowledgment `status updated`. The last raw form, method, path,
status and receipt timestamp are persisted and exposed through MQTT.
STATUS_PATH/STATUS_METHOD can override the endpoint if needed; supported
form-body methods are POST/PUT/PATCH. Raw status and its timestamp remain
independent of MOD/TEN telemetry; only the explicitly assumed `0=off, 1=on`
state is derived. Other codes are unknown.

TA/TF/TR, PM-associated temperature and pressure are measurements. NA, TEN1/
TEN2, MOD heating/counts, PM state and AF phase are actual states, not settings.
AF Off means standby; On means checking, not enabled. Unknown raw Err encoding
is not decoded into numbered diagnostic errors. Clock, raw weekday, sensor
type and diagnostics are read-only; unsupported writes are not invented.
Nominal Pow and stage capacities are **rated kW**, never current consumption.
Manual stage permissions do not prove heating is active.

STA period/amount, StD, StW and twelve YSt indexes are reference sensors with
**presumed kWh** units. Scaling, resets/windows and month ordering remain
unverified. They have no energy device class or total/total_increasing state
class. Never sum successive reports, accumulate positive differences, import
them as timestamped history, or use them as Energy dashboard sources. Prefer
a verified external cumulative electricity meter. No estimated power or
historical energy import is enabled.

Availability requires both bridge connection and fresh boiler reports; a
live bridge alone does not make old temperatures fresh. Separate-status
entities require bridge connection and fresh status updates, independently
of parameter-report freshness; status does not refresh old temperatures.

## Persistence and diagnostics

`tenko-data` preserves `/data/state.json` across container recreation.
Writes use fsync + atomic replacement and a single-process file lock, not
SQLite. One bridge process may own a state file. Stop the bridge before
backing up/restoring JSON; UID/GID 10001 must be able to write both file and
directory. Mount the directory, not only the file. Invalid JSON fails startup
rather than silently resetting pending changes.

`GET /health` reports HTTP liveness and MQTT connectivity. Other non-boiler
HTTP routes, including the former web editor/API, return 404. Operational
details and raw state are available through MQTT diagnostic entities/topics.
MQTT outages do not block durable boiler exchanges; reconnect republishes the
latest cache and discovery. Storage failures reject commands explicitly.

Set `LOG_LEVEL=DEBUG` (lowercase `debug` also works), then recreate the
container with `docker compose up -d --build` to enable data dumps.
`docker compose logs -f tenko` will include HTTP request/response methods,
paths and exact body bytes (including unknown paths), plus incoming/outgoing
MQTT topics and payloads. Normal INFO logging omits these dumps.
DEBUG logs include serial numbers and raw telemetry/settings, so treat them
as private. Authentication headers and MQTT broker passwords are not dumped.

```sh
.venv/bin/python -m unittest discover -s tests -v
docker compose config --quiet
./build.sh
# Optional isolated Docker + authenticated MQTT end-to-end check:
TENKO_DOCKER_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_docker.py -v
```

Physical boiler acceptance, including actual status payloads and schedule
execution, still requires verification against the installation.
