import json
from unittest import mock
import pytest

import aetherscale.api.rest


@pytest.fixture
def client():
    with aetherscale.api.rest.app.test_client() as client:
        return client


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_list_vms(handler, client):
    handler.return_value.list_vms.return_value = [[]]
    rv = client.get('/vm')
    assert rv.json == []

    handler.return_value.list_vms.return_value = [[{'vm-id': 'abc123'}]]
    rv = client.get('/vm')
    assert len(rv.json) == 1


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_show_vm_info(handler, client):
    handler.return_value.vm_info.return_value = [{'vm-id': 'abc123'}]
    rv = client.get('/vm/abc123')
    assert rv.json['vm-id'] == 'abc123'


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_create_vm(handler, client):
    client.post(
        '/vm', data=json.dumps({'image': 'dummy-image'}),
        content_type='application/json')

    handler.return_value.create_vm.assert_called_with({'image': 'dummy-image'})


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_delete_vm(handler, client):
    client.delete('/vm/my-vm-id')
    handler.return_value.delete_vm.assert_called_with({'vm-id': 'my-vm-id'})


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_start_vm(handler, client):
    handler.return_value.start_vm.return_value = [[
        {'vm-id': 'my-vm-id', 'status': 'started'},
    ]]

    client.patch(
        '/vm/my-vm-id', data=json.dumps({'status': 'started'}),
        content_type='application/json')

    handler.return_value.start_vm.assert_called_with({'vm-id': 'my-vm-id'})

    # missing message must lead to error
    rv = client.patch('/vm/my-vm-id', content_type='application/json')
    assert rv.status_code == 400

    # wrong content type must result in an 415 UNSUPPORTED MEDIA TYPE
    rv = client.patch('/vm/my-vm-id')
    assert rv.status_code == 415


@mock.patch('aetherscale.api.rest.ComputingHandler')
def test_stop_vm(handler, client):
    handler.return_value.stop_vm.return_value = [[
        {'vm-id': 'my-vm-id', 'status': 'stopped'},
    ]]

    client.patch(
        '/vm/my-vm-id', data=json.dumps({'status': 'stopped'}),
        content_type='application/json')

    handler.return_value.stop_vm.assert_called_with({'vm-id': 'my-vm-id'})

    # missing message must lead to error
    rv = client.patch('/vm/my-vm-id', content_type='application/json')
    assert rv.status_code == 400

    # wrong content type must result in an 415 UNSUPPORTED MEDIA TYPE
    rv = client.patch('/vm/my-vm-id')
    assert rv.status_code == 415
