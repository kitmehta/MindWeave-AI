"""LightRAG instance management and graph utilities."""

import os
import re
import asyncio
import inspect
from typing import Optional

# Module-level caches
_rag_instances = {}       # key: storage_dir path → LightRAG instance
_initialized_instances = set()
_ingest_jobs = {}


def get_lightrag_instance(storage_dir: Optional[str] = None):
    """
    Return a cached LightRAG instance using local SentenceTransformer embeddings.

    Fixes:
    - "the first argument must be callable"
    - async embedding compatibility
    - singleton embedding model loading
    """

    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc
    from sentence_transformers import SentenceTransformer

    # ---------------------------------------------------
    # Default storage directory
    # ---------------------------------------------------
    if storage_dir is None:
        backend_dir = os.path.dirname(os.path.abspath(__file__))

        storage_dir = os.path.normpath(
            os.path.join(
                backend_dir,
                "..",
                "..",
                "data",
                "lightrag_storage",
            )
        )

    # ---------------------------------------------------
    # Return cached instance
    # ---------------------------------------------------
    if storage_dir in _rag_instances:
        return _rag_instances[storage_dir]

    # ---------------------------------------------------
    # Create storage directory if missing
    # ---------------------------------------------------
    os.makedirs(storage_dir, exist_ok=True)

    # ---------------------------------------------------
    # Load embedding model ONLY ONCE
    # ---------------------------------------------------
    global _embedding_model

    if "_embedding_model" not in globals():
        print("Loading SentenceTransformer model...")
        _embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

    # ---------------------------------------------------
    # IMPORTANT FIX:
    # LightRAG expects a REAL callable function
    # ---------------------------------------------------
    def local_embed(texts):
        """
        Synchronous embedding function for LightRAG.
        """

        if isinstance(texts, str):
            texts = [texts]

        embeddings = _embedding_model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        return embeddings.tolist()

    # ---------------------------------------------------
    # Extra safety wrapper
    # ---------------------------------------------------
    async def async_local_embed(texts):
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            None,
            local_embed,
            texts,
        )

    # ---------------------------------------------------
    # Verify callable
    # ---------------------------------------------------
    if not callable(async_local_embed):
        raise ValueError("Embedding function is NOT callable")

    # ---------------------------------------------------
    # Create LightRAG instance
    # ---------------------------------------------------
    rag = LightRAG(
        working_dir=storage_dir,
        embedding_func=EmbeddingFunc(
            embedding_dim=384,
            max_token_size=512,
            func=async_local_embed,
        ),
    )

    # ---------------------------------------------------
    # Cache instance
    # ---------------------------------------------------
    _rag_instances[storage_dir] = rag

    return rag


# =========================================================
# Subject alias map
# =========================================================
_SUBJECT_ALIASES: dict[str, str] = {
    "call": "lightrag_storage_call",
    "business-law": "lightrag_storage",

    # OB aliases
    "organizational-behavior": "lightrag_storage_organizational-behavior",
    "organization-behavior": "lightrag_storage_organizational-behavior",
    "adms-2400": "lightrag_storage_organizational-behavior",
    "mgmt-301": "lightrag_storage_organizational-behavior",
}


def get_graphml_path(subject: str = "all") -> str | None:
    """
    Return graphml path for subject.
    """

    backend_dir = os.path.dirname(os.path.abspath(__file__))

    base_data = os.path.normpath(
        os.path.join(
            backend_dir,
            "..",
            "..",
            "data",
        )
    )

    storage_dir = _SUBJECT_ALIASES.get(
        subject,
        f"lightrag_storage_{subject}",
    )

    return os.path.normpath(
        os.path.join(
            base_data,
            storage_dir,
            "graph_chunk_entity_relation.graphml",
        )
    )


def get_all_graphml_paths() -> list:
    """
    Return all known graphml paths.
    """

    backend_dir = os.path.dirname(os.path.abspath(__file__))

    data_dir = os.path.normpath(
        os.path.join(
            backend_dir,
            "..",
            "..",
            "data",
        )
    )

    return [
        os.path.join(
            data_dir,
            "lightrag_storage",
            "graph_chunk_entity_relation.graphml",
        ),
        os.path.join(
            data_dir,
            "lightrag_storage_call",
            "graph_chunk_entity_relation.graphml",
        ),
        os.path.join(
            data_dir,
            "lightrag_storage_organizational-behavior",
            "graph_chunk_entity_relation.graphml",
        ),
    ]


def slug(text: str) -> str:
    """
    Convert subject name to filesystem-safe slug.
    """

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        text.strip().lower(),
    ).strip("-")


def build_graph_response(graphs):
    """
    Merge networkx graphs into API-friendly structure.
    """

    PERSON_TYPES = {
        "person",
        "PERSON",
    }

    PERSON_DESC_PHRASES = (
        "a person",
        "a student",
        "a fictional",
    )

    merged_nodes = {}
    merged_edges = {}

    # ---------------------------------------------------
    # Merge nodes
    # ---------------------------------------------------
    for G in graphs:

        for node_id, attrs in G.nodes(data=True):

            nid = str(node_id)

            if (
                nid not in merged_nodes
                or len(attrs) > len(merged_nodes[nid])
            ):
                merged_nodes[nid] = dict(attrs)

        for source, target, attrs in G.edges(data=True):

            relation = attrs.get(
                "relation",
                attrs.get("label", ""),
            )

            key = (
                str(source),
                str(target),
                relation,
            )

            if key not in merged_edges:
                merged_edges[key] = dict(attrs)

    # ---------------------------------------------------
    # Regex patterns
    # ---------------------------------------------------
    _DATE_FULL_RE = re.compile(
        r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{4}$",
        re.IGNORECASE,
    )

    _DATE_YEAR_RE = re.compile(r"^\d{4}$")

    filtered_node_ids = set()
    nodes = []

    # ---------------------------------------------------
    # Process nodes
    # ---------------------------------------------------
    for node_id, attrs in merged_nodes.items():

        entity_type = attrs.get("entity_type", "")

        raw_desc = attrs.get("description", "")

        if raw_desc and "<SEP>" in raw_desc:
            raw_desc = raw_desc.split("<SEP>")[0].strip()

        # Remove person entities
        if entity_type in PERSON_TYPES:
            filtered_node_ids.add(node_id)
            continue

        if raw_desc and any(
            phrase in raw_desc.lower()
            for phrase in PERSON_DESC_PHRASES
        ):
            filtered_node_ids.add(node_id)
            continue

        node_label = attrs.get("label", node_id)

        # Remove date nodes
        if (
            _DATE_FULL_RE.match(str(node_label))
            or _DATE_YEAR_RE.match(str(node_label))
        ):
            filtered_node_ids.add(node_id)
            continue

        # Detect source layer
        source_layer = "hot"

        full_desc = attrs.get("description", "")

        if "[layer: warm]" in full_desc:
            source_layer = "warm"

        elif "[layer: cold]" in full_desc:
            source_layer = "cold"

        nodes.append({
            "id": node_id,
            "label": node_label,
            "entity_type": entity_type,
            "description": raw_desc,
            "source_layer": source_layer,
        })

    # ---------------------------------------------------
    # Process edges
    # ---------------------------------------------------
    edges = []

    for (source, target, relation), attrs in merged_edges.items():

        if (
            source in filtered_node_ids
            or target in filtered_node_ids
        ):
            continue

        edges.append({
            "source": source,
            "target": target,
            "label": attrs.get("label", relation),
        })

    return nodes, edges