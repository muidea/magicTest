#!/usr/bin/env python3
"""Validate the acceptance catalogue and evidence; never infer a live pass from tests."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {'passed', 'failed', 'blocked', 'untested'}
SUITES = {'standard', 'abnormal', 'special'}
CORE = ('magicPanel', 'magicWebPortal', 'magiccas', 'magicbase', 'magicGateway', 'magicFile', 'postgres', 'traefik')


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_execution(catalog):
    """Shared by reporting and read-only navigation; no dependency on script readiness."""
    suites = catalog.get('executionSuites')
    require(isinstance(suites, dict) and set(suites) == SUITES and all(nonempty(x) for x in suites.values()),
            'invalid execution suites')
    prerequisites = catalog.get('specialPrerequisites', {})
    require(isinstance(prerequisites, dict) and bool(prerequisites), 'missing special prerequisites')
    for definition in prerequisites.values():
        require(isinstance(definition, dict) and
                all(nonempty(definition.get(key)) for key in ('name', 'preparation', 'exitCriteria')),
                'incomplete special prerequisite')
    for case in catalog.get('cases', []):
        parts = case.get('execution')
        require(isinstance(parts, list) and bool(parts), 'case needs execution scope')
        seen = set()
        for part in parts:
            require(isinstance(part, dict), 'invalid execution branch')
            suite = part.get('suite')
            require(suite in SUITES and suite not in seen, 'unknown or duplicate execution suite')
            seen.add(suite)
            require(nonempty(part.get('scope')), 'missing execution branch scope')
            require(part.get('fixture') in catalog.get('fixtures', {}), 'unknown execution branch fixture')
            deps = part.get('prerequisites')
            require(isinstance(deps, list) and all(isinstance(x, str) for x in deps),
                    'invalid prerequisite list')
            require(len(deps) == len(set(deps)) and set(deps) <= prerequisites.keys(),
                    'duplicate or unknown prerequisite')
            require(bool(deps) == (suite == 'special'), 'only special branches require special prerequisites')
            require(suite == 'special' or part['fixture'] not in {'natural-time', 'external-idp'},
                    'automatic suite fixture must not wait for special conditions')
        if 'abnormal' in seen:
            require(case.get('kind') in {'authorization', 'boundary', 'recovery'},
                    'abnormal suite only contains disruptive authorization/boundary/recovery cases')
        if seen & {'standard', 'abnormal'}:
            require(bool(set(case.get('methods', [])) & {'live', 'browser'}),
                    'automatic branch needs automatic verification method')


def validate_catalog(catalog):
    require(catalog.get('schema') == 'magic.acceptance/v1', 'invalid catalogue schema')
    require(nonempty(catalog.get('baseline')), 'missing catalogue baseline')
    require(isinstance(catalog.get('sources'), list) and bool(catalog['sources']) and
            all(nonempty(x) and x.startswith('~/') for x in catalog['sources']),
            'catalogue sources must use current home-rooted paths')
    for key in ('scope', 'applicability', 'oracle', 'isolation', 'completion', 'cleanup', 'evidence', 'automation'):
        require(nonempty(catalog.get('executionRequirements', {}).get(key)),
                'missing execution requirement: ' + key)
    features = catalog.get('features', [])
    require(bool(features), 'empty feature scope')
    ids = [f.get('id') for f in features]
    require(len(set(ids)) == len(ids), 'duplicate feature IDs')
    require(all(isinstance(i, str) and re.fullmatch(r'F\d{3}', i) for i in ids), 'invalid feature ID')
    for feature in features:
        require(isinstance(feature.get('owners'), list) and bool(feature['owners']) and
                all(nonempty(x) for x in feature['owners']), 'feature needs fact owners')
    cases = catalog.get('cases', [])
    case_ids = [c.get('id') for c in cases]
    require(len(set(case_ids)) == len(case_ids), 'duplicate case IDs')
    for case in cases:
        fid = case.get('featureId')
        require(fid in ids, 'case references unknown feature')
        require(isinstance(case.get('id'), str) and re.fullmatch(fid + r'-\d{3}', case['id']), 'invalid case ID')
        require(case.get('kind') in {'normal', 'boundary', 'authorization', 'recovery', 'interaction'}, 'invalid case kind')
        require(case.get('fixture') in catalog.get('fixtures', {}), 'unknown fixture')
        require(type(case.get('required')) is bool, 'required must be boolean')
        require(nonempty(case.get('purpose')), 'case needs necessity and distinct purpose')
        for key in ('steps', 'expected', 'methods'):
            require(isinstance(case.get(key), list) and bool(case[key]) and all(nonempty(x) for x in case[key]), 'empty ' + key)
        require(set(case['methods']) <= {'live', 'browser', 'manual'}, 'unit tests cannot establish a live acceptance pass')
    for fid in ids:
        kinds = {c['kind'] for c in cases if c['featureId'] == fid and c['required']}
        require('normal' in kinds and len(kinds) > 1, fid + ' needs normal and negative/interaction acceptance cases')
    validate_execution(catalog)
    return {c['id']: c for c in cases}


def validate_results(catalog, results, base):
    cases = validate_catalog(catalog)
    require(results.get('schema') == 'magic.acceptance.results/v1', 'invalid result schema')
    require(results.get('baseline') == catalog['baseline'], 'baseline mismatch')
    entries = results.get('results', [])
    require(isinstance(entries, list), 'results must be an array')
    if not entries:
        return {}
    require(nonempty(results.get('runId')), 'missing run ID')
    require(results.get('catalogDigest') == digest(catalog), 'catalogue changed; review cases and rerun affected scope')
    env = results.get('environment', {})
    require(nonempty(env.get('name')), 'missing environment name')
    is_remote = env.get('mode') == 'remote-https'
    for key in ('fingerprint', 'configurationDigest'):
        require(isinstance(env.get(key), str) and re.fullmatch(r'sha256:[0-9a-f]{64}', env[key]), 'missing immutable ' + key)
    if is_remote:
        require(nonempty(env.get('origin')) and env['origin'].startswith('https://'), 'remote-https mode requires explicit HTTPS origin')
        require(env['fingerprint'] == digest({'mode': 'remote-https', 'origin': env['origin'], 'configurationDigest': env['configurationDigest']}),
                'environment fingerprint mismatch')
    else:
        versions = env.get('versions', {})
        require(all(name in versions for name in CORE), 'missing deployed component versions')
        require(all(isinstance(v, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', v) for v in versions.values()), 'tags alone are not version evidence')
        require(env['fingerprint'] == digest({'versions': versions, 'configurationDigest': env['configurationDigest']}), 'environment fingerprint mismatch')
    output = {}
    for item in entries:
        cid = item.get('caseId')
        require(cid in cases, 'unknown result case')
        suite = item.get('suite')
        require(suite in {p['suite'] for p in cases[cid]['execution']}, 'unknown result execution suite')
        if is_remote and cid == 'F059-001' and item.get('status') == 'passed':
            raise ValueError('remote-https mode cannot mark Docker container check F059-001 as passed')
        result_key = (cid, suite)
        require(result_key not in output, 'duplicate result branch; preserve prior attempts separately')
        require(item.get('status') in STATUSES, 'invalid result status')
        require(item.get('environmentFingerprint') == env['fingerprint'], 'mixed deployment versions in one report')
        require(item.get('method') in cases[cid]['methods'], 'wrong verification method; tests are separate evidence')
        if suite in {'standard', 'abnormal'} and item['status'] == 'passed':
            require(item['method'] in {'live', 'browser'}, 'automatic pass needs automated live/browser verification')
        for key in ('role', 'namespace', 'resource', 'actual'):
            require(nonempty(item.get(key)), 'missing result ' + key)
        require(isinstance(item.get('observedAt'), str), 'missing result timestamp')
        timestamp = datetime.fromisoformat(item['observedAt'].replace('Z', '+00:00'))
        require(timestamp.tzinfo is not None, 'timestamp needs timezone')
        if item['status'] in {'failed', 'blocked'}:
            require(nonempty(item.get('reason')), 'failed/blocked result needs reason')
        if item['status'] == 'failed':
            require(nonempty(item.get('defectId')), 'failure needs tracked defect')
        if item['status'] in {'passed', 'failed'}:
            evidence = item.get('evidence', [])
            require(isinstance(evidence, list) and bool(evidence), 'executed case needs evidence')
            for proof in evidence:
                require(proof.get('kind') in {'browser', 'manual', 'live', 'operational'}, 'historical or unit evidence cannot mark live pass')
                require(nonempty(proof.get('path')), 'missing evidence path')
                path = (base / proof['path']).resolve()
                require(path.is_file(), 'evidence file missing: ' + proof['path'])
                actual_hash = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
                require(proof.get('sha256') == actual_hash, 'evidence checksum mismatch')
            if item['method'] in {'manual', 'browser'}:
                require(any(p['kind'] in {'manual', 'browser'} for p in evidence), 'UI acceptance needs browser/manual evidence')
            if suite in {'standard', 'abnormal'} and item['status'] == 'passed':
                require(any(p['kind'] in {'live', 'browser', 'operational'} for p in evidence),
                        'automatic pass needs automatically collected evidence')
        output[result_key] = item
    return output


def combined_status(states):
    return ('failed' if states['failed'] else 'blocked' if states['blocked'] else
            'passed' if states and states['passed'] == sum(states.values()) else
            'partial' if states['passed'] else 'untested')


def summarize(catalog, entries, suite='standard'):
    require(suite in SUITES | {'all'}, 'invalid report suite')
    required = [c for c in catalog['cases'] if c['required']]
    selected = [(c, p['suite']) for c in required for p in c['execution']
                if suite == 'all' or p['suite'] == suite]
    counts = Counter(entries.get((c['id'], group), {}).get('status', 'untested') for c, group in selected)
    executed = counts['passed'] + counts['failed']
    features = []
    for feature in catalog['features']:
        cases = [(c, group) for c, group in selected if c['featureId'] == feature['id']]
        if not cases:
            continue
        states = Counter(entries.get((c['id'], group), {}).get('status', 'untested') for c, group in cases)
        features.append({'id': feature['id'], 'name': feature['name'],
                         'status': combined_status(states), 'counts': dict(states)})
    whole_cases = []
    for case in required:
        parts = {p['suite']: entries.get((case['id'], p['suite']), {}).get('status', 'untested')
                 for p in case['execution']}
        whole_cases.append({'caseId': case['id'], 'status': combined_status(Counter(parts.values())), 'parts': parts})
    whole_counts = Counter(c['status'] for c in whole_cases)
    return {'baseline': catalog['baseline'], 'suite': suite,
            'requiredCases': len({c['id'] for c, _ in selected}), 'requiredChecks': len(selected),
            'counts': dict(counts), 'coverage': executed / len(selected) if selected else 0,
            'passRate': counts['passed'] / executed if executed else None,
            'complete': bool(selected) and counts['passed'] == len(selected), 'features': features,
            'catalogCoverage': {'requiredCases': len(required), 'counts': dict(whole_counts),
                                'complete': bool(required) and whole_counts['passed'] == len(required),
                                'cases': whole_cases}}


def render_ledger(catalog):
    lines = ['# 平台功能回归用例', '',
             '本表由[唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)生成，只描述当前要求。执行结果由报告工具按当次候选另行汇总，不手改生成表。', '',
             f"共 {len(catalog['features'])} 类功能、{len(catalog['cases'])} 条用例，其中 {sum(c['required'] for c in catalog['cases'])} 条完整回归必需。稳定编号不可复用；用例定义不表示脚本就绪或业务验证通过。", '',
             '## 共同执行要求', '']
    lines.extend('- ' + value for value in catalog['executionRequirements'].values())
    lines += ['', '## 夹具与条件', '']
    lines.extend('- ' + name + '：' + description for name, description in catalog['fixtures'].items())
    lines += ['', '## 合同来源', '']
    lines.extend('- ' + source for source in catalog['sources'])
    lines.append('')
    for feature in catalog['features']:
        lines += ['## ' + feature['id'] + ' ' + feature['name'], '', '入口：' + feature['entry'], '', '边界：' + feature['boundary'], '',
                  '事实owner：' + '、'.join(feature['owners']), '',
                  '| 用例 | 必要性与独立目的 | 类型 | 操作与步骤 | 预期结果 | 环境 / 方法 | 执行分组与范围 |', '| --- | --- | --- | --- | --- | --- | --- |']
        for case in catalog['cases']:
            if case['featureId'] != feature['id']:
                continue
            cells = [case['id'] + ' ' + case['title'], case['purpose'], case['kind'], '；'.join(case['steps']), '；'.join(case['expected']),
                     case['fixture'] + ' / ' + ','.join(case['methods']),
                     '；'.join(p['suite'] + ' [' + p['fixture'] + ']：' + p['scope'] for p in case['execution'])]
            lines.append('| ' + ' | '.join(x.replace('|', '／').replace('\n', ' ') for x in cells) + ' |')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def render_special_cases(catalog):
    cases = [c for c in catalog['cases'] if any(p['suite'] == 'special' for p in c['execution'])]
    mixed = sum(len(c['execution']) > 1 for c in cases)
    owners = {f['id']: '、'.join(f['owners']) for f in catalog['features']}
    lines = ['# 平台条件专项用例', '',
             '由[唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)生成；完整步骤和预期见[用例表](~/codespace/magicTest/acceptance/platform-case-ledger.md)。不手工维护第二套用例正文。', '',
             f'共{len(cases)}条涉及专项，其中{mixed}条同时包含自动回归分项。专项缺条件不阻断常规正向或异常回归；混合用例必须全部分组都通过才算整条通过。', '',
             '## 条件、准备与退出要求', '']
    for key, dep in catalog['specialPrerequisites'].items():
        lines += [f"### {key}：{dep['name']}", '', '准备：' + dep['preparation'], '', '退出：' + dep['exitCriteria'], '']
    lines += ['## 执行与证据', '', catalog['executionRequirements']['oracle'], '',
              catalog['executionRequirements']['cleanup'], '', catalog['executionRequirements']['evidence'], '',
              '专项按各自条件预检和调度。缺脚本、owner测试装置、有效预算或支持合同分别登记缺口，不统一归为第三方不可用。不得在业务环境临时停服务制造样本。', '',
              '| 用例 | 事实owner | 保留在自动回归的范围 | 单列专项范围 | 前置条件 |', '| --- | --- | --- | --- | --- |']
    for case in cases:
        parts = {p['suite']: p for p in case['execution']}
        auto_scope = next((p['suite'] + '：' + p['scope'] for p in case['execution'] if p['suite'] != 'special'),
                          '无；本用例全部单列专项')
        cells = [case['id'] + ' ' + case['title'], owners[case['featureId']], auto_scope,
                 parts['special']['scope'], parts['special']['fixture'] + '；' + '、'.join(parts['special']['prerequisites'])]
        lines.append('| ' + ' | '.join(x.replace('|', '／').replace('\n', ' ') for x in cells) + ' |')
    return '\n'.join(lines).rstrip() + '\n'


def render_abnormal_cases(catalog):
    cases = [c for c in catalog['cases'] if any(p['suite'] == 'abnormal' for p in c['execution'])]
    mixed = sum(any(p['suite'] == 'special' for p in c['execution']) for c in cases)
    counts = Counter(c['kind'] for c in cases)
    owners = {f['id']: '、'.join(f['owners']) for f in catalog['features']}
    kind_labels = {'authorization': '故障/伪造边界', 'boundary': '破坏/超限/受损校验', 'recovery': '并发冲突与故障恢复'}
    lines = ['# 平台破坏性与异常故障验证清单', '',
             '由[唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)生成；完整步骤和预期见[用例表](~/codespace/magicTest/acceptance/platform-case-ledger.md)。不手工维护第二套用例正文。', '',
             f"共{len(cases)}条破坏性及故障异常测试分项（权限故障类{counts.get('authorization', 0)}、破坏/超限类{counts.get('boundary', 0)}、并发/中断恢复类{counts.get('recovery', 0)}），其中{mixed}条同时包含条件专项分项。不产生破坏性的正向功能、只读权限隔离、正常输入拒绝与无副作用取消保留在默认常规正向验证（`standard`）；本表所列用例统一单列并通过 `platform-abnormal` 独立执行。", '',
             '## 分类与执行原则', '',
             '- 归入原则：仅包含故障注入、请求/清理中断、损坏制品/快照、进程重启、响应丢失模拟、并发写竞争、来源限流/锁定及全局边界冲突等产生破坏性或干扰性的测试。',
             '- 不产生破坏性的权限矩阵、跨租户隔离、分页聚合及合法输入/引用保护拒绝均保留在正向回归（`standard`）。',
             '- 通过正向常规回归不代表破坏性异常测试或完整目录通过；混合专项分项按各自条件单独预检与验收。', '',
             '| 用例 | 类型 | 事实owner | 异常验证范围 | 并存专项范围 | 夹具 / 方法 |', '| --- | --- | --- | --- | --- | --- |']
    for case in cases:
        parts = {p['suite']: p for p in case['execution']}
        special_scope = parts.get('special', {}).get('scope', '无')
        cells = [case['id'] + ' ' + case['title'],
                 f"{case['kind']}（{kind_labels.get(case['kind'], case['kind'])}）",
                 owners[case['featureId']],
                 parts['abnormal']['scope'],
                 special_scope,
                 parts['abnormal']['fixture'] + ' / ' + ','.join(case['methods'])]
        lines.append('| ' + ' | '.join(x.replace('|', '／').replace('\n', ' ') for x in cells) + ' |')
    return '\n'.join(lines).rstrip() + '\n'


def configuration_digest(inspected):
    """Docker mount enumeration order is not a configuration change."""
    configuration = []
    for container in sorted(inspected, key=lambda item: item['Name']):
        entry = {key: container.get(key) for key in ('Name', 'Config', 'HostConfig')}
        entry['Mounts'] = sorted(container.get('Mounts', []),
                                 key=lambda mount: json.dumps(mount, sort_keys=True))
        configuration.append(entry)
    return digest(configuration)


def capture_health(catalog, directory):
    """Read-only Docker baseline. No exec, restarts, log contents, Env output or secrets."""
    inspected = json.loads(subprocess.check_output(['docker', 'inspect', *CORE], text=True))
    require(len(inspected) == len(CORE), 'missing core containers')
    versions = {c['Name'].lstrip('/'): c['Image'] for c in inspected}
    config_digest = configuration_digest(inspected)  # private configuration is never written
    fingerprint = digest({'versions': versions, 'configurationDigest': config_digest})
    observed = datetime.now(timezone.utc).isoformat()
    summary = [{'name': c['Name'].lstrip('/'), 'imageId': c['Image'], 'imageAddress': c['Config']['Image'],
                'state': c['State']['Status'], 'health': c['State'].get('Health', {}).get('Status', 'not-configured'),
                'restartCount': c.get('RestartCount', 0)} for c in inspected]
    passed = all(c['state'] == 'running' and c['health'] in {'healthy', 'not-configured'} for c in summary)
    directory.mkdir(parents=True, exist_ok=True)
    evidence = directory / 'core-health.json'
    evidence.write_text(json.dumps({'observedAt': observed, 'containers': summary}, ensure_ascii=False, indent=2) + '\n')
    env = {'name': 'local-docker-core', 'versions': versions, 'configurationDigest': config_digest, 'fingerprint': fingerprint}
    result = {'schema': 'magic.acceptance.results/v1', 'baseline': catalog['baseline'], 'catalogDigest': digest(catalog),
              'runId': 'core-health-' + observed, 'environment': env,
              'results': [{'caseId': 'F059-001', 'suite': 'standard', 'status': 'passed' if passed else 'failed', 'method': 'live',
                           'observedAt': observed, 'environmentFingerprint': fingerprint, 'role': 'deployment-inspector',
                           'namespace': 'platform', 'resource': 'core-containers',
                           'actual': '核心容器运行状态与已配置的健康检查核对；不代表数据库连接或业务链路通过。',
                           'evidence': [{'kind': 'operational', 'path': evidence.name,
                                         'sha256': 'sha256:' + hashlib.sha256(evidence.read_bytes()).hexdigest()}]}]}
    if not passed:
        result['results'][0].update(reason='核心容器未运行或健康检查未通过', defectId='ENV-CORE-HEALTH')
    target = directory / 'results.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return target


class _SniHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an explicit IP/address while preserving TLS SNI for the target hostname."""

    def __init__(self, connect_host, sni_host, port, *, context, timeout):
        super().__init__(connect_host, port=port, context=context, timeout=timeout)
        self._sni_host = sni_host

    def connect(self):
        sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)


