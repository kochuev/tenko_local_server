# Tenko local server

Python bridge for the captured Tenko 8.2w1.2 boiler protocol in
[`prompt.md`](prompt.md). The boiler reports over HTTP; Home Assistant reads
and configures it using **native MQTT entities only**. No iframe, web editor,
custom card, HACS integration, cloud service, or SQLite is needed.

The boiler stores and executes applied settings and schedules. The bridge
holds pending commands in a small atomic JSON file, plus a cache of the last
report for discovery/diagnostics. That cache is
**not** an independent active configuration: a fresh boiler report always
supplies the confirmed state. Once a later report confirms pending settings,
the pending command is cleared. Newer edits are preserved.
HA and the bridge need not stay online for a confirmed boiler schedule to execute.

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
The built-in device page has fixed HA sections: MQTT discovery cannot add
custom schedule sections or control their sorting. Schedule controls belong
to Configuration; other settings are uncategorized Controls and operational
readings are Sensors. Diagnostic entities exist only with `LOG_LEVEL=DEBUG`.

## Native Home Assistant configuration

### Ordinary settings

Two native MQTT thermostats replace the old enable switches and setpoint numbers:

| Thermostat | Modes and setpoints |
|---|---|
| **Constant temperature** | Off / Heat; target **7-30 C**, precision/step **0.1 C**. Off writes TMP enable=Off. |
| **Maintaining Minimum Temperature** | Off / Heat-Cool range; lower restart **6-15 C**, upper stop **7-17 C**, whole degrees, lower < upper. Off writes PMT enable=Off. |

The second thermostat uses HA's native dual-setpoint `heat_cool` mode to expose
the restart/stop band; it does **not** add cooling to the boiler. Its current
temperature is the reported PM reading; the constant thermostat uses TA.
An enable change does not change USE: the separate control-mode selector
still chooses constant versus scheduled operation.

**Power Modulation Mode** and the two manual-stage permissions remain switches.
Flow/return cutoff and restart-drop values and pump delays remain numbers.
A select chooses:

| Control mode | Meaning |
|---|---|
| `Temp` | Constant air-temperature target |
| `GraphD` | Repeating daily timetable, ED |
| `GraphW` | Weekly Monday-Sunday timetables, MO-SU |

These controls show **accepted pending values** while a command is waiting
for confirmation, otherwise boiler-reported values. A change queues a command
for the next boiler poll, without snapping the field back to the old value.
The original reported settings remain separately available in DEBUG MQTT diagnostics;
telemetry such as measured temperatures and actual heating is never overridden.
**Settings upload status** remains `pending` until a later parameter report
confirms it. Inspect
**Settings command error** if a command is rejected or not confirmed.
Accepted uploads keep retrying until the boiler confirms them; there is no
pending-upload cancellation control.

Main parameter meanings and accepted *new* values:

| Wire setting | Native control / interpretation | Accepted values |
|---|---|---|
| `TMP[0]` | Constant thermostat mode | Off / Heat maps to Off/On |
| `TMP[1]` | Constant thermostat **air target**, not measured TA | 7-30 C, step 0.1 |
| `FI[0]` | Flow-temperature heating cutoff | 10-75 C, whole degrees |
| `FI[1]` | Flow restart drop below cutoff | 1-9 C, whole degrees |
| `RE[0]` | Return-temperature heating cutoff | 10-75 C, whole degrees |
| `RE[1]` | Return restart drop below cutoff | 1-9 C, whole degrees |
| `PMT[0]` | Maintaining Minimum Temperature thermostat mode | Off / range maps to Off/On |
| `PMT[1]` | Lower/restart setpoint | 6-15 C, whole degrees |
| `PMT[2]` | Upper/stop setpoint | 7-17 C, whole degrees; strictly above lower |
| `pNA[0]` | Pump start to heating lead-in | 1-15 whole minutes |
| `pNA[1]` | Heating stop to pump stop run-on | 1-15 whole minutes |
| `MOD` | Power Modulation Mode enable, not actual heating | On/Off |
| `STU[0/1]` | Manual stage 1/2 permission, not actual heating | On/Off, applicable with modulation off |

Reported values outside UI limits, such as the captured stored target 6.9 C,
are retained in raw diagnostics without clamping; the thermostat target is
unknown until it is valid. Set a valid target before enabling the thermostat.
Turning a thermostat off remains possible without rewriting its old setpoints.
Old pending TMP commands outside 7-30 C are blocked with an explicit error
rather than retransmitted; entering a valid target replaces the blocked command.
Range changes are validated as a pair; adjust them in an order that keeps
lower < upper, or send an atomic tuple through MQTT.

**STU is always authoritative** for manual-stage permissions. ST1/ST2 conflicts
are logged as warnings; they do not block controls or unrelated uploads.
The conflict-source selector and resolve button have been removed.

### Schedule: individual point rows

