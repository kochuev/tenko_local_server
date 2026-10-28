# Tenko local server specification

## Goal and implementation requirements

Develop a local replacement for the Tenko boiler's cloud server. Listen on configurable HTTP port 9080 by default, receive boiler reports, publish their values to MQTT for Home Assistant, and return pending settings using the boiler's existing protocol.

| Requirement | Details |
|---|---|
| HTTP interface | Handle `POST /update/param` reports and return settings or a no-change response. Support the separate status exchange once its missing request path/method are captured or explicitly configured. |
| MQTT | Publish measured values, actual operating states, reported settings, diagnostics, statistics, and separate status reports. Configuration must include broker connection details and authentication, including password. |
| Home Assistant | Automatically discover a device named **Tenko Boiler**, with stable serial-based device/entity identifiers and all applicable read-only sensors and configurable entities described below. Distinguish readings from settings and actual heating from manual stage-enable controls. |
| Temperature timetable | Provide a visual daily/weekly temperature schedule editor, including OFF periods, usable inside a Home Assistant dashboard. Store schedules on the boiler so their execution does not depend on HA automations remaining online. |
| Statistics | Expose boiler-reported period totals as diagnostic/reference data, separate from HA's cumulative energy accounting. Do not feed rolling totals into the Energy dashboard or reconstruct consumption by summing them. |
| Deployment | Provide a Docker build and Compose configuration so the service can run with `docker-compose up -d`. |
| Power semantics | `Pow=15.0` means nominal capacity of 15 kW, not current consumption. Stage capacities are also kW, not kWh. |
| Protocol evidence | Use the captured firmware's formats below. Consult https://my.tenko.ua/api/ for supporting descriptions, not as a substitute for the boiler wire protocol. |

## Protocol directions

Throughout this document, **request** means boiler -> local server, and **response** means local server -> boiler. A request reports both measurements and currently configured settings; appearing in a request does not make a field a sensor.

| Exchange | Boiler request | Server response |
|---|---|---|
| Parameter report | `POST /update/param`, form-encoded fields | HTTP 200 with `NewData:...;EndData`, `nochange`, or an empty body |
| Separate status report | Form body `sn=...&status=...`; request method/path missing from capture | HTTP 200 with `status updated` |

The meaning of the separate status code is unverified. For this implementation, assume `status=0` means heating off and `status=1` means heating on, but retain the raw code and mark this derived state as assumed. All other codes remain unknown.

## Original captured HTTP exchanges

These are historical captures, not ready-to-replay fixtures: preserve their payloads as evidence, but calculate lengths and current HTTP headers when generating messages.

### Parameter report with a settings response

```http
POST /update/param HTTP/1.1
Host: my.tenko.ua
User-Agent: runscope/0.1
Accept: */*
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 1208
sn=211229_005&TA=23.7&TF=39.1&TR=35.6&NA=Off&PM=[On,23.7]&VER=8.2w1.2&Pow=15.0&ST1=Off,5.0&ST2=Off,10.0&TEN1=Off&TEN2=Off&STA=[30,1475]&YSt=[1025.468,0.0,68.078,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.494,0.0]&StD=0&StW=220&TIM=[19,23,3,27,10,26]&USE=GraphD&TMP=Off,6.9&ED=[[00,40.0],[00,40.0],[00,40.0],[03,40.0],[07,0.0],[12,0.0],[15,0.0],[20,0.0],[21,0.0],[23,40.0]];&MO=[[02,39.0],[03,37.1],[04,35.2],[05,33.3],[06,31.4],[07,29.5],[08,27.6],[09,25.7],[11,40.0],[18,40.0]];&TU=[[04,38.0],[05,36.1],[06,34.2],[07,32.3],[08,30.4],[09,28.5],[10,26.6],[11,24.7],[12,22.8],[13,20.9]];&WE=[[06,37.0],[07,35.1],[08,33.2],[09,31.3],[10,29.4],[11,27.5],[12,25.6],[13,23.7],[14,21.8],[15,19.9]];&TH=[[08,36.0],[09,34.1],[10,32.2],[11,30.3],[12,28.4],[13,26.5],[14,24.6],[15,22.7],[16,20.8],[17,18.9]];&FR=[[10,35.0],[11,33.1],[12,31.2],[13,29.3],[14,27.4],[15,25.5],[16,23.6],[17,21.7],[18,19.8],[19,17.9]];&SA=[[12,34.0],[13,32.1],[14,30.2],[15,28.3],[16,26.4],[17,24.5],[18,22.6],[19,20.7],[20,18.8],[21,16.9]];&SU=[[14,33.0],[15,31.1],[16,29.2],[17,27.3],[18,25.4],[19,23.5],[20,21.6],[21,19.7],[22,17.8],[23,15.9]];&FI=[50,5]&RE=[45,5]&PMT=[On,15,17]&pNA=[1,1]&Davl=1.6&MOD=On,Off,0,3&AF=Off&STU=[Off,Off]&Sens=wire&Err=0
HTTP/1.1 200 OK
Date: Tue, 27 Oct 2026 16:15:05 GMT
Server: Apache/2.4.7 (Ubuntu)
Cache-Control: no-cache
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
Content-Length: 766
Content-Type: text/html; charset=UTF-8
NewData:USE=GraphD;TMP=Off,40.0;MO=02,39.0/03,37.1/04,35.2/05,33.3/06,31.4/07,29.5/08,27.6/09,25.7/11,40.0/18,40.0;TU=04,38.0/05,36.1/06,34.2/07,32.3/08,30.4/09,28.5/10,26.6/11,24.7/12,22.8/13,20.9;WE=06,37.0/07,35.1/08,33.2/09,31.3/10,29.4/11,27.5/12,25.6/13,23.7/14,21.8/15,19.9;TH=08,36.0/09,34.1/10,32.2/11,30.3/12,28.4/13,26.5/14,24.6/15,22.7/16,20.8/17,18.9;FR=10,35.0/11,33.1/12,31.2/13,29.3/14,27.4/15,25.5/16,23.6/17,21.7/18,19.8/19,17.9;SA=12,34.0/13,32.1/14,30.2/15,28.3/16,26.4/17,24.5/18,22.6/19,20.7/20,18.8/21,16.9;SU=14,33.0/15,31.1/16,29.2/17,27.3/18,25.4/19,23.5/20,21.6/21,19.7/22,17.8/23,15.9;ED=00,40.0/00,40.0/00,40.0/03,20.4/07,00.0/12,00.0/15,00.0/20,00.0/21,00.0/23,40.0;FI=50,05.0;RE=45,05;PMT=Off,15,17;pNA=01,01;STU=Off,Off;MOD=On;EndData
```

