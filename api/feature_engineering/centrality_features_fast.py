import random
import networkx as nx

def compute_centrality_fast(G, edges_gdf, k=500):
    """
    Sampled betweenness and closeness centrality:
    - G: NetworkX graph
    - edges_gdf: GeoDataFrame with an 'osmid' column
    - k: number of source nodes to sample
    Returns two dicts: {osmid: betweenness}, {osmid: closeness}
    """
    # 1) sample k nodes
    nodes = list(G.nodes())
    if k < len(nodes):
        sample = random.sample(nodes, k)
    else:
        sample = nodes

    # 2) compute betweenness on sample
    betweenness = nx.betweenness_centrality_subset(
        G, sources=sample, targets=nodes, normalized=True, weight="length"
    )

    # 3) compute closeness on sample and average
    closeness = {}
    for u in sample:
        c = nx.closeness_centrality(G, u, distance="length")
        for v in edges_gdf["osmid"]:
            # Ensure v is hashable (int or str), not a list
            if isinstance(v, list):
                if v:  # non-empty
                    v_key = v[0]
                else:
                    continue
            else:
                v_key = v
            closeness[v_key] = closeness.get(v_key, 0) + c
    # normalize closeness by number of samples
    for v in closeness:
        closeness[v] /= len(sample)

    # Normalize closeness to 0-1 range (betweenness is already normalized)
    # This ensures both metrics are on the same scale for frontend display
    if closeness:
        max_closeness = max(closeness.values()) if closeness.values() else 1.0
        min_closeness = min(closeness.values()) if closeness.values() else 0.0
        closeness_range = max_closeness - min_closeness

        if closeness_range > 0:
            # Normalize to 0-1
            closeness = {
                node: (value - min_closeness) / closeness_range
                for node, value in closeness.items()
            }
        else:
            # All values are the same, set to 0.5
            closeness = {node: 0.5 for node in closeness.keys()}

    return betweenness, closeness 