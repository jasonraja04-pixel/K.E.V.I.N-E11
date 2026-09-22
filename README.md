# SMC Engine V6 — Top-Down SMC/ICT Analysis

This version keeps the same frontend API contract as the original project:
- GET /api/signal/{symbol}
- GET /api/timeframe/{symbol}/{tf}
- GET /api/symbols

Data:
- OANDA: major FX pairs + XAU/USD + XAG/USD
- Capital.com: NAS100 (US Tech 100) + SPX500 (US 500)

Top-down logic:
4H -> directional market structure
1H -> POI/context (order block, FVG, OTE, structure alignment)
15M -> trigger context (liquidity raid, displacement, structure event)

The engine is analysis-only: it does not place orders and does not generate executable entry/SL/TP instructions.

Important:
- OANDA instruments available depend on the account/division.
- Capital.com regional instrument epics are resolved through /markets rather than hard-coded.
- All candles used for analysis are completed candles where the provider exposes completion state.
- Fractal swing confirmation inherently requires candles to the right of the swing; this is safe for live analysis but historical backtests must timestamp swing confirmation correctly.