### Parameter report with no changes

```http
POST /update/param HTTP/1.1
Host: my.tenko.ua
User-Agent: runscope/0.1
Accept: */*
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 1208
sn=211229_005&TA=24.0&TF=40.6&TR=38.3&NA=Off&PM=[On,24.0]&VER=8.2w1.2&Pow=15.0&ST1=Off,5.0&ST2=Off,10.0&TEN1=Off&TEN2=Off&STA=[30,1475]&YSt=[1025.468,0.0,68.078,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.494,0.0]&StD=0&StW=220&TIM=[18,55,3,27,10,26]&USE=GraphD&TMP=Off,6.9&ED=[[00,40.0],[00,40.0],[00,40.0],[03,40.0],[07,0.0],[12,0.0],[15,0.0],[20,0.0],[21,0.0],[23,40.0]];&MO=[[02,39.0],[03,37.1],[04,35.2],[05,33.3],[06,31.4],[07,29.5],[08,27.6],[09,25.7],[11,40.0],[18,40.0]];&TU=[[04,38.0],[05,36.1],[06,34.2],[07,32.3],[08,30.4],[09,28.5],[10,26.6],[11,24.7],[12,22.8],[13,20.9]];&WE=[[06,37.0],[07,35.1],[08,33.2],[09,31.3],[10,29.4],[11,27.5],[12,25.6],[13,23.7],[14,21.8],[15,19.9]];&TH=[[08,36.0],[09,34.1],[10,32.2],[11,30.3],[12,28.4],[13,26.5],[14,24.6],[15,22.7],[16,20.8],[17,18.9]];&FR=[[10,35.0],[11,33.1],[12,31.2],[13,29.3],[14,27.4],[15,25.5],[16,23.6],[17,21.7],[18,19.8],[19,17.9]];&SA=[[12,34.0],[13,32.1],[14,30.2],[15,28.3],[16,26.4],[17,24.5],[18,22.6],[19,20.7],[20,18.8],[21,16.9]];&SU=[[14,33.0],[15,31.1],[16,29.2],[17,27.3],[18,25.4],[19,23.5],[20,21.6],[21,19.7],[22,17.8],[23,15.9]];&FI=[50,5]&RE=[45,5]&PMT=[On,15,17]&pNA=[1,1]&Davl=1.9&MOD=On,Off,0,3&AF=Off&STU=[Off,Off]&Sens=wire&Err=0
HTTP/1.1 200 OK
Date: Tue, 27 Oct 2026 15:47:34 GMT
Server: Apache/2.4.7 (Ubuntu)
Cache-Control: no-cache
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
Content-Length: 8
Content-Type: text/html; charset=UTF-8
nochange
```

### Parameter report with an empty response

```http
POST /update/param HTTP/1.1
Host: my.tenko.ua
User-Agent: runscope/0.1
Accept: */*
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 1208
sn=211229_005&TA=24.0&TF=40.6&TR=38.3&NA=Off&PM=[On,24.0]&VER=8.2w1.2&Pow=15.0&ST1=Off,5.0&ST2=Off,10.0&TEN1=Off&TEN2=Off&STA=[30,1475]&YSt=[1025.468,0.0,68.078,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.494,0.0]&StD=0&StW=220&TIM=[18,55,3,27,10,26]&USE=GraphD&TMP=Off,6.9&ED=[[00,40.0],[00,40.0],[00,40.0],[03,40.0],[07,0.0],[12,0.0],[15,0.0],[20,0.0],[21,0.0],[23,40.0]];&MO=[[02,39.0],[03,37.1],[04,35.2],[05,33.3],[06,31.4],[07,29.5],[08,27.6],[09,25.7],[11,40.0],[18,40.0]];&TU=[[04,38.0],[05,36.1],[06,34.2],[07,32.3],[08,30.4],[09,28.5],[10,26.6],[11,24.7],[12,22.8],[13,20.9]];&WE=[[06,37.0],[07,35.1],[08,33.2],[09,31.3],[10,29.4],[11,27.5],[12,25.6],[13,23.7],[14,21.8],[15,19.9]];&TH=[[08,36.0],[09,34.1],[10,32.2],[11,30.3],[12,28.4],[13,26.5],[14,24.6],[15,22.7],[16,20.8],[17,18.9]];&FR=[[10,35.0],[11,33.1],[12,31.2],[13,29.3],[14,27.4],[15,25.5],[16,23.6],[17,21.7],[18,19.8],[19,17.9]];&SA=[[12,34.0],[13,32.1],[14,30.2],[15,28.3],[16,26.4],[17,24.5],[18,22.6],[19,20.7],[20,18.8],[21,16.9]];&SU=[[14,33.0],[15,31.1],[16,29.2],[17,27.3],[18,25.4],[19,23.5],[20,21.6],[21,19.7],[22,17.8],[23,15.9]];&FI=[50,5]&RE=[45,5]&PMT=[On,15,17]&pNA=[1,1]&Davl=1.9&MOD=On,Off,0,3&AF=Off&STU=[Off,Off]&Sens=wire&Err=0
HTTP/1.1 200 OK
Date: Tue, 27 Oct 2026 15:46:59 GMT
Server: Apache/2.4.7 (Ubuntu)
Cache-Control: no-cache
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
Content-Length: 0
Content-Type: text/html; charset=UTF-8
```

### Separate status exchange (request line not captured)

```http
Accept: */*
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 22
sn=211229_005&status=0
HTTP/1.1 200 OK
Date: Tue, 27 Oct 2026 16:15:12 GMT
Server: Apache/2.4.7 (Ubuntu)
Cache-Control: no-cache
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
Content-Length: 14
Content-Type: text/html; charset=UTF-8
status updated
```

## Protocol reference and evidence

This reference covers all 37 parameters in the captured POST /update/param body, plus the separate status field. It describes the captured boiler protocol, not the public cloud API's JSON format.

Sources:

