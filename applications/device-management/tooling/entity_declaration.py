#!/usr/bin/env python3
"""Prepare a versioned complete entity update offline; never write a live API."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import re

# EntityDefinitionParam embeds remote.Object. Keep all schema declarations,
# including non-unique indexes; query-only workflow/read fields stay excluded.
DECLARATION_KEYS = frozenset((
    'name', 'showName', 'icon', 'pkgPath', 'description', 'fields',
    'uniqueConstraints', 'indexes', 'writeRules', 'blockInfo', 'serviceExpose',
    'uiMeta', 'version',
))
VIEW_KEYS = DECLARATION_KEYS | {'id', 'application', 'createTime', 'updateTime'}


def value(document):
    if not isinstance(document, dict):
        raise ValueError('expected an object')
    if 'error' in document:
        if document['error'] is not None:
            raise ValueError('owner read did not succeed')
        document = document.get('value')
    if not isinstance(document, dict):
        raise ValueError('owner returned no object')
    return document


def positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError('current positive owner identity/version required')
    return value


def prepare(entity_document, application_document, changes):
    entity, application = value(entity_document), value(application_document)
    if set(entity) - VIEW_KEYS:
        raise ValueError('unrecognized entity view fields; review the owner contract before updating')
    if not isinstance(changes, dict) or set(changes) - DECLARATION_KEYS:
        raise ValueError('patch contains identity, workflow or unknown fields')
    eid, aid = positive(entity.get('id')), positive(application.get('id'))
    if not isinstance(entity.get('application'), dict) or entity['application'].get('id') != aid:
        raise ValueError('entity and application identities differ')
    if not isinstance(entity.get('fields'), list) or not entity['fields']:
        raise ValueError('complete current entity fields required')
    declaration = {key: deepcopy(entity[key]) for key in DECLARATION_KEYS if key in entity}
    declaration.update(deepcopy(changes))
    return dict(declaration, id=eid, application={'id': aid},
                expectedEntityVersion=positive(entity.get('updateTime')),
                expectedDefinitionVersion=positive(application.get('updateTime')))


def verify(request, entity_document):
    actual = value(entity_document)
    if set(actual) - VIEW_KEYS or actual.get('id') != request.get('id') or actual.get('application', {}).get('id') != request.get('application', {}).get('id'):
        raise ValueError('readback identity or contract differs')
    for key in DECLARATION_KEYS:
        # Omitted optional empty declarations and JSON null are equivalent,
        # but no list member, index, field or binding can silently disappear.
        if actual.get(key) != request.get(key):
            raise ValueError('declaration readback differs: ' + key)
    if positive(actual.get('updateTime')) <= request['expectedEntityVersion']:
        raise ValueError('readback does not confirm a newer owner version')
    return True


def restore_index(entity_document, application_document, index):
    """Merge one historical index; never replace a newer index collection."""
    entity = value(entity_document)
    if not isinstance(index, dict) or set(index) != {'name', 'fields'}:
        raise ValueError('one complete non-unique index declaration required')
    name, fields = index['name'], index['fields']
    identifier = lambda text: isinstance(text, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', text)
    if not identifier(name) or not isinstance(fields, list) or not fields or not all(identifier(x) for x in fields) or len(set(fields)) != len(fields):
        raise ValueError('index identifiers are invalid or duplicated')
    known = {field.get('name') for field in entity.get('fields', []) if isinstance(field, dict)}
    if not set(fields) <= known:
        raise ValueError('index references unavailable fields')
    indexes = deepcopy(entity.get('indexes') or [])
    if not isinstance(indexes, list) or any(not isinstance(item, dict) for item in indexes):
        raise ValueError('current index collection is invalid')
    same = [item for item in indexes if item.get('name') == name]
    if len(same) > 1 or same and same[0] != index:
        raise ValueError('current index with that name conflicts; review instead of overwriting')
    if not same:
        indexes.append(deepcopy(index))
    return prepare(entity_document, application_document, {'indexes': indexes})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entity', type=Path, required=True)
    parser.add_argument('--application', type=Path, required=True)
    changes = parser.add_mutually_exclusive_group(required=True)
    changes.add_argument('--patch', type=Path)
    changes.add_argument('--restore-index', type=Path, help='merge one index without replacing newer indexes')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    builder = restore_index if args.restore_index else prepare
    request = builder(json.loads(args.entity.read_text()), json.loads(args.application.read_text()),
                      json.loads((args.restore_index or args.patch).read_text()))
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(request, output, ensure_ascii=False, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
