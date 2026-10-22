/* ============================================================================
   GRAPH LAYOUT — readable link charts
   ----------------------------------------------------------------------------
   Established practice for node-link diagrams with labelled boxes:
   - force-directed placement with cooling (d3-force: Barnes-Hut many-body, links,
     collision), computed off-screen before drawing;
   - collision on the real size of each node (card or shape + its label);
   - a final rectangle overlap-removal pass, so no two nodes ever intersect;
   - layout in free space, then zoom/pan to fit the view (no clamping to the edges);
   - ring and row sizes derived from the number of nodes;
   - deterministic seeds: the same network always gets the same picture;
   - crowded hubs collapsed into an expandable "+N" group node.
   All coordinates are graph coordinates centred on (0, 0); the SVG viewport transform
   (graphZoomState) maps them to the screen.
   ============================================================================ */

const GraphLayout = (() => {
  const PAD = 18; // free space kept around every node
  const GROUP_THRESHOLD = 6; // more leaves than this on one hub -> "+N" group
  const CARD_TYPES = new Set(["Company", "LegalEntity", "OffshoreEntity", "Group"]);

  function labelWidth(text, px) {
    return (text || "").length * px * 0.6;
  }

  /** Bounding box (width, height) of a node as drawn by renderNodeShapeAndGlyph, badges and label included. */
  function nodeBox(n) {
    if (CARD_TYPES.has(n.node_type)) return { w: 140, h: 70 };
    const label = n.short_label || n.label || n.id;
    if (n.node_type === "Address") {
      return { w: Math.max(56, labelWidth(`${label} [${n.colocated_count || 1} cos]`, 10)), h: 86 };
    }
    return { w: Math.max(56, labelWidth(label, 10.5)), h: 86 };
  }

  /** Stable pseudo-random number in [0, 1) from a string (FNV-1a). */
  function seeded(str, salt = 0) {
    let h = 2166136261 ^ salt;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ((h >>> 0) % 100000) / 100000;
  }

  function isFixed(n, rootId) {
    return n.pinned || n.id === rootId;
  }

  /* ---------- hub grouping ---------- */

  /**
   * Replace the company leaves of crowded hubs with one group node.
   * Returns new arrays; `expanded` holds hub ids the analyst opened.
   */
  function collapseCrowdedHubs(nodes, edges, rootId, expanded) {
    const degree = new Map();
    edges.forEach((e) => {
      degree.set(e.source, (degree.get(e.source) || 0) + 1);
      degree.set(e.target, (degree.get(e.target) || 0) + 1);
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const leavesOf = new Map();
    edges.forEach((e) => {
      [
        [e.source, e.target],
        [e.target, e.source],
      ].forEach(([hub, leaf]) => {
        const leafNode = byId.get(leaf);
        if (!leafNode || leaf === rootId || degree.get(leaf) !== 1) return;
        if (leafNode.node_type !== "Company" || leafNode.is_flagged) return; // flagged companies stay visible
        if (!leavesOf.has(hub)) leavesOf.set(hub, []);
        leavesOf.get(hub).push(leafNode);
      });
    });

    const hidden = new Set();
    const groups = [];
    leavesOf.forEach((leaves, hub) => {
      if (leaves.length <= GROUP_THRESHOLD || expanded.has(hub)) return;
      leaves.forEach((l) => hidden.add(l.id));
      groups.push({
        id: `group:${hub}`,
        node_type: "Group",
        label: `+${leaves.length} companies`,
        short_label: `+${leaves.length} companies`,
        group_hub: hub,
        group_members: leaves.map((l) => l.company_number || l.id),
        hop_distance: (byId.get(hub)?.hop_distance || 0) + 1,
        x: 0,
        y: 0,
        pinned: false,
      });
    });
    if (!groups.length) return { nodes, edges, groups: 0 };
    return {
      nodes: nodes.filter((n) => !hidden.has(n.id)).concat(groups),
      edges: edges
        .filter((e) => !hidden.has(e.source) && !hidden.has(e.target))
        .concat(groups.map((g) => ({ id: `edge:${g.id}`, source: g.group_hub, target: g.id, label: "", is_group: true }))),
      groups: groups.length,
    };
  }

  /* ---------- layouts ---------- */

  function organic(nodes, edges, rootId, salt = 0) {
    nodes.forEach((n) => (n._box = nodeBox(n)));
    // seeded start: rings by hop distance, angle from the id
    nodes.forEach((n) => {
      if (n.pinned) return;
      if (n.id === rootId) {
        n.x = 0;
        n.y = 0;
        return;
      }
      const ring = 180 + 160 * Math.min(n.hop_distance || 1, 3);
      const angle = 2 * Math.PI * seeded(n.id, salt);
      n.x = ring * Math.cos(angle);
      n.y = ring * Math.sin(angle);
    });

    if (window.d3 && typeof d3.forceSimulation === "function") {
      const radius = (n) => Math.max(n._box.w, n._box.h) / 2 + PAD / 2;
      const links = edges.map((e) => ({ source: e.source, target: e.target }));
      nodes.forEach((n) => {
        if (isFixed(n, rootId)) {
          n.fx = n.x;
          n.fy = n.y;
        }
      });
      const sim = d3
        .forceSimulation(nodes)
        .randomSource(() => seeded(String(salt), 7)) // d3 jiggles coincident nodes: keep it reproducible
        .force(
          "link",
          d3
            .forceLink(links)
            .id((d) => d.id)
            .distance((l) => radius(l.source) + radius(l.target) + 40)
            .strength(0.5)
        )
        .force("charge", d3.forceManyBody().strength(-700).distanceMax(1400))
        .force("collide", d3.forceCollide(radius).strength(1).iterations(3))
        .force("x", d3.forceX(0).strength(0.04))
        .force("y", d3.forceY(0).strength(0.04))
        .stop();
      for (let i = 0; i < 320; i++) sim.tick();
      nodes.forEach((n) => {
        delete n.fx;
        delete n.fy;
        delete n.vx;
        delete n.vy;
      });
    } else {
      grid(nodes, rootId); // CDN unreachable: still readable
    }
    removeOverlaps(nodes, rootId);
    return null;
  }

  function grid(nodes, rootId) {
    const cols = Math.ceil(Math.sqrt(nodes.length));
    const cellW = Math.max(...nodes.map((n) => n._box.w)) + PAD * 2;
    const cellH = Math.max(...nodes.map((n) => n._box.h)) + PAD * 2;
    nodes
      .filter((n) => !n.pinned)
      .sort((a, b) => (a.id === rootId ? -1 : b.id === rootId ? 1 : (a.hop_distance || 0) - (b.hop_distance || 0)))
      .forEach((n, i) => {
        n.x = ((i % cols) - (cols - 1) / 2) * cellW;
        n.y = (Math.floor(i / cols) - (Math.ceil(nodes.length / cols) - 1) / 2) * cellH;
      });
  }

  /** Radius so that `items` boxes fit side by side on the circumference. */
  function ringRadius(items, minRadius) {
    const perimeter = items.reduce((sum, n) => sum + Math.max(n._box.w, n._box.h) + PAD, 0);
    return Math.max(minRadius, perimeter / (2 * Math.PI));
  }

  function placeOnRing(items, radius, offset) {
    items.forEach((n, i) => {
      if (n.pinned) return;
      const angle = (2 * Math.PI * i) / Math.max(items.length, 1) + offset;
      n.x = radius * Math.cos(angle);
      n.y = radius * Math.sin(angle);
    });
  }

  function concentric(nodes, edges, rootId) {
    nodes.forEach((n) => (n._box = nodeBox(n)));
    let center = nodes.find((n) => n.id === rootId || n.is_root);
    if (!center) center = [...nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0))[0];
    const direct = new Set();
    edges.forEach((e) => {
      if (e.source === center.id) direct.add(e.target);
      if (e.target === center.id) direct.add(e.source);
    });
    const ring1 = nodes.filter((n) => n !== center && direct.has(n.id));
    const ring2 = nodes.filter((n) => n !== center && !direct.has(n.id));
    ring1.sort((a, b) => seeded(a.id) - seeded(b.id));
    ring2.sort((a, b) => seeded(a.id) - seeded(b.id));
    if (!center.pinned) {
      center.x = 0;
      center.y = 0;
    }
    const r1 = ringRadius(ring1, 240);
    const r2 = Math.max(ringRadius(ring2, r1 + 200), r1 + 200);
    placeOnRing(ring1, r1, -Math.PI / 2);
    placeOnRing(ring2, r2, -Math.PI / 4);
    removeOverlaps(nodes, center.id);
    return { type: "rings", radii: [r1, ring2.length ? r2 : null] };
  }

  function circular(nodes, edges, rootId) {
    nodes.forEach((n) => (n._box = nodeBox(n)));
    const order = { Sanction: 1, Person: 2, SuperSecurePSC: 3, OffshoreEntity: 4, LegalEntity: 5, Company: 6, Group: 7, Address: 8 };
    const sorted = [...nodes].sort(
      (a, b) => (order[a.node_type] || 9) - (order[b.node_type] || 9) || (b.risk_score || 0) - (a.risk_score || 0)
    );
    placeOnRing(sorted, ringRadius(sorted, 260), -Math.PI / 2);
    removeOverlaps(nodes, null);
    return null;
  }

  function hierarchical(nodes, edges, rootId) {
    nodes.forEach((n) => (n._box = nodeBox(n)));
    const tiers = new Map();
    nodes.forEach((n) => {
      let lvl = n.hierarchy_level;
      if (lvl === undefined || lvl === null) {
        if (["Sanction", "Person", "SuperSecurePSC"].includes(n.node_type)) lvl = 0;
        else if (["OffshoreEntity", "LegalEntity"].includes(n.node_type)) lvl = 1;
        else if (n.is_root || n.id === rootId) lvl = 2;
        else if (n.node_type === "Company" || n.node_type === "Group") lvl = 3;
        else lvl = 4;
      }
      if (!tiers.has(lvl)) tiers.set(lvl, []);
      tiers.get(lvl).push(n);
    });
    const levels = [...tiers.keys()].sort((a, b) => a - b);
    const maxRowWidth = 1600; // wider rows wrap onto a second line within the tier
    const rows = [];
    let y = 0;
    levels.forEach((lvl) => {
      const tierNodes = tiers.get(lvl).sort((a, b) => (b.degree || 0) - (a.degree || 0));
      const lines = [[]];
      let lineWidth = 0;
      tierNodes.forEach((n) => {
        const w = n._box.w + PAD * 2;
        if (lineWidth + w > maxRowWidth && lines[lines.length - 1].length) {
          lines.push([]);
          lineWidth = 0;
        }
        lines[lines.length - 1].push(n);
        lineWidth += w;
      });
      rows.push({ level: lvl, y });
      lines.forEach((line) => {
        const total = line.reduce((s, n) => s + n._box.w + PAD * 2, 0);
        let x = -total / 2;
        const lineH = Math.max(...line.map((n) => n._box.h));
        line.forEach((n) => {
          const w = n._box.w + PAD * 2;
          if (!n.pinned) {
            n.x = x + w / 2;
            n.y = y;
          }
          x += w;
        });
        y += lineH + PAD * 2;
      });
      y += 70; // gap between tiers for the tier caption
    });
    removeOverlaps(nodes, null);
    return { type: "tiers", rows };
  }

  /* ---------- guarantees ---------- */

  /** Push intersecting boxes apart along the axis of least overlap until none intersect. */
  function removeOverlaps(nodes, rootId, maxPasses = 400) {
    nodes.forEach((n) => (n._box = n._box || nodeBox(n)));
    for (let pass = 0; pass < maxPasses; pass++) {
      let moved = false;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const ox = (a._box.w + b._box.w) / 2 + PAD - Math.abs(dx);
          const oy = (a._box.h + b._box.h) / 2 + PAD - Math.abs(dy);
          if (ox <= 0 || oy <= 0) continue;
          moved = true;
          const aFixed = isFixed(a, rootId);
          const bFixed = isFixed(b, rootId);
          if (aFixed && bFixed) continue;
          const shareA = aFixed ? 0 : bFixed ? 1 : 0.5;
          const shareB = 1 - shareA;
          if (ox < oy) {
            const dir = dx !== 0 ? Math.sign(dx) : seeded(a.id + b.id) < 0.5 ? -1 : 1;
            a.x -= dir * ox * shareA;
            b.x += dir * ox * shareB;
          } else {
            const dir = dy !== 0 ? Math.sign(dy) : seeded(b.id + a.id) < 0.5 ? -1 : 1;
            a.y -= dir * oy * shareA;
            b.y += dir * oy * shareB;
          }
        }
      }
      if (!moved) return 0;
    }
    return countOverlaps(nodes);
  }

  function countOverlaps(nodes) {
    let count = 0;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const ab = a._box || nodeBox(a);
        const bb = b._box || nodeBox(b);
        if (Math.abs(b.x - a.x) < (ab.w + bb.w) / 2 && Math.abs(b.y - a.y) < (ab.h + bb.h) / 2) count++;
      }
    }
    return count;
  }

  /** Zoom/pan so the whole chart fits the SVG (never above 110 %, never below 30 %). */
  function fitTransform(nodes, viewW, viewH, margin = 30) {
    if (!nodes.length) return { scale: 1, tx: viewW / 2, ty: viewH / 2 };
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    nodes.forEach((n) => {
      const b = n._box || nodeBox(n);
      minX = Math.min(minX, n.x - b.w / 2);
      maxX = Math.max(maxX, n.x + b.w / 2);
      minY = Math.min(minY, n.y - b.h / 2);
      maxY = Math.max(maxY, n.y + b.h / 2);
    });
    const scale = Math.max(0.3, Math.min(1.1, (viewW - 2 * margin) / (maxX - minX), (viewH - 2 * margin) / (maxY - minY)));
    return {
      scale,
      tx: viewW / 2 - scale * ((minX + maxX) / 2),
      ty: viewH / 2 - scale * ((minY + maxY) / 2),
    };
  }

  function apply(name, nodes, edges, rootId, salt = 0) {
    if (name === "concentric") return concentric(nodes, edges, rootId);
    if (name === "circular") return circular(nodes, edges, rootId);
    if (name === "hierarchical") return hierarchical(nodes, edges, rootId);
    return organic(nodes, edges, rootId, salt);
  }

  return { apply, organic, removeOverlaps, countOverlaps, fitTransform, collapseCrowdedHubs, nodeBox };
})();