The **Schedule** dashboard view has eight sections: **Whole week** (ED) and
**Monday-Sunday** (MO-SU). Every section shows all **ten numbered rows**, with
independently editable **Hour** and **Target** fields side by side: 80 points,
80 native **hour dropdowns (0-23)** and 80 **temperature inputs**.
There is no shared day/slot cursor.
You can edit inactive schedules without activating them.

**Each valid value change queues immediately**, just like ordinary settings.
There are no drafts or Apply/Discard buttons. The boiler receives the updated
settings on its next parameter poll. Upload status remains `pending` until
a subsequent report confirms the values, then becomes `applied`.
**Schedule mode** selects **Whole week** (`GraphD`, ED repeated daily) or
**Individual days** (`GraphW`, Monday-Sunday). **Constant temperature** (`Temp`)
is also shown so an existing nonschedule mode is represented accurately.
This selector and the ordinary Control mode select configure the same USE
setting, and both show the same accepted pending or reported value.

Point fields show **pending values** while an accepted change is waiting for
confirmation, otherwise boiler-reported values. Each day's **schedule layer**
distinguishes `reported`, `pending`, and `no data`. Schedule sensor attributes
expose all ten displayed points and the separate reported and pending arrays.

Exactly ten slots must be supplied, with strictly increasing whole-hour times.
A target is **0 = OFF**, or **7-40 C** in steps of 0.1. Values between 0 and 7
other than zero are rejected, even though a native number's min/max UI cannot
represent that gap. **An hour change must remain strictly between its
neighbors**; duplicate or out-of-order choices are rejected, the field
returns to its accepted value, and Settings command error explains why.
When shifting several points, move them in an order that avoids conflicts,
or submit a complete valid day atomically through MQTT.

Existing duplicate hours from boiler reports are preserved and flagged by
schedule validation, not silently sorted or deduplicated. Editing a target
does not rewrite unrelated hours. An hour can only be changed to one that
fits its neighbors, allowing existing duplicates to be corrected explicitly.
Full schedule patches through MQTT require all ten hours to be strictly
increasing.

Pending uploads survive bridge restarts and keep retrying until confirmed.
A report of an older uploaded value never clears a newer pending edit.
Commands for different fixed points cannot be redirected by another client's
day/slot selection.

The dashboard uses standard HA sections, grids and Entities cards with native
select dropdowns and number inputs, not an iframe or the HA Schedule helper.
Schedule points are step changes, not interpolated curves; duplicate-hour resolution and midnight
wraparound remain unverified. HA's Schedule helper is not another active
schedule authority and is not synchronized implicitly.

After upgrading, replace the old dashboard YAML and adapt entity IDs to your
registry. The bridge clears obsolete hour-number, draft-button, compact-editor,
cancellation and separate-heating discovery topics automatically. Hour controls
now use the `select` domain instead of `number`. Existing pending settings
are preserved. Old unsent drafts are retained only in diagnostic JSON for
recovery; they do not drive controls or upload automatically. Re-enter any
desired legacy draft values using the new controls. The repetitive
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
| `STATE_PATH` | `data/state.json` native / `/data/state.json` Compose | JSON cache/pending file |
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
| `tenko/211229_005/state` | Actual telemetry, accepted pending control values and upload status |
| `tenko/211229_005/diagnostics` | DEBUG only: raw/decoded parameters, last status request, reported settings, pending commands and legacy drafts |
| `tenko/211229_005/schedules/ED` | `{points, displayed_points, pending, layer, validation_error, ...}`; equivalent topics for MO-SU |
| `tenko/211229_005/command/<entity-key>` | Native control command, never retained |
| `tenko/211229_005/command/settings` | Atomic JSON patch of demonstrated response keys |
| `homeassistant/<component>/tenko_211229_005/<entity-key>/config` | Retained HA discovery configuration |

Ordinary command keys:

| Keys | Wire field |
|---|---|
| `mode` | USE |
| `constant_mode`, `constant_target` | TMP[0/1]; mode payload is `off` or `heat` |
| `flow_cutoff`, `flow_hysteresis` | FI[0/1] |
| `return_cutoff`, `return_hysteresis` | RE[0/1] |
| `minimum_mode`, `minimum_low`, `minimum_high` | PMT[0/1/2]; mode payload is `off` or `heat_cool` |
| `modulation` | MOD enable flag |
| `manual_1`, `manual_2` | STU[0/1] |
| `pump_start`, `pump_stop` | pNA[0/1] |

Schedule point commands use `schedule_<DAY>_<POINT>_hour` and
`schedule_<DAY>_<POINT>_target`, e.g. `schedule_MO_01_hour` with `6` and
`schedule_MO_01_target` with `21.5`. DAY is ED/MO/TU/WE/TH/FR/SA/SU;
POINT is 01-10. `schedule_mode` accepts `Whole week`, `Individual days`, or
`Constant temperature`.

