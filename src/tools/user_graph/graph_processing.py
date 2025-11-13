"""Graph processing pipeline for exported MongoDB user records."""
from __future__ import annotations

import json
import os
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import ijson

ProgressCallback = Optional[Callable[[str], None]]


@dataclass
class GraphEdge:
    source: str
    target: str
    weight: int

    def to_dict(self) -> Dict[str, object]:
        return {"source": self.source, "target": self.target, "weight": self.weight}


@dataclass
class GraphNode:
    id: str
    account_id: str
    label: str
    node_size: int
    shared_callsign_count: int
    shared_callsigns: List[str]
    online: bool
    last_online: Optional[str]
    metadata: Dict[str, object] = field(default_factory=dict)
    color: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        payload = {
            "id": self.id,
            "accountId": self.account_id,
            "label": self.label,
            "nodeSize": self.node_size,
            "sharedCallsignCount": self.shared_callsign_count,
            "sharedCallsigns": self.shared_callsigns,
            "online": self.online,
            "lastOnline": self.last_online,
        }
        payload.update(self.metadata)
        if self.color:
            payload["color"] = self.color
        if "degree" not in payload:
            payload["degree"] = 0
        return payload


@dataclass
class GraphComponent:
    component_id: str
    color: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]

    def summary(self) -> Dict[str, object]:
        return {
            "id": self.component_id,
            "nodeCount": len(self.nodes),
            "edgeCount": len(self.edges),
            "color": self.color,
        }

    def payload(self, limit: Optional[int] = None) -> Dict[str, object]:
        if not limit or limit >= len(self.nodes):
            nodes = [node.to_dict() for node in self.nodes]
            node_ids = {node.id for node in self.nodes}
        else:
            sorted_nodes = sorted(
                self.nodes,
                key=lambda n: (n.shared_callsign_count, n.node_size),
                reverse=True,
            )
            limited_nodes = sorted_nodes[:limit]
            node_ids = {node.id for node in limited_nodes}
            nodes = [node.to_dict() for node in limited_nodes]
        edges = [edge.to_dict() for edge in self.edges if edge.source in node_ids and edge.target in node_ids]
        return {
            "componentId": self.component_id,
            "nodes": nodes,
            "edges": edges,
            "color": self.color,
            "nodeCount": len(self.nodes),
            "edgeCount": len(self.edges),
        }


@dataclass
class GraphBuildResult:
    components: Dict[str, GraphComponent]
    total_nodes: int
    total_edges: int

    def summary(self) -> List[Dict[str, object]]:
        return sorted(
            (component.summary() for component in self.components.values()),
            key=lambda entry: entry["nodeCount"],
            reverse=True,
        )


def _iter_users(file_path: Path) -> Iterable[Dict[str, object]]:
    with file_path.open("rb") as handle:
        for user in ijson.items(handle, "item"):
            if user:
                yield user


def _safe_account_id(user: Dict[str, object]) -> str:
    account_id = user.get("accountID")
    if account_id is not None:
        return str(account_id)
    nested_id = user.get("_id")
    if isinstance(nested_id, dict) and "$oid" in nested_id:
        return str(nested_id["$oid"])
    return str(uuid.uuid4())