def _build_remote_ssl_context(*, ca_file=None, insecure=False):
    if insecure:
        ctx = ssl._create_unverified_context()
        return ctx, 'insecure'
    if ca_file:
        ctx = ssl.create_default_context(cafile=str(Path(ca_file).expanduser()))
        if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
            ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        return ctx, f'custom-ca:{Path(ca_file).name}'
    return ssl.create_default_context(), 'system-ca'


def capture_remote_health(catalog, directory, *, origin, target_address=None, ca_file=None, insecure=False, timeout=10):
    """Read-only remote HTTPS baseline without local Docker daemon inspection."""
    parsed = urlsplit(origin)
    require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password,
            'remote-https health check requires an explicit HTTPS origin without userinfo')
    connect_host = str(target_address).strip() if target_address else parsed.hostname
    port = parsed.port or 443
    host_header = parsed.netloc
    context, tls_mode = _build_remote_ssl_context(ca_file=ca_file, insecure=insecure)

    probe_specs = (
        ('http_portal_root', '/', None),
        ('http_oidc_discovery', '/api/v1/cas/.well-known/openid-configuration', 'issuer'),
        ('http_oidc_jwks', '/api/v1/cas/oauth/jwks', 'keys'),
        ('http_web_branding', '/api/v1/web/branding/', None),
    )
    probes = []
    issuer = ''
    jwks_keys = []
    branding_status = None
    for name, route, required_key in probe_specs:
        conn = _SniHTTPSConnection(connect_host, parsed.hostname, port, context=context, timeout=timeout)
        entry = {'name': name, 'path': route, 'passed': False, 'status': None}
        try:
            conn.request('GET', route, headers={'Host': host_header, 'Accept': 'application/json'})
            resp = conn.getresponse()
            body = resp.read(1024 * 1024)
            entry['status'] = resp.status
            if name == 'http_web_branding':
                branding_status = resp.status
            if resp.status == 200:
                if required_key:
                    payload = json.loads(body.decode('utf-8'))
                    if isinstance(payload, dict) and payload.get(required_key):
                        entry['passed'] = True
                        if name == 'http_oidc_discovery':
                            issuer = str(payload['issuer'])
                        elif name == 'http_oidc_jwks' and isinstance(payload['keys'], list):
                            jwks_keys = sorted(
                                f"{k.get('kid', '')}:{k.get('kty', '')}:{k.get('alg', '')}"
                                for k in payload['keys'] if isinstance(k, dict)
                            )
                else:
                    entry['passed'] = True
        except Exception as exc:
            entry['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            conn.close()
        probes.append(entry)

    passed = all(p['passed'] for p in probes)
    observed = datetime.now(timezone.utc).isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    evidence = directory / 'remote-health.json'
    evidence.write_text(json.dumps({
        'observedAt': observed,
        'origin': origin,
        'targetAddress': connect_host if target_address else None,
        'tlsVerification': tls_mode,
        'issuer': issuer,
        'jwksKeys': jwks_keys,
        'probes': probes,
    }, ensure_ascii=False, indent=2) + '\n')
    config_digest = digest({
        'origin': origin,
        'issuer': issuer,
        'jwksKeys': jwks_keys,
        'brandingStatus': branding_status,
    })
    fingerprint = digest({'mode': 'remote-https', 'origin': origin, 'configurationDigest': config_digest})
    env = {
        'name': 'remote-https',
        'mode': 'remote-https',
        'origin': origin,
        'targetAddress': connect_host if target_address else None,
        'tlsVerification': tls_mode,
        'configurationDigest': config_digest,
        'fingerprint': fingerprint,
    }
    result = {
        'schema': 'magic.acceptance.results/v1',
        'baseline': catalog['baseline'],
        'catalogDigest': digest(catalog),
        'runId': 'remote-health-' + observed,
        'environment': env,
        'remoteHealth': {
            'passed': passed,
            'origin': origin,
            'probes': probes,
            'evidence': {
                'kind': 'live',
                'path': evidence.name,
                'sha256': 'sha256:' + hashlib.sha256(evidence.read_bytes()).hexdigest(),
            },
        },
        'results': [],
    }
    target = directory / 'results.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'acceptance/platform-catalog.json')
    parser.add_argument('--results', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--abnormal-ledger', type=Path, help='generate the abnormal-case view from the catalogue')
    parser.add_argument('--special-ledger', type=Path, help='generate the special-case view from the catalogue')
    parser.add_argument('--suite', choices=['standard', 'abnormal', 'special', 'all'], default='standard')
    parser.add_argument('--capture-health', type=Path, help='read-only Docker baseline evidence directory')
    parser.add_argument('--resource-state', type=Path, help='reconcile live infrastructure; require confirmed cleanup for completion')
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text())
        validate_catalog(catalog)
        if args.ledger:
            args.ledger.write_text(render_ledger(catalog))
        if args.abnormal_ledger:
            args.abnormal_ledger.write_text(render_abnormal_cases(catalog))
        if args.special_ledger:
            args.special_ledger.write_text(render_special_cases(catalog))
        if args.capture_health:
            require(args.results is None, 'capture-health cannot overwrite a supplied results run')
            if args.resource_state is None:
                args.resource_state = Path.home() / '.local/state/platform-acceptance/resources'
            args.results = capture_health(catalog, args.capture_health)
        if args.results:
            raw = json.loads(args.results.read_text())
            entries = validate_results(catalog, raw, args.results.parent)
        else:
            entries = {}
        report = summarize(catalog, entries, args.suite)
        report['environment'] = raw['environment'] if args.results and entries else None
        if args.resource_state:
            from acceptance_resources import Resources
            with Resources(args.resource_state).locked() as owner:
                report['resourceLifecycle'] = owner.report()
            report['caseComplete'] = report['complete']
            report['complete'] = report['complete'] and report['resourceLifecycle']['allCleaned']
            report['catalogCoverage']['caseComplete'] = report['catalogCoverage']['complete']
            report['catalogCoverage']['complete'] = (report['catalogCoverage']['complete'] and
                                                      report['resourceLifecycle']['allCleaned'])
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        counts = report['counts']
        print(f"suite={args.suite} features={len(report['features'])} requiredCases={report['requiredCases']} requiredChecks={report['requiredChecks']} passed={counts.get('passed', 0)} failed={counts.get('failed', 0)} blocked={counts.get('blocked', 0)} untested={counts.get('untested', 0)}")
        print('coverage={:.2%} passRate={} complete={}'.format(report['coverage'], 'not-measured' if report['passRate'] is None else f"{report['passRate']:.2%}", report['complete']))
        if 'catalogCoverage' in report:
            print('catalogComplete=' + str(report['catalogCoverage']['complete']))
        return 0 if report['complete'] else 2
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        print('invalid acceptance evidence: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