- `my.tenko.ua_old/Tenko.html`: the closest match, saved for serial `211229_005`, firmware `8.2w1.2`, nominal power 15 kW. Its labels and settings serialization take precedence over the newer demo.
- `my.tenko.ua/Tenko.html`: a newer SMART demo with different data structures. Use only as supporting evidence, not as the wire-format specification for this boiler.
- https://my.tenko.ua/api/: public API names and descriptions corroborate meanings but do not expose the backend conversion from raw boiler fields.
- The original HTTP captures above establish the observed request and response syntax.
- User clarification: request `ST1`/`ST2` report manual stage-enable settings plus rated capacities, NOT actual heating state. The response sets these controls through `STU`; they apply when automatic modulation is off.
- User-directed implementation assumption: incoming `STU[0]` duplicates the enable flag in `ST1`, and incoming `STU[1]` duplicates the enable flag in `ST2`. Treat them as two representations of the same manual-stage settings, not separate controls. This equivalence is assumed, not proven by the saved pages.
- `manual.pdf`: Premium/Premium Plus operating manual, especially pages 23-26, 28-32, 34-38, and 40. It explains control behavior and diagnostic codes, but illustrates older firmware (7.5/7.6) rather than the captured 8.2 firmware. It is not an HTTP protocol specification.

Confidence below means:

- Confirmed: supported by matching page labels, explicit serialization, or the API.
- Supported: meaning is corroborated, but some raw-field details remain unverified.
- Unknown: preserve the value without inventing a decoding.

## Incoming request parameters (boiler -> server)

Every example in this section is a request value, not response syntax. The tables separate readings/operating state from settings reported by the boiler. Outgoing names and formats are listed separately below.

### Identity, sensor readings, and actual operating state

| Parameter | Example | Meaning and decoding | Confidence |
|---|---|---|---|
| `sn` | `211229_005` | Boiler serial number; page label "S/N". Keep as a string and use to associate telemetry and pending settings with a device. | Confirmed |
| `VER` | `8.2w1.2` | Reported boiler firmware version; page label "Boiler version". | Confirmed |
| `TA` | `23.7` | Measured air temperature in degrees Celsius. Not a target temperature. | Confirmed |
| `TF` | `39.1` | Measured supply/forward-flow temperature in degrees Celsius; page label "Flow temperature". | Confirmed |
| `TR` | `35.6` | Measured return-flow temperature in degrees Celsius; page label "Return temperature". | Confirmed |
| `NA` | `Off` | Circulation pump operating state. `On` / `Off` are on / off. The newer page also recognizes `Up` as "Pause on" and `Down` as "Pause off"; those values are not demonstrated in this boiler's capture. | Confirmed On/Off; other states supported |
| `PM` | `[On,23.7]` | Minimum-temperature-maintenance (PMT/MMT) reported state and associated measured temperature: `[state, temperature_C]`. The old page labels this "PMT (status/temperature)"; the API exposes it as MMT state. Not the configured enable/min/max tuple and not a pump field. Exact conditions under which its state changes are unverified. | Confirmed structure |
| `Pow` | `15.0` | Nominal boiler capacity in kW, not current electrical power or accumulated energy. Capitalization is significant: the wire key is `Pow`, while the newer page uses `POW`. | Confirmed |
| `Davl` | `1.6` | Heating-system pressure in bar. The newer page recognizes `minErr`, `maxErr`, and `Err` for low pressure, high pressure, and sensor faults; preserve nonnumeric values rather than converting them to zero. | Confirmed measurement; fault codes supported |
| `Sens` | `wire` | Air sensor type: `wire` means wired. The newer page additionally recognizes `rs` (radio), `extNC` (external normally closed contact), and `extNO` (external normally open contact), with optional status components. The old page also handles a processed `ext` representation. Do not assume those server-side representations are this firmware's raw encoding. | Confirmed wire; alternatives supported |
| `AF` | `Off` | AF-5 frost-protection operating state. The old page explicitly maps `Off` to "Standby" and `On` to "Checking", not disabled/enabled. It displays other values as "Heating" and separately flags `Err` as an error. Manual page 26 confirms frost protection cannot be disabled: while the pump is stopped it checks every 60 minutes, circulates for one minute, heats if return temperature is below 5 degrees until it reaches 5 degrees, then runs the pump for one more minute. The actual raw heating code remains unknown; preserve unknown codes rather than adopting the page's catch-all as a decoder. | Confirmed behavior and display mapping; heating code unknown |
| `Err` | `0` | Raw boiler error indicator/code. Zero is presumed to mean no reported boiler error, but its full encoding is unknown. The old page uses a server-processed `Err == 1` aggregate with separate connectivity/component flags; that does not prove the raw wire field is the same boolean. | Supported; full decoding unknown |
| `TEN1` | `Off` | Actual reported heating-element/group 1 operating state, not permission to use the stage. `On` / `Off` mean heating on / off for the reported group. The old page displays this as "TEN 1". Faults must remain distinct from off. | Confirmed page meaning; physical grouping may rotate |
| `TEN2` | `Off` | Actual reported heating-element/group 2 operating state, not its manual-enable setting. `On` / `Off` mean heating on / off for the reported group. The old page displays this as "TEN 2". | Confirmed page meaning; physical grouping may rotate |
| `MOD` | `On,Off,0,3` | Mixed setting/state tuple `[modulation_enabled, heating_status, active_element_count, total_element_count]`. Position 0 is the configured automatic-modulation enable; position 1 is actual heating status; positions 2/3 are active/total elements. Example: automatic modulation enabled, heating off, 0 of 3 elements active. The response writes ONLY position 0 as `MOD=On` or `MOD=Off`. | Supported by both pages and API |

Temperature values may be nonnumeric fault indicators. The newer page recognizes `NC` or empty as no sensor connection and `WP` as incorrect polarity/short circuit for TA/TF/TR. Preserve raw readings and expose a fault/unavailable state rather than a fabricated numeric temperature.

`Sens` reports the selected sensor type/configuration, not a measured temperature. No writable response field for selecting it is demonstrated. Likewise, `Pow` is device capacity metadata, not a live power sensor. None of the readings or actual states in this table should be echoed as writable settings; only MOD's enable component has a demonstrated write format.

### Diagnostic errors: meanings versus wire encoding

The manual does explain the diagnostic names. What remains unknown is how this firmware packages them into the captured raw `Err` field; an error's documented meaning does not establish a numeric code or bitmask.

