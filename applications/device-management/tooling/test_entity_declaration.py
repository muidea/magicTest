from copy import deepcopy
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_workspace_root
from entity_declaration import DECLARATION_KEYS, prepare, verify, restore_index


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.entity = {'id': 9, 'name': 'measurement', 'pkgPath': '/sample',
                       'fields': [{'name': 'id'}], 'indexes': [{'name': 'ix_sampled', 'fields': ['sampledAt']}],
                       'uniqueConstraints': [{'name': 'uq_sample', 'fields': ['device', 'sampledAt']}],
                       'blockInfo': [{'key': 'derived', 'nested': {'maxRecords': 3}}],
                       'writeRules': {'appendOnly': True}, 'serviceExpose': {},
                       'application': {'id': 17}, 'updateTime': 41}
        self.application = {'id': 17, 'updateTime': 52}

    def test_preserves_whole_schema_and_binding_and_verifies_readback(self):
        request = prepare(self.entity, self.application, {'indexes': [{'name': 'ix_other', 'fields': ['id']}]})
        self.assertEqual(request['blockInfo'], self.entity['blockInfo'])
        self.assertEqual(request['uniqueConstraints'], self.entity['uniqueConstraints'])
        self.assertEqual(request['expectedEntityVersion'], 41)
        self.assertEqual(request['expectedDefinitionVersion'], 52)
        self.assertNotIn('updateTime', request)
        after = deepcopy(self.entity)
        after.update(indexes=request['indexes'], updateTime=42)
        self.assertTrue(verify(request, after))
        del after['indexes']
        with self.assertRaises(ValueError): verify(request, after)
        self.assertEqual(self.entity['indexes'][0]['name'], 'ix_sampled')

    def test_rejects_unknown_read_fields_and_workflow_patch(self):
        for key in ('phase', 'receipt', 'newSchemaDeclaration'):
            entity = dict(self.entity, **{key: 'x'})
            with self.assertRaises(ValueError): prepare(entity, self.application, {})
        for key in ('application', 'id', 'updateTime', 'expectedEntityVersion'):
            with self.assertRaises(ValueError): prepare(self.entity, self.application, {key: 1})
        with self.assertRaises(ValueError): prepare(self.entity, {'id': 18, 'updateTime': 52}, {})
        with self.assertRaises(ValueError): prepare(self.entity, {'id': 17}, {})

    def test_declaration_keys_cover_current_remote_object_contract(self):
        owner = resolve_workspace_root() / 'magicOrm/provider/remote/declarations.go'
        if not owner.is_file():
            self.skipTest('magicOrm source checkout not present')
        text = owner.read_text().split('type Object struct {', 1)[1].split('\n}', 1)[0]
        keys = set(re.findall(r'`json:"([^",]+)', text)) - {'-', 'id'}
        self.assertLessEqual(keys, DECLARATION_KEYS)

    def test_restore_one_index_preserves_newer_indexes_and_refuses_conflicts(self):
        self.entity['fields'].append({'name': 'sampledAt'})
        self.entity['indexes'] = [{'name': 'ix_new', 'fields': ['id']}]
        original = {'name': 'ix_sampled', 'fields': ['sampledAt']}
        request = restore_index(self.entity, self.application, original)
        self.assertEqual(request['indexes'], self.entity['indexes'] + [original])
        self.assertEqual(request['blockInfo'], self.entity['blockInfo'])
        self.assertEqual(request['uniqueConstraints'], self.entity['uniqueConstraints'])
        self.entity['indexes'] = request['indexes']
        self.assertEqual(restore_index(self.entity, self.application, original)['indexes'], request['indexes'])
        for bad in ({'name': 'ix_sampled', 'fields': ['id']},
                    {'name': 'ix_unknown', 'fields': ['absent']},
                    {'name': 'ix_unknown', 'fields': ['id', 'id']}):
            with self.assertRaises(ValueError): restore_index(self.entity, self.application, bad)


if __name__ == '__main__':
    unittest.main()
