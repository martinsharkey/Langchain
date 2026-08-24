# Trading Dashboard v2

Modern analytics-focused trading dashboard for strategy performance analysis and optimization tracking.

## Features

- **Strategy Performance Dashboard**: Compare all strategies side-by-side with backtest metrics
- **Backtest Results**: Walk-forward validation visualization
- **Optuna Optimization**: Track parameter tuning progress and trials
- **Vectorbt Discovery**: View edge discovery status and regime analysis
- **Live Trading**: Real-time account state and position tracking

## Tech Stack

- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- Chart.js + Recharts (charts)
- Axios (API client)

## Setup

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm run dev

# Build for production
pnpm run build

# Type checking
pnpm run type-check
```

## Development

Server runs on `http://localhost:3000` by default. API requests proxy to `http://localhost:5000/api/v2`.

## Building

```bash
pnpm run build
```

Output goes to `../dashboard/public/` for deployment.

## API Integration

The dashboard consumes the backend API at `/api/v2`:

- `GET /api/v2/strategies` - List all strategies
- `GET /api/v2/backtest/results` - Backtest data
- `GET /api/v2/vectorbt/discovery` - Edge discovery
- `GET /api/v2/optuna/studies` - Optuna studies
- `GET /api/v2/summary` - Dashboard summary

See `src/api.ts` for API client implementation.