| Code | Explanation | Evidence and scope |
|---|---|---|
| `OK` | The indicated power channel is working; when assigned to a current sensor, the channels checked by that sensor are working. | Manual page 28, startup power-channel diagnostics. |
| `Err1` | No current in the indicated power channel(s) during the diagnostic test. This identifies a failed current path, not necessarily a particular failed component. The newer page describes possible heating-element, contactor, or solid-state-relay faults. | Manual pages 28-29; newer page `PEr.Err1`. |
| `Err2` | Reserved. Do not assign a fault meaning. | Manual page 28. |
| `Err3` | A relay in one or more channels remains closed and does not open: a stuck-on relay/power-switch fault. | Manual pages 28-29; newer page `PEr.Err3`. |
| `Err4` | Current leakage detected; the newer page mentions heating elements, wiring, or solid-state relays as possible causes. | Newer SMART page `PEr.Err4`, not established by this manual's diagnostic-code list or by the captured raw payload. |
| `UNK` | Board configuration cannot be determined. | Newer SMART page `PEr.UNK`; not a demonstrated raw code for this boiler. |
| `Err` | Generic fault state in stage/heating/pump displays; not synonymous with a particular numbered diagnostic error. Stage/heating faults can indicate faulty power channels; the manual associates the pump fault display with absence of flow. | Manual pages 36-38. Exact raw transport representation remains unverified. |
| `NC` | Temperature sensor disconnected, broken wire, or poor connector contact. | Manual pages 35-36. |
| `WP` | Temperature sensor wiring short circuit or incorrect polarity. | Manual pages 35-36. |

Preserve the diagnostic code and any accompanying channel/current-sensor identifiers separately. Reports may identify an individual channel, list several channels, or assign a result to a current sensor such as CS1/CS2/CS3. Sensor-to-channel grouping depends on star/delta wiring and single-/dual-block construction (manual pages 28-29); do not infer a universal grouping from the nominal power alone.

In particular, do not decode raw `Err=1` as `Err1`, `Err=2` as `Err2`, etc. without evidence. The captured field, local diagnostic names, and server-processed SMART `PEr` object are distinct representations.

### Reported control settings (not sensor readings)

| Parameter | Example | Meaning and decoding | Confidence |
|---|---|---|---|
| `ST1` | `Off,5.0` | `[manual_stage_1_enabled, rated_power_kW]`: stage 1 is configured NOT to be used in manual (modulation-off) mode; its rated capacity is 5 kW. `On` permits use, but does not mean it is currently heating. Write its enable setting using response `STU` position 0; never send its capacity as a control. Actual operating state is reported separately by TEN1. | Confirmed by user clarification; capacity corroborated by manual |
| `ST2` | `Off,10.0` | `[manual_stage_2_enabled, rated_power_kW]`: stage 2 is configured NOT to be used in manual (modulation-off) mode; its rated capacity is 10 kW. `On` permits use, but does not mean it is currently heating. Write its enable setting using response `STU` position 1; never send its capacity as a control. Actual operating state is reported separately by TEN2. | Confirmed by user clarification; capacity corroborated by manual |
| `STU` | `[Off,Off]` | `[manual_stage_1_enabled, manual_stage_2_enabled]`: assume position 0 duplicates ST1's enable flag and position 1 duplicates ST2's enable flag. Unlike ST1/ST2, this tuple carries no rated capacities. Normalize these duplicate representations to the same two manual-stage settings, NOT actual heating status. Write them as response `STU=Off,Off` without brackets. Manual controls apply only when MOD position 0 is Off. Preserve raw representations; if their enable flags disagree, explicitly expose/log the inconsistency rather than silently selecting a winner. | Tuple and write format confirmed; duplication is a user-directed assumption |
| `USE` | `GraphD` | Selected air-temperature control mode: `Temp` = constant-temperature mode, `GraphD` = repeating daily schedule, `GraphW` = weekly schedules. The old page explicitly serializes these values. | Confirmed |
| `TMP` | `Off,6.9` | `[constant_temperature_enabled, target_air_temperature_C]`. This is explicitly serialized by the old page. The stored target in this report is 6.9 degrees even though the UI normally validates 7-40; accept/preserve reported values without silently clamping them. | Confirmed |
| `FI` | `[50,5]` | `[flow_heating_cutoff_C, restart_drop_C]`: stop heating at flow temperature 50 degrees; allow it to resume after temperature drops by 5 degrees to 45. Manual page 30 defines these boundaries. Other demand/protection conditions still apply. | Confirmed |
| `RE` | `[45,5]` | `[return_heating_cutoff_C, restart_drop_C]`: stop heating at return temperature 45 degrees; allow it to resume after temperature drops by 5 degrees to 40. Manual pages 23 and 31 explain that either coolant sensor can interrupt heating despite continued room demand. | Confirmed |
| `PMT` | `[On,15,17]` | `[minimum_temperature_maintenance_enabled, minimum_air_temperature_C, maximum_air_temperature_C]`. Enabled, restart threshold 15 degrees, stop threshold 17 degrees (manual page 31). Disabling this low-temperature preset restores the normal manual/timer target (page 24). Distinct from PM, which is reported status/temperature. | Confirmed |
| `pNA` | `[1,1]` | `[pump_start_delay_minutes, pump_stop_delay_minutes]`: wait 1 minute between pump start and heater enable; wait 1 minute between heater stop and pump stop. | Confirmed |

For modulation configuration, read MOD position 0 from the mixed request tuple above and write the response's single MOD flag. With modulation on, Off/Off in manual stage settings does not imply heating is disabled. With modulation off, enabling a stage only permits its use; demand, pump timing, and protections still govern actual heating.

Manual page 40 specifies stage 1 as one-third of nominal power and stage 2 as two-thirds, confirming 5 and 10 kW for this 15 kW boiler. These are capacity groups, not fixed physical element identities: selectivity rotates working elements to balance usage and supply phases (pages 26 and 37). Page 34 confirms the modulation fraction as currently energized elements / total elements. Current measured power is absent; calculations from rated capacities/counts must be labeled estimates, not measured power.

The sensor/setting relationships are:

