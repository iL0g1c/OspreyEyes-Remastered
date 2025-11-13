# Callsign Lineage Explorer

This lightweight, browser-based tool renders a force-directed "web of accounts" from a MongoDB export of the `users` collection. No database credentials are required; everything runs entirely inside your browser.

## Running the tool
1. Serve the directory (or open `index.html` directly) from `src/tools/callsign-network-visualizer/`.
2. Upload a JSON file that contains an array (or newline-delimited list) of user documents as exported from MongoDB.
3. Wait for the nodes to settle into their minimum-tension state. Adjust the controls at the top to tune repulsion, link distance, minimum callsigns per node, or the maximum number of accounts linked through a single callsign.
4. Search for a specific account ID or callsign with the finder box.
5. Export the current view to **SVG** (vector) or **PNG** (raster) using the buttons in the header.

Large MongoDB exports (100 MB+) are streamed and parsed incrementally so you can upload multi-gigabyte datasets without exhausting browser memory. The status banner and inline progress bar show live byte/percentage progress plus how many accounts have been parsed so far.

> Want to make sure everything is wired up before loading a large dump? Upload
> `sample-data/multi-account-example.json`, which contains three synthetic accounts that intentionally share
> callsigns so the graph immediately renders two links.

## Data processing rules
- Each account becomes a node whose size is proportional to its unique `pastCallsigns` entries.
- Two nodes are connected if they share a callsign. The strength of the edge is the sum of their recency scores for that callsign (more recent changes create stronger links).
- An account's current callsign is folded into its history (using the `lastOnline` timestamp) so the freshest identity is always represented, even if it never appeared in `pastCallsigns`.
- Callsign comparisons are case-insensitive, so `Noah47`, `NOAH47`, and `noah47` all produce links.
- To keep the visualization performant for very large collections (200k+ accounts), the UI caps the number of accounts connected through any single callsign. This safeguard can be adjusted or removed from the control panel.
- Connected components are assigned a shared color palette and rendered with a gradient so that neighboring accounts remain visually related.

Because everything is handled client-side, no user information leaves the machine where the file is loaded.

If a dataset contains zero overlapping callsigns (or the filters hide every overlap), the status bar now makes that explicit so you know the missing links are a data issue rather than a rendering problem. Try lowering the "Minimum callsigns per node" or raising the "Maximum accounts per callsign" threshold before assuming something is broken.

### Offline dependency

The ForceGraph runtime is vendored locally as `force-graph.min.js`, so the visualization works even on machines without internet access or in hardened environments where CDNs such as unpkg/jsDelivr are blocked.
