name: praamid-monitor

on:
  schedule:
    - cron: "*/5 * * * *"   # every 5 min (GitHub may delay; see README)
  workflow_dispatch:
    inputs:
      mode:
        description: "Run mode"
        type: choice
        options: [check, test-email, probe]
        default: check

permissions:
  contents: write   # needed to commit the alert-state file back

concurrency:
  group: praamid-monitor
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - name: Run monitor
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: |
          MODE="${{ github.event.inputs.mode || 'check' }}"
          case "$MODE" in
            test-email) python3 praamid_monitor.py --test ;;
            probe)      python3 praamid_monitor.py --probe ;;
            *)          python3 praamid_monitor.py --once ;;
          esac

      - name: Persist alert state
        run: |
          if [ -f alerted_departures.json ] && ! git diff --quiet -- alerted_departures.json 2>/dev/null || [ -n "$(git status --porcelain alerted_departures.json)" ]; then
            git config user.name "praamid-monitor"
            git config user.email "actions@github.com"
            git add alerted_departures.json
            git commit -m "Update alert state" || true
            git pull --rebase || true
            git push || true
          fi
