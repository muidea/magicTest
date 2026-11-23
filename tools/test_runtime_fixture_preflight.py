import copy
import time
import unittest

import runtime_fixture_preflight as subject


class RuntimeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fingerprint = 'sha256:' + 'f' * 64
        self.fixture = {'namespace': 't001', 'installationId': 1, 'deploymentId': 'a'*32, 'applicationUuid': 'b'*32,
                        'applicationName': 'accept-model', 'sourceDigest': 'sha256:'+'c'*64, 'expectedVersion': 1,
                        'status': 'running', 'purpose': 'acceptance', 'allowedActions': ['read', 'uninstall'], 'cleanup': 'owner API uninstall'}
        self.runtime = {'instanceId': 'accept-base', 'incarnation': 'boot', 'purpose': 'acceptance', 'containerId': 'd'*64,
                        'providerDeploymentId': 'e'*32, 'providerApplicationUuid': 'f'*32,
                        'startup': {'apiVersion': 'magic.runtime-instance/v1', 'instanceId': 'accept-base', 'incarnation': 'boot', 'kind': 'base',
                                    'namespaceScope': 't001', 'bootstrapApplications': []}}
        self.manifest = {'schema': 'magic.acceptance.fixtures/v1', 'environmentFingerprint': self.fingerprint, 'fixtures': [self.fixture], 'runtimes': [self.runtime]}
        self.inventory = {'environmentFingerprint': self.fingerprint, 'capturedAt': int(time.time()), 'complete': True,
                          'assignments': [{**self.fixture, 'executionInstanceId': 'accept-base', 'incarnation': 'boot',
                                           'gatewayInstanceId': 'accept-gateway', 'gatewayIncarnation': 'gateway-boot', 'desiredState': 'running'}]}
        self.containers = {'d'*64: {'Id': 'd'*64, 'Name': '/native-test-base', 'Image': 'sha256:'+'a'*64, 'State': {'Running': True},
                                  '_acceptanceStartup': copy.deepcopy(self.runtime['startup']),
                                  'Config': {'Env': ['SECRET=never-export'], 'Labels': {'io.platform.deployment-id': 'e'*32, 'io.platform.runtime.application-uuid': 'f'*32}}}}

    def test_isolated_owner_is_read_only_and_does_not_export_secrets(self):
        result = subject.verify_runtime_owners(self.manifest, self.inventory, self.containers)
        self.assertTrue(result['isolationVerified'])
        self.assertFalse(result['livePassed'])
        self.assertNotIn('SECRET', str(result))

    def test_shared_or_replaced_owner_is_rejected(self):
        faults = ['demo', 'incomplete', 'stale', 'bootstrap', 'global', 'incarnation', 'container', 'label']
        for fault in faults:
            with self.subTest(fault=fault):
                manifest, inventory, containers = copy.deepcopy((self.manifest, self.inventory, self.containers))
                if fault == 'demo': inventory['assignments'][0]['deploymentId'] = '0'*32
                if fault == 'incomplete': inventory['complete'] = False
                if fault == 'stale': inventory['capturedAt'] -= 61
                if fault == 'bootstrap': manifest['runtimes'][0]['startup']['bootstrapApplications'] = ['magicPanel']
                if fault == 'global': manifest['runtimes'][0]['startup']['namespaceScope'] = '*'
                if fault == 'incarnation': inventory['assignments'][0]['incarnation'] = 'replacement'
                if fault == 'container': containers['d'*64]['Name'] = '/magicbase'
                if fault == 'label': containers['d'*64]['Config']['Labels']['io.platform.deployment-id'] = '0'*32
                with self.assertRaises(ValueError): subject.verify_runtime_owners(manifest, inventory, containers)


    def test_uninstall_checkpoint_requires_original_instance_and_drain(self):
        assignment = dict(self.inventory['assignments'][0], runtimeApplicationUuid='7'*32, revisionDigest='8'*64,
                          planDigest='9'*64, generation=2, executionEpoch=1, executionGrantId='grant', desiredState='revoked',
                          gatewayAppliedGeneration=2, gatewayAppliedSnapshotVersion=3, gatewayAppliedAt=int(time.time()*1000), gatewayAppliedTargetAddress='')
        observed = dict(assignment, state='stopped', baseInstanceId=assignment['executionInstanceId'], baseIncarnation=assignment['incarnation'], targetAddress='', observedAt=1)
        installation = {'id': 1, 'namespace': 't001', 'deploymentId': 'a'*32, 'applicationUuid': 'b'*32,
                        'sourceDigest': 'sha256:'+'c'*64, 'runtimeType': 'model-driven', 'status': 'uninstallFailed', 'operationId': 'original',
                        'receipt': {'runtimeApplicationUuid': '7'*32, 'uninstallation': {'startedAt':1,'dataDisposition':'retain'}}}
        checkpoint = {'schema':'magic.acceptance.uninstall-checkpoint/v1', 'environmentFingerprint':self.fingerprint,
                      'installation':installation, 'assignment':assignment, 'runtimeReceipt':observed}
        result=subject.verify_uninstall_checkpoint(self.manifest, checkpoint)
        self.assertTrue(result['checkpointVerified'])
        self.assertFalse(result['livePassed'])
        for disposition in ('retain', 'destroy'):
            with self.subTest(dataDisposition=disposition):
                valid = copy.deepcopy(checkpoint)
                valid['installation']['receipt']['uninstallation']['dataDisposition'] = disposition
                result = subject.verify_uninstall_checkpoint(self.manifest, valid)
                self.assertTrue(result['checkpointVerified'])
                self.assertFalse(result['livePassed'])
        invalid = copy.deepcopy(checkpoint)
        invalid['installation']['receipt']['uninstallation']['dataDisposition'] = 'delete'
        with self.assertRaises(ValueError):
            subject.verify_uninstall_checkpoint(self.manifest, invalid)
        for mode in ('normal', 'complete', 'different-instance', 'epoch', 'route-present', 'missing-receipt', 'different-candidate'):
            with self.subTest(mode=mode):
                bad=copy.deepcopy(checkpoint)
                if mode=='normal': bad['installation']['status']='running'
                if mode=='complete': bad['installation']['receipt']['uninstallation']['finishedAt']=2
                if mode=='different-instance': bad['installation']['deploymentId']='0'*32
                if mode=='epoch': bad['runtimeReceipt']['executionEpoch']=2
                if mode=='route-present': bad['assignment']['gatewayAppliedTargetAddress']='http://base:8080'
                if mode=='missing-receipt': bad['runtimeReceipt']={}
                if mode=='different-candidate': bad['environmentFingerprint']='sha256:'+'0'*64
                with self.assertRaises(ValueError): subject.verify_uninstall_checkpoint(self.manifest,bad)


if __name__ == '__main__': unittest.main()