| Physical quantity | Actual reading/state in request | Reported setting in request | Setting written in response |
|---|---|---|---|
| Air temperature | TA (measured degrees Celsius); PM position 1 is the temperature reported with PMT status | TMP enable/target, PMT enable/lower/upper thresholds, USE, and ED/MO/TU/WE/TH/FR/SA/SU targets | TMP, PMT, USE, and corresponding schedules |
| Flow temperature | TF (measured degrees Celsius) | FI position 0 = cutoff target; position 1 = restart hysteresis | FI target/hysteresis |
| Return temperature | TR (measured degrees Celsius) | RE position 0 = cutoff target; position 1 = restart hysteresis | RE target/hysteresis |
| Manual stage selection | TEN1/TEN2 report actual operation, not permission | ST1/ST2 enable flags, assumed duplicated by STU position 0/1; one logical setting per stage | STU position 0/1 |
| Automatic modulation | MOD heating status and active/total counts | MOD position 0 = automatic-modulation enable | MOD single enable flag |
| Pump | NA actual operating state | pNA lead-in/run-on delay settings | pNA delays, not a direct pump on/off command |

Relevant old-page input validation:

- PMT minimum: 6-15 degrees; maximum: 7-17 degrees; minimum must be strictly less than maximum.
- Constant target: 7-40 degrees in JavaScript validation. Some HTML attributes/tooltips still say 7-30; they are inconsistent. The serializer supports one decimal place on this saved page.
- FI/RE temperatures: 10-75 degrees; differentials: 1-9 degrees. The old page serializes these as whole numbers.
- Each pump delay: 1-15 minutes. Do not substitute the newer SMART page's 1-5 minute limit.

These are UI constraints, not a complete firmware specification. Validate outgoing user settings separately from parsing incoming telemetry.

Manual pages 24 and 31 confirm pump delays of 1-15 minutes and explain that they apply to air-demand-driven start/stop cycles, not each coolant-temperature switching cycle. Manual page 23 explains that explicitly blocking the wired air sensor in service settings disables timer, PMT, and modulation and makes the pump run continuously without these delays. A sensor fault or missing sensor alone is not proof this deliberate bypass is configured.

Do not copy the newer SMART format: its TMP is `[target, differential]` and PMT is `[minimum, maximum]`, unlike this captured firmware. Also, SMART's `USE=OFF` is not established for this older boiler. The public API's `DChart`/`WChart` vocabulary must not replace the observed `GraphD`/`GraphW` wire values.

### Reported schedule settings (not measured temperatures)

| Parameter | Example first point (within request array) | Meaning and decoding | Confidence |
|---|---|---|---|
| `ED` | `[00,40.0]` | Repeating daily schedule selected by USE=GraphD. Each pair is `[hour, target_air_temperature_C]`; this point selects target 40 degrees at 00:00. Full request format is a ten-pair nested array followed by `;`. | Confirmed |
| `MO` | `[02,39.0]` | Monday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 39 degrees at 02:00. | Confirmed |
| `TU` | `[04,38.0]` | Tuesday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 38 degrees at 04:00. | Confirmed |
| `WE` | `[06,37.0]` | Wednesday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 37 degrees at 06:00. | Confirmed |
| `TH` | `[08,36.0]` | Thursday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 36 degrees at 08:00. | Confirmed |
| `FR` | `[10,35.0]` | Friday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 35 degrees at 10:00. | Confirmed |
| `SA` | `[12,34.0]` | Saturday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 34 degrees at 12:00. | Confirmed |
| `SU` | `[14,33.0]` | Sunday schedule in weekly mode; each pair is `[hour, target_air_temperature_C]`. This point selects target 33 degrees at 14:00. | Confirmed |

Each schedule reports pairs `[hour, target_air_temperature_C]`, with whole hours 00-23. Example: `[02,39.0]` is a point at 02:00 targeting 39 degrees. These are air-temperature targets, not flow-temperature settings. Manual page 32 requires all 10 points for each day, or all 70 points for a weekly program, filled in chronological order across 00-23. Preserve the observed 10-point layout for outgoing schedules rather than assuming variable-length lists are accepted.

Zero represents OFF in the schedule UI. The old page's tooltip uses rounded temperature > 6 as its numeric/OFF distinction; the newer page converts targets below 7 to OFF when saving. Manual page 32 describes timed target changes, including explicit OFF points, rather than linear interpolation between temperatures. Exact raw cutoff, duplicate-hour resolution, and midnight wraparound behavior remain unverified.

The captured ED contains duplicate hour-00 points. Preserve the raw points when ingesting. The newer page keeps the last point per hour on save, while the old page warns about same-hour points; neither proves how firmware resolves duplicates. Do not automatically rewrite received schedules as a side effect of parsing.

### Energy statistics and clock

| Parameter | Example | Meaning and decoding | Confidence |
|---|---|---|---|
| `STA` | `[30,1475]` | `[statistics_period_days, consumption_for_period]`: 30 days, amount 1475. The old page displays exactly these values. Treat the amount as presumed kWh, not instantaneous kW, pending confirmation of unit/scaling. The newer page's STA is a different daily-history array, not this tuple. | Confirmed period/amount; energy unit inferred |
| `StD` | `0` | 1-day consumption amount. The old page displays "1 day 0" alongside the matching STA and StW amounts. Reset boundary (calendar day vs trailing 24 hours), unit/scaling, and rollover behavior remain unverified. | Strongly supported by matching values |
| `StW` | `220` | 7-day consumption amount. The old page displays "7 days 220". Do not assume a calendar week or a specific reset rule. Unit/scaling remain unverified. | Strongly supported by matching values |
| `YSt` | `[1025.468,0.0,68.078,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.494,0.0]` | Twelve monthly consumption amounts used for the annual chart. Preserve index order. The newer page rotates month labels based on the boiler clock, but the raw index-to-calendar-month mapping for this firmware is unresolved; do not label index 0 as January without evidence. Energy units are presumed kWh, scaling unverified. | Confirmed purpose; ordering unresolved |
| `TIM` | `[19,23,3,27,10,26]` | `[hour, minute, weekday_code, day, month, two_digit_year]`: 19:23 on 2026-10-27. No seconds or timezone are supplied. Weekday numbering is unverified: the old page displays Wednesday for that date although the calendar date is Tuesday. Preserve the raw weekday instead of silently treating it as ISO weekday. | Confirmed structure; weekday/timezone unresolved |

Period consumption totals can decrease or reset. Do not mark STA/StD/StW or monthly values as Home Assistant lifetime `total_increasing` counters without establishing their reset semantics.

### Separate incoming status request

