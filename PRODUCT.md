# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS (PWA on GitHub Pages, no build step). Prototype: one HTML file, `prototype/index.html`. Decided in docs/plan.md.

## Users

One private user in Berlin (postcode 14167), buying a premium TV for themself. Situation: evenings at home on the phone, browsing prices and offers, reacting to a push notification. Phone: Samsung Galaxy S25 (Android, Chrome, 360 px CSS width), not an iPhone (confirmed 2026-11-21). Job: find the moment and the place (online shop or a specific expert store, by postcode) where a watched TV is cheapest, including set deals and manufacturer cashback, and decide whether a TV + soundbar cashback path with soundbar resale beats buying the TV alone.

Current targets: Philips 65OLED951 and Sony BRAVIA 9 II (65"/75"). Secondary: LG OLED65C69LB, Samsung The Frame Pro.

## Product Purpose

A free, automatic price and promotion watcher for expert.de. It scans all 348 expert stores plus the online shop, keeps the best shipped and best pickup price per product, lists manufacturer cashback offers with amounts and qualifying devices, and pushes a notification on a price drop, a new set deal, or a new cashback. Success: the user buys at the lowest effective price without checking expert.de by hand.

## Positioning

Every expert store has its own price and its own promotions. Price comparison sites show one expert price. This tool shows all 349 and the exact set-deal and cashback arithmetic per store.

## Operating Context

- Data from the unofficial expert API (`production.brntgs.expert.de`), scanned by a scheduled job; the app reads static JSON.
- Store pickup requires a store choice on expert.de; the store picker on expert.de works by postcode, so every store in the app shows its postcode and city, and links to the product page with `?branch_id=<store id>`.
- "Online-Shop" = expert's central online shop (`e_2879130`), ships from the central warehouse; it has its own price, free or paid shipping, and online-only codes (for example WERO10).
- Restposten (clearance) and display items are real offers at a store, pickup only, usually one unit.
- Set deals: TV + accessory in one cart at one store, exact discount known. Cashback: manufacturer pays after registration; amounts come from the terms PDF; some offers need TV and soundbar on one invoice (Sony), others allow separate purchases (Samsung Mix & Match).
- Notifications via ntfy; default: every price drop against the previous scan, so a drop after a rise counts too; per product switchable to "nur bei neuem 30-Tage-Tief" or an optional target price (confirmed 2026-11-22). Rises are shown in the app, never pushed.

## Capabilities and Constraints

- Screens: watch list, product detail (price rows, promotions, history, stores), cashback list, cashback detail with resale calculator, settings. Open: the Cashback tab may be folded into the watch list (docs/requirements.md, open question 9).
- UI language: German (confirmed). Documentation: English.
- Product images come from `cdn.expert.de` (path from `/api/medium/<id>`).
- No product search in the API (search endpoint gone, verified 2026-11-21); input is a product URL. Open: a search by model name over a cached article list.
- Free hosting only, no server. Everything must work as static files.
- Prices and stock change hourly; the app always shows the scan age.

## Brand Commitments

- Visual direction (confirmed 2026-11-21): the category standard of price-tracker apps, played straight, at the craft level of the idealo and Geizhals apps with native polish on an Android phone. White cards on a cool grey ground, product image in every row, two prices side by side (Versand and Abholung) with the place named. The user rejected the dark "Heimkino" direction and the split-flap board.
- Revised 2026-11-22 (card B2): the two prices side by side are gone. The card head holds image, name and subtitle, no price. Receipt rows below: the cheapest path first with place, distance, stock and Aussteller badge; the cashback deduction; the total "Dein Preis inkl. Cashback"; the other path; set deals marked "nicht im Preis". Every price says whether cashback is included. Footer: 30-day sparkline, movement and verdict. Green only for the lowest price of the last 30 days after cashback. No fact appears twice. Prototype: prototype/b2.html, published at https://claude.ai/artifact/Y1dntJo3RAE6oRvnXTK2h2.
- No expert or manufacturer logos as the app's identity.

## Evidence on Hand

- Live prices and set deals of 2026-11-21 in docs/expert-api.md and the scratch analysis; cashback PDFs of Sony (TV Winter 2026) and Samsung (The Frame Pro Deals, Mix & Match).

## Product Principles

1. The cheapest effective total is the headline; everything else supports it.
2. Every price names its place: store, postcode, distance, pickup or shipping, and a link that opens that store's product page.
3. Show only what changes a decision; hide ids and internals.
4. Promotions are explained in one line in plain German, with the condition that matters (one invoice, registration deadline).
5. Never silent: the scan age and failures are visible.
