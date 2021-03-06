from lab.master.WorkerInterface import WorkerInterface
from lab.util.distributed_graph import DistributedGraph, ForeignVertex, Vertex, Edge
from lab.downscaling.worker.RandomWalker import RandomWalker, ForeignVertexException
from numpy.random import randint, random
from numpy import array
from lab.util import message, file_io
from time import sleep, time


class Worker(WorkerInterface):
    def __init__(self, worker_id: int, master_host: str, master_port: int, scale: float, method: str, load_backup: bool, number_of_random_walkers: int, backup_size: int, walking_iterations: int):
        started_at = time()

        super().__init__(worker_id, master_host, master_port)

        self.message_interface = {
            message.META_DATA: self.handle_meta_data,
            message.RANDOM_WALKER: self.handle_random_walker,
            message.FINISH_JOB: self.handle_finish_job,
            message.WORKER_FAILED: self.handle_worker_failed,
            message.CONTINUE: self.handle_continue,
            message.START_SEND_FILE: self.handle_start_send_file,
            message.FILE_CHUNK: self.handle_file_chunk,
            message.END_SEND_FILE: self.handle_end_send_file,
            message.MISSING_CHUNK: self.handle_missing_chunk,
            message.RECEIVED_FILE: self.handle_received_file
        }

        self.running = False

        if backup_size == 0:
            self.backup_size = float("inf")
        else:
            self.backup_size = backup_size

        self.walking_iterations = walking_iterations

        self.number_of_random_walkers = number_of_random_walkers
        self.add_random_walker_at = []

        self.receive_graph()
        self.send_debug_message(
            f"Receiving graph took {time() - self.file_receivers[message.GRAPH].started_at}")
        setup_graph_started_at = time()

        if method == "random_edge":
            self.scale = scale
            self.edges = []
            for line in self.file_receivers[message.GRAPH].file:
                vertex1_label, vertex2_label = file_io.parse_to_edge(line)
                self.edges.append(
                    Edge(Vertex(vertex1_label), Vertex(vertex2_label)))
            self.edges = array(self.edges)
            self.send_debug_message(
                f"Setting up graph took {time() - setup_graph_started_at}")
            self.send_debug_message(f"Setup time: {time() - started_at}")
            self.wait_until_continue()
            self.run_random_edge()
        elif method == "random_walk":
            self.graph = DistributedGraph(
                worker_id, self.combined_meta_data, self.file_receivers[message.GRAPH].file)
            self.random_walkers = [
                RandomWalker(self.get_random_vertex()) for _ in range(number_of_random_walkers)
            ]
            self.send_debug_message(
                f"Setting up graph took {time() - setup_graph_started_at}")

            for vertex_label in self.add_random_walker_at:
                self.random_walkers.append(RandomWalker(
                    self.graph.vertices[vertex_label]))

            if load_backup:
                self.collected_edges = self.build_from_backup()
            else:
                self.collected_edges = {}

            self.send_debug_message(f"Setup time: {time() - started_at}")
            self.wait_until_continue()
            self.run_random_walk()

    def build_from_backup(self):
        while self.file_receivers[message.BACKUP] is None or not self.file_receivers[message.BACKUP].received_complete_file:
            self.handle_queue()
            sleep(0.1)

        collected_edges = {}

        for line in self.file_receivers[message.BACKUP].file:
            if line == '':
                continue

            collected_edges[line.strip()] = True

        return collected_edges

    def get_random_vertex(self):
        print(self.combined_meta_data[self.worker_id].max_vertex)
        while True:
            # generate vertex indices until a valid one is found (in case of missing vertices)
            try:
                return self.graph.vertices[
                    randint(
                        self.combined_meta_data[self.worker_id].min_vertex,
                        self.combined_meta_data[self.worker_id].max_vertex
                    )
                ]
            except KeyError:
                pass

    def handle_random_walker(self, vertex_label: int):
        # If worker is still being setup after crash and receives a message from another already running worker
        if not hasattr(self, 'random_walkers'):
            self.add_random_walker_at.append(vertex_label)
            return

        self.random_walkers.append(RandomWalker(
            self.graph.vertices[vertex_label]))

    def handle_continue(self):
        self.running = True

    def handle_worker_failed(self):
        self.running = False

        # If worker is still being setup after crash and receives a message from another already running worker
        if not hasattr(self, 'random_walkers'):
            number_of_random_walkers = self.number_of_random_walkers + \
                len(self.add_random_walker_at)
        else:
            number_of_random_walkers = len(self.random_walkers)

        self.send_message_to_master(message.write_random_walker_count(
            self.worker_id, number_of_random_walkers))
        self.wait_until_continue()

    def wait_until_continue(self):
        while not self.running:
            self.handle_queue()
            sleep(0.01)

    def send_random_walker_message(self, vertex: ForeignVertex):
        self.send_message_to_node(
            *self.combined_meta_data.get_connection_that_has_vertex(vertex.label),
            message.write_random_walker(vertex.label)
        )

    def run_random_edge(self):
        """
        Runs the worker
        """
        self.collected_edges = self.edges[random(len(self.edges)) < self.scale]
        self.send_backup_to_master(
            [str(edge) + '\n' for edge in self.collected_edges])
        self.send_job_complete()

    def run_random_walk(self):
        """
        Runs the worker
        """

        started_at = time()
        new_edges = []
        last_progress_message_at = 0

        while not self.cancel:
            self.handle_queue()

            for _ in range(self.walking_iterations):
                for random_walker in self.random_walkers:
                    try:
                        edge = random_walker.step()

                        if str(edge) not in self.collected_edges:
                            self.collected_edges[str(edge)] = True
                            new_edges.append(str(edge) + "\n")
                    except ForeignVertexException:
                        try:
                            self.send_random_walker_message(
                                random_walker.vertex)
                        except ConnectionRefusedError:
                            continue

                        self.random_walkers.remove(random_walker)

            # Make sure to not overload the master with progress messages
            if len(self.collected_edges) % 100 == 0 and last_progress_message_at != len(self.collected_edges):
                self.send_progress_message(len(self.collected_edges))
                last_progress_message_at = len(self.collected_edges)

            if len(new_edges) > self.backup_size:
                self.send_backup_to_master(new_edges)
                new_edges = []

        if len(new_edges) > 0:
            self.send_backup_to_master(new_edges)

        self.send_debug_message(f"Runtime: {time() - started_at}")
        self.send_job_complete()
