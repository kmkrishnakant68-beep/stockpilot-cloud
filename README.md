# StockPilot Cloud — ready-to-deploy GitHub edition

Tracks the supplied watchlist without needing your phone or PC to stay on. Uses `yfinance` and `pandas` for latest available quotes, 50-day / 200-day simple moving averages, downward-cross alerts, and a mobile-friendly static dashboard.

**Deployment status:** These files are a deployment kit. They are not installed on GitHub, are not running, and are not integrated into the existing private StockPilot website until you deploy them.

## One-time setup (phone browser or desktop)

1. Make a GitHub account at https://github.com/signup if you don't have one.
2. Create **a new public repository** named `stockpilot-cloud`. A public repo allows GitHub Pages on GitHub Free. **Your ticker list, site data and dashboard are public; do not upload balances, credentials, or private brokerage statements.** If you want a private dashboard, use a private authenticated hosting provider instead of public GitHub Pages.
3. Unzip this folder, then upload *the contents of the folder*, including the hidden `.github/workflows/market-scan.yml`, into the **root** of the new repository. Easiest: use a computer with Git (`git add .`, `git commit`, `git push`), or GitHub's browser upload and verify the hidden `.github` file appears. You can also upload files individually in GitHub's interface. A GitHub repository is not created by uploading the ZIP unchanged.
4. Open the repository's **Settings → Pages → Build and deployment → Source: GitHub Actions**. Save.
5. Open **Actions → StockPilot cloud scan → Run workflow**. It will install Python packages, check stocks, publish the dashboard and save state. Enable workflows if GitHub prompts you.
6. After the action succeeds, visit `https://YOUR_GITHUB_USERNAME.github.io/stockpilot-cloud/` (replace the username). Bookmark on Android or **Add to Home Screen** in Chrome.
7. **To edit stocks**: edit `watchlist.txt` (one ticker per line), commit changes, then manually run the workflow once. This sample watchlist is not connected to your original StockPilot's actual watchlist.

### Automatic schedule

GitHub checks at approximately 9:47 AM, then 10:17/10:47 through 3:47 PM, and at 4:47 PM **New York time** on weekdays. This works across daylight-saving changes. Scheduled jobs can be delayed or occasionally missed and will run even on exchange holidays unless Yahoo returns the last close. The site shows the most recent available scan; hitting Refresh on the page does **not** force a new Yahoo market-data scan. For an immediate scan, use **Actions → Run workflow**.

The scan commits only technical data/state, not credentials. New downward crosses are logged, and repeated scans do not notify again while prices remain below the average.

## Optional Android Telegram notifications

1. Install Telegram and create a new bot using the official **@BotFather** account (`/newbot`); copy the bot token. Never place this token in code or a public file.
2. Message your new bot with `/start`. Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` privately to find `message.chat.id` (do not share a token-bearing URL). If this does not show your message, send another message to the bot and retry.
3. In GitHub repo **Settings → Secrets and variables → Actions → New repository secret**, add:
    - `TELEGRAM_BOT_TOKEN`: your bot token
    - `TELEGRAM_CHAT_ID`: your personal chat ID
4. Run the workflow once. The bot messages **only for fresh downward 50/200 SMA crosses**; no Telegram message appears if none occurs. To verify notifications, test `telegram_alerts.py` locally with an appropriate `stockpilot_data/new_alerts.json`.

GitHub stores these as masked encrypted secrets in Actions, not as files in the repository. Do not upload your bot token in JSON, README, or HTML.

## Outputs / files

- `stockpilot_ma_tracker.py`: original tracker adapted with trend lines and new-alert JSON
- `.github/workflows/market-scan.yml`: cloud schedule, code execution, state persistence and GitHub Pages deployment
- `watchlist.txt`: edit tracked tickers
- `stockpilot_data/latest_signals.json`: machine-readable results persisted after first run
- `stockpilot_data/alert_history.json`: recent downward crossing events
- `public/index.html`: dashboard (fetches `public/data/latest_signals.json`)
- `telegram_alerts.py`: optional mobile alerts

## Things to know

- The regular-market quote can be delayed or provisional; a crossover can reverse before the final closing price. Data is provided by Yahoo through unofficial `yfinance`, which is intended for personal/research use; access and rate limits can change.
- The average is computed over 50/200 most recent daily close observations (including a provisional current-session observation when available). It is a **simple** moving average.
- GitHub Pages is **public**, even if a paid GitHub plan allows building from a private repository. This deployment has **no account or password login**.
- GitHub Free includes a monthly Actions minutes quota for *private* repositories, while standard GitHub-hosted Actions minutes are free for public repositories. Check current GitHub docs for details. Public repo schedules can be auto-disabled after 60 days of inactivity, although bot commits usually update the repository; check workflow settings if scans stop.
- This cloud kit runs separately from the original private StockPilot site. To integrate results into that site, its backend would need to fetch and authorize the generated data, or the original app would need a deployment update; this package does not directly change that app.
- If requests are rate-limited or scans are slow, reduce the watchlist or run the workflow less often. Never depend on this tool for time-critical order execution.
