#!/usr/bin/env python3
"""Build a non-secret portable fixture with the current Runner-owned codec.

This is an offline producer. It never publishes a revision, uploads bytes,
imports a package or submits an installation. Go overlays stay outside repos.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

PACKAGE = Path('internal/modules/kernel/panel/pkg/modelpackage')
SOURCE = r'''package modelpackage
import (
 "bytes"
 "encoding/json"
 "os"
 "io"
 "path/filepath"
 "testing"
 panelcommon "github.com/muidea/magicRunner/internal/modules/kernel/panel/pkg/common"
)
func TestMagicTestPortableFixture(t *testing.T) {
 input, err := os.ReadFile(os.Getenv("MAGICTEST_FIXTURE_INPUT")); if err != nil { t.Fatal(err) }
 var artifact panelcommon.ApplicationModelArtifact
 decoder := json.NewDecoder(bytes.NewReader(input)); decoder.DisallowUnknownFields()
 if err := decoder.Decode(&artifact); err != nil { t.Fatal(err) }
 if err := decoder.Decode(&struct{}{}); err != io.EOF { t.Fatal("fixture must contain exactly one artifact JSON value") }
 first, err := Build(&artifact); if err != nil { t.Fatal(err) }
 second, err := Build(&artifact); if err != nil { t.Fatal(err) }
 if !bytes.Equal(first.Payload, second.Payload) { t.Fatal("owner Build is not deterministic for original input") }
 parsed, err := Parse(first.Payload); if err != nil { t.Fatal(err) }
 if parsed.PackageDigest != first.PackageDigest || parsed.ModelDigest != first.ModelDigest || parsed.ArtifactDigest != first.ArtifactDigest { t.Fatal("owner Parse differs from original Build") }
 if parsed.Artifact.SourceRevisionID != 0 || parsed.Artifact.SourceRevisionRef != "" || parsed.Artifact.Application.ID != 0 { t.Fatal("owner retained local persistence identity in portable package") }
 output := os.Getenv("MAGICTEST_FIXTURE_OUTPUT")
 if err := os.WriteFile(filepath.Join(output,"package.zip"),first.Payload,0600); err != nil { t.Fatal(err) }
 write := func(name string, value any) { payload, err := json.MarshalIndent(value,"","  "); if err != nil { t.Fatal(err) }; if err := os.WriteFile(filepath.Join(output,name),append(payload,'\n'),0600); err != nil { t.Fatal(err) } }
 write("portable-artifact.json", parsed.Artifact)
 write("codec-result.json", map[string]any{"packageDigest":parsed.PackageDigest,"transportDigest":parsed.TransportDigest,"artifactDigest":parsed.ArtifactDigest,"modelDigest":parsed.ModelDigest,"manifest":parsed.Manifest,"size":len(first.Payload),"roundTripVerified":true,"deterministicBuildVerified":true,"sourceRevisionId":parsed.Artifact.SourceRevisionID})
}
'''


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(runner):
    paths = set()
    for directory in [PACKAGE, Path('internal/modules/kernel/panel/pkg/common'), Path('pkg/definitionjson')]:
        paths.update(path for path in (runner / directory).glob('*.go') if path.is_file())
    paths.update(runner / name for name in ['go.mod', 'go.sum', 'vendor/modules.txt'] if (runner / name).is_file())
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=runner, check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(['git', 'status', '--porcelain'], cwd=runner, check=True, capture_output=True, text=True).stdout.splitlines()
    return {'revision': revision, 'workingTreeStatus': status,
            'reviewedOwnerAndModuleHashes': {str(p.relative_to(runner)): digest(p) for p in sorted(paths)},
            'scope': 'current checkout codec/common/definitionjson and module manifests; not a deployed image identity or exhaustive transitive source attestation'}


def produce(runner, artifact, output):
    runner, artifact, output = (Path(p).expanduser().resolve() for p in [runner, artifact, output])
    if not (runner / PACKAGE / 'codec.go').is_file() or not (runner / 'vendor/modules.txt').is_file():
        raise ValueError('Current Runner source and default vendor dependencies are required')
    for protected in [runner, Path(__file__).resolve().parents[1]]:
        if output == protected or protected in output.parents:
            raise ValueError('Fixture output must stay outside Runner and magicTest source trees')
    if not artifact.is_file() or artifact.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('Fixture input must be a file within the 256 MiB tool read budget')
    # Fail before creating output or running Go if input is not JSON.
    json.loads(artifact.read_bytes())
    before = source_identity(runner)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {'status': 'started', 'inputSha256': digest(artifact), 'producerSha256': digest(Path(__file__)),
              'sourceBefore': before, 'dependencyMode': 'vendor',
              'live': 'not executed; no upload reference, publication, import, installation or owner mutation',
              'inputPolicy': 'caller supplies non-secret fixtures; no credential discovery or Live operations' }
    with tempfile.TemporaryDirectory(prefix='magictest-model-codec-') as temporary:
        scratch = Path(temporary)
        original = runner / PACKAGE / 'zz_magictest_fixture_producer_test.go'
        if original.exists():
            raise ValueError('Overlay test name already exists in owner checkout')
        replacement = scratch / original.name
        replacement.write_text(SOURCE)
        overlay = scratch / 'overlay.json'
        overlay.write_text(json.dumps({'Replace': {str(original): str(replacement)}}))
        # Snapshot exact original bytes: the caller cannot change the artifact
        # after the hash and before owner decoding without being detected.
        original_input = scratch / 'input.json'
        original_input.write_bytes(artifact.read_bytes())
        if digest(original_input) != report['inputSha256']:
            raise ValueError('Fixture input changed before owner execution')
        env = os.environ.copy()
        env.update({'MAGICTEST_FIXTURE_INPUT': str(original_input), 'MAGICTEST_FIXTURE_OUTPUT': str(output),
                    'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off'})
        command = ['go', 'test', '-mod=vendor', '-overlay', str(overlay), '-run', '^TestMagicTestPortableFixture$', '-count=1', './' + str(PACKAGE)]
        try:
            result = subprocess.run(command, cwd=runner, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180, check=False)
            (output / 'codec.log').write_bytes(result.stdout)
            report.update(exitCode=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        except subprocess.TimeoutExpired as error:
            (output / 'codec.log').write_bytes(error.stdout or b'')
            report.update(status='blocked', reason='Owner codec exceeded finite 180s tool budget; no Live command was dispatched')
        report['sourceAfter'] = source_identity(runner)
        report['sourceUnchanged'] = report['sourceBefore'] == report['sourceAfter']
        if not report['sourceUnchanged']:
            report.update(status='blocked', reason='Owner checkout changed during offline fixture production')
        if report['status'] == 'passed':
            required = ['package.zip', 'portable-artifact.json', 'codec-result.json']
            if not all((output / name).is_file() for name in required):
                report.update(status='failed', reason='Owner codec did not return every declared output')
            else:
                report['outputSha256'] = {name: digest(output / name) for name in required}
    (output / 'producer-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', required=True, help='current Runner checkout with generated vendor')
    parser.add_argument('--artifact', required=True, help='non-secret current ApplicationModelArtifact JSON')
    parser.add_argument('--output', required=True, help='new directory outside source repositories')
    args = parser.parse_args()
    report = produce(args.runner, args.artifact, args.output)
    print(json.dumps({'status': report['status'], 'sourceUnchanged': report['sourceUnchanged'], 'live': report['live']}))
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
