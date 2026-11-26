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

# Cases requiring deliveryFixtureConfig (dedicated isolated deployment + published public-owner fixture),
# which is disallowed in remote-https mode.
DELIVERY_FIXTURE_STANDARD_CASES = frozenset({
    'F003-004',
    'F006-001',
    'F006-002',
    'F006-003',
    'F006-004',
    'F011-001',
    'F013-001',
    'F013-002',
    'F014-001',
    'F014-002',
    'F014-003',
    'F014-004',
    'F015-001',
    'F016-001',
    'F017-003',
    'F019-003',
    'F025-001',
    'F025-002',
    'F025-003',
    'F027-001',
    'F027-002',
    'F028-001',
    'F028-003',
    'F029-001',
    'F029-003',
    'F030-002',
    'F032-002',
    'F032-003',
    'F033-001',
    'F034-001',
    'F035-001',
    'F035-003',
    'F036-001',
    'F036-002',
    'F037-001',
    'F038-001',
    'F038-002',
    'F038-003',
    'F049-004',
    'F050-001',
    'F050-002',
    'F052-003',
    'F065-002',
    'F067-001',
    'F067-003',
    'F068-001',
    'F068-002',
    'F068-004',
    'F069-001',
    'F069-002',
    'F069-003',
    'F069-004',
    'F069-005',
    'F070-001',
    'F070-002',
    'F070-004',
    'F071-001',
    'F071-003',
})

DELIVERY_FIXTURE_ABNORMAL_CASES = frozenset({
    'F010-005',
    'F020-002',
    'F027-003',
    'F028-002',
    'F034-002',
    'F048-003',
    'F071-002',
    'F071-004',
    'F071-005',
})

def remote_exclusion_breakdown(
    suite='standard',
    *,
    include_upstream=False,
    include_delivery_fixture=False,
):
    """Return categorized case IDs excluded in remote-https mode."""
    if suite == 'standard':
        return {
            'hostCoupled': sorted(HOST_COUPLED_STANDARD_CASES),
            'deliveryFixture': [] if include_delivery_fixture else sorted(DELIVERY_FIXTURE_STANDARD_CASES),
            'upstreamCallback': [] if include_upstream else sorted(UPSTREAM_CALLBACK_STANDARD_CASES),
        }
    if suite == 'abnormal':
        return {
            'hostCoupled': sorted(HOST_COUPLED_ABNORMAL_CASES),
            'deliveryFixture': [] if include_delivery_fixture else sorted(DELIVERY_FIXTURE_ABNORMAL_CASES),
            'upstreamCallback': [] if include_upstream else sorted(UPSTREAM_CALLBACK_ABNORMAL_CASES),
        }
    raise ValueError(f'Unsupported suite for remote profile: {suite}')


def excluded_for_remote(
    suite='standard',
    *,
    include_upstream=False,
    include_delivery_fixture=False,
):
    """Return sorted case IDs to exclude in remote-https mode when host-coupled exclusion is active."""
    breakdown = remote_exclusion_breakdown(
        suite,
        include_upstream=include_upstream,
        include_delivery_fixture=include_delivery_fixture,
    )
    excluded = set()
    for ids in breakdown.values():
        excluded.update(ids)
    return sorted(excluded)
