"""Rebuild frozen original candidates from an owner's local pinned source checkout.

No network access or source-code execution. Checks canonical Git-blob/SHA256 and
reconstructed candidate SHA256. Published sparse excerpts are not full inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.scientific_workflows import local_path, read


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rehydrate(corpus, source_root, output):
    corpus, source_root, output = map(Path, (corpus, source_root, output))
    sources = {s['path']: s for s in read(corpus / 'source-manifest.json')['files']}
    records = [r for r in read(corpus / 'excerpt-provenance.json')['entries'] if r['kind'] == 'candidates']
    prepared = []
    for record in records:
        bundle = read(local_path(corpus, record['published_bundle']))
        for entry in record['sources']:
            source = sources[entry['upstream_path']]
            raw = local_path(source_root, source['path']).read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if sha(raw) != source['canonical_sha256'] or blob != source['git_blob_sha']:
                raise ValueError('Pinned source bytes differ: ' + source['path'])
            # This transformation is recorded in the frozen source manifest.
            if source.get('capture_transform') == 'One trailing newline added by apply_patch; line spans and content unchanged.':
                raw += b'\n'
            elif source.get('capture_transform'):
                raise ValueError('Unsupported recorded capture transform.')
            text = raw.decode('utf-8')
            if sha(raw) != entry['full_captured_sha256']:
                raise ValueError('Original captured source hash differs.')
            bundle['sources'][entry['source_id']] = text
        for span in bundle['contract']['interpretation'].get('unsupported_spans', []):
            span['quote'] = '\n'.join(bundle['sources'][span['source_id']].splitlines()[span['start_line']-1:span['end_line']])
        data = (json.dumps(bundle, indent=2) + '\n').encode()
        if sha(data) != record['original_bundle_sha256']:
            raise ValueError('Reconstructed original candidate hash differs: ' + record['case_id'])
        target = local_path(output, 'bundles/' + record['case_id'] + '.json')
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Output exists with different bytes: ' + str(target))
        prepared.append((target, data))
    for target, data in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {'reconstructed_original_candidates': len(prepared), 'source_code_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path(__file__).resolve().parents[1] / 'corpus/scientific_workflows')
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rehydrate(args.corpus, args.source_root, args.output), indent=2))


if __name__ == '__main__':
    main()
