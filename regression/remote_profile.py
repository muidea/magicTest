"""Remote-HTTPS case classification for separated-server functional regression."""

# Cases requiring local Docker daemon, platformRoot filesystem, postgres_fixture,
# deliveryFixtureConfig, or runtimeSnapshotConfig on the test runner host.
HOST_COUPLED_STANDARD_CASES = frozenset({
    'F059-001',
    'F008-002',
    'F019-002',
    'F020-003',
    'F021-001',
    'F021-002',
    'F021-003',
    'F022-001',
    'F022-002',
    'F023-001',
    'F023-002',
    'F023-003',
    'F024-001',
    'F024-002',
    'F026-002',
    'F030-001',
    'F031-001',
    'F031-002',
    'F032-001',
    'F033-002',
    'F035-004',
    'F036-003',
    'F040-002',
    'F040-003',
    'F041-002',
    'F041-003',
    'F042-001',
    'F042-002',
    'F042-003',
    'F043-003',
    'F047-001',
    'F047-002',
    'F048-001',
    'F048-002',
})

HOST_COUPLED_ABNORMAL_CASES = frozenset({
    'F022-003',
    'F031-003',
    'F035-006',
    'F058-002',
    'F060-003',
    'F070-003',
})

# Cases requiring a controlled HTTP upstream reachable from the platform magicGateway.
UPSTREAM_CALLBACK_STANDARD_CASES = frozenset({
    'F004-001',
    'F007-001',
    'F007-002',
    'F007-003',
    'F007-004',
    'F008-003',
    'F019-001',
    'F020-001',
    'F020-004',
    'F033-004',
    'F033-005',
    'F039-001',
    'F039-002',
    'F039-003',
    'F040-001',
    'F041-001',
    'F043-001',
    'F043-002',
    'F044-001',
    'F044-002',
    'F044-003',
    'F045-001',
    'F045-003',
    'F046-001',
    'F046-002',
    'F046-003',
    'F057-002',
    'F065-001',
})

UPSTREAM_CALLBACK_ABNORMAL_CASES = frozenset({
    'F010-004',
    'F057-004',
})


def excluded_for_remote(suite='standard', *, include_upstream=False):
    """Return sorted case IDs to exclude in remote-https mode when host-coupled exclusion is active."""
    if suite == 'standard':
        excluded = set(HOST_COUPLED_STANDARD_CASES)
        if not include_upstream:
            excluded |= UPSTREAM_CALLBACK_STANDARD_CASES
        return sorted(excluded)
    if suite == 'abnormal':
        excluded = set(HOST_COUPLED_ABNORMAL_CASES)
        if not include_upstream:
            excluded |= UPSTREAM_CALLBACK_ABNORMAL_CASES
        return sorted(excluded)
    raise ValueError(f'Unsupported suite for remote profile: {suite}')
