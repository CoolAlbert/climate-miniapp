# Yandex Climate Mini App

Telegram Mini App for viewing Yandex Smart Home climate sensor readings.

The backend is a small Python stdlib HTTP server. It fetches Yandex IoT data, serves the static Mini App, and protects `/api/climate` with Telegram WebApp `initData` verification plus an allowlist of Telegram user IDs.

## Features

- Room-grouped climate readings from Yandex Smart Home.
- Temperature, humidity, pressure, and battery status.
- Telegram Mini App authentication via signed `initData`.
- Light and dark themes based on Telegram theme variables.
- No runtime Python dependencies beyond the standard library.

## Configuration

Create an env file or export variables:

```sh
cp .env.example .env
```

Required values:

- `YANDEX_IOT_ACCESS_TOKEN`: OAuth token for Yandex Smart Home API.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token used to verify Mini App `initData`.
- `TELEGRAM_ALLOWED_USER_IDS`: comma-separated Telegram user IDs allowed to read climate data.

Optional values:

- `HOST`: bind address, defaults to `127.0.0.1`.
- `PORT`: bind port, defaults to `8095`.
- `YANDEX_IOT_ENV`: path to an env file with the values above.
- `OPENCLAW_CONFIG`: optional OpenClaw config path used as a fallback for Telegram bot token and allowlist.

## Run

```sh
YANDEX_IOT_ENV=.env python3 server.py
```

Open the app through Telegram Mini App. Direct browser requests to `/api/climate` return `403` because they do not include signed Telegram WebApp data.

## Caddy

Example reverse proxy:

```caddyfile
climate.example.com {
	reverse_proxy 127.0.0.1:8095
}
```
