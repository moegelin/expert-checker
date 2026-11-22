---
version: 1
slug: "prototype-index-html"
primary_target: "prototype/index.html"
related_targets: []
---

# Surface brief: prototype/index.html (expert-checker app)

Scope: the whole app prototype, four screens plus settings. Visitor mode: Operate.
Audience: one private buyer in Berlin, evenings on the phone. Task: see where a watched TV is cheapest today (shipped vs pickup), explore stores with postcode and links, understand cashback and set deals in plain German, decide.
Constraints: German UI; static HTML; real prices of 2026-11-21 for 14167 Berlin; images from cdn.expert.de embedded; no ids or internals shown.
Memorable moment: two prices side by side on every product, each naming its place; the resale calculator comparing three purchase paths.

## Direction contract

THESIS: A price tracker that always answers two questions at once, "Versand" and "Abholung", each with the place named. It refuses the single best-price headline that hides where the price is.
OWN-WORLD: White cards on a cool grey ground, system sans (SF on iPhone, Roboto fallback), tabular numerals. Green marks the best total, blue marks actions and selection, amber marks cashback, teal marks set deals, red marks Aussteller and Restposten. A product image sits at the left of every product row. Badges share one shape and one size across all screens.
STORY: The user opens the list, sees which path is cheaper today and by how much, taps into the stores with postcode, stock and a link to that store's product page, reads an offer's condition in one German sentence, and decides.
FIRST VIEWPORT: Top bar with location, radius and scan age. One card per product: image left; name and type; two price columns "Versand" and "Abholung", each with price, place and distance, the cheaper one highlighted green with a check; a badge row (Aussteller, Set-Deal, Cashback, price drop). Bottom tabs: Beobachten, Cashback, Einstellungen.
FORM: The category canon (standard price-tracker app), chosen by the user over the roll's assignment (Heimkino at night) and the Warentest table; the Warentest table donated the two-price column. Bar: idealo app, Geizhals app, native iOS polish. Seed key 7214f8f0.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
