# Linger

*Stay a little longer.* A marketplace for homes and hideaways from independent hosts, with flights to get you there, booked in one place.

This repository currently holds the **design prototype** and a small local server that connects it to live flight data from [Duffel](https://duffel.com).

## What's here

| Path | What it is |
|---|---|
| `prototype/linger.html` | The clickable, animated prototype (home, map search, property page with booking flow, flight results). Photos are embedded, so it opens on its own. |
| `prototype/linger.template.html` | Editable source of the prototype, without the embedded photos. |
| `server.py` | Local dev server: serves the prototype and proxies flight and airport searches to Duffel so the API token never reaches the browser. |
| `.env.example` | Template for your local `.env`. |

## Run it locally

1. Copy `.env.example` to `.env` and add a Duffel **test** token (Duffel dashboard → Developers → Access tokens). Never commit `.env`.
2. Start the server (Python 3, no packages needed):

   ```bash
   python3 server.py
   ```

3. Open <http://localhost:8765/linger.html#flights>

Without the server (for example, opening the HTML file directly), the prototype falls back to sample fares and a built-in list of about 40 airports.

### Local API

- `GET /api/flights?from=BKK&to=KBV&date=2026-12-12&adults=2` returns Duffel offers, trimmed to what the UI needs.
- `GET /api/places?q=krabi` returns airport and city suggestions.

## Prototype notes

- Listings, hosts, reviews and stay prices are sample data. Photos are from Unsplash (free licence).
- Currencies use fixed indicative exchange rates; the real build will use a daily rate feed.
- Duffel test mode returns simulated schedules. Real fares need a live token after Duffel verifies the business.

## Planned stack

Next.js, Supabase (database, auth, storage), Stripe Connect (guest payments and host payouts), Duffel (flights).
