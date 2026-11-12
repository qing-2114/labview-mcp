"""Hardware-free acceptance checks against a RUNNING LabVIEW 2019 IDE.

Uses the real stdio MCP server; never substitutes a fake LabVIEW for acceptance.
Outputs stay in artifacts/labview2019 (gitignored). No DAQ task is started.
"""
import argparse
import json
import math
import pathlib
import queue
import subprocess
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]

class Client:
    def __init__(self, exe):
        self.proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
        self.messages = queue.Queue()
        self.ident = 0
        threading.Thread(target=self.read, daemon=True).start()
        self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                  'clientInfo': {'name': 'verify-labview2019', 'version': '1'}})
        self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def read(self):
        for line in self.proc.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def send(self, value):
        self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()

    def request(self, method, params):
        self.ident += 1
        self.send({'jsonrpc': '2.0', 'id': self.ident, 'method': method, 'params': params})
        while True:
            msg = self.messages.get(timeout=180)
            if msg.get('id') == self.ident:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg['result']

    def call(self, name, **arguments):
        response = self.request('tools/call', {'name': name, 'arguments': arguments})
        return json.loads('\n'.join(x.get('text', '') for x in response.get('content', [])))

    def close(self):
        self.proc.kill()
        self.proc.wait(timeout=10)

def equal(actual, expected):
    if isinstance(expected, str):
        if expected.lower() in ('true', 'false'):
            return str(actual).lower() == expected.lower()
        return str(actual).replace('True', 'true').replace('False', 'false') == expected.replace('True', 'true').replace('False', 'false')
    if isinstance(expected, (float, int)):
        try:
            return math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return actual == expected

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=pathlib.Path, default=ROOT / 'src/LabVIEWMCP/bin/Debug/net8.0/LabVIEWMCP.exe')
    parser.add_argument('--only', help='Comma-separated fixture names')
    parser.add_argument('--features', action='store_true', help='Also exercise native layout, error inspection and rendering')
    args = parser.parse_args()
    output = ROOT / 'artifacts/labview2019'
    output.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / 'experiments/aixml-without-grpc/tests'
    expectations = json.loads((fixtures / 'expect.json').read_text(encoding='utf-8'))
    names = (args.only or 't01_add,t02_const_strlen,t03_select,t20_while_count,t30_for_sum,t31_for_scale,t40_case_bool,t60_cluster_pass,t61_array_pass,t66_array_nodes,t67_for_indexing,t73_case_error').split(',')
    results = {}
    client = Client(args.exe.resolve())
    try:
        ready = client.call('lvai_ensure_labview', backend='pylabview', keepAutoSave=True, waitSeconds=30)
        results['ready'] = ready
        if not ready.get('ok') or not str(ready.get('labviewVersion', '')).startswith('19.'):
            raise RuntimeError('Acceptance requires a responsive LabVIEW 2019 instance: ' + str(ready))
        for name in names:
            record = results[name] = {}
            try:
                source = fixtures / (name + '.xml')
                vi = output / (name + '.vi')
                record['generate'] = client.call('lvai_generate_vi', aiXmlFilePath=str(source), viPath=str(vi),
                    backend='pylabview', measurePane=False, measureDiagram=False,
                    cleanUpDiagram=False, cleanUpPanel=False, icon='none', timeoutSeconds=30)
                if not record['generate'].get('ok'):
                    raise AssertionError('generate failed')
                record['cases'] = []
                cases = expectations.get(name, {}).get('cases', []) or [{'inputs': '', 'outputs': {}}]
                for case in cases:
                    inputs = dict(item.split('=', 1) for item in case['inputs'].split(';') if item)
                    # Older corpus used braces for cluster inputs; the ActiveX route uses brackets.
                    inputs = {k: '[' + v[1:-1] + ']' if v.startswith('{') and v.endswith('}') else v
                              for k, v in inputs.items()}
                    run = client.call('lvai_run_vi_and_read_values', viPath=str(vi), backend='pylabview',
                                      inputsJson=json.dumps(inputs), timeoutSeconds=30)
                    record['cases'].append({'expected': case['outputs'], 'run': run})
                    assert run.get('ok') and run.get('ran') and run.get('finished'), 'run failed'
                    for key, expected in case['outputs'].items():
                        entry = run.get('values', {}).get(key, {})
                        assert not entry.get('problem'), (key, entry)
                        actual = entry.get('value')
                        # Legacy corpus represents arrays/clusters using AIXML literals.
                        assert equal(actual, expected) or equal(entry.get('literal'), expected), (key, actual, expected)
                record['passed'] = True
            except Exception as exc:
                record['passed'] = False
                record['error'] = str(exc)
            print(name, 'PASS' if record['passed'] else 'FAIL ' + record['error'], flush=True)
            (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.features:
            if 't01_add' not in names:
                raise ValueError('--features requires t01_add in the fixture selection')
            vi = str(output / 't01_add.vi')
            for tool, arguments in [
                ('lvai_exec_state', {'viPath': vi}),
                ('lvai_layout_diagram', {'viPath': vi, 'verify': True}),
                ('lvai_render_diagrams', {'viPaths': vi, 'outputDirectory': str(output / 'render')})
            ]:
                answer = client.call(tool, backend='pylabview', timeoutSeconds=60, **arguments)
                passed = bool(answer.get('ok'))
                if tool == 'lvai_exec_state':
                    passed = passed and answer.get('execState') == 1
                elif tool == 'lvai_layout_diagram':
                    passed = passed and answer.get('landedOff') == 0 and answer.get('moveErrors') == 0
                elif tool == 'lvai_render_diagrams':
                    passed = passed and answer.get('rendered') == 1
                results[tool] = {'passed': passed, 'answer': answer}
                print(tool, json.dumps(answer, ensure_ascii=False), flush=True)
    finally:
        client.close()
        (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if all(v.get('passed') for k, v in results.items() if k != 'ready') else 1

if __name__ == '__main__':
    raise SystemExit(main())