| Parameter | Example | Meaning and decoding | Confidence |
|---|---|---|---|
| `sn` | `211229_005` | Device serial number, identical to the parameter-report identifier. Associate this status with the correct device. | Confirmed |
| `status` | `0` | Raw status code from a separate request. Implementation assumption only: 0 = heating off, 1 = heating on; other codes = unknown. Preserve the raw value independently of TEN1/TEN2 and MOD heating status. No corresponding writable response parameter is demonstrated; the acknowledgment body is `status updated`. | Meaning unverified; 0/1 interpretation user-directed |

## Outgoing response parameters (server -> boiler)

These are desired settings written inside `NewData:...;EndData`, not measured values. Every captured response assignment is listed here. A response example can differ from its corresponding request example because the response is asking the boiler to change a setting.

| Response parameter | Example response value | Corresponding incoming request field(s) | Meaning and components |
|---|---|---|---|
| `USE` | `GraphD` | USE | Select control mode: Temp = constant air target; GraphD = daily schedule; GraphW = weekly schedules. Not an actual heating-status flag. |
| `TMP` | `Off,40.0` | TMP=`Off,6.9` | `[constant_temperature_enabled, target_air_temperature_C]`: leave constant-temperature enable off and request stored target 40.0 degrees. Not TA and not a hysteresis pair. |
| `MO` | `02,39.0/03,37.1/04,35.2/05,33.3/06,31.4/07,29.5/08,27.6/09,25.7/11,40.0/18,40.0` | MO | Set Monday's ten `[hour, target_air_temperature_C]` points. A slash separates points; there are no brackets. |
| `TU` | `04,38.0/05,36.1/06,34.2/07,32.3/08,30.4/09,28.5/10,26.6/11,24.7/12,22.8/13,20.9` | TU | Set Tuesday's ten `[hour, target_air_temperature_C]` points. |
| `WE` | `06,37.0/07,35.1/08,33.2/09,31.3/10,29.4/11,27.5/12,25.6/13,23.7/14,21.8/15,19.9` | WE | Set Wednesday's ten `[hour, target_air_temperature_C]` points. |
| `TH` | `08,36.0/09,34.1/10,32.2/11,30.3/12,28.4/13,26.5/14,24.6/15,22.7/16,20.8/17,18.9` | TH | Set Thursday's ten `[hour, target_air_temperature_C]` points. |
| `FR` | `10,35.0/11,33.1/12,31.2/13,29.3/14,27.4/15,25.5/16,23.6/17,21.7/18,19.8/19,17.9` | FR | Set Friday's ten `[hour, target_air_temperature_C]` points. |
| `SA` | `12,34.0/13,32.1/14,30.2/15,28.3/16,26.4/17,24.5/18,22.6/19,20.7/20,18.8/21,16.9` | SA | Set Saturday's ten `[hour, target_air_temperature_C]` points. |
| `SU` | `14,33.0/15,31.1/16,29.2/17,27.3/18,25.4/19,23.5/20,21.6/21,19.7/22,17.8/23,15.9` | SU | Set Sunday's ten `[hour, target_air_temperature_C]` points. |
| `ED` | `00,40.0/00,40.0/00,40.0/03,20.4/07,00.0/12,00.0/15,00.0/20,00.0/21,00.0/23,40.0` | ED | Set the repeating daily schedule's ten `[hour, target_air_temperature_C]` points. Zero targets represent OFF in the UI. Duplicate hours shown here are captured evidence, not recommended new settings. |
| `FI` | `50,05.0` | FI=`[50,5]`; compared against sensor TF | `[flow_heating_cutoff_C, restart_drop_C]`: cutoff target 50 degrees, hysteresis 5 degrees, restart at 45 degrees subject to other conditions. A setting, NOT a measured flow temperature. |
| `RE` | `45,05` | RE=`[45,5]`; compared against sensor TR | `[return_heating_cutoff_C, restart_drop_C]`: cutoff target 45 degrees, hysteresis 5 degrees, restart at 40 degrees subject to other conditions. A setting, NOT a measured return temperature. |
| `PMT` | `Off,15,17` | PMT=`[On,15,17]`; NOT the PM status/temperature tuple | `[minimum_temperature_maintenance_enabled, restart_threshold_C, stop_threshold_C]`: request preset disabled, retain thresholds 15 and 17 degrees. |
| `pNA` | `01,01` | pNA=`[1,1]`; NOT the NA operating state | `[pump_start_delay_minutes, pump_stop_delay_minutes]`: one minute from pump start to heating, one minute from heating stop to pump stop. |
| `STU` | `Off,Off` | ST1 enable + ST2 enable, assumed duplicated by request STU=`[Off,Off]` | `[manual_stage_1_enabled, manual_stage_2_enabled]`: write the same two logical settings reported under ST1/ST2 and incoming STU. Here both stages are not selected for manual operation. Only applicable with automatic modulation off; this is not a request to falsify TEN1/TEN2 operating status. Do not emit ST1/ST2 names or rated capacities in the response. |
| `MOD` | `On` | Position 0 of MOD=`On,Off,0,3` | Enable automatic modulation. Accept On/Off as the demonstrated setting format; do not send the heating-status/count components back as commands. |

No writable response representation is demonstrated for sn, VER, TA, TF, TR, NA, PM, Pow, TEN1, TEN2, STA, YSt, StD, StW, TIM, Davl, AF, Sens, Err, or the separate status code. Do not invent same-name commands for those fields.

## Parsing and exchange handling

The request body is `application/x-www-form-urlencoded`, not JSON:

- Decode form fields using `&` as the separator and normal URL decoding. A schedule's trailing `;` belongs to its value; do not treat it as a top-level form-field separator.
- Preserve key capitalization and serial numbers as strings.
- Values use inconsistent wrappers: PM/FI/RE/PMT/pNA/STU/STA/TIM/YSt are bracketed, while TMP/ST1/ST2/MOD are comma-separated without brackets. Schedules are nested bracketed pairs followed by `;`.
- These values are not strict JSON: tokens such as On/Off are unquoted, and hours may have leading zeros. Use explicit field parsers, never eval or executable expression parsing.
- Keep original values alongside decoded data, including unknown fields and fault tokens. Report malformed data explicitly; never replace it with a success-shaped zero/default.
- Separate observed telemetry from desired settings so an incoming report cannot silently overwrite a pending user change.

### No pending settings

The capture shows HTTP 200 with either exact body `nochange` or an empty body. Both are observed no-update responses. There is no need to emulate Apache identity, historical Date headers, or rate-limit headers. Compute Content-Length from actual response bytes if setting it explicitly; captured lengths are not reusable constants.

### Pending settings

