# LabVIEW 2019 compatibility fork

Status: experimental compatibility subset, tested 2026-11-12 with **LabVIEW 2019 SP1 f5,
32-bit Chinese Professional**, Windows, .NET 8. Not an NI-supported product or a claim that
all MCP tools work on 2019. Upstream base: v2.6.8 / commit
`4939b406cd2fa8f598439c30cf9bc7e2269b5d9b`.

## What changed

- The server selects the actual 2019 target instead of emitting a 2026 VI that 2019 rejects
  with error 1125. It uses the existing composer's version-dependent serialization, including
  version records and flattened variants; changing a single file header is insufficient.
- Cached composed helpers also use the selected target version.
- Class-linked VI generation is refused for target 19: this composer's older class-link
  serialization has not been established as safe for 2019. The refusal happens before the
  output VI is rebuilt and preserves an existing output file. LabVIEW 2019 itself supports
  classes; this is a limitation of this generator.
- A real-IDE acceptance script and regression checks make the tested subset reproducible.

Generation still uses the upstream pylabview file composer. Execution uses LabVIEW's ActiveX
server. Layout uses native VI Scripting helpers inside the actual IDE. This fork does not
replace generation with a newly implemented, entirely native VI Scripting generator.

## Build and configure

Requirements: Windows, a licensed LabVIEW 2019 development environment, .NET 8 SDK for building,
and the pylabview runtime already bundled in this checkout. No separate provisioning step is needed.
Runtime use requires .NET 8. No OpenAI API key is required by this MCP server.

```powershell
git clone --branch support/labview-2019 https://github.com/qing-2114/labview-mcp.git
cd labview-mcp
dotnet build src/LabVIEWMCP/LabVIEWMCP.csproj -c Release
```

Create a settings JSON, substituting your actual installed paths:

```json
{
  "aixmlBackend": "pylabview",
  "setDefaultDone": true,
  "labviewExe": "D:\\Multisim\\LabVIEW 2019\\LabVIEW.exe",
  "labviewPref": "D:\\Multisim\\LabVIEW 2019\\LabVIEW.ini"
}
```

Point your client's stdio MCP command at the absolute path to
`src/LabVIEWMCP/bin/Release/net8.0/LabVIEWMCP.exe`. Set `LABVIEWMCP_SETTINGS` to the absolute
settings JSON path. Start LabVIEW 2019, then call `lvai_ensure_labview` with
`backend: "pylabview", keepAutoSave: true`. Check that the returned version starts with `19.`.
Use `pylv_status` for backend diagnostics. `lvai_status` checks the newer NI AI gRPC service
and is not a 2019 readiness test. Restart/reload the MCP client after changing its command.

For native Scripting operations, enable **Tools → Options → VI Server → Show VI Scripting
functions, properties and methods** if required by the installed IDE. The adaptation does
not edit LabVIEW.ini or install/upgrade drivers.

## Tested behavior

| Area | Result in the actual 2019 IDE |
| --- | --- |
| MCP handshake and ActiveX connection | Passed |
| Addition, string length, Select | Generated, run, values compared |
| While, For sum/scale, Boolean Case | Generated, run, values compared |
| Cluster/error cluster, arrays, array nodes/indexing, error Case | Generated, run, values compared |
| Diagram layout | Native dump/apply/save, 4 objects landed exactly, no move errors |
| Render | Native Print.VI To HTML produced front panel and diagram PNGs; addition diagram visually inspected |
| Default generation | Valid AIXML generated with panel cleanup, diagram cleanup/measurement and connector-pane inspection |
| Execution state | Direct ActiveX reports executable; detailed error helper is unavailable |

Reproduce the stable subset (12 fixtures plus optional native feature checks):

```powershell
$env:LABVIEWMCP_SETTINGS = 'C:\absolute\settings.json'
python -X utf8 scripts/test_labview2019_guard.py
dotnet test tests/LabVIEWMCP.Tests/LabVIEWMCP.Tests.csproj --filter FullyQualifiedName~AixmlBackendTests
python -X utf8 scripts/verify_labview2019.py --exe src/LabVIEWMCP/bin/Release/net8.0/LabVIEWMCP.exe --features
```

Python 3 is required only for these developer checks. The acceptance script runs generated
fixture VIs in a running 2019 IDE, writes `artifacts/labview2019/results.json`, and stops its
own MCP process afterward. It does not start a DAQ task or delete autosave files.
An empty test-case list now triggers a default run rather than counting generation as execution.

## Known limitations and failed probes

- `t110_graphs` and `t200_waveform_array_constant` generated and were reported executable,
  but run-and-read returned ActiveX error **1000 / 0x3E8** in the extended probe. Their waveform
  readback path is not supported by this tested subset. Do not infer that a graph has been
  populated or measured merely because generation succeeded. Reproduce with
  `--only t110_graphs,t200_waveform_array_constant` (expected to fail on the tested installation).
- `lvai_exec_state` falls back to direct ActiveX because its composed error helper is itself
  broken in 2019. `linkerErrorsAvailable: false` and `errorsRead: false` mean unavailable,
  not an empty error list. Inspect compiler details in the IDE until a 2019 helper is implemented.
- Class-linked generation is blocked. Actor Framework, DQMH, interfaces, event editing and
  other advanced helpers are not covered by these tests. Do not treat tool discovery as certification.
- No physical DAQ device was exercised. Installed NI-DAQmx examples are the starting point for
  device-specific work. Confirm device model, compatible driver, channel/terminal configuration,
  input range, sample clock and actual readings before accepting a measurement application.
- NI AI gRPC workflows require a newer LabVIEW environment and are not provided by enabling
  VI Scripting in 2019.

For the user's AI-built DAQ workflow, basic panel/diagram scaffolding and numeric/array processing
can be automated now. An unattended waveform acquisition application needs additional work on
the 2019 readback helper and tests with the actual DAQ hardware.

## NI references

- [Enable VI Scripting](https://www.ni.com/docs/en-US/bundle/labview/page/enabling-vi-scripting.html)
- [Tutorial: wiring objects using VI Scripting](https://www.ni.com/docs/en-US/bundle/labview/page/tutorial-wiring-objects-using-vi-scripting.html)
  describes New VI Object and Connect Wire/Connect Wires.
- [LabVIEW 2019 / SP1 known issues](https://www.ni.com/en/support/documentation/bugs/19/labview-2019-and-2019-sp1-known-issues.html)
- Installed version-specific examples: `examples/Application Control/VI Scripting/Creating VIs/`
  and `Creating Objects/`, including `Creating New VI From Scratch.vi` and `Test - New VI Object.vi`.
  DAQ examples: `examples/DAQmx/Analog Input/Voltage - Finite Input.vi` and continuous-input examples.

The official tutorials guide the native Scripting operations; they do not establish compatibility
of the third-party composer. The actual target-IDE tests above provide that narrower evidence.
