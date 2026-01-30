/**
 * Minimal React example showing how to integrate OPEN_CARD TurnState events
 * and load cards.json/cards_index.json locally (for dev).
 *
 * This is an integration snippet for app teams adapting TurnState trace capture.
 */
import React, { useEffect, useRef, useState } from "react";
import { TraceBuilder, TraceEvent } from "../ts_exporter_snippets/trace_exporter";
import { buildTurnState, buildStepEvent } from "../ts_exporter_snippets/capture_helpers";

type Card = {
  card_id: string;
  content?: any;
  actions?: Array<{ action_id: string }>;
};

export function OpenCardDemo() {
  const [cards, setCards] = useState<Record<string, Card>>({});
  const traceRef = useRef<TraceBuilder | null>(null);
  const [turnState, setTurnState] = useState<any>(() =>
    buildTurnState({
      turn_id: "t0",
      scaffolding_level: "HIGH",
      input_mode: "TAP",
      affordances: ["what_can_i_say", "open_card"],
      options: [],
      hints: null,
      slots: { required: [], filled: {}, selectors_present: [] },
      cardPanel: { open: false, card_id: null, reveal_level: null },
    })
  );

  useEffect(() => {
    // Initialize trace builder
    traceRef.current = new TraceBuilder({
      trace_id: `trace_${Date.now()}`,
      app_build: { repo: "mandarinos-example", commit: "dev", env: "dev" },
      locale: "zh-CN",
      user_profile: { user_id: "dev_user", level: "BEGINNER" },
      scenario: { scenario_id: "open_card_demo", description: "Open card demo" },
    });

    // Load cards.json (local file for now)
    (async () => {
      try {
        // Try to fetch relative path (works in dev server that serves repo)
        const resp = await fetch("/tools/cards/out/cards.json");
        if (!resp.ok) throw new Error("Fetch failed");
        const j = await resp.json();
        const map: Record<string, Card> = {};
        for (const c of j.cards || []) {
          map[c.card_id] = c;
        }
        setCards(map);
      } catch (e) {
        // Fallback: try to import via dynamic require (Node/Electron dev)
        try {
          // @ts-ignore
          const fs = require("fs");
          const path = require("path");
          const p = path.resolve(__dirname, "../../tools/cards/out/cards.json");
          const txt = fs.readFileSync(p, { encoding: "utf-8" });
          const j = JSON.parse(txt);
          const map: Record<string, Card> = {};
          for (const c of j.cards || []) {
            map[c.card_id] = c;
          }
          setCards(map);
        } catch (e2) {
          console.warn("Failed to load cards.json locally", e2);
        }
      }
    })();
  }, []);

  const openCard = async (cardId: string) => {
    const beforeState = turnState;
    const afterState = { ...turnState, cardPanel: { open: true, card_id: cardId, reveal_level: 0 } };

    const event: TraceEvent = buildStepEvent("OPEN_CARD", { card_id: cardId });

    traceRef.current?.step(event, beforeState, afterState, "User opened card panel");
    setTurnState(afterState);
  };

  const closeCard = (note?: string) => {
    const beforeState = turnState;
    const afterState = { ...turnState, cardPanel: { open: false, card_id: null, reveal_level: null } };
    const event: TraceEvent = buildStepEvent("OPEN_CARD", { card_id: beforeState.cardPanel?.card_id, action: "close" });
    traceRef.current?.step(event, beforeState, afterState, note || "User closed card panel");
    setTurnState(afterState);
  };

  return (
    <div>
      <h3>Open Card Demo</h3>
      <div>
        <strong>Loaded cards:</strong> {Object.keys(cards).length}
      </div>
      <div style={{ marginTop: 8 }}>
        {Object.keys(cards).slice(0, 10).map((cid) => (
          <button key={cid} onClick={() => openCard(cid)} style={{ marginRight: 6 }}>
            Open {cid}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 12 }}>
        <button onClick={() => closeCard()}>Close Card</button>
      </div>
      <div style={{ marginTop: 12 }}>
        <pre>{JSON.stringify(turnState.cardPanel, null, 2)}</pre>
      </div>
      <div style={{ marginTop: 12 }}>
        <pre>{traceRef.current?.exportAsJson?.() || ""}</pre>
      </div>
    </div>
  );
}
