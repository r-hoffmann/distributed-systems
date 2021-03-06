import subprocess
from typing import TextIO
from math import floor
import pandas as pd


def get_number_of_lines(path: str) -> int:
    """
    Uses the bash wc command to count the number of lines in the file

    :param path: Path to the file
    :return: Number of lines in the file
    """

    out = subprocess.Popen(['wc', '-l', path],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT
                           ).communicate()[0]
    return int(out.strip(b' ').partition(b' ')[0])


def read_n_lines(f: TextIO, n: int) -> [str]:
    """
    Reads n lines into a list

    :param f: File to read from
    :param n: Number of lines to read
    :return: List of n lines
    """

    return [next(f) for _ in range(n)]


def get_first_line(path: str):
    return subprocess.check_output(['head', '-1', path]).decode()


def get_last_line(path: str):
    return subprocess.check_output(['tail', '-1', path]).decode()


def get_start_vertex(edge: str) -> int or None:
    """
    Retrieves the start vertex of an edge

    :param edge: Edge to get the start vertex from. Has the form "start_vertex end_vertex"
    :return: Start vertex
    """

    try:
        return int(edge.split(" ")[0])
    except IndexError:
        return None


def reverse_edge(edge: str):
    return " ".join(reversed(edge.rstrip().split(" "))) + "\n"


def read_rest_of_edges(f: TextIO, start_vertex: str):
    """
    Reads in the rest of the edges that have the same start vertex
    :param f: File to read from
    :param start_vertex: Start vertex to look out for
    :return: Next start edge, rest of edges with the same start vertex as `start_vertex`
    """

    rest_of_edges = []
    while True:
        current_edge = next(f)

        # EOF
        if not current_edge:
            return None, rest_of_edges

        # Return if new start vertex has been found
        if get_start_vertex(current_edge) != start_vertex:
            return current_edge, rest_of_edges

        rest_of_edges.append(current_edge)


def count_vertices(path: str):
    counts = {}

    f = open(path, "r")
    for line in f:
        vertex1, vertex2 = parse_to_edge(line)

        try:
            counts[vertex1] += 1
        except KeyError:
            counts[vertex1] = 1

        try:
            counts[vertex2] += 1
        except KeyError:
            counts[vertex2] = 1
    f.close()

    return counts


def read_in_chunks(f: TextIO, n_workers: int) -> [str]:
    """
    Generator that divides a file into n_workers parts, where each part contains all the edges from each start vertex

    :param f: File to read from
    :param n_workers: Number of parts to divide the files in
    :return: List of lines
    """
    vertex_counts = count_vertices(f.name)
    number_of_lines = get_number_of_lines(f.name)

    chunk_size = int(floor(number_of_lines * 2 / n_workers))

    edges = []
    lines_read = 0
    for i in range(n_workers):
        if len(edges) > 0:
            last_start_vertex = get_start_vertex(edges[-1])
            number_of_vertices = vertex_counts[last_start_vertex]
        else:
            number_of_vertices = 0
            last_start_vertex = None

        while True:
            try:
                edge = next(f)
            except StopIteration:
                yield edges
                return

            edges.append(edge)

            start_vertex = get_start_vertex(edge)

            if start_vertex != last_start_vertex:
                if i < n_workers - 1 and number_of_vertices + vertex_counts[start_vertex] >= chunk_size:
                    yield edges
                    edges = [edge]
                    break

                number_of_vertices += vertex_counts[start_vertex]
                last_start_vertex = start_vertex

            lines_read += 1


def read_as_reversed_edges(f: TextIO):
    for edge in f:
        yield reverse_edge(edge)


def append_edge(path: str, edge: str):
    f = open(path, "a")
    f.write(edge)
    f.close()


def read_file(path):
    f = open(path, "r")
    lines = f.readlines()
    f.close()

    return lines


def parse_to_edge(line):
    edge = line.rstrip().split(" ")

    return [int(edge[0]), int(edge[1])]


def to_int_edge_list(data) -> [[int, int]]:
    edges = []

    for line in data:
        edges.append(parse_to_edge(line))

    return edges


def write_to_file(path, data):
    f = open(path, "w")
    f.writelines(data)
    f.close()


def append_to_file(path, data):
    f = open(path, "a")
    f.writelines(data)
    f.close()


def sort_file(path):
    edges = pd.DataFrame(to_int_edge_list(read_file(path)), columns=['start', 'end'])
    edges = edges.sort_values(['start', 'end'])
    edges.to_csv(path, sep=" ", header=False, index=False)

