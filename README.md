# Salad Tracker for Home Assistant

A [HACS](https://hacs.xyz) custom integration that surfaces your [Salad](https://salad.com) (SaladChef) earnings and GPU demand in Home Assistant, using the same undocumented `app-api.salad.com` API the Salad web app and Salad Tracker extension use.

## Features

| Entity | Meaning |
|---|---|
| `sensor.salad_balance` | Current Salad balance (USD) |
| `sensor.salad_lifetime_balance` | Lifetime balance (USD) |
| `sensor.salad_earnings_today` | Earnings since local midnight (USD, resets daily) |
| `sensor.salad_earnings_last_24_hours` | Rolling 24-hour earnings (USD) |
| `sensor.salad_earnings_last_7_days` | Last 7 calendar days (USD) |
| `sensor.salad_earning_rate` | Current rate, newest 15-min bucket scaled to $/h (unknown while Salad reporting lags) |
| `sensor.salad_last_earning` | Timestamp of the most recent non-zero 15-min earning bucket |
| `sensor.salad_gpu_demand` | Count of GPUs currently in High demand, with per-GPU detail in attributes |

The integration polls `app-api.salad.com` (balance + 30-day 15-minute earning history + demand monitor) with your auth cookie and re-authenticates through Home Assistant's standard reauth flow when the cookie expires.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/anoopr/ha-salad-tracker`, category **Integration**
3. Install **Salad Tracker**, then restart Home Assistant

### Getting the auth cookie

1. Log in at [salad.com](https://salad.com) (or app.salad.com) in your browser
2. DevTools → **Application** → **Cookies** → `app-api.salad.com` (may appear as `.salad.com`)
3. Copy the value of the **`auth`** cookie

### Configuration

1. Settings → Devices & Services → **Add Integration** → **Salad Tracker**
2. Paste the `auth` cookie, set the update interval (default 5 min), choose whether to include GPU demand data

When the cookie expires (Salad rotates sessions), the integration raises a reauth prompt — just paste a fresh `auth` cookie.

## Notes

- Unofficial, undocumented API — endpoint shapes can change without notice; the parsers tolerate the known variants.
- GPU demand data comes from `/api/v2/demand-monitor/gpu`, which is public (no auth) but polled alongside your account data.
- The 30-day earning history's values are dollars per 15-minute interval; the earning rate is the newest bucket × 4 ($/h), and it reads *unknown* once the newest bucket is more than 45 minutes old so reporting lag isn't mistaken for idle.