Schedule point commands queue immediately; no apply/discard commands exist.
There are no apply, discard, conflict-resolution or cancel buttons.
All entities and their
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
status and receipt timestamp are persisted and exposed through DEBUG diagnostics.
STATUS_PATH/STATUS_METHOD can override the endpoint if needed; supported
form-body methods are POST/PUT/PATCH. Raw status and its timestamp remain
independent of MOD/TEN telemetry. **Status meanings are unknown**: no status
code is interpreted as heating, and no separate-heating entity is published.
Its timing after `NewData` suggests it may acknowledge an update, but neither
the status code meaning nor an association with a specific command is verified.
A status request therefore does not clear pending settings or mark them
applied; matching parameter values remain the confirmation.

TA/TF/TR, PM-associated temperature and pressure are measurements. NA, TEN1/
TEN2, MOD flags/counts, PM state and AF phase are reports, not settings.
TEN1 and TEN2 are labeled **Heating element 1** and **Heating element 2**.
These use plain On/Off binary sensors, not the
heat device class that Home Assistant renders as Hot/Normal. Their existing
unique IDs are preserved, so an existing registry may retain old entity IDs.
**AF-5**, **Pump**, **Error Code** and **Boiler clock** are normal Sensors,
not Diagnostics. Their discovery entries are recreated once at bridge startup
to clear old registry categories, keeping their unique IDs and history.
The clock is formatted as `HH:MM`, without inventing a timezone.
AF Off means standby; On means checking, not enabled. Err is shown as its
reported Error Code without inventing a numbered fault description. Raw weekday, sensor
type and diagnostics are read-only; unsupported writes are not invented.
Nominal Pow and stage capacities are **rated kW**, never current consumption.
Manual stage permissions do not prove heating is active.

### Modulated Power

The old Modulation heating sensor is replaced by **Modulated Power** (%):

| MOD report | Percentage |
|---|---|
| `On,Off,1,3` | 0% |
| `On,On,1,3` | 33% |
| `On,On,2,3` | 66% |
| `Off,Off,1,3` | unknown |

When mode and heating are On, the formula is `floor(100 * count / total)`.
Heating Off gives zero only when Power Modulation Mode is On. Disabled mode,
unknown flags, fractional/out-of-range counts and nonpositive totals give
unknown, not zero. Stale reports make the sensor unavailable. This is a
modulation percentage, not measured electrical power in watts.

### Energy meter

The dependent **TENKO Boiler Energy Meter** device exposes **Energy** in kWh,
using the same `STA[1]` reading previously named Boiler period consumption.
Its existing MQTT unique ID and `period_amount` state key are preserved;
HA may therefore retain the old entity ID. New installations normally use
`sensor.tenko_boiler_energy_meter_energy`.

Older HA versions do not move an existing MQTT entity when only its device
metadata changes, leaving the new energy-meter device empty. On the first
discovery per bridge startup, the bridge removes and recreates the Energy
discovery configuration in order. HA re-registers the sensor on the energy
meter while retaining its unique ID and history. Later discovery refreshes
update it normally; no manual device deletion is needed.

This is the boiler's reported **period total**, not a verified lifetime
counter. It has energy device class but deliberately no `total` or
`total_increasing` state class: do not accumulate its deltas or assume it is
suitable for the HA Energy dashboard. No scaling, historical import or
extra consumption estimation is performed.

The STA period length, StD, StW and YSt monthly values are DEBUG-only diagnostic
sensors. Their windows, resets and month ordering remain unverified.

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
details and raw state are available through MQTT diagnostic entities/topics
with `LOG_LEVEL=DEBUG`.
MQTT outages do not block durable boiler exchanges; reconnect republishes the
latest cache and discovery. Storage failures reject commands explicitly.

Set `LOG_LEVEL=DEBUG` (lowercase `debug` also works), then recreate the
container with `docker compose up -d --build` to enable data dumps.
`docker compose logs -f tenko` will include HTTP request/response methods,
paths and exact body bytes (including unknown paths), plus incoming/outgoing
MQTT topics and payloads. Each **HTTP EXCHANGE** line pairs `request_body`
with `response_body`, immediately before the access log entry. A startup
message confirms that HTTP payload dumps are enabled. Low-level MQTT packet
chatter (PUBACK/PUBLISH) is suppressed, while protocol warnings/errors remain
visible. Normal INFO logging omits payload dumps and debug-only diagnostic
entities, including extra energy statistics. Switching out of DEBUG clears
their retained discovery configurations and raw diagnostics topic.

On upgrade, retained discovery for replaced temperature switches/numbers,
Modulation heating, duplicate raw readings and conflict-resolution controls
is removed automatically. Names/categories and the Energy device association
are republished; existing HA entity IDs or user-customized names may remain.

To see only HTTP request/response pairs without MQTT traffic:

```sh
docker compose logs -f tenko | grep --line-buffered 'HTTP EXCHANGE'
```

For example:

```text
DEBUG tenko.server: HTTP EXCHANGE peer=192.168.3.1 method=POST path='/update/status' status=200 request_body=b'sn=211229_005&status=1' response_body=b'status updated'
```

If the startup message is missing despite DEBUG being enabled, rebuild and
recreate the container from the updated source:
`docker compose up -d --build --force-recreate tenko`.

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