def _normalize_callsigns(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    normalized = []
    seen = set()
    for value in values:
        if not value:
            continue
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _call_counts(file_path: Path, progress_cb: ProgressCallback = None) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    processed = 0
    for user in _iter_users(file_path):
        processed += 1
        if progress_cb and processed % 1000 == 0:
            progress_cb(f"Scanning callsigns: {processed:,} users")
        for callsign in _normalize_callsigns(user.get("pastCallsigns")):
            counts[callsign] += 1
    if progress_cb:
        progress_cb(f"Finished scanning {processed:,} users for callsigns")
    return counts


def _random_color(seed: str) -> str:
    numeric_seed = abs(hash(seed)) % (2 ** 32)
    r = (numeric_seed & 0xFF0000) >> 16
    g = (numeric_seed & 0x00FF00) >> 8
    b = numeric_seed & 0x0000FF
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_components(nodes: Dict[str, GraphNode], edges: List[GraphEdge]) -> GraphBuildResult:
    parent: Dict[str, str] = {node_id: node_id for node_id in nodes.keys()}
    rank: Dict[str, int] = {node_id: 0 for node_id in nodes.keys()}

    def find(node_id: str) -> str:
        root = node_id
        while parent[root] != root:
            root = parent[root]
        while parent[node_id] != node_id:
            next_id = parent[node_id]
            parent[node_id] = root
            node_id = next_id
        return root

    def union(a: str, b: str) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        if rank[root_a] < rank[root_b]:
            parent[root_a] = root_b
        elif rank[root_a] > rank[root_b]:
            parent[root_b] = root_a
        else:
            parent[root_b] = root_a
            rank[root_a] += 1

    for edge in edges:
        union(edge.source, edge.target)

    components: Dict[str, GraphComponent] = {}
    for node_id, node in nodes.items():
        root = find(node_id)
        if root not in components:
            components[root] = GraphComponent(component_id=root, color=_random_color(root), nodes=[], edges=[])
        node.color = components[root].color
        components[root].nodes.append(node)

    for edge in edges:
        root = find(edge.source)
        components[root].edges.append(edge)

    total_edges = len(edges)
    total_nodes = len(nodes)
    return GraphBuildResult(components=components, total_edges=total_edges, total_nodes=total_nodes)


def build_graph_from_export(
    file_path: Path,
    *,
    progress_cb: ProgressCallback = None,
) -> GraphBuildResult:
    if progress_cb:
        progress_cb("Starting first pass to count callsigns")
    counts = _call_counts(file_path, progress_cb=progress_cb)

    nodes: Dict[str, GraphNode] = {}
    call_clusters: Dict[str, List[str]] = defaultdict(list)
    processed = 0
    kept = 0
    if progress_cb:
        progress_cb("Starting second pass to build nodes")
    for user in _iter_users(file_path):
        processed += 1
        if progress_cb and processed % 1000 == 0:
            progress_cb(f"Evaluated {processed:,} users; retained {kept:,}")
        callsigns = _normalize_callsigns(user.get("pastCallsigns"))
        shared = [call for call in callsigns if counts.get(call, 0) > 1]
        if not shared:
            continue
        account_id = _safe_account_id(user)
        node = GraphNode(
            id=account_id,
            account_id=account_id,
            label=str(user.get("currentCallsign") or user.get("accountID") or account_id),
            node_size=max(len(callsigns), 1),
            shared_callsign_count=len(shared),
            shared_callsigns=shared,
            online=bool(user.get("Online")),
            last_online=(user.get("lastOnline") or {}).get("$date") if isinstance(user.get("lastOnline"), dict) else user.get("lastOnline"),
            metadata={
                "currentAircraft": user.get("currentAircraft"),
            },
        )
        nodes[account_id] = node
        kept += 1
        for callsign in shared:
            call_clusters[callsign].append(account_id)
    if progress_cb:
        progress_cb(f"Second pass complete; retained {kept:,} linked accounts")

    edge_weights: Dict[Tuple[str, str], int] = defaultdict(int)
    if progress_cb:
        progress_cb("Generating edges from shared callsigns")
    for callsign, accounts in call_clusters.items():
        unique_accounts = list(dict.fromkeys(accounts))
        count = len(unique_accounts)
        if count < 2:
            continue
        for i in range(count):
            source = unique_accounts[i]
            for j in range(i + 1, count):
                target = unique_accounts[j]
                key = (source, target) if source < target else (target, source)
                edge_weights[key] += 1
        if progress_cb and len(edge_weights) % 5000 == 0:
            progress_cb(f"Constructed {len(edge_weights):,} edges so far")

    edges: List[GraphEdge] = [GraphEdge(source=src, target=dst, weight=weight) for (src, dst), weight in edge_weights.items()]
    if progress_cb:
        progress_cb(f"Created {len(edges):,} weighted edges")

    # Degree calculation
    degree: Dict[str, int] = defaultdict(int)
    for edge in edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
    for node_id, node in nodes.items():
        node.metadata["degree"] = degree.get(node_id, 0)

    result = _build_components(nodes, edges)
    if progress_cb:
        progress_cb("Graph build complete")
    return result


class GraphProcessingService:
    """Manages background jobs that build graphs from large exports."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, object]] = {}
        self._graphs: Dict[str, GraphBuildResult] = {}

    def _update_status(self, job_id: str, **updates: object) -> None:
        with self._lock:
            self._jobs.setdefault(job_id, {}).update(updates)

    def start_job(self, file_path: Path) -> str:
        job_id = uuid.uuid4().hex
        self._update_status(job_id, status="queued", message="Waiting for processing", filePath=str(file_path))

        def progress(message: str) -> None:
            self._update_status(job_id, status="processing", message=message)

        def worker() -> None:
            try:
                graph = build_graph_from_export(file_path, progress_cb=progress)
                with self._lock:
                    self._graphs[job_id] = graph
                    self._jobs[job_id].update(
                        status="ready",
                        message="Graph ready",
                        summary=graph.summary(),
                        totals={"nodes": graph.total_nodes, "edges": graph.total_edges},
                    )
            except Exception as exc:  # pylint: disable=broad-except
                self._update_status(job_id, status="error", message=str(exc))
            finally:
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        thread = threading.Thread(target=worker, name=f"graph-job-{job_id}")
        thread.daemon = True
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_component(self, job_id: str, component_id: str, limit: Optional[int] = None) -> Optional[Dict[str, object]]:
        with self._lock:
            graph = self._graphs.get(job_id)
        if not graph:
            return None
        component = graph.components.get(component_id)
        if not component:
            return None
        return component.payload(limit)

    def drop_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            self._graphs.pop(job_id, None)


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a callsign graph from a MongoDB export")
    parser.add_argument("input", type=Path, help="Path to the MongoDB JSON export")
    parser.add_argument("--summary", type=Path, default=None, help="Optional path to write the summary JSON")
    args = parser.parse_args()

    result = build_graph_from_export(args.input, progress_cb=lambda msg: print(msg))
    print(f"Built graph with {result.total_nodes:,} nodes and {result.total_edges:,} edges")
    if args.summary:
        with args.summary.open("w", encoding="utf-8") as handle:
            json.dump(result.summary(), handle, indent=2)
        print(f"Wrote summary to {args.summary}")


if __name__ == "__main__":
    _cli()
