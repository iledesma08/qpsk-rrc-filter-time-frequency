#!/usr/bin/env bash
# Create the canonical triage labels + project domain labels.
# Usage: bash scripts/setup-labels.sh
set -euo pipefail

mk() { # name color description
  gh label create "$1" --color "$2" --description "$3" 2>/dev/null \
    || gh label edit "$1" --color "$2" --description "$3";
}

echo "== triage =="
mk "needs-triage"    "FBCA04" "This issue still needs evaluation"
mk "needs-info"      "D4C5F9" "Waiting on the reporter for more info"
mk "ready-for-agent" "0E8A16" "Ready and specified, an agent can take it"
mk "ready-for-human" "1D76DB" "Requires human implementation (RTL/HW)"
mk "wontfix"         "BEC2C9" "Will not be done"

echo "== area =="
mk "sim"     "5319E7" "Python float/fxp simulator"
mk "rtl"     "0052CC" "RTL / testbenches"
mk "time"    "FEF2C0" "Time-domain filter"
mk "freq"    "C5DEF5" "Frequency-domain filter"
mk "ppa"     "E99695" "Performance / Power / Area"
mk "docs"    "006B75" "Docs, slides, Gantt"
mk "repo"    "BFDADC" "Repo infra (templates, CI, scripts)"
mk "verif"   "3E4B9E" "Vector matching / SQNR / tests"

echo "== type =="
mk "bug"     "D93F0B" "Something broken"
mk "feature" "A2EEEF" "New functionality"

echo "OK. See: gh label list"