The observed response body is plain text despite Content-Type `text/html; charset=UTF-8`:

```text
NewData:USE=GraphD;TMP=Off,40.0;MO=02,39.0/03,37.1/04,35.2/05,33.3/06,31.4/07,29.5/08,27.6/09,25.7/11,40.0/18,40.0;TU=04,38.0/05,36.1/06,34.2/07,32.3/08,30.4/09,28.5/10,26.6/11,24.7/12,22.8/13,20.9;WE=06,37.0/07,35.1/08,33.2/09,31.3/10,29.4/11,27.5/12,25.6/13,23.7/14,21.8/15,19.9;TH=08,36.0/09,34.1/10,32.2/11,30.3/12,28.4/13,26.5/14,24.6/15,22.7/16,20.8/17,18.9;FR=10,35.0/11,33.1/12,31.2/13,29.3/14,27.4/15,25.5/16,23.6/17,21.7/18,19.8/19,17.9;SA=12,34.0/13,32.1/14,30.2/15,28.3/16,26.4/17,24.5/18,22.6/19,20.7/20,18.8/21,16.9;SU=14,33.0/15,31.1/16,29.2/17,27.3/18,25.4/19,23.5/20,21.6/21,19.7/22,17.8/23,15.9;ED=00,40.0/00,40.0/00,40.0/03,20.4/07,00.0/12,00.0/15,00.0/20,00.0/21,00.0/23,40.0;FI=50,05.0;RE=45,05;PMT=Off,15,17;pNA=01,01;STU=Off,Off;MOD=On;EndData
```

Serialization rules established by this capture:

- Exact envelope: `NewData:` followed by semicolon-delimited assignments and final `;EndData`.
- Ordinary tuple values omit brackets: e.g. `PMT=Off,15,17`, `pNA=01,01`.
- Schedules omit brackets and use `/` between `hour,temperature` points, e.g. the captured Monday schedule above.
- Preserve the observed field order and numeric formatting initially. The capture demonstrates mixed padding (`05`, `05.0`, `01`, `00.0`), but does not prove which widths are mandatory.
- Captured response settings are USE, TMP, MO/TU/WE/TH/FR/SA/SU/ED, FI, RE, PMT, pNA, STU, and MOD. MOD is just the enable flag here, not the four-field telemetry tuple.
- Partial updates, alternate field ordering, and writing telemetry-only fields are not demonstrated. Start with the captured complete settings layout rather than assuming arbitrary partial commands are supported.
- An HTTP response being sent is not proof the boiler applied a setting. Compare subsequent reports with requested settings before claiming confirmation; retain raw reported and desired values where they differ.

### Separate status exchange

The known form body is `sn=211229_005&status=0`; the observed HTTP 200 body is exactly `status updated`. Its request path/method are absent from the capture.

Publish raw status independently from any derived heating state. The requested 0=off / 1=on interpretation is an explicit implementation assumption, not a protocol fact. Other codes must remain unknown, and a status report must not overwrite independently reported MOD/TEN state.

## MQTT and Home Assistant interpretation

Publish both decoded values and raw diagnostic data, including all fields above and the separate status code. Identify temperature sensors in degrees Celsius, pressure in bar, and rated power in kW. Label inferred energy units and any estimated values appropriately rather than implying confirmed measurements.

Keep reported states (TEN1/TEN2, MOD status, PM, AF) separate from settings (ST1/ST2 enable flags, STU, MOD enable, FI, RE, PMT, TMP, USE, pNA, and schedules). Expose manual-stage controls using incoming ST1/ST2 enable flags and outgoing STU positions, applicable only with modulation off, not as heating-status binary sensors. Sensor TF must remain distinct from FI target/hysteresis, and sensor TR from RE target/hysteresis. In particular, AF is a diagnostic state rather than a simple boolean, and Pow must not become the current-power sensor.

Under the duplicate-field assumption, create only one manual-enable control per stage, not separate ST1/ST2 and STU controls. Retain the original fields as diagnostic data; ST1/ST2 rated capacities remain separate metadata.

Use the serial number for stable discovery/device identifiers. Preserve the existing requirements for configurable HTTP port, MQTT connection/authentication including password, Home Assistant discovery, and Docker Compose packaging. Unknown protocol meanings must stay documented and visible, not be silently guessed to make discovery entities appear complete.

### Device discovery and entity coverage

Implement MQTT discovery for one device named **Tenko Boiler** per serial number, manufacturer Tenko, with reported firmware version. Multiple boilers must have distinct serial-based identifiers even if their display names match. Set a device configuration URL pointing to the local settings/schedule editor.

Publish retained discovery configurations, restore discovery after MQTT reconnect and Home Assistant birth messages, and provide availability based on both bridge connection and boiler report freshness. A running bridge does not prove the boiler is online. Make discovery prefix and freshness timeout configurable. Never replay a retained control command automatically on startup.

Expose every meaningful decoded component, not just one opaque entity per raw parameter. Unknown or compound values must remain accessible through diagnostic sensors/attributes rather than guessed numeric readings. Use the duplicate-field assumption to avoid duplicate controls for STU and ST1/ST2.

| Entity group | Required HA representation |
|---|---|
| Measured temperatures | Read-only numeric sensors for TA air, TF flow, TR return, and PM's associated reported temperature. Celsius units; measurement state class for actual numeric readings. Preserve faults separately and make invalid numeric readings unavailable, not zero. |
| Pressure and capacities | Read-only pressure sensor for Davl; nominal boiler capacity and stage-1/stage-2 rated capacity sensors as device metadata/diagnostics. Do not label capacities as current electrical draw or use them as measured-power inputs. |
| Actual operating states | Read-only entities for pump NA, TEN1/TEN2, MOD heating status and active/total counts, PM state, AF phase, raw Err, raw separate status, and the explicitly assumed status-derived heating state. Use binary sensors only for unambiguous on/off states; preserve pause, fault, standby, checking, and unknown states in diagnostic sensors. |
| Constant-temperature settings | Configurable switch for TMP enable and number for its stored air target. These are not the TA sensor. |
| Flow/return settings | Four configurable number entities: FI cutoff target and hysteresis, RE cutoff target and hysteresis, with appropriate units/ranges. Do not replace TF/TR readings with these settings. |
| Minimum-temperature preset | Configurable PMT enable switch and lower/restart and upper/stop threshold numbers. Validate the pair together, including ordering. PM's reported state remains read-only. |
| Modulation and manual stages | Configurable modulation-enable switch plus exactly two manual-stage-enable switches, written as STU. Clearly indicate that manual-stage settings are inapplicable while modulation is enabled; never infer actual heating from these controls. |
| Pump timing | Two configurable number entities for pNA lead-in and run-on delays, in minutes. No invented direct pump on/off control. |
| Control mode and schedules | Configurable select for constant/daily/weekly mode (Temp/GraphD/GraphW); visual editor for all eight stored schedules ED and MO-SU. Provide compact read-only schedule summaries and full schedule data as attributes or structured MQTT data. Do not make a large JSON schedule the primary user interface or a long HA state string. |
| Identity and diagnostics | Serial/firmware in device metadata; boiler clock, sensor type, fault details, last report time, pending/applied settings status, and raw field diagnostics available as appropriate entities/attributes. Unknown sensor-selection/clock/error write protocols remain read-only. |
| Consumption statistics | Read-only sensors for STA period and amount, StD, StW, and the 12 YSt indexed values, with the limitations described below. Keep unknown month identities explicit rather than inventing calendar labels. |

