# Callsign Graph Explorer

This tool builds a force-directed graph from a MongoDB JSON export of the
`user` collection without talking to the production database. It is designed to
handle files that are at least 2 GB in size (≈200k accounts) by streaming the
export twice and only storing the pruned subset of users that share callsigns
with other accounts.

## Running the service

```bash
pip install -r requirements.txt
python -m src.tools.user_graph.app
```

The Flask server starts on port `8000`. Open `http://localhost:8000` to access
the UI.

## Upload workflow

1. Export your MongoDB `user` collection as a JSON array using `mongoexport`.
2. Open the Callsign Graph Explorer and upload the JSON file.
3. The backend writes the upload to disk and processes it in the background.
   * Pass 1 counts how many times each `pastCallsign` appears so we can prune
     accounts whose callsigns are unique.
   * Pass 2 emits one node per remaining account, builds a set of weighted edges
     (weight = number of shared callsigns), and detects connected components.
4. Once processing is complete, the UI lists every connected component along
   with its node/edge counts.

## Visualisation controls

* **Node size** – proportional to the number of past callsigns on the account.
* **Edge thickness** – logarithmic function of the number of overlapping
  callsigns between two accounts.
* **Colors** – each connected component gets a deterministic random color so
  isolated clusters are visually distinct.
* **Node limit** – the renderer only loads the requested number of nodes from
  the selected component. This prevents trying to draw all 200k nodes at once.
  Re-run the component fetch with a different limit at any time.
* **Focus** – search for an `accountID` to zoom to that node.
* **Export** – capture the current view as either a PNG (canvas snapshot) or an
  SVG (positions are converted into vector instructions after the simulation
  settles).

The simulation is powered by `force-graph`'s WebGL renderer, so even the large
components stay interactive while the layout cools to a low-tension state.
