from multiprocessing import Process, Queue
import time

from lab.util import sockets, message
from lab.util.meta_data import MetaData, CombinedMetaData
from lab.util.server import Server


class Node:
    """ Worker node representing a process that may communicate with master and
    other workers, superclass for the actual workers.
    """

    def __init__(self, worker_id: int, master_host: str, master_port: int):
        self.worker_id = worker_id
        self.master_host = master_host
        self.master_port = master_port

    def send_message_to_master(self, message_to_send: bytes):
        """
        Sends a message to the master
        """
        for i in range(1000):
            try:
                sockets.send_message(
                    self.master_host, self.master_port, message_to_send)
                return
            except ConnectionResetError:
                # Possibly:  [Errno 54] Connection reset by peer
                # Try again until success
                pass
            except Exception as e:
                print('Send msg to master error \n\t', e)

        raise Exception(
            f'Failed to connect to master. worker_id: {self.worker_id}')

    @staticmethod
    def send_message_to_node(host, port, message_to_send: bytes):
        sockets.send_message(host, port, message_to_send)


class HearbeatDaemon(Node):
    """ Daemon process that periodically pings Master to indicate the
    corresponding worker is alive.
    """

    def __init__(self, worker_id: int, master_host: str, master_port: int,
                 wait_time: float):
        super().__init__(worker_id, master_host, master_port)

        # TODO this prevents `BrokenPipeError: [Errno 32] Broken pipe` raised by s.send() in util.sockets.send_message
        # time.sleep(0.1)
        while True:
            self.send_message_to_master(message.write_alive(self.worker_id))
            time.sleep(wait_time)


class WorkerInterface(Node):
    """ Actually an abstract base class
    """

    def __init__(self, worker_id: int, master_host: str, master_port: int,
                 graph_path: str):
        super().__init__(worker_id, master_host, master_port)
        self.graph_path = graph_path

        # Create queue
        self.server_queue = Queue()

        # Start server with queue
        server = Process(target=Server, args=(self.server_queue,))
        server.start()

        # Wait for server to send its hostname and port
        self.hostname, self.port = self.server_queue.get()

        # Register self at master
        self.register()

        # Wait for the meta data of the other workers
        self.combined_meta_data: CombinedMetaData = self.receive_meta_data()

        self.init_hearbeat_daemon(wait_time=1)

    def run(self):
        raise NotImplementedError()

    def get_message_from_queue(self) -> [str]:
        """
        :return: List of the elements of the data in the queue
        """
        return message.read(self.server_queue.get())

    def receive_meta_data(self) -> CombinedMetaData:
        status, all_meta_data = self.get_message_from_queue()

        return CombinedMetaData([
            MetaData(
                worker_id=meta_data['worker_id'],
                number_of_edges=meta_data['number_of_edges'],
                min_vertex=meta_data['min_vertex'],
                max_vertex=meta_data['max_vertex'],
                host=meta_data['host'],
                port=meta_data['port']
            )
            for meta_data in all_meta_data
        ])

    def register(self):
        """
        Sends a REGISTER request to the master
        """

        self.send_message_to_master(message.write_register(
            self.worker_id,
            self.hostname,
            self.port
        ))

    def send_job_complete(self):
        """ Sends a JOB_COMPLETE to master. Override if additional information
        is required.
        """
        self.send_message_to_master(message.write_job_complete(self.worker_id))

    def send_debug_message(self, debug_message: str):
        self.send_message_to_master(message.write_debug(
            self.worker_id,
            debug_message
        ))

    def init_hearbeat_daemon(self, wait_time=1):
        self.hearbeat_daemon = Process(target=HearbeatDaemon, args=(
            self.worker_id, self.master_host, self.master_port, wait_time))
        self.hearbeat_daemon.start()

    def message_in_queue(self) -> bool:
        """
        :return: Boolean whether there are any messages in the queue
        """

        return not self.server_queue.empty()