Use configuration/diagnostic entity categories where appropriate and retain clear friendly names. Supply command/state topic mappings and discovery payloads for all entity types. Controls must represent confirmed boiler-reported settings, not claim success as soon as MQTT accepts a command: persist pending desired settings, send them on the next boiler poll, and show pending/error status until later reports confirm them. Inconsistent duplicate enable flags must remain visible as a diagnostic issue.

Do not expose unsupported writes solely to make every parameter configurable. Each parameter must be represented, but only settings with demonstrated response formats may be controlled.

### Daily and weekly temperature timetable UI

Recommended implementation: serve a responsive schedule editor from the local server, and include a ready-to-use HA **Webpage (iframe) card** configuration embedding it. The editor must work without third-party cloud services, HACS, a custom HA integration, or a separately installed custom card. MQTT discovery creates the device/entities; it does not install dashboard cards automatically, so document the one-time dashboard setup.

The editor must provide:

- Daily mode: a 24-hour temperature timeline for ED. Weekly mode: a Monday-Sunday overview with selectable days and their individual timelines.
- Explicit temperature and OFF intervals, readable time labels, and a point-list alternative to graphical editing. Use step changes, not a misleading interpolated temperature curve.
- Editing of all ten hour/target slots per schedule, copy-day and apply-to-multiple-days actions, and clear separation between editing stored schedules and activating daily/weekly control mode.
- Validation of whole-hour 00-23 times, allowed targets/OFF, chronological ordering, and the firmware's ten-slot layout. Do not silently drop, pad, or deduplicate points; if a compact interval view requires additional slots, show the resulting ten-point representation before applying it. Preserve received duplicate-hour schedules for inspection and surface validation warnings.
- Separate boiler-reported, draft, and pending schedules, an explicit Apply action, persistence across bridge restarts, and confirmation/error feedback. Do not overwrite an unsaved draft when telemetry arrives or report a response as already applied.

Write schedules through the existing NewData response on the next parameter poll. The boiler, not HA, executes the uploaded timetable. Keep a structured MQTT command/state interface available for automation as well as the graphical editor.

The native HA Schedule helper is useful for HA-driven time-block automations and can carry additional data such as a temperature, but it is not an automatically discovered MQTT editor for the boiler's ten-point schedule format. Do not claim it uploads ED/MO-SU without an explicitly implemented translation/synchronization layer. Avoid introducing two independent active schedule authorities by default.

Document browser embedding requirements: an HTTPS HA frontend cannot embed an HTTP editor. Provide a configurable externally reachable HTTPS editor URL/reverse-proxy example, while keeping the boiler's HTTP protocol unchanged. Ensure the embedded editor's authentication and framing policy are intentionally configured; embedding must not require disabling browser security or expose unauthenticated boiler controls to the Internet.

### Boiler statistics versus Home Assistant energy accounting

Recommended default: keep the boiler's supplied statistics as **reference sensors**, and let HA maintain its own history for live measurements. Receiving a boiler period total is not receiving a new increment of energy.

| Data | How HA should consume it |
|---|---|
| TA/TF/TR, pressure, and actual operating states | Record live values normally. Numeric physical measurements may use measurement state class so HA generates its own long-term statistics. Status values remain states rather than energy totals. |
| STA amount over its selected period, StD, and StW | Display as boiler-reported period totals in entity/history cards. Do not assign total or total_increasing state class and do not use as Energy dashboard sources. Units are presumed kWh until independently verified; label this assumption. These values can fall as a window advances, reset, or use undocumented boundaries. Never sum successive reports or accumulate only their positive deltas. |
| YSt | Display the twelve supplied totals as indexed reference values, with full data available for a chart. Do not claim calendar-month labels until the index mapping is established. Do not turn repeated monthly totals into lifetime-energy increments or backdate them into HA history as though they were timestamped measurements. |
| A future verified cumulative electricity meter | This is the preferred Energy dashboard source. Use energy device class, verified Wh/kWh units, and a suitable total/total_increasing state class based on documented reset behavior. This capture does not provide such a verified meter. |
| Optional estimated live power | Only if explicitly enabled and a justified model is documented, derive a clearly named estimated power sensor from verified energized-element/group information. Never use Pow alone or manual-enable settings as actual draw, and do not double-count stage and modulation representations. Unknown/stale operation must not become zero consumption. HA's Integral helper can integrate an appropriate power signal; resulting energy remains an estimate, not the boiler's measured consumption. |

Provide a simple HA dashboard example separating **Live readings**, **Settings**, **Schedule**, and **Boiler-reported consumption**. Include STA's selected period, StD, StW, and an indexed YSt chart/list in the reference section. The reference totals are not additional loads to add alongside the same boiler's external electricity meter in the Energy dashboard.

Do not attempt historical-statistics import by default. Importing past monthly/daily energy would require verified timestamps, periods, units, month ordering, and a supported statistics-import integration; MQTT discovery and attributes alone do not backfill HA long-term statistics.

Relevant HA references:

- MQTT discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- Sensor state classes: https://www.home-assistant.io/integrations/sensor/#state-class
- Schedule helper: https://www.home-assistant.io/integrations/schedule/
- Webpage card: https://www.home-assistant.io/dashboards/iframe/
- Integral helper: https://www.home-assistant.io/integrations/integration/