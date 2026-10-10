"""Re-run shipped controls and write deterministic synthetic artifacts."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prompt_skill_linter.engine import lint  # noqa: E402
from prompt_skill_linter.cli import render  # noqa: E402


def main():
    examples = ROOT / 'examples'
    contract = json.loads((examples / 'bulk.contract.json').read_text())
    tools = json.loads((examples / 'tools.json').read_text())
    destination = ROOT / 'corpus/synthetic'
    destination.mkdir(parents=True, exist_ok=True)
    runs = []
    for name, expected in [('runtime', 2), ('runtime-budget32', 0), ('runtime-budget38', 0), ('runtime-budget40', 0)]:
        runtime = json.loads((examples / (name + '.json')).read_text())
        report = lint(contract, tools, runtime, examples)
        assert report['summary']['error'] == expected, (name, report['summary'])
        (destination / (name + '.report.json')).write_text(json.dumps(report, indent=2) + '\n')
        (destination / (name + '.report.txt')).write_text(render(report))
        runs.append({'runtime': name, 'expected_errors': expected, 'observed_errors': report['summary']['error'],
                     'classification': 'synthetic', 'status': 'passed'})
    (destination / 'manifest.json').write_text(json.dumps({'version': 1, 'runs': runs, 'scope': 'Declared lower-bound controls, not whole-pipeline evaluation'}, indent=2) + '\n')
    print(json.dumps(runs, indent=2))


if __name__ == '__main__': main()
