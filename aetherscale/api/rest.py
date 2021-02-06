import flask
from pathlib import Path

from aetherscale.computing import ComputingHandler
from aetherscale import services


app = flask.Flask(__name__)


@app.before_request
def initialize_handler():
    systemd_path = Path.home() / '.config/systemd/user'
    service_manager = services.SystemdServiceManager(systemd_path)
    handler = ComputingHandler(radvd=None, service_manager=service_manager)
    flask.g.handler = handler


@app.route('/vm', methods=['GET'])
def list_vms():
    handler: ComputingHandler = flask.g.handler
    result = list(handler.list_vms({}))[0]

    return flask.jsonify(result)


@app.route('/vm/<vm_id>', methods=['GET'])
def vm_info(vm_id):
    handler: ComputingHandler = flask.g.handler

    try:
        result = list(handler.vm_info({'vm-id': vm_id}))[0]
    except RuntimeError:
        return 'VM does not exist', 404

    return flask.jsonify(result)


@app.route('/vm', methods=['POST'])
def create_vm():
    options = flask.request.json
    handler: ComputingHandler = flask.g.handler
    results = list(handler.create_vm(options))

    # return the final status
    return flask.jsonify(results[-1])


@app.route('/vm/<vm_id>', methods=['PATCH'])
def update_vm_status(vm_id):
    data = flask.request.json

    if not data or 'status' not in data:
        return '"status" field in data missing', 400

    handler: ComputingHandler = flask.g.handler

    if data['status'] == 'started':
        result = list(handler.start_vm({'vm-id': vm_id}))[0]
    elif data['status'] == 'stopped':
        result = list(handler.stop_vm({'vm-id': vm_id}))[0]
    else:
        return 'invalid value for "status"', 400

    # return the final status
    return flask.jsonify(result)


@app.route('/vm/<vm_id>', methods=['DELETE'])
def delete_vm(vm_id):
    handler: ComputingHandler = flask.g.handler
    result = list(handler.delete_vm({'vm-id': vm_id}))[0]

    return flask.jsonify(result)


@app.route('/vpn', methods=['GET'])
def list_vpns():
    handler: ComputingHandler = flask.g.handler
    result = list(handler.list_vpns({}))[0]

    return flask.jsonify(result)


@app.route('/vpn/<vpn_name>', methods=['GET'])
def vpn_info(vpn_name):
    handler: ComputingHandler = flask.g.handler
    try:
        result = list(handler.vpn_info({'vpn-name': vpn_name}))[0]
    except KeyError:
        return 'VPN does not exist', 404

    return flask.jsonify(result)
