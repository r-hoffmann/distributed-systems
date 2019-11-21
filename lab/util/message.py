import json


# Status Codes
ALIVE = 200
REGISTER = 201
META_DATA = 202


def write(status: int, body: dict or list):
    return json.dumps({'status': status, 'body': body}).encode()


def write_alive(worker_id: int):
    return write(
        status=ALIVE,
        body={
            'worker_id': worker_id
        }
    )


def write_register(worker_id: int, host: str, port: int):
    return write(
        status=REGISTER,
        body={
            'worker_id': worker_id,
            'host': host,
            'port': port
        }
    )


def write_meta_data(meta_data: list):
    return write(status=META_DATA, body=meta_data)


def read(message: bytes):
    content = json.loads(message.decode())

    return MESSAGE_INTERFACE[content['status']](content['body'])


def read_register(body: dict):
    return REGISTER, body['worker_id'], body['host'], body['port']


def read_alive(body: dict):
    return ALIVE, body['worker_id']


def read_meta_data(body: list):
    return META_DATA, body


MESSAGE_INTERFACE = {
    ALIVE: read_alive,
    REGISTER: read_register,
    META_DATA: read_meta_data
}